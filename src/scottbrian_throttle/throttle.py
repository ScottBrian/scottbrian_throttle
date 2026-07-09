"""Module throttle.

========
Throttle
========

The throttle allows you to limit the rate at which a function is
executed. This is helpful to avoid exceeding a limit, such as when
sending requests to an internet service that specifies a limit on the
number of requests that can be sent per some time interval.

The throttle can be used as a class or as a decorator, and can also be
synchronous or asynchronous.

When you instantiate the throttle as a class, you specify the number of
requests that can be sent per second with the *reqs_per_sec* argument.
This is used to calculate the request interval as 1/*reqs_per_sec*.
Method *get_interval_secs* can be used to obtain the request interval.

:Example: instantiate a throttle for 2 requests per second:

>>> from scottbrian_throttle.throttle import Throttle
>>> throttle = Throttle(reqs_per_sec=2)
>>> print(f"{throttle.get_interval_secs()}")
0.5


To send a request through the throttle, call the *send_request* method
with the target routine and any args or keyword args. The throttle
checks to see whether the request interval has elapsed since the last
request was sent, and if not, sleeps for the remaining request interval.
The throttle then calls the target routine which runs and returns
control to the throttle. The throttle returns control to the caller of
*send_request*, passing back any return values from the target routine.

:Example: send a request through the throttle:

>>> import time
>>> def target_rtn1(request_number, time_of_start):
...     ret_value = (f'request {request_number} sent at elapsed time: '
...                  f'{time.time() - time_of_start:0.1f}')
...     return ret_value
>>> start_time = time.time()
>>> for i in range(10):
...     ret_val = throttle.send_request(target_rtn1, i, start_time)
...     print(ret_val)
request 0 sent at elapsed time: 0.0
request 1 sent at elapsed time: 0.5
request 2 sent at elapsed time: 1.0
request 3 sent at elapsed time: 1.5
request 4 sent at elapsed time: 2.0
request 5 sent at elapsed time: 2.5
request 6 sent at elapsed time: 3.0
request 7 sent at elapsed time: 3.5
request 8 sent at elapsed time: 4.0
request 9 sent at elapsed time: 4.5


Note that in the above scenario, the caller of *send_request* does not
receive control back until the target routine completes, which means the
caller will observe any delay imposed by the throttle. There is also an
asynchronous mode that allows the caller to invoke *send_request* and
receive control back immediately. In this case, the request is queued
and is sent through the throttle from another thread. Note that the
caller is unable to receive a return value from the target routine via
the throttle, so some other protocol will need to be worked out if a
return value is needed. Also, the caller may need to shut down the
throttle at the end of its processing to ensure any in-progress requests
are complete.

:Example: instantiate an asynchronous throttle and send some requests:

>>> async_throttle = Throttle(reqs_per_sec=2, throttle_mode=ThrottleMode.ASYNC)
>>> def target_rtn2(request_number, time_of_start):
...     print(f'request {request_number} sent at elapsed time: '
...           f'{time.time() - time_of_start:0.1f}')
>>> start_time = time.time()
>>> for i in range(10):
...     async_throttle.send_request(target_rtn2, i, start_time)
>>> # do other processing since not waiting for return from throttle
>>> # after other processing, do a shutdown of the throttle
>>> async_throttle.shutdown()
request 0 sent at elapsed time: 0.0
request 1 sent at elapsed time: 0.5
request 2 sent at elapsed time: 1.0
request 3 sent at elapsed time: 1.5
request 4 sent at elapsed time: 2.0
request 5 sent at elapsed time: 2.5
request 6 sent at elapsed time: 3.0
request 7 sent at elapsed time: 3.5
request 8 sent at elapsed time: 4.0
request 9 sent at elapsed time: 4.5


The throttle also provides a leaky bucket implementation, configured by
setting the *bucket_size* to a value greater than 1. In this case, some
number of requests can be sent immediately. Each request is
conceptually placed into a bucket that has with a hole in the bottom.
The bucket leaks out at the request interval rate. The idea is that once
the bucket is full, the throttle delays any addition requests until the
bucket has leaked enough to fit a new request. At that point, the next
request is placed into the bucket and sent. If no new requests arrive
for some extended interval, the bucket becomes empty, and the next
set of requests can be placed into the buck and immediately sent. The
throttle acts like a shock absorber, allowing small bursts of requests
to be sent without delay, with the limiting action kicking in as
additional requests continue to rapidly arrive. The average request
interval will decrease as the size of the bucket increases. Note that a
*bucket_size* of 1 will effectively result in normal non-leaky bucket
behavior. Note also that an asynchronous leaky bucket throttle can be
configured by specifying a *bucket_size* greater than 1 and
*throttle_mode=ThrottleMode.Async*.

:Example: instantiate a leaky bucket throttle and send some requests:

>>> lb_throttle = Throttle(reqs_per_sec=2, name="t1", bucket_count=3)
>>> def target_rtn3(request_number, time_of_start):
...     print(f'request {request_number} sent at elapsed time: '
...           f'{time.time() - time_of_start:0.1f}')
>>> start_time = time.time()
>>> for i in range(10):
...     lb_throttle.send_request(target_rtn3, i, start_time)
request 0 sent at elapsed time: 0.0
request 1 sent at elapsed time: 0.0
request 2 sent at elapsed time: 0.0
request 3 sent at elapsed time: 0.5
request 4 sent at elapsed time: 1.0
request 5 sent at elapsed time: 1.5
request 6 sent at elapsed time: 2.0
request 7 sent at elapsed time: 2.5
request 8 sent at elapsed time: 3.0
request 9 sent at elapsed time: 3.5


All throttle configurations are also provided as decorators:

:Example: Wrapping a function with the **@throttle** decorator

>>> from scottbrian_throttle.throttle import throttle
>>> @throttle(reqs_per_sec=2)
... def func1(request_number, time_of_start):
...     print(f'request {request_number} sent at elapsed time: '
...           f'{time.time() - time_of_start:0.1f}')
>>> start_time = time.time()
>>> for i in range(10):
...     func1(i, start_time)
request 0 sent at elapsed time: 0.0
request 1 sent at elapsed time: 0.5
request 2 sent at elapsed time: 1.0
request 3 sent at elapsed time: 1.5
request 4 sent at elapsed time: 2.0
request 5 sent at elapsed time: 2.5
request 6 sent at elapsed time: 3.0
request 7 sent at elapsed time: 3.5
request 8 sent at elapsed time: 4.0
request 9 sent at elapsed time: 4.5


:Example: Wrapping a function with the **@throttle** decorator for async

>>> @throttle(reqs_per_sec=2, asynch=True)
>>> def func2(request_number, time_of_start):
...     print(f'request {request_number} sent at elapsed time: '
...           f'{time.time() - time_of_start:0.1f}')
>>> start_time = time.time()
>>> for i in range(10):
...     func2(i, start_time)
>>> # do other processing since not waiting for return from throttle
>>> # after other processing, do a shutdown of the throttle
>>> func2.shutdown()
request 0 sent at elapsed time: 0.0
request 1 sent at elapsed time: 0.5
request 2 sent at elapsed time: 1.0
request 3 sent at elapsed time: 1.5
request 4 sent at elapsed time: 2.0
request 5 sent at elapsed time: 2.5
request 6 sent at elapsed time: 3.0
request 7 sent at elapsed time: 3.5
request 8 sent at elapsed time: 4.0
request 9 sent at elapsed time: 4.5


:Example: Wrapping a function with the **@throttle** decorator for async
          and with the leaky bucket

>>> @throttle(reqs_per_sec=2, bucket_count=3, asynch=True)
>>> def func3(request_number, time_of_start):
...     print(f'request {request_number} sent at elapsed time: '
...           f'{time.time() - time_of_start:0.1f}')
>>> start_time = time.time()
>>> for i in range(10):
...     func3(i, start_time)
>>> # do other processing since not waiting for return from throttle
>>> # after other processing, do a shutdown of the throttle
>>> func2.shutdown()
request 0 sent at elapsed time: 0.0
request 1 sent at elapsed time: 0.0
request 2 sent at elapsed time: 0.0
request 3 sent at elapsed time: 0.5
request 4 sent at elapsed time: 1.0
request 5 sent at elapsed time: 1.5
request 6 sent at elapsed time: 2.0
request 7 sent at elapsed time: 2.5
request 8 sent at elapsed time: 3.0
request 9 sent at elapsed time: 3.5

"""

import functools
import logging
import queue
import threading
import time
########################################################################
# Standard Library
########################################################################
from enum import Enum, auto
from typing import (
    Any,
    Callable,
    cast,
    Final,
    NamedTuple,
    Optional,
    overload,
    Protocol,
    TYPE_CHECKING,
    Type,
    TypeVar,
    Union,
)

########################################################################
# Third Party
########################################################################
from scottbrian_utils.pauser import Pauser
from scottbrian_utils.timer import Timer
from typing_extensions import TypeAlias
from wrapt.decorators import decorator  # type: ignore

########################################################################
# Local
########################################################################

########################################################################
# type aliases and TypeVars
########################################################################
IntFloat: TypeAlias = Union[int, float]
OptIntFloat: TypeAlias = Optional[IntFloat]


########################################################################
# Throttle class exceptions
########################################################################
class ThrottleError(Exception):
    """Base class for exceptions in this module."""

    pass


class IncorrectAsyncQSizeSpecified(ThrottleError):
    """Throttle exception for incorrect async_q_size specification."""

    pass


class IncorrectReqsPerSecSpecified(ThrottleError):
    """Throttle exception for incorrect reqs_per_sec specification."""

    pass


class IncorrectBucketSizeSpecified(ThrottleError):
    """Throttle exception for incorrect bucket_size specification."""

    pass


class IncorrectShutdownTypeSpecified(ThrottleError):
    """Throttle exception for incorrect shutdown_type specification."""

    pass


class InvalidAsyncQSizeSpecified(ThrottleError):
    """Throttle exception for invalid asynjc_q_size specification."""


########################################################################
# Mode
########################################################################
class ThrottleMode(Enum):
    """ThrottleMode is SYNC or ASYNC."""

    SYNC = auto()
    ASYNC = auto()


########################################################################
# Throttle class
########################################################################
class Throttle:
    """Throttle class."""

    DEFAULT_ASYNC_Q_SIZE: Final[int] = 4096
    MAX_PAUSE_NS: Final[int] = 1000000000

    ####################################################################
    # start_shutdown request constants
    ####################################################################
    TYPE_SHUTDOWN_SOFT: Final[int] = 4
    TYPE_SHUTDOWN_HARD: Final[int] = 8

    ####################################################################
    # start_shutdown return code constants
    ####################################################################
    RC_SHUTDOWN_SOFT_COMPLETED_OK: Final[int] = 0
    RC_SHUTDOWN_HARD_COMPLETED_OK: Final[int] = 4
    RC_SHUTDOWN_TIMED_OUT: Final[int] = 8

    ####################################################################
    # throttle state constants
    ####################################################################
    _ACTIVE: Final[int] = 0
    _SOFT_SHUTDOWN_STARTED: Final[int] = 1
    _HARD_SHUTDOWN_STARTED: Final[int] = 2
    _SOFT_SHUTDOWN_COMPLETED: Final[int] = 3
    _HARD_SHUTDOWN_COMPLETED: Final[int] = 4

    ####################################################################
    # send_request return codes
    ####################################################################
    RC_OK: Final[int] = 0
    RC_THROTTLE_IS_SHUTDOWN: Final[int] = 4

    class Request(NamedTuple):
        """NamedTuple for the request queue item."""

        request_func: Callable[..., Any]
        args: tuple[Any, ...]
        kwargs: dict[str, Any]
        arrival_time: float

    SECS_2_NS: Final[int] = 1000000000
    NS_2_SECS: Final[float] = 0.000000001

    __slots__ = (
        "_arrival_time",
        "_next_target_time",
        "_target_interval",
        "_target_interval_ns",
        "_throttle_shutdown_started",
        "_wait_time_ns",
        "async_q",
        "async_q_size",
        "throttle_mode",
        "bucket_size",
        "lb_adjustment",
        "lb_adjustment_ns",
        "logger",
        "pauser",
        "reqs_per_sec",
        "request_scheduler_thread",
        "shutdown_elapsed_time",
        "shutdown_lock",
        "shutdown_start_time",
        "sync_lock",
        "t_name",
        "throttle_state",
    )

    ####################################################################
    # __init__
    ####################################################################
    def __init__(
        self,
        *,
        reqs_per_sec: int | float,
        bucket_size: int | float = 1,
        throttle_mode: ThrottleMode = ThrottleMode.SYNC,
        async_q_size: Optional[int] = None,
        name: Optional[str] = None,
    ) -> None:
        """Initialize an instance of the Throttle class.

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
                         one for the bucket_count will effectively
                         cause non-leaky bucket behavior, meaning that
                         each request that arrives before the previous
                         request interval has elapsed will be delayed.
                         The bucket_count must be greater than or equal
                         to 1.
            throttle_mode: If ThrottleMode.ASYNC, the throttle is asynchronous. If
                    ThrottleMode.SYNC, the default, the throttle is synchronous.
            async_q_size: Specifies the size of the request
                          queue for async requests. When the request
                          queue is totally populated, any additional
                          calls to send_request will be delayed
                          until queued requests are removed and
                          scheduled. The default is 4096 requests.
            name: The name used to identify the throttle in log messages
                issued by the throttle. The default name is
                the python id of the Throttle class instance.


        Raises:
            IncorrectReqsPerSecSpecified: The *reqs_per_sec*
                specification must be a positive int or float greater
                than zero.
            IncorrectAsyncQSizeSpecified: *async_q_size* must be an
                integer greater than zero.

        """
        ################################################################
        # reqs_per_sec
        ################################################################
        if isinstance(reqs_per_sec, int | float) and (0 < reqs_per_sec):
            self.reqs_per_sec = reqs_per_sec
        else:
            raise IncorrectReqsPerSecSpecified(
                "The reqs_per_sec specification must be a positive "
                "int or float greater than zero."
            )
        ################################################################
        # bucket_size
        ################################################################
        if isinstance(bucket_size, int | float) and (1 <= bucket_size):
            self.bucket_size = bucket_size
        else:
            raise IncorrectBucketSizeSpecified(
                "The bucket_size specification must be a positive "
                "int or float greater than or equal to 1."
            )

        ################################################################
        # async_throttle
        ################################################################
        ################################################################
        # States and processing for Throttle:
        #
        #     The Throttle is initialized with an empty async_q and the
        #     scheduler thread is started and ready to receive work. The
        #     starting state is 'active'.
        #
        #     1) state: active
        #        a) send_request called (directly or via decorated func
        #           call):
        #           1) request is queued to the async_q
        #           2) state remains 'active'
        #        b) start_shutdown called:
        #           1) state is changed to 'shutdown'
        #           2) Any new requests are rejected. For "soft"
        #           shutdown, scheduler schedules the remaining requests
        #           currently queued on the async_q with the normal
        #           interval. With "hard" shutdown, the scheduler
        #           removes and discards the requests on the async_q.
        #           3) scheduler exits
        #           4) control returns after scheduler thread returns
        #     2) state: shutdown
        #        a) send_request called (directly or via decorated func
        #           call):
        #           1) request is ignored  (i.e, not queued to async_q)
        #        b) start_shutdown called (non-decorator only):
        #           1) state remains 'shutdown'
        #           2) control returns immediately
        ################################################################
        self.throttle_mode = throttle_mode

        if self.throttle_mode == ThrottleMode.ASYNC:
            if async_q_size is not None:
                if isinstance(async_q_size, int) and (0 < async_q_size):
                    self.async_q_size = async_q_size
                else:
                    raise IncorrectAsyncQSizeSpecified(
                        "async_q_size must be an integer greater than zero."
                    )
            else:
                self.async_q_size = Throttle.DEFAULT_ASYNC_Q_SIZE
        else:
            if async_q_size is not None and async_q_size != 0:
                raise InvalidAsyncQSizeSpecified(
                    "a non_zero async_q_size is not allowed when throttle_mode is "
                    "ThrottleMode.SYNC."
                )
            self.async_q_size = 0

        ################################################################
        # name
        ################################################################
        # if name is None:
        #     self.t_name = str(id(self))
        # else:
        #     self.t_name = name
        self.t_name = name or str(id(self))

        ################################################################
        # Set remainder of vars
        ################################################################
        self._target_interval = 1 / reqs_per_sec
        self._target_interval_ns: float = self._target_interval * Throttle.SECS_2_NS
        self.sync_lock = threading.Lock()
        self._arrival_time = 0.0
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

        # adjust _next_target_time for normal or lb algo
        self._next_target_time = time.perf_counter_ns() - self.lb_adjustment_ns

        if self.throttle_mode == ThrottleMode.ASYNC:
            ########################################################
            # Set remainder of async vars
            ########################################################
            self.shutdown_lock = threading.Lock()
            self._throttle_shutdown_started = False
            self.throttle_state = Throttle._ACTIVE
            self.shutdown_start_time = 0.0
            self.shutdown_elapsed_time = 0.0
            self.async_q: queue.Queue[Throttle.Request] = queue.Queue(
                maxsize=self.async_q_size
            )
            self.request_scheduler_thread: threading.Thread = threading.Thread(
                target=self.schedule_requests
            )
            self.request_scheduler_thread.start()

    ####################################################################
    # repr
    ####################################################################
    def __repr__(self) -> str:
        """Return a representation of the class.

        Returns:
            The representation as how the class is instantiated

        :Example: instantiate a throttle for 1 requests every 2 seconds

        >>> from scottbrian_throttle.throttle import Throttle
        >>> request_throttle = ThrottleSync(reqs_per_sec=0.5)
        >>> repr(request_throttle)
        'ThrottleSync(reqs_per_sec=0.5 bucket_size=1, throttle_mode=ThrottleMode.SYNC, async_q_size=None, name=3056773933840)'

        """
        if TYPE_CHECKING:
            __class__: Type[Throttle]  # noqa: F842
        classname = self.__class__.__name__
        parms = (
            f"reqs_per_sec={self.reqs_per_sec}, "
            f"bucket_size={self.bucket_size}, "
            f"throttle_mode={str(self.throttle_mode)}, "
            f"async_q_size={self.async_q_size}, "
            f"name={self.t_name}"
        )

        return f"{classname}({parms})"

    ####################################################################
    # len
    ####################################################################
    def __len__(self) -> int:
        """Return the number of items in the async_q.

        Returns:
            The number of entries in the async_q as an integer

        For an asynchronous throttle, calls to the send_request add
        request items to the async_q. The request items are eventually
        removed and scheduled. The len of Throttle is the number of
        request items on the async_q when the len function is called.
        Note that the returned queue size is the approximate size as
        described in the documentation for the python threading queue.

        :Example: instantiate an asynchronous throttle for 1 request per second

        >>> from scottbrian_throttle.throttle import Throttle
        >>> import time
        >>> def my_request():
        ...     pass
        >>> request_throttle = Throttle(reqs_per_sec=1,throttle_mode=ThrottleMode.ASYNC)
        >>> for i in range(3):  # quickly queue up 3 items
        ...     _ = request_throttle.send_request(my_request)
        >>> time.sleep(0.5)  # allow first request to be dequeued
        >>> print(len(request_throttle))
        2

        >>> request_throttle.start_shutdown()

        """
        return self.async_q.qsize()

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
    # get_completion_time
    ####################################################################
    def get_completion_time_secs(self, requests: int, from_start: bool) -> float:
        """Calculate completion time secs for given number requests.

        Args:
            requests: number of requests to do
            from_start: specifies whether the calculation should be done
                          for a series that is starting fresh where the
                          first request has no delay

        Returns:
            The estimated number of elapsed seconds for the number
            of requests specified

        """
        if from_start:
            return (requests - 1) * self._target_interval
        else:
            return requests * self._target_interval

    ####################################################################
    # get_completion_time
    ####################################################################
    def get_completion_time_ns(self, requests: int, from_start: bool) -> float:
        """Calculate completion time ns for given number requests.

        Args:
            requests: number of requests to do
            from_start: specifies whether the calculation should be done
                          for a series that is starting fresh where the
                          first request has no delay

        Returns:
            The estimated number of elapsed seconds for the number
            of requests specified

        """
        if from_start:
            return (requests - 1) * self._target_interval_ns
        else:
            return requests * self._target_interval_ns

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
    # send_request
    ####################################################################
    def send_request(self, func: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
        """Send the request.

        Args:
            func: the request function to be run
            args: the request function positional arguments
            kwargs: the request function keyword arguments

        Returns:
              The return value from the request function. For
              throttle_mode = False, the return value may be any value
              or None. For throttle_mode = True, the return value will
              be None.

        Raises:
            Exception: An exception occurred in the request target. It
                will be logged and re-raised.

        """
        if self.throttle_mode == ThrottleMode.ASYNC:
            # if self.throttle_state != Throttle._ACTIVE:
            #     return Throttle.RC_THROTTLE_IS_SHUTDOWN

            # We obtain the shutdown lock to protect against the following
            # scenario:
            # 1) send_request is entered for async throttle_mode and sees at
            # the while statement that we are *not* in shutdown
            # 2) send_request proceeds to the try statement just
            # before the request will be queued to the async_q
            # 2) shutdown is requested and is detected by
            # schedule_requests
            # 3) schedule_requests cleans up the async_q end exits
            # 4) back here in send_request, we put our request on the
            # async_q - this request will never be processed
            with self.shutdown_lock:
                request_item = Throttle.Request(
                    func, args, kwargs, time.perf_counter_ns()
                )
                # start_shutdown will set _throttle_shutdown_started to tell
                # us to abandon our attempts to get a request on a full
                # async_q so that we give up the lock to allow
                # start_shutdown to proceed
                while not self._throttle_shutdown_started:
                    try:
                        self.async_q.put(request_item, block=True, timeout=0.5)
                        return Throttle.RC_OK
                    except queue.Full:
                        continue  # no need to wait since we already did
                return Throttle.RC_THROTTLE_IS_SHUTDOWN
        else:
            ################################################################
            # SYNC_MODE
            ################################################################
            ################################################################
            # The SYNC_MODE Throttle algorithm works as follows:
            # 1) during throttle instantiation:
            #    a) a target interval is calculated as 1/reqs_per_sec.
            #       For example, with a specification of 4 reqs_per_sec,
            #       the target interval will be 0.25 seconds.
            #    b) _next_target_time is set to a current time reference via
            #       time.perf_counter_ns
            # 2) as each request arrives, it is checked against the
            #    _next_target_time and:
            #    a) if it arrives at or after _next_target_time, it is
            #       allowed to proceed without delay
            #    b) if it arrives before the _next_target_time the request
            #       is delayed until _next_target_time is reached
            # 3) _next_target_time is increased by the target_interval
            #
            ################################################################
            with self.sync_lock:
                # # set the time that this request is being made
                # self._arrival_time = time.perf_counter_ns()
                #
                # if self._arrival_time < self._next_target_time:
                #     wait_time = (
                #         self._next_target_time - self._arrival_time
                #     ) * Throttle.NS_2_SECS
                #     self.pauser.pause(wait_time)

                ############################################################
                # Update the expected arrival time for the next request by
                # adding the request interval to our current time. Note that
                # we update the target time before we send the request which
                # means we
                # face a possible scenario where we send a request that gets
                # delayed en route to the service, but our next request
                # arrives at the updated expected arrival time and is sent
                # out immediately, but it now arrives early relative to the
                # previous request, as observed by the service. If we update
                # the target time after sending the request we avoid that
                # scenario, but we would then be adding in the request
                # processing time to the throttle delay with the undesirable
                # effect that all requests will now be throttled more than
                # they need to be.
                ########################################################
                # self._next_target_time = time.perf_counter_ns() + self._target_interval_ns
                ########################################################
                # The leaky bucket algorith uses a virtual bucket into which
                # arriving requests are placed. As time progresses, the
                # bucket leaks the requests out at the rate of the target
                # interval. If the bucket has room for an arriving request,
                # the request is placed into the bucket and is sent
                # immediately. If, instead, the bucket does not have room
                # for the request, the request is delayed until the bucket
                # has leaked enough of the preceding requests such that the
                # new request can fit and be sent. The effect of the bucket
                # is to allow a burst of requests to be sent immediately at
                # a faster rate than the target interval, acting as a
                # shock absorber to the flow of traffic. The number of
                # requests allowed to go immediately is controlled by the
                # size of the bucket which in turn is specified by the
                # lb_threshold argument when the throttle is instantiated.
                #
                # Note that by allowing short bursts to go immediately,
                # the overall effect is that the average interval will be
                # less than the target interval.
                #
                # The actual implementation does not employ a bucket, but
                # instead sets a target time for the next request by adding
                # the target interval and subtracting the size of the
                # bucket. This has the effect of making it appear as if
                # requests are arriving after the target time and are thus
                # in compliance with the target interval, but eventually
                # the next target time will exceed the size of the bucket
                # and requests will get delayed to allow the target time
                # to catch up.
                ########################################################

                ########################################################
                # In the following code we handle three cases:
                # 1) The current send request arrives well beyond the last
                #    send such that the bucket is completely empty. We need
                #    to start a new bucket relative to the current arrival
                #    time.
                # 2) The current send arrives rapidly on the heels of the
                #    previous sends such that the bucket is full enough that
                #    it does not contain enough room to add a new entry. We
                #    need to delay this current send until there is room
                #    enough in the bucket to add this one entry.
                # 3) The current send arrives when the bucket has one or
                #    more previous sends still leaking out, but there is
                #    still enough room in the bucket to add another send
                #    without delay.
                #
                # Note that we update the bucket (i.e., target time) before
                # we call the requested function instead of updating the
                # target time after control returns from the requested
                # function. This means we face a possible scenario where we
                # encounter a delay during the call to the requested
                # function, and upon return we receive the next send request
                # which, because of the prior delay, appears ok to send
                # immediately. But this new request might appear early as
                # observed by the called service (i.e., requested function).
                # If instead we were to update the target time after getting
                # back control from the requested function, we avoid the
                # "too early" scenario, but we would then be adding in the
                # request processing time to the throttle delay with the
                # undesirable effect that all requests will now be throttled
                # more than they need to be. The "too early" scenario seemed
                # less problematic compared to the "extra throttling"
                # effect, so the design choice was made to update the target
                # time before calling the requested function.
                ########################################################
                self._arrival_time = time.perf_counter_ns()
                self._wait_time_ns = 0.0
                if self._next_target_time + self.lb_adjustment_ns < self._arrival_time:
                    # we are well beyond the target time - we need to start
                    # a new bucket with the first send entry added
                    self._next_target_time = (
                        self._arrival_time
                        - self.lb_adjustment_ns
                        + self._target_interval_ns
                    )
                else:  # still in the range of the bucket
                    if self._arrival_time < self._next_target_time:
                        # we need to delay to allow the bucket to leak out
                        # enough to fit the next entry we are sending
                        self._wait_time_ns = self._next_target_time - self._arrival_time
                        self.pauser.pause_ns(self._wait_time_ns)
                    # add one entry to the bucket
                    self._next_target_time += self._target_interval_ns

                ########################################################
                # Call the request function and return with the request
                # return value. We use try/except to log and re-raise any
                # unhandled errors.
                ########################################################
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    self.logger.debug(
                        f"throttle {self.t_name} send_request unhandled exception in "
                        f"request: {e}"
                    )
                    raise

    ####################################################################
    # schedule_requests
    ####################################################################
    def schedule_requests(self) -> None:
        """Get tasks from queue and run them.

        Raises:
            Exception: re-raise any throttle schedule_requests unhandled
                         exception in request

        """
        # Requests will be scheduled from the async_q at the interval
        # calculated from the requests and seconds arguments when the
        # throttle was instantiated. If shutdown is indicated,
        # the async_q will be cleaned up with any remaining requests
        # either processed (Throttle.TYPE_SHUTDOWN_SOFT) or dropped
        # (Throttle.TYPE_SHUTDOWN_HARD). Note that async_q.get will
        # only wait for a second to allow us to detect shutdown in a
        # timely fashion.
        while True:
            try:
                request_item = self.async_q.get(block=True, timeout=1)

                self._next_target_time = (
                    time.perf_counter_ns() + self._target_interval_ns
                )
            except queue.Empty:
                if self.throttle_state != Throttle._ACTIVE:
                    return
                continue  # no need to wait since we already did
            ############################################################
            # Call the request function.
            # We use try/except to log and re-raise any unhandled
            # errors.
            ############################################################
            try:
                if self.throttle_state != Throttle._HARD_SHUTDOWN_STARTED:
                    self._arrival_time = request_item.arrival_time
                    request_item.request_func(*request_item.args, **request_item.kwargs)
                    # obtained_nowait=obtained_nowait)
            except Exception as e:
                self.logger.debug(
                    f"throttle {self.t_name} schedule_requests unhandled exception in "
                    f"request: {e}"
                )
                raise

            ############################################################
            # wait (i.e., throttle)
            # Note that the wait time could be anywhere from a fraction
            # of a second to several seconds. We want to be responsive
            # in case we need to bail for shutdown, so we wait in 1
            # second or fewer increments and bail if we detect shutdown.
            ############################################################
            self._wait_time_ns = self._next_target_time - time.perf_counter_ns()
            while True:
                # handle shutdown
                if self.throttle_state != Throttle._ACTIVE:
                    if self.async_q.empty():
                        return  # we are done with shutdown
                    if self.throttle_state == Throttle._HARD_SHUTDOWN_STARTED:
                        break  # don't sleep for hard shutdown

                # Use min to ensure we don't sleep too long and appear
                # slow to respond to a shutdown request
                sleep_ns = self._next_target_time - time.perf_counter_ns()
                if sleep_ns > 0:  # if still time to go
                    self.pauser.pause_ns(min(Throttle.MAX_PAUSE_NS, sleep_ns))
                    # time_trace, stop_time = self.pauser.pause(min(1.0,
                    #                                         sleep_ns))
                    # self.time_traces.append(time_trace)
                    # self.stop_times.append(stop_time)
                else:  # we are done sleeping
                    break

    ####################################################################
    # start_shutdown
    ####################################################################
    def start_shutdown(
        self,
        shutdown_type: int = TYPE_SHUTDOWN_SOFT,
        timeout: OptIntFloat = None,
        suppress_timeout_msg: bool = False,
    ) -> int:
        """Shutdown the async throttle request scheduling.

        Shutdown is used to stop and clean up any pending requests on
        the async request queue. This should be done during normal
        application shutdown or when an error occurs. Once the throttle
        has completed shutdown it can no longer be used. If a throttle
        is once again needed after shutdown, a new one will need to be
        instantiated to replace the old one.

        Note that a soft shutdown can be started and eventually be
        followed by a hard shutdown to force shutdown to complete
        quickly. A hard shutdown, however, can not be followed by a
        soft shutdown since there is no way to retrieve and run any
        of the requests that were already removed and tossed by the
        hard shutdown.

        Args:
            shutdown_type: specifies whether to do a soft or a hard
                shutdown:

                     * A soft shutdown
                       (Throttle.TYPE_SHUTDOWN_SOFT),
                       the default, stops any additional
                       requests from being queued and cleans up
                       the request queue by scheduling any
                       remaining requests at the normal interval
                       as calculated by the *seconds* and
                       *requests* arguments specified during
                       throttle instantiation.
                     * A hard shutdown
                       (Throttle.TYPE_SHUTDOWN_HARD) stops
                       any additional requests from being queued
                       and cleans up the request queue by
                       quickly removing any remaining requests
                       without executing them.

            timeout: number of seconds to allow for shutdown to
                       complete. If the shutdown times out, control is
                       returned with a return value of False. The
                       shutdown will continue and a subsequent call to
                       start_shutdown, with or without a timeout value,
                       may eventually return control with a return value
                       of True to indicate that the shutdown has
                       completed. Note that a *timeout* value of zero or
                       less is handled as if shutdown None was
                       specified, whether explicitly or by default, in
                       which case the shutdown will not timeout and will
                       control will be returned if and when the shutdown
                       completes. A very small value, such as 0.001,
                       can be used to start the shutdown and then get
                       back control to allow other cleanup activities
                       to be performed and eventually issue a second
                       shutdown request to ensure that it is completed.
            suppress_timeout_msg: used by shutdown_throttle_funcs to
                       prevent the timeout log message since it will
                       issue its own log message

        .. # noqa: DAR101

        Returns: One of the following return codes is returned:

            * RC_SHUTDOWN_SOFT_COMPLETED_OK (0): the
              ``start_shutdown()`` request either completed a soft
              shutdown or detected that a previous soft shutdown
              request had been completed.
            * RC_SHUTDOWN_HARD_COMPLETED_OK (4): the
              ``start_shutdown()`` request either completed a hard
              shutdown or detected that a previous hard shutdown
              request had been completed.
            * RC_SHUTDOWN_TIMED_OUT (8): the ``start_shutdown()``
              request with a non-zero positive *timeout* value was
              specified and did not complete within the specified
              number of seconds

        Raises:
            IncorrectShutdownTypeSpecified: For start_shutdown,
            shutdownType must be specified as either
            Throttle.TYPE_SHUTDOWN_SOFT or
            Throttle.TYPE_SHUTDOWN_HARD

        """
        if shutdown_type not in (
            Throttle.TYPE_SHUTDOWN_SOFT,
            Throttle.TYPE_SHUTDOWN_HARD,
        ):
            raise IncorrectShutdownTypeSpecified(
                "For start_shutdown, shutdownType must be specified as "
                "either Throttle.TYPE_SHUTDOWN_SOFT or "
                "Throttle.TYPE_SHUTDOWN_HARD"
            )

        ################################################################
        # We are good to go for shutdown
        ################################################################
        # The shutdown started flag is initialized to False and once
        # set to True is never changed back to False. We set it here
        # when we are about to start shutdown to tell send_request to
        # exit immediately rather that continuing to loop trying to get
        # a request on a full async_q

        self._throttle_shutdown_started = True

        # We use the shutdown lock to block us until any in progress
        # send_requests are complete, and to block other shutdown
        # requests while the variables are been checked and set.
        # TODO: use se_lock
        with self.shutdown_lock:
            # Soft shutdown finishes the queued requests while also
            # doing the throttling, meaning that a soft shutdown
            # is done when the queued requests are important and must be
            # done.
            # Hard shutdown is done to toss any queued requests and
            # quickly bring the throttle to the shutdown state.
            # A hard shutdown request can be done while a soft shutdown
            # is in progress - this will simply cause the requests to
            # be tossed and the shutdown will complete more quickly.
            # Request a soft shutdown after a hard shutdown has been
            # initiated is OK, but the shutdown will not be changed to
            # a soft shutdown. The return codes will tell either type
            # of request how the throttle was shutdown.

            if self.throttle_state == Throttle._ACTIVE:
                # We will set the start time only when the first
                # shutdown request is made. More than one shutdown
                # request can be made. Whichever request first detects
                # the completion of the shutdown will calculate the
                # elapsed time.
                self.shutdown_start_time = time.time()

                if shutdown_type == Throttle.TYPE_SHUTDOWN_SOFT:
                    self.throttle_state = Throttle._SOFT_SHUTDOWN_STARTED
                else:
                    self.throttle_state = Throttle._HARD_SHUTDOWN_STARTED
            else:  # shutdown already started or has already completed
                # if currently processing a soft shutdown and a hard
                # shutdown is now being requested, we need to shift to a
                # hard shutdown
                if (
                    self.throttle_state == Throttle._SOFT_SHUTDOWN_STARTED
                    and shutdown_type == Throttle.TYPE_SHUTDOWN_HARD
                ):
                    self.throttle_state = Throttle._HARD_SHUTDOWN_STARTED

        ################################################################
        # join the schedule_requests thread to wait for the shutdown
        ################################################################
        timer = Timer(timeout=timeout)
        if timeout and timeout > 0:
            join_timeout = min(0.1, timeout)
        else:
            join_timeout = 0.1

        while self.request_scheduler_thread.is_alive() and not timer.is_expired():
            self.request_scheduler_thread.join(timeout=join_timeout)

        ################################################################
        # determine results
        ################################################################
        with self.shutdown_lock:
            if self.request_scheduler_thread.is_alive():
                if not suppress_timeout_msg:
                    self.logger.debug(
                        f"throttle {self.t_name} start_shutdown request timed out with "
                        f"{timeout=:.4f}"
                    )
                return Throttle.RC_SHUTDOWN_TIMED_OUT

            # if here, throttle is shutdown
            completion_log_msg_needed = False
            if self.throttle_state == Throttle._SOFT_SHUTDOWN_STARTED:
                self.throttle_state = Throttle._SOFT_SHUTDOWN_COMPLETED
                completion_log_msg_needed = True
            elif self.throttle_state == Throttle._HARD_SHUTDOWN_STARTED:
                self.throttle_state = Throttle._HARD_SHUTDOWN_COMPLETED
                completion_log_msg_needed = True

            if completion_log_msg_needed:
                # add 0.0001 so we don't get a zero elapsed time
                self.shutdown_elapsed_time = (
                    time.time() - self.shutdown_start_time + 0.0001
                )
                self.logger.debug(
                    f"throttle {self.t_name} start_shutdown request successfully "
                    f"completed in {self.shutdown_elapsed_time:.4f} seconds"
                )

            if self.throttle_state == Throttle._SOFT_SHUTDOWN_COMPLETED:
                return Throttle.RC_SHUTDOWN_SOFT_COMPLETED_OK
            else:
                return Throttle.RC_SHUTDOWN_HARD_COMPLETED_OK


########################################################################
# Pie Throttle Decorator
########################################################################
F = TypeVar("F", bound=Callable[..., Any])


########################################################################
# FuncWithThrottleAttr class
########################################################################
class FuncWithThrottleAttr(Protocol[F]):
    """Class to allow type checking on function with attribute."""

    throttle: Throttle
    __call__: F


def add_throttle_attr(func: F) -> FuncWithThrottleAttr[F]:
    """Wrapper to add throttle attribute to function.

    Args:
        func: function that has the attribute added

    Returns:
        input function with throttle attached as attribute

    """
    return cast(FuncWithThrottleAttr[F], func)


########################################################################
# @throttle
########################################################################
@overload
def throttle(
    wrapped: F,
    *,
    reqs_per_sec: int,
    bucket_size: int | float = 1,
    throttle_mode: ThrottleMode = ThrottleMode.SYNC,
    async_q_size: Optional[int] = None,
    name: Optional[str] = None,
) -> FuncWithThrottleAttr[F]:
    pass


@overload
def throttle(
    *,
    reqs_per_sec: int,
    bucket_size: int | float = 1,
    throttle_mode: ThrottleMode = ThrottleMode.SYNC,
    async_q_size: Optional[int] = None,
    name: Optional[str] = None,
) -> Callable[[F], FuncWithThrottleAttr[F]]:
    pass


def throttle(
    wrapped: Optional[F] = None,
    *,
    reqs_per_sec: int,
    bucket_size: int | float = 1,
    throttle_mode: ThrottleMode = ThrottleMode.SYNC,
    async_q_size: Optional[int] = None,
    name: Optional[str] = None,
) -> Union[F, FuncWithThrottleAttr[F]]:
    """Decorator to wrap a function in a sync throttle.

    The throttle wraps code around a function that is typically used to
    issue requests to an online service. Some services state a limit as
    to how many requests can be made per some time interval (e.g., 3
    requests per second). The throttle code ensures that the limit is
    not exceeded.

    Args:
        wrapped: Any callable function that accepts optional positional
                   and/or optional keyword arguments, and optionally
                   returns a value. The default is None, which will be
                   the case when the pie decorator version is used with
                   any of the following arguments specified.
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
                     one for the bucket_count will effectively
                     cause non-leaky bucket behavior, meaning that
                     each request that arrives before the previous
                     request interval has elapsed will be delayed.
                     The bucket_count must be greater than or equal
                     to 1.
        throttle_mode: If ThrottleMode.ASYNC, the throttle is asynchronous. If
                ThrottleeMode.SYNC, the default, the throttle is synchronous.
        async_q_size: Specifies the size of the request
                      queue for async requests. When the request
                      queue is totally populated, any additional
                      calls to send_request will be delayed
                      until queued requests are removed and
                      scheduled. The default is 4096 requests.
        name: The name used to identify the throttle in log messages
            issued by the throttle. The default name is
            the python id of the Throttle class instance.

    Returns:
        A callable function that delays the request as needed in
        accordance with the specified limits.

    :Example: wrap a function with a sync throttle for 1 request
                  per second

    >>> from scottbrian_throttle.throttle import Throttle
    >>> @throttle(reqs_per_sec=1)
    ... def f1() -> None:
    ...     print('example 1 request function')


    """
    # ==================================================================
    #  The following code covers cases where throttle is used with or
    #  without the pie character, where the decorated function has or
    #  does not have parameters.
    #
    #     Here's an example of throttle with a function that has no
    #         args:
    #         @throttle(reqs_per_sec=1)
    #         def a_func():
    #             print('42')
    #
    #     This is what essentially happens under the covers:
    #         def a_func():
    #             print('42')
    #         aFunc = throttle(reqs_per_sec=1)(a_func)
    #
    #     The call to throttle results in a function being returned that
    #     takes as its first argument the a_func specification that we
    #     see in parens immediately following the throttle call.
    #
    #     Note that we can also code the above as shown and get the same
    #     result:
    #         def a_func():
    #             print('42')
    #         a_func = throttle(a_func, reqs_per_sec=1)
    #
    #     What happens is throttle gets control and tests whether a_func
    #     was specified, and if not returns a call to functools.partial
    #     which is the function that accepts the a_func
    #     specification and then calls throttle with a_func as the first
    #     argument with the other arg for reqs_per_sec.
    #
    #     One other complication is that we are also using the
    #     wrapt.decorator for the inner wrapper function which helps to
    #     ensure introspection will work as expected.
    # ==================================================================

    if wrapped is None:
        return cast(
            FuncWithThrottleAttr[F],
            functools.partial(
                throttle,
                reqs_per_sec=reqs_per_sec,
                bucket_size=bucket_size,
                throttle_mode=throttle_mode,
                async_q_size=async_q_size,
                name=name,
            ),
        )

    if name is None:
        name = wrapped.__name__
    a_throttle = Throttle(
        reqs_per_sec=reqs_per_sec,
        bucket_size=bucket_size,
        throttle_mode=throttle_mode,
        async_q_size=async_q_size,
        name=name,
    )

    @decorator  # type: ignore
    def wrapper(
        func_to_wrap: F,
        instance: Optional[Any],
        args: tuple[Any, ...],
        kwargs2: dict[str, Any],
    ) -> Any:

        return a_throttle.send_request(func_to_wrap, *args, **kwargs2)

    wrapper = wrapper(wrapped)

    wrapper = add_throttle_attr(wrapper)
    wrapper.throttle = a_throttle

    return cast(FuncWithThrottleAttr[F], wrapper)


########################################################################
# shutdown_throttle_funcs
########################################################################
def shutdown_throttle_funcs(
    *args: FuncWithThrottleAttr[Callable[..., Any]],
    # *args: FuncWithThrottleAttr[Protocol[F]],
    shutdown_type: int = Throttle.TYPE_SHUTDOWN_SOFT,
    timeout: OptIntFloat = None,
) -> bool:
    """Shutdown the throttle request scheduling for decorated functions.

    The shutdown_throttle_funcs function is used to shutdown one or more
    functions that were decorated with the throttle. The arguments apply
    to each of the functions that are specified to be shutdown. If
    timeout is specified, then True is returned if all functions
    were shutdown within the timeout number of seconds specified.

    Args:
        args: one or more functions to be shutdown
        shutdown_type: specifies whether to do a soft or a hard
                         shutdown:

                         * A soft shutdown
                           (Throttle.TYPE_SHUTDOWN_SOFT), the
                           default, stops any additional requests from
                           being queued and cleans up the request queue
                           by scheduling any remaining requests at the
                           normal interval as calculated by the seconds
                           and requests that were specified during
                           instantiation.
                         * A hard shutdown
                           (Throttle.TYPE_SHUTDOWN_HARD) stops any
                           additional requests from being queued and
                           cleans up the request queue by quickly
                           removing any remaining requests without
                           executing them.
        timeout: number of seconds to allow for shutdown to complete for
                   all functions specified to be shutdown.
                   Note that a *timeout* of zero or less is equivalent
                   to a *timeout* of None, meaning start_shutdown will
                   return when the shutdown is complete without a
                   timeout.

    .. # noqa: DAR101

    Returns:
        * ``True`` if *timeout* was not specified, or if it was
          specified and all specified functions completed
          shutdown within the specified number of seconds. Also, if the
          list of funcs to shutdown is empty, True is returned.
        * ``False`` if *timeout* was specified and at least one of the
          functions specified to shutdown did not complete within the
          specified number of seconds.

    """
    funcs = [func for func in args]
    timer = Timer(timeout=timeout)
    ####################################################################
    # In the following code we loop until we all funcs are shutdown or
    # until we time out when timeout is specified. We call shutdown for
    # each func with a very short timeout value. The first attempt for
    # each func will get its shutdown started and very likely result in
    # a timeout retcode. This is OK since we suppress the timeout log
    # message. Even though the timeout happens, the shutdown, once
    # started, will continue processing. Each subsequent attempt will
    # either timeout again or come back with a completed retcode. We
    # remove each completed func from the list and keep trying the
    # remining funcs.
    ####################################################################
    while funcs:
        funcs_remaining = [func for func in funcs]
        for func in funcs_remaining:
            if Throttle.RC_SHUTDOWN_TIMED_OUT != func.throttle.start_shutdown(
                shutdown_type=shutdown_type, timeout=0.01, suppress_timeout_msg=True
            ):
                funcs.remove(func)

        if timer.is_expired() and funcs:
            for func in funcs:
                func.throttle.logger.debug(
                    f"Throttle {func.throttle.t_name} shutdown_throttle_funcs request "
                    f"timed out with {timeout=:.4f}"
                )
            return False  # we timed out

        time.sleep(0.1)  # allow shutdowns to progress

    # if here, all funcs successfully shutdown
    return True
