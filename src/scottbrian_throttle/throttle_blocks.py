"""Module throttle_blocks.

===============
throttle_blocks
===============

The throttle_blocks module contains the parts needed by the throttle
decorator.

========
Throttle
========

The Throttle class provides routines to delay as needed the function
wrapped the throttle decorator. After any delay, the decorated function
is called, and any error are captured and reported. The Throttle used a
leaky bucket algorithm to rate limit the execution of the decorated
function.

The leaky bucket algorith uses a virtual bucket into which arriving
requests are placed. As time progresses, the bucket leaks the requests
out at the rate of the target interval. If the bucket has room for an
arriving request, the request is placed into the bucket and is sent
immediately. If, instead, the bucket does not have room for the request,
the request is delayed until the bucket has leaked enough of the
preceding requests such that the new request can fit and be sent. The
effect of the bucket is to allow a burst of requests to be sent
immediately at a faster rate than the target interval, acting as a shock
absorber to the flow of traffic. The number of requests allowed to go
immediately is controlled by the size of the bucket which in turn is
specified by the bucket_size argument when the throttle is instantiated.
Note that a bucket_size of 1 means there will never be enough room in
the bucket for more than one request at a time.

Note that by allowing short bursts to go immediately, the overall effect
is that the average interval will be less than the target interval.

The actual implementation does not employ a bucket, but instead sets a
target time for the next request by adding the target interval and
subtracting the size of the bucket. This has the effect of making it
appear as if requests are arriving after the target time and are thus
in compliance with the target interval. The next target time will
eventually exceed the size of the bucket, and requests will get delayed
to allow the target time to catch up.

The Throttle provides both sync and async versions of the throttle
function: sync_throttle and async_throttle. Both routines are similar:
sync_throttle uses a threading lock, time.sleep, and calls the decorated
function synchronously, while async_throttle uses an asyncio lock,
asyncio.sleep, and call the decorated function with an await. The
following explains the detail of the leaky bucket adjustment which is
the same for both routines:

There are three cases to consider:

1) The current request arrives well beyond the last request
   such that the bucket is completely empty. We need to start
   a new bucket relative to the current arrival time.
2) The current request arrives rapidly on the heels of the
   previous request such that the bucket is full enough that
   it does not contain enough room to add a new entry. We need
   to delay this current request until there is room enough in
   the bucket to add this one entry.
3) The current request arrives when the bucket has one or more
   previous requests still leaking out, but there is still
   enough room in the bucket to add another request without
   delay.

Note that we update the bucket (i.e., target time) before we
call the requested function instead of updating the target
time after control returns from the requested function. This
means we face a possible scenario where we encounter a delay
during the call to the requested function, and upon return we
receive the next request which, because of the prior delay,
appears ok to send immediately. But this new request might
appear early as observed by the called service (i.e.,
requested function). If instead we were to update the target
time after getting back control from the requested function,
we avoid the "too early" scenario. But we would then be adding
in the request processing time to the throttle delay with the
undesirable effect that all requests will now be throttled
more than they need to be. The "too early" scenario seemed
less problematic compared to the "extra throttling" effect,
so the design choice was made to update the target time before
calling the requested function.


"""

########################################################################
# Standard Library
########################################################################
import asyncio
import contextvars  # Native context tracking
########################################################################
# Third Party
########################################################################
import logging
import threading
import time
from enum import Enum, auto
from typing import (
    Any,
    Callable,
    Final,
    TYPE_CHECKING,
    Type,
)

import scottbrian_locking.se_lock as selk  # noqa F401
from pydantic import BaseModel, Field, ConfigDict
from scottbrian_utils.pauser import Pauser
from wrapt.decorators import decorator  # type: ignore


########################################################################
# Local
########################################################################


class Throttle(BaseModel):
    """Throttle class.


    Args:
        reqs_per_sec: The number of requests that can be made in
                      one second.
        bucket_size: Specifies the number of requests that can be
                     conceptually placed into the bucket for the
                     leaky bucket algorithm. As requests arrive,
                     the bucket is checked to determine if it has
                     room for the request. If so, it is placed into
                     the bucket and sent without delay. If not, the
                     request is delayed until enough time has
                     elapsed for the bucket to leak out enough to
                     allow the request to fit. A specification of
                     one for the bucket_size will effectively
                     cause non-leaky bucket behavior, meaning that
                     each request that arrives before the previous
                     request interval has elapsed will be delayed.
                     The bucket_size must be greater than or equal
                     to 1.
        convert_to_async: If the function being throttled is
                          synchronous and the user is in an asyncio
                          environment, the user can specify
                          *convert_to_async=True* to request that
                          asyncio.sleep be used for delay if needed
                          and the function is to be run in a
                          separate thread using asyncio.to_thread.
                          Otherwise, if *convert_to_async=False*,
                          the use can use asyncio.to_thread to
                          run the synchronous function is a separate
                          thread and time.sleep will be used for
                          any delay as needed. Note that
                          *convert_to_async* has no meaning is a
                          non-asyncio environment.
        name: The name of the function that was wrapped by the
              throttle decorator, meaning the function that is being
              throttled.


    """

    model_config = ConfigDict(extra="allow")

    reqs_per_sec: float = Field(
        gt=0, default=1, description="Number of requests allowed per second"
    )
    bucket_size: float = Field(ge=1, default=1, description="Size of leaky bucket")
    convert_to_async: bool = False
    name: str | None = None

    class Mode(Enum):
        SYNC = auto()
        ASYNC = auto()

    SECS_2_NS: Final[int] = 1000000000
    NS_2_SECS: Final[float] = 0.000000001

    def model_post_init(self, context: Any) -> None:

        ################################################################
        # set up logging
        ################################################################
        # self.logger = logging.getLogger(__name__)

        ################################################################
        # Set remainder of vars
        ################################################################
        self._target_interval = 1 / self.reqs_per_sec
        self._target_interval_ns: float = self._target_interval * Throttle.SECS_2_NS
        self.sync_lock = threading.Lock()
        self.async_lock = asyncio.Lock()
        self._arrival_time_ns = 0.0
        self.sent_time_ns = time.perf_counter_ns()
        self._wait_time_ns: float = 0.0
        self.logger = logging.getLogger(__name__)
        self.pauser = Pauser()

        ################################################################
        # Set leaky bucket vars
        ################################################################
        self.lb_adjustment: float = max(
            0.0, (self._target_interval * self.bucket_size) - self._target_interval
        )
        self.lb_adjustment_ns: float = self.lb_adjustment * Throttle.SECS_2_NS

        self.lb_with_one_request = -self.lb_adjustment_ns + self._target_interval_ns

        # adjust _next_target_time_ns for normal or lb algo
        self._next_target_time_ns = time.perf_counter_ns() - self.lb_adjustment_ns

        self.call_count = 0

    ####################################################################
    # repr
    ####################################################################
    def __repr__(self) -> str:
        """Return a representation of the class.

        Returns:
            The representation as how the class is instantiated

        :Example 1: call __repr__ for Throttle

        .. code-block:: python

            from scottbrian_throttle.throttle import throttle

            @throttle(reqs_per_sec=0.5)
            def func1(request_number, time_of_start):
                pass

            print(repr(func1.throttle))

            Expected output for Example 1::

            'Throttle(reqs_per_sec=0.5, bucket_size=1, convert_to_async=False, name=func1)'



        """
        if TYPE_CHECKING:
            __class__: Type[Throttle]  # noqa: F842
        classname = self.__class__.__name__
        parms = (
            f"reqs_per_sec={self.reqs_per_sec}, "
            f"bucket_size={self.bucket_size}, "
            f"convert_to_async={str(self.convert_to_async)}, "
            # f"name={self.t_name}"
            f"name={self.name}"
        )

        return f"{classname}({parms})"

    ####################################################################
    # get_interval
    ####################################################################
    def get_interval_secs(self) -> float:
        """Calculate the interval between requests in seconds.

        Returns:
            The target interval in seconds.
        """
        return self._target_interval

    ####################################################################
    # get_interval
    ####################################################################
    def get_interval_ns(self) -> float:
        """Calculate the interval between requests in nanoseconds.

        Returns:
            The target interval in nanoseconds.

        """
        return self._target_interval_ns

    ####################################################################
    # get_completion_time_secs
    ####################################################################
    def get_completion_time_secs(self, num_requests: int, from_start: bool) -> float:
        """Calculate completion time secs for given number requests.

        Args:
            num_requests: number of requests to do
            from_start: specifies whether the calculation should be done
                          for a series that is starting fresh where the
                          first request has no delay

        Returns:
            The estimated number of elapsed seconds for the number
            of requests specified

        """
        if from_start:
            return (num_requests - 1) * self._target_interval
        else:
            return num_requests * self._target_interval

    ####################################################################
    # get_completion_time_ns
    ####################################################################
    def get_completion_time_ns(self, num_requests: int, from_start: bool) -> float:
        """Calculate completion time ns for given number requests.

        Args:
            num_requests: number of requests to do
            from_start: specifies whether the calculation should be done
                          for a series that is starting fresh where the
                          first request has no delay

        Returns:
            The estimated number of elapsed seconds for the number
            of requests specified

        """
        if from_start:
            return (num_requests - 1) * self._target_interval_ns
        else:
            return num_requests * self._target_interval_ns

    ####################################################################
    # get_expected_num_completed_reqs
    ####################################################################
    def get_expected_num_completed_reqs(self, interval: float) -> int:
        """Calculate number of requests that completed.

        Args:
            interval: number of elapsed seconds that requests were being
              processed

        Returns:
            The estimated number of requests that were processed during
            the given interval

        """
        return int(interval / self._target_interval) + 1

    ####################################################################
    # sync_send_request
    ####################################################################
    def sync_send_request(
        self, func: Callable[..., Any], *args: Any, **kwargs: Any
    ) -> Any:
        """Send the request.

        Args:
            func: the request function to be run
            args: the request function positional arguments
            kwargs: the request function keyword arguments

        Returns:
              The return value from the request function which may be
              any value or None.
        Raises:
            Exception: An exception occurred in the request target. It
                will be logged and re-raised.

        """
        self.call_count += 1
        ############################################################
        # SYNC mode
        ############################################################
        self.logger.debug(f"sync_send_request entered: {func=}")
        with self.sync_lock:
            self._arrival_time_ns = time.perf_counter_ns()
            self._wait_time_ns = max(
                0.0, self._next_target_time_ns - self._arrival_time_ns
            )
            if (
                self._next_target_time_ns + self.lb_adjustment_ns
                < self._arrival_time_ns
            ):
                # we are well beyond the target time - we need to start
                # a new bucket with the first send entry added
                self._next_target_time_ns = (
                    self._arrival_time_ns + self.lb_with_one_request
                )

            else:  # still in the range of the bucket
                # Sleep, if needed, until we have room in the bucket for
                # one entry.
                if self._wait_time_ns > 0:
                    self.pauser.pause_ns(self._wait_time_ns)

                # add one entry to the bucket
                self._next_target_time_ns += self._target_interval_ns

            self.sent_time_ns = time.perf_counter_ns()

            ########################################################
            # Call the request function and return with the request
            # return value. We use try/except to log and re-raise
            # any unhandled errors.
            ########################################################
            try:
                return func(*args, **kwargs)
            except Exception as e:
                self._capture_apm_error(e, "pure sync context")
                raise

    ####################################################################
    # async_send_request
    ####################################################################
    async def async_send_request(
        self, func: Callable[..., Any], *args: Any, **kwargs: Any
    ) -> Any:
        """Send the request.

        Args:
            func: the request function to be run
            args: the request function positional arguments
            kwargs: the request function keyword arguments

        Returns:
              The return value from the request function which may be
              any value or None.
        Raises:
            Exception: An exception occurred in the request target. It
                will be logged and re-raised.

        """
        self.call_count += 1
        ############################################################
        # ASYNC mode
        ############################################################
        self.logger.debug(f"async_send_request entered: {func=}")
        async with self.async_lock:
            self._arrival_time_ns = time.perf_counter_ns()
            self._wait_time_ns = max(
                0.0, self._next_target_time_ns - self._arrival_time_ns
            )
            if (
                self._next_target_time_ns + self.lb_adjustment_ns
                < self._arrival_time_ns
            ):
                # we are well beyond the target time - we need to start
                # a new bucket with the first send entry added
                self._next_target_time_ns = (
                    self._arrival_time_ns + self.lb_with_one_request
                )

            else:  # still in the range of the bucket
                # Sleep, if needed, until we have room in the bucket for
                # one entry.
                if self._wait_time_ns > 0:
                    await asyncio.sleep(self._wait_time_ns * Throttle.NS_2_SECS)

                # add one entry to the bucket
                self._next_target_time_ns += self._target_interval_ns

            self.sent_time_ns = time.perf_counter_ns()

            ########################################################
            # Call the request function and return with the request
            # return value. We use try/except to log and re-raise
            # any unhandled errors.
            ########################################################
            ctx = contextvars.copy_context()
            if self.convert_to_async:

                def worker_thread_target():
                    try:
                        return func(*args, **kwargs)
                    except Exception as e:
                        self._capture_apm_error(e, "sync to async to_thread")
                        raise

                # Run the worker thread using the captured main-thread context
                return await asyncio.to_thread(lambda: ctx.run(worker_thread_target))
            else:
                try:
                    return await func(*args, **kwargs)
                except Exception as e:
                    self._capture_apm_error(e, "async context")
                    raise

    ####################################################################
    # _capture_apm_error
    ####################################################################
    def _capture_apm_error(self, e: Exception, context_name: str):
        # 1. Standard structured logging (parsed cleanly by Datadog/ELK)
        # self.logger.error(
        #     f"Exception in {context_name} for '{self.t_name}': {e}",
        #     exc_info=True,
        #     extra={
        #         "function_name": self.t_name,
        #         "throttle_delay": self._wait_time_ns * Throttle.NS_2_SECS,
        #     },
        # )

        self.logger.debug(
            f"Exception in {context_name} for '{self.name}': {e}",
            exc_info=True,
            extra={
                "function_name": self.name,
                "throttle_delay": self._wait_time_ns * Throttle.NS_2_SECS,
            },
        )
        # 2. Sentry Explicit Fallback (If the developer uses Sentry)
        # Many APMs capture unhandled exceptions automatically, but inside
        # background threads, explicit capture guarantees it isn't dropped.
        try:
            import sentry_sdk

            sentry_sdk.capture_exception(e)
        except ImportError:
            pass
