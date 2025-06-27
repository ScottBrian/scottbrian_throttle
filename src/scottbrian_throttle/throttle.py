"""Module throttle.

========
Throttle
========

The throttle allows you to limit the rate at which a function is
executed. This is helpful to avoid exceeding a limit, such as when
sending requests to an internet service that specifies a limit as to the
number of requests that can be sent in a specific time interval.

The throttle package include four different algorithms for the limiting
control, each provided as a decorator or as a class:

  1. **@throttle_sync** decorator and **ThrottleSync** class provide a
     synchronous algorithm.

       For synchronous throttling, you specify the *requests* and
       *seconds* which determine the send rate limit. The throttle
       keeps track of the intervals between each request and will block
       only as needed to ensure the send rate limit is not exceeded.
       This algorithm provides a strict adherence to the send rate limit
       for those cases that need it.

  2. **@throttle_sync_ec** decorator and **ThrottleSyncEc** class
     provide an early arrival algorithm.

       For synchronous throttling with the early arrival algorithm, you
       specify the *requests* and *seconds* which determine the send
       rate limit. You also specify an *early_count*, the number of
       requests the throttle will send immediately without delay. Once
       the *early_count* is reached, the throttle kicks in and, if
       needed, delays the next request by a cumulative amount that
       reflects the current request and the requests that were sent
       early. This will ensure that the average send rate for all
       requests stay within the send rate limit. This algorithm is best
       used when you have a steady stream of requests within the send
       rate limit, and an occasional burst of requests that the target
       service will tolerate.

  3. **@throttle_sync_lb** decorator and **ThrottleSyncLb** class
     provide a leaky bucket algorithm.

       For synchronous throttling with the leaky bucket algorithm, you
       specify the *requests* and *seconds* which determine the send
       rate limit. You also specify an *lb_threshold* value, the number
       of requests that will fit into a conceptual bucket. As each
       request is received, if it fits, it is placed into the bucket and
       is sent. The bucket leaks at a fixed rate that reflects the send
       rate limit such that each new request will fit given it does
       not exceed the send rate limit. If the bucket becomes full, the
       next request will be delayed until the bucket has leaked enough
       to hold it, at which time it will be sent. Unlike the early count
       algorithm, the leaky bucket algorithm results in an average send
       rate that slightly exceeds the send rate limit. This algorithm is
       best used when you have a steady stream of requests within the
       send rate limit, and an occasional burst of requests that the
       target service will tolerate.

  4. **@throttle_async** decorator and **ThrottleAsync** class provide
     an asynchronous algorithm.

       With asynchronous throttling, you specify the *requests* and
       *seconds* which determine the send rate limit. As each request is
       received, it is placed on a queue and control returns to the
       caller. A separate request schedular thread pulls the requests
       from the queue and sends them at a steady interval to achieve the
       specified send rate limit. You may also specify an *async_q_size*
       that determines the number of requests that can build up on the
       queue before the caller is blocked while trying to add requests.
       This algorithm provides a strict adherence to the send rate limit
       without having to delay the user (unless the queue become full).
       This is best used when you have a steady stream of requests
       within the send rate limit, and an occasional burst of requests
       that you do not want to be delayed for. It has an added
       responsibility that you need to perform a shutdown of the
       throttle when your program ends to ensure that the request
       schedular thread is properly ended.


:Example: 1) Wrapping a function with the **@throttle_sync** decorator

Here we are using the **@throttle_sync** decorator to wrap a function
that needs to be limited to no more than 2 executions per second. In the
following code, make_request will be called 10 times in rapid
succession. The **@throttle_sync** keeps track of the time for each
invocation and will insert a wait as needed to stay within the limit.
The first execution of make_request will be done immediately while the
remaining executions will each be delayed by 1/2 second as seen in the
output messages.

>>> from scottbrian_throttle.throttle import throttle_sync
>>> import time
>>> @throttle_sync(requests=2, seconds=1)
... def make_request(request_number, time_of_start):
...     print(f'request {request_number} sent at elapsed time: '
...           f'{time.time() - time_of_start:0.1f}')
>>> start_time = time.time()
>>> for i in range(10):
...     make_request(i, start_time)
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


:Example: 2) Using the **ThrottleSync** class

Here's the same example from above, but instead of the decorator we use
the **ThrottleSync** class. Note that the loop now calls send_request,
passing in the make_request function and its arguments:

>>> from scottbrian_throttle.throttle import ThrottleSync
>>> import time
>>> def make_request(request_number, time_of_start):
...     print(f'request {request_number} sent at elapsed time: '
...           f'{time.time() - time_of_start:0.1f}')
>>> a_throttle = ThrottleSync(requests=2, seconds=1)
>>> start_time = time.time()
>>> for i in range(10):
...     a_throttle.send_request(make_request, i, start_time)
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



:Example: 3) Wrapping a function with the **@throttle_sync_ec**
  decorator

Here we continue with the same example, only this time using the
**@throttle_sync_ec** decorator to see how its algorithm in action.
We will use the same *requests* of 2 and *seconds* of 1, and an
*early_count* of 2. The make_request function will again be called 10
times in rapid succession. The **@throttle_sync_ec** will allow the
first request to proceed immediately. The next two requests are
considered early, so they will be allowed to proceed as well. The third
request will be delayed to allow the throttle to catch up to where we
should be, and then the process will repeat with some requests going
early followed by a catch-up delay. We can see this behavior in the
messages that show the intervals.

>>> from scottbrian_throttle.throttle import throttle_sync_ec
>>> import time
>>> @throttle_sync_ec(requests=2, seconds=1, early_count=2)
... def make_request(request_number, time_of_start):
...     print(f'request {request_number} sent at elapsed time: '
...           f'{time.time() - time_of_start:0.1f}')
>>> start_time = time.time()
>>> for i in range(10):
...     make_request(i, start_time)
request 0 sent at elapsed time: 0.0
request 1 sent at elapsed time: 0.0
request 2 sent at elapsed time: 0.0
request 3 sent at elapsed time: 1.5
request 4 sent at elapsed time: 1.5
request 5 sent at elapsed time: 1.5
request 6 sent at elapsed time: 3.0
request 7 sent at elapsed time: 3.0
request 8 sent at elapsed time: 3.0
request 9 sent at elapsed time: 4.5


:Example: 4) Using the **ThrottleSyncEc** class

Here we show the early count with the **ThrottleSyncEc** class:

>>> from scottbrian_throttle.throttle import ThrottleSyncEc
>>> import time
>>> def make_request(request_number, time_of_start):
...     print(f'request {request_number} sent at elapsed time: '
...           f'{time.time() - time_of_start:0.1f}')
>>> a_throttle = ThrottleSyncEc(requests=2, seconds=1, early_count=2)
>>> start_time = time.time()
>>> for i in range(10):
...     a_throttle.send_request(make_request, i, start_time)
request 0 sent at elapsed time: 0.0
request 1 sent at elapsed time: 0.0
request 2 sent at elapsed time: 0.0
request 3 sent at elapsed time: 1.5
request 4 sent at elapsed time: 1.5
request 5 sent at elapsed time: 1.5
request 6 sent at elapsed time: 3.0
request 7 sent at elapsed time: 3.0
request 8 sent at elapsed time: 3.0
request 9 sent at elapsed time: 4.5


:Example: 5) Wrapping a function with the **@throttle_sync_lb**
             decorator

We now take the early count example from above and switch in the leaky
bucket algorithm instead. We will use the *requests* of 2,  *seconds* of
1, and *lb_threshold* of 3. The make_request function will again be
called 10 times in rapid succession. The **@throttle_sync_lb** will
be able to fit the first three requests into the bucket and send them
immediately. The fourth request will not fit into the bucket which now
causes the throttle to delay to allow the bucket to leak out one of the
requests. After the delay, the fourth request is placed into the bucket
and sent, follwed immediately by the fifth and sunsequent requests, each
of which are delayed to allow the bucket to accomodate them. We can see
this behavior in the messages that show the intervals.

>>> from scottbrian_throttle.throttle import throttle_sync_lb
>>> import time
>>> @throttle_sync_lb(requests=2, seconds=1, lb_threshold=3)
... def make_request(request_number, time_of_start):
...     print(f'request {request_number} sent at elapsed time: '
...           f'{time.time() - time_of_start:0.1f}')
>>> start_time = time.time()
>>> for i in range(10):
...     make_request(i, start_time)
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


:Example: 6) Using the **ThrottleSyncLb** class

Here we show the leaky bucket example using the **ThrottleSyncLb**
class:

>>> from scottbrian_throttle.throttle import ThrottleSyncLb
>>> import time
>>> def make_request(request_number, time_of_start):
...     print(f'request {request_number} sent at elapsed time: '
...           f'{time.time() - time_of_start:0.1f}')
>>> a_throttle = ThrottleSyncLb(requests=2, seconds=1, lb_threshold=3)
>>> start_time = time.time()
>>> for i in range(10):
...     a_throttle.send_request(make_request, i, start_time)
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


:Example: 7) Wrapping a function with the **@throttle_async** decorator

We now continue with the same setup from above, only now we are using
the **@throttle_async** decorator.  We will again specify *requests* of
2 and *seconds* of 1. The make_request function will be called 10
times in rapid succession. The **@throttle_aync_lb** will queue the
requests to the request queue and the schedule_request method running
under a separate thread will dequeue and execute them at the send rate
interval determined by the requests and seconds arguments (in this case,
1/2 second). This will have similar behavior to the throttle_sync
algorithm, except that the request are executed from a separate thread.

>>> from scottbrian_throttle.throttle import throttle_async
>>> import time
>>> @throttle_async(requests=2, seconds=1)
... def make_request(request_number, time_of_start):
...     results.append(f'request {request_number} sent at elapsed time:'
...                    f' {time.time() - time_of_start:0.1f}')
>>> results = []
>>> start_time = time.time()
>>> for i in range(10):
...     _ = make_request(i, start_time)
>>> shutdown_throttle_funcs(make_request)
>>> for line in results:
...     print(line)
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


:Example: 8) Using the **ThrottleSyncAsync** class

Here we continue with the same setup, only now using the
**ThrottleSyncAsync** class:

>>> from scottbrian_throttle.throttle import ThrottleAsync
>>> import time
>>> def make_request(request_number, time_of_start):
...     results.append(f'request {request_number} sent at elapsed time:'
...                    f' {time.time() - time_of_start:0.1f}')
>>> a_throttle = ThrottleAsync(requests=2, seconds=1)
>>> results = []
>>> start_time = time.time()
>>> for i in range(10):
...     _ = a_throttle.send_request(make_request, i, start_time)
>>> _ = a_throttle.start_shutdown()
>>> for line in results:
...     print(line)
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

"""

########################################################################
# Standard Library
########################################################################
from abc import ABC, abstractmethod
import functools
import logging
import queue
import threading
import time
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
from typing_extensions import TypeAlias


########################################################################
# Third Party
########################################################################
from scottbrian_utils.pauser import Pauser
from scottbrian_utils.timer import Timer
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


class IncorrectEarlyCountSpecified(ThrottleError):
    """Throttle exception for incorrect early_count specification."""

    pass


class IncorrectLbThresholdSpecified(ThrottleError):
    """Throttle exception for incorrect lb_threshold specification."""

    pass


class IncorrectRequestsSpecified(ThrottleError):
    """Throttle exception for incorrect requests specification."""

    pass


class IncorrectSecondsSpecified(ThrottleError):
    """Throttle exception for incorrect seconds specification."""

    pass


class IncorrectShutdownTypeSpecified(ThrottleError):
    """Throttle exception for incorrect shutdown_type specification."""

    pass


class MissingEarlyCountSpecification(ThrottleError):
    """Throttle exception for missing early_count specification."""

    pass


class MissingLbThresholdSpecification(ThrottleError):
    """Throttle exception for missing lb_threshold specification."""

    pass


########################################################################
# Throttle Base class
########################################################################
class Throttle(ABC):
    """Throttle base class."""

    DEFAULT_ASYNC_Q_SIZE: Final[int] = 4096

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
        "logger",
        "pauser",
        "requests",
        "seconds",
        "sync_lock",
        "t_name",
    )

    ####################################################################
    # __init__
    ####################################################################
    def __init__(
        self, *, requests: int, seconds: IntFloat, name: Optional[str] = None
    ) -> None:
        """Initialize an instance of the Throttle class.

        Args:
            requests: The number of requests that can be made in
                        the interval specified by seconds.
            seconds: The number of seconds in which the number of
                       requests specified in requests can be made.
            name: The name used to identify the throttle in log messages
                issued by the throttle. The default name is
                the python id of the Throttle class instance.


        Raises:
            IncorrectRequestsSpecified: The *requests* specification
                must be a positive integer greater than zero.
            IncorrectSecondsSpecified: The *seconds* specification must
                be a positive int or float greater than zero.


        """
        ################################################################
        # requests
        ################################################################
        if isinstance(requests, int) and (0 < requests):
            self.requests = requests
        else:
            raise IncorrectRequestsSpecified(
                "The requests "
                "specification must be a "
                "positive integer greater "
                "than zero."
            )

        ################################################################
        # seconds
        ################################################################
        if isinstance(seconds, (int, float)) and (0 < seconds):
            self.seconds = seconds  # timedelta(seconds=seconds)
        else:
            raise IncorrectSecondsSpecified(
                "The seconds specification "
                "must be an integer or "
                "float greater than zero."
            )

        if name is None:
            self.t_name = str(id(self))
        else:
            self.t_name = name
        ################################################################
        # Set remainder of vars
        ################################################################
        self._target_interval = seconds / requests
        self._target_interval_ns: float = self._target_interval * Throttle.SECS_2_NS
        self.sync_lock = threading.Lock()
        self._arrival_time = 0.0
        self._next_target_time: float = time.perf_counter_ns()
        self.logger = logging.getLogger(__name__)
        self.pauser = Pauser()

    ####################################################################
    # send_request
    ####################################################################
    @abstractmethod
    def send_request(self, func: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
        """Send the request.

        Args:
            func: the request function to be run
            args: the request function positional arguments
            kwargs: the request function keyword arguments

        Returns:
              The return code from the request function (may be None)

        Raises:
            Exception: An exception occurred in the request target. It
                will be logged and re-raised.

        """
        pass

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
        """Calculate number of completed requests that completed.

        Args:
            interval: number of elapsed seconds that requests were being
              processed

        Returns:
            The estimated number of requests that were processed during
            the given interval

        """
        return int(interval / self._target_interval) + 1


########################################################################
# Throttle Base class
########################################################################
class ThrottleSync(Throttle):
    """Throttle class for sync mode."""

    ####################################################################
    # __init__
    ####################################################################
    def __init__(
        self, *, requests: int, seconds: IntFloat, name: Optional[str] = None
    ) -> None:
        """Initialize an instance of the Throttle class.

        Args:
            requests: The number of requests that can be made in
                        the interval specified by seconds.
            seconds: The number of seconds in which the number of
                       requests specified in requests can be made.
            name: The name used to identify the throttle in log messages
                issued by the throttle. The default name is
                the python id of the Throttle class instance.

        """
        super().__init__(requests=requests, seconds=seconds, name=name)

    ####################################################################
    # repr
    ####################################################################
    def __repr__(self) -> str:
        """Return a representation of the class.

        Returns:
            The representation as how the class is instantiated

        :Example: instantiate a throttle for 1 requests every 2 seconds

         >>> from scottbrian_throttle.throttle import Throttle
        >>> request_throttle = ThrottleSync(requests=1,
        ...                                 seconds=2)
        >>> repr(request_throttle)
        'ThrottleSync(requests=1, seconds=2.0)'

        """
        if TYPE_CHECKING:
            __class__: Type[ThrottleSync]  # noqa: F842
        classname = self.__class__.__name__
        parms = f"requests={self.requests}, " f"seconds={float(self.seconds)}"

        return f"{classname}({parms})"

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
              The return code from the request function (may be None)

        Raises:
            Exception: An exception occurred in the request target. It
                will be logged and re-raised.

        """
        ################################################################
        # SYNC_MODE
        ################################################################
        ################################################################
        # The SYNC_MODE Throttle algorithm works as follows:
        # 1) during throttle instantiation:
        #    a) a target interval is calculated as seconds/requests.
        #       For example, with a specification of 4 requests per 1
        #       second, the target interval will be 0.25 seconds.
        #    b) _next_target_time is set to a current time reference via
        #       time.perf_counter_ns
        # 2) as each request arrives, it is checked against the
        #    _next_target_time and:
        #    a) if it arrived at or after _next_target_time, it is
        #       allowed to proceed without delay
        #    b) if it arrived before the _next_target_time the request
        #       is delayed until _next_target_time is reached
        # 3) _next_target_time is increased by the target_interval
        #
        ################################################################
        with self.sync_lock:
            # set the time that this request is being made
            self._arrival_time = time.perf_counter_ns()

            if self._arrival_time < self._next_target_time:
                wait_time = (
                    self._next_target_time - self._arrival_time
                ) * Throttle.NS_2_SECS
                self.pauser.pause(wait_time)

            ############################################################
            # Update the expected arrival time for the next request by
            # adding the request interval to our current time or the
            # next arrival time, whichever is later. Note that we update
            # the target time before we send the request which means we
            # face a possible scenario where we send a request that gets
            # delayed en route to the service, but out next request
            # arrives at the updated expected arrival time and is sent
            # out immediately, but it now arrives early relative to the
            # previous request, as observed by the service. If we update
            # the target time after sending the request we avoid that
            # scenario, but we would then be adding in the request
            # processing time to the throttle delay with the undesirable
            # effect that all requests will now be throttled more than
            # they need to be.
            ############################################################
            self._next_target_time = time.perf_counter_ns() + self._target_interval_ns

            ############################################################
            # Call the request function and return with the request
            # return value. We use try/except to log and re-raise any
            # unhandled errors.
            ############################################################
            try:
                return func(*args, **kwargs)
            except Exception as e:
                self.logger.debug(
                    f"throttle {self.t_name} send_request unhandled exception in "
                    f"request: {e}"
                )
                raise


########################################################################
# Throttle class
########################################################################
class ThrottleSyncEc(ThrottleSync):
    """Throttle class with early count algo."""

    __slots__ = ("_early_arrival_count", "early_count")

    ####################################################################
    # __init__
    ####################################################################
    def __init__(
        self,
        *,
        requests: int,
        seconds: IntFloat,
        name: Optional[str] = None,
        early_count: int,
    ) -> None:
        """Initialize an instance of the early count Throttle class.

        Args:
            requests: The number of requests that can be made in
                        the interval specified by seconds.
            seconds: The number of seconds in which the number of
                       requests specified in requests can be made.
            name: The name used to identify the throttle in log messages
                issued by the throttle. The default name is
                the python id of the Throttle class instance.
            early_count: Specifies the number of requests that are
                           allowed to proceed immediately without delay.
                           Note that a specification of 0 for the
                           *early_count* will result in the same
                           behavior as the ThrottleSync class.

        Raises:
            IncorrectEarlyCountSpecified: *early_count* must be an
                integer greater than zero.

        """
        ################################################################
        # early_count
        ################################################################
        super().__init__(requests=requests, seconds=seconds, name=name)

        if isinstance(early_count, int) and (0 < early_count):
            self.early_count = early_count
        else:
            raise IncorrectEarlyCountSpecified(
                "early_count must be " "an integer greater" "than zero."
            )

        ################################################################
        # Set remainder of vars
        ################################################################
        self._early_arrival_count = 0

    ####################################################################
    # repr
    ####################################################################
    def __repr__(self) -> str:
        """Return a representation of the class.

        Returns:
            The representation as how the class is instantiated

        :Example: instantiate a throttle for 2 requests per second

         >>> from scottbrian_throttle.throttle import Throttle
        >>> request_throttle = ThrottleSyncEc(requests=2,
        ...                                   seconds=1,
        ...                                   early_count=3)
        >>> repr(request_throttle)
        'ThrottleSyncEc(requests=2, seconds=1.0, early_count=3)'


        .. # noqa: W505, E501

        """
        if TYPE_CHECKING:
            __class__: Type[ThrottleSyncEc]  # noqa: F842
        classname = self.__class__.__name__
        parms = (
            f"requests={self.requests}, "
            f"seconds={float(self.seconds)}, "
            f"early_count={self.early_count}"
        )

        return f"{classname}({parms})"

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
              The return code from the request function (may be None)


        Raises:
            Exception: An exception occurred in the request target. It
                will be logged and re-raised.

        """
        ################################################################
        # SYNC_MODE_EC
        ################################################################
        ################################################################
        # The ThrottleSyncEc algorithm works as follows:
        # 1) during throttle instantiation:
        #    a) a target interval is calculated as seconds/requests.
        #       For example, with a specification of 4 requests per 1
        #       second, the target interval will be 0.25 seconds.
        #    b) _next_target_time is set to a current time reference via
        #       time.perf_counter_ns
        #    c) the specified early_count is saved
        #    d) _early_arrival_count is set to zero
        # 2) as each request arrives, it is checked against the
        #    _next_target_time and:
        #    a) if it arrived at or after _next_target_time, it is
        #       allowed to proceed without delay and the
        #       _early_arrival_count is reset
        #    b) if it arrived before the _next_target_time, the
        #       _early_arrival_count is increased by 1 and:
        #       1) if _early_arrival_count is less than or equal to
        #          early_count, the request is allowed to proceed
        #          without delay
        #       2) if _early_arrival_count is greater than early_count,
        #          _early_arrival_count is reset and the request is
        #          delayed until _next_target_time is reached
        # 3) _next_target_time is increased by the target_interval
        #
        # Note that as each request is sent, the _next_target_time is
        # increased. This means that once the early count is exhausted,
        # the next request will be delayed for the sum of target
        # intervals of the requests that were sent without delay. This
        # allows short bursts of requests to go immediately while also
        # ensuring that the average interval not less than is the
        # target interval.
        ################################################################
        with self.sync_lock:
            # set the time that this request is being made
            self._arrival_time = time.perf_counter_ns()

            if self._next_target_time <= self._arrival_time:
                self._early_arrival_count = 0
            else:
                self._early_arrival_count += 1
                if self.early_count < self._early_arrival_count:
                    self._early_arrival_count = 0  # reset the count

                    wait_time = (
                        self._next_target_time - self._arrival_time
                    ) * Throttle.NS_2_SECS

                    self.pauser.pause(wait_time)

            ############################################################
            # Update the expected arrival time for the next request by
            # adding the request interval to our current time or the
            # next arrival time, whichever is later. Note that we update
            # the target time before we send the request which means we
            # face a possible scenario where we send a request that gets
            # delayed en route to the service, but out next request
            # arrives at the updated expected arrival time and is sent
            # out immediately, but it now arrives early relative to the
            # previous request, as observed by the service. If we update
            # the target time after sending the request we avoid that
            # scenario, but we would then be adding in the request
            # processing time to the throttle delay with the undesirable
            # effect that all requests will now be throttled more than
            # they need to be.
            ############################################################
            self._next_target_time = (
                max(float(time.perf_counter_ns()), self._next_target_time)
                + self._target_interval_ns
            )

            ############################################################
            # Call the request function and return with the request
            # return value. We use try/except to log and re-raise any
            # unhandled errors.
            ############################################################
            try:
                return func(*args, **kwargs)
            except Exception as e:
                self.logger.debug(
                    f"throttle {self.t_name} send_request unhandled exception in "
                    f"request: {e}"
                )
                raise


########################################################################
# Throttle class
########################################################################
class ThrottleSyncLb(ThrottleSync):
    """Throttle class with leaky bucket algo."""

    __slots__ = (
        "_next_target_time",
        "lb_adjustment",
        "lb_adjustment_ns",
        "lb_threshold",
        "_wait_time",
        "_before_next_target_time",
        "_entry_bucket_amt",
        "_exit_bucket_amt",
    )

    ####################################################################
    # __init__
    ####################################################################
    def __init__(
        self,
        *,
        requests: int,
        seconds: IntFloat,
        name: Optional[str] = None,
        lb_threshold: IntFloat,
    ) -> None:
        """Initialize an instance of the leaky bucket Throttle class.

        Args:
            requests: The number of requests that can be made in
                        the interval specified by seconds.
            seconds: The number of seconds in which the number of
                       requests specified in requests can be made.
            name: The name used to identify the throttle in log messages
                issued by the throttle. The default name is
                the python id of the Throttle class instance.
            lb_threshold: Specifies the threshold for the leaky bucket.
                            This is the number of requests that can be
                            in the bucket such that the next request is
                            allowed to proceed without delay. That
                            request is added to the bucket, and then the
                            bucket leaks out the requests. When the next
                            request arrives, it will be delayed by
                            whatever amount of time is needed for the
                            bucket to have leaked enough to be at the
                            threshold. A specification of zero for the
                            lb_threshold will effectively cause all
                            requests that are early to be delayed.

        Raises:
            IncorrectLbThresholdSpecified: *lb_threshold* must be an
                integer or float greater than zero.

        """
        ################################################################
        # lb_threshold
        ################################################################
        super().__init__(requests=requests, seconds=seconds, name=name)

        if isinstance(lb_threshold, (int, float)) and (0 < lb_threshold):
            self.lb_threshold = float(lb_threshold)
        else:
            raise IncorrectLbThresholdSpecified(
                "lb_threshold must be an integer or float greater than " "zero."
            )

        ################################################################
        # Set remainder of vars
        ################################################################
        self.lb_adjustment: float = max(
            0.0, (self._target_interval * self.lb_threshold) - self._target_interval
        )
        self.lb_adjustment_ns: float = self.lb_adjustment * Throttle.SECS_2_NS

        # adjust _next_target_time for lb algo
        self._next_target_time = time.perf_counter_ns() - self.lb_adjustment_ns

        self._wait_time: float = 0.0

        self._before_next_target_time: float = 0.0
        self._entry_bucket_amt: float = 0.0
        self._exit_bucket_amt: float = 0.0

    ####################################################################
    # repr
    ####################################################################
    def __repr__(self) -> str:
        """Return a representation of the class.

        Returns:
            The representation as how the class is instantiated

        :Example: instantiate a throttle for 20 requests per 1/2 minute

        >>> from scottbrian_throttle.throttle import Throttle
        >>> request_throttle = ThrottleSyncLb(requests=20,
        ...                                   seconds=30,
        ...                                   lb_threshold=4)
        >>> repr(request_throttle)
        'ThrottleSyncLb(requests=20, seconds=30.0, lb_threshold=4.0)'


        .. # noqa: W505, E501

        """
        if TYPE_CHECKING:
            __class__: Type[ThrottleSyncLb]  # noqa: F842
        classname = self.__class__.__name__
        parms = (
            f"requests={self.requests}, "
            f"seconds={float(self.seconds)}, "
            f"lb_threshold={self.lb_threshold}"
        )

        return f"{classname}({parms})"

    ####################################################################
    # MODE_SYNC_LB send_request
    ####################################################################
    def send_request(self, func: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
        """Send the request.

        Args:
            func: the request function to be run
            args: the request function positional arguments
            kwargs: the request function keyword arguments

        Returns:
              The return value from the request function (perhaps None)

        Raises:
            Exception: An exception occurred in the request target. It
                will be logged and re-raised.

        """
        ################################################################
        # Leaky Bucket
        ################################################################
        with self.sync_lock:
            # set the time that this request is being made
            self._arrival_time = time.perf_counter_ns()
            ############################################################
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
            # and request will get delayed to allow the target time
            # to catch up.
            ############################################################
            self._wait_time = 0.0
            self._before_next_target_time = self._next_target_time

            # full_bucket_ns = (
            #     self._target_interval * self.lb_threshold
            # ) * Throttle.SECS_2_NS
            # self._entry_bucket_amt = max(
            #     0.0, (self._next_target_time - self._arrival_time) * Throttle.NS_2_SECS
            # )
            #
            # if self._arrival_time < self._next_target_time:
            #     wait_time = 0.0
            #     if (
            #         self._next_target_time - self._arrival_time
            #         >= full_bucket_ns - self._target_interval_ns
            #     ):
            #         wait_time = (
            #             self._next_target_time
            #             - self._arrival_time
            #             - (full_bucket_ns - self._target_interval_ns)
            #         ) * Throttle.NS_2_SECS
            #         self._wait_time = wait_time
            #         self.pauser.pause(wait_time)
            #     self._next_target_time += (
            #         self._target_interval_ns - wait_time * Throttle.SECS_2_NS
            #     )
            # else:
            #     self._next_target_time = self._arrival_time + self._target_interval_ns
            #
            # self._exit_bucket_amt = max(
            #     0.0, (self._next_target_time - self._arrival_time) * Throttle.NS_2_SECS
            # )

            self._entry_bucket_amt = max(
                0.0, (self._next_target_time - self._arrival_time) * Throttle.NS_2_SECS
            )

            ############################################################
            # good code
            ############################################################
            # if self._next_target_time <= self._arrival_time:
            #     # bucket is empty
            #     self._next_target_time = self._arrival_time + self._target_interval_ns
            # elif self._next_target_time - self._arrival_time < self.lb_adjustment_ns:
            #     # bucket has room for another send
            #     self._next_target_time += self._target_interval_ns
            # else:
            #     # we need to wait to drain the bucket some more
            #     wait_time = (
            #         self._next_target_time - self._arrival_time - self.lb_adjustment_ns
            #     )
            #     self._wait_time = wait_time * Throttle.NS_2_SECS
            #     self.pauser.pause(wait_time * Throttle.NS_2_SECS)
            #
            #     self._next_target_time += self._target_interval_ns - wait_time
            #
            # self._exit_bucket_amt = max(
            #     0.0, (self._next_target_time - self._arrival_time) * Throttle.NS_2_SECS
            # )

            ############################################################
            # try 2:
            ############################################################
            if self._arrival_time < self._next_target_time:
                wait_time = self._next_target_time - self._arrival_time
                self._wait_time = wait_time * Throttle.NS_2_SECS
                self.pauser.pause(wait_time * Throttle.NS_2_SECS)
                self._next_target_time = (
                    self._arrival_time + self._wait_time + self._target_interval_ns
                )
            else:
                if (
                    self._arrival_time - self._next_target_time
                    >= self.lb_adjustment_ns + self._target_interval_ns
                ):
                    self._next_target_time = self._arrival_time - self.lb_adjustment_ns
                else:
                    self._next_target_time += self._target_interval_ns

            ############################################################
            # Update the expected arrival time for the next request by
            # adding the request interval to our current time or the
            # next arrival time, whichever is later. Note that we update
            # the target time before we send the request which means we
            # face a possible scenario where we send a request that gets
            # delayed en route to the service, but out next request
            # arrives at the updated expected arrival time and is sent
            # out immediately, but it now arrives early relative to the
            # previous request, as observed by the service. If we update
            # the target time after sending the request we avoid that
            # scenario, but we would then be adding in the request
            # processing time to the throttle delay with the undesirable
            # effect that all requests will now be throttled more than
            # they need to be.
            ############################################################
            # if self._arrival_time < self._next_target_time:
            #     wait_time = (
            #         self._next_target_time - self._arrival_time
            #     ) * Throttle.NS_2_SECS
            #     self._wait_time = wait_time
            #     self.pauser.pause(wait_time)

            ############################################################
            # Update the expected arrival time for the next request by
            # adding the request interval to our current time or the
            # next arrival time, whichever is later. Note that we update
            # the target time before we send the request which means we
            # face a possible scenario where we send a request that gets
            # delayed en route to the service, but out next request
            # arrives at the updated expected arrival time and is sent
            # out immediately, but it now arrives early relative to the
            # previous request, as observed by the service. If we update
            # the target time after sending the request we avoid that
            # scenario, but we would then be adding in the request
            # processing time to the throttle delay with the undesirable
            # effect that all requests will now be throttled more than
            # they need to be.
            ############################################################
            # self._next_target_time = (
            #     max(
            #         float(time.perf_counter_ns()),
            #         self._next_target_time + self.lb_adjustment_ns,
            #     )
            #     - self.lb_adjustment_ns
            #     + self._target_interval_ns
            # )

            self._exit_bucket_amt = max(
                0.0, (self._next_target_time - self._arrival_time) * Throttle.NS_2_SECS
            )
            ############################################################
            # Call the request function and return with the request
            # return value. We use try/except to log and re-raise any
            # unhandled errors.
            ############################################################
            try:
                return func(*args, **kwargs)
            except Exception as e:
                self.logger.debug(
                    f"throttle {self.t_name} send_request unhandled exception in "
                    f"request: {e}"
                )
                raise


########################################################################
# Throttle class
########################################################################
class ThrottleAsync(Throttle):
    """An asynchronous throttle mechanism."""

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

    __slots__ = (
        "_check_async_q_time",
        "_check_async_q_time2",
        "_throttle_shutdown_started",
        "async_q",
        "async_q_size",
        "request_scheduler_thread",
        "shutdown_elapsed_time",
        "shutdown_lock",
        "shutdown_start_time",
        "throttle_state",
    )

    ####################################################################
    # __init__
    ####################################################################
    def __init__(
        self,
        *,
        requests: int,
        seconds: IntFloat,
        name: Optional[str] = None,
        async_q_size: Optional[int] = None,
    ) -> None:
        """Initialize an instance of the ThrottleAsync class.

        Args:
            requests: The number of requests that can be made in
                        the interval specified by seconds.
            seconds: The number of seconds in which the number of
                       requests specified in requests can be made.
            name: The name used to identify the throttle in log messages
                issued by the throttle. The default name is
                the python id of the Throttle class instance.
            async_q_size: Specifies the size of the request
                            queue for async requests. When the request
                            queue is totally populated, any additional
                            calls to send_request will be delayed
                            until queued requests are removed and
                            scheduled. The default is 4096 requests.

        Raises:
            IncorrectAsyncQSizeSpecified: *async_q_size* must be an
                integer greater than zero.

        """
        ################################################################
        # States and processing for ThrottleAsync:
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
        ################################################################
        # async_q_size
        ################################################################
        super().__init__(requests=requests, seconds=seconds, name=name)
        if async_q_size is not None:
            if isinstance(async_q_size, int) and (0 < async_q_size):
                self.async_q_size = async_q_size
            else:
                raise IncorrectAsyncQSizeSpecified(
                    "async_q_size must be an integer greater than zero."
                )
        else:
            self.async_q_size = Throttle.DEFAULT_ASYNC_Q_SIZE

        ################################################################
        # Set remainder of vars
        ################################################################
        self.shutdown_lock = threading.Lock()
        self._throttle_shutdown_started = False
        self.throttle_state = ThrottleAsync._ACTIVE
        self._check_async_q_time = 0.0
        self._check_async_q_time2 = 0.0
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
    # len
    ####################################################################
    def __len__(self) -> int:
        """Return the number of items in the async_q.

        Returns:
            The number of entries in the async_q as an integer

        The calls to the send_request add request items to the async_q.
        The request items are eventually removed and scheduled. The len
        of Throttle is the number of request items on the async_q when
        the len function is called. Note that the returned queue size is
        the approximate size as described in the documentation for the
        python threading queue.

        :Example: instantiate a throttle for 1 request per second

        >>> from scottbrian_throttle.throttle import Throttle
        >>> import time
        >>> def my_request():
        ...     pass
        >>> request_throttle = ThrottleAsync(requests=1,
        ...                                  seconds=1)
        >>> for i in range(3):  # quickly queue up 3 items
        ...     _ = request_throttle.send_request(my_request)
        >>> time.sleep(0.5)  # allow first request to be dequeued
        >>> print(len(request_throttle))
        2

        >>> request_throttle.start_shutdown()

        """
        return self.async_q.qsize()

    ####################################################################
    # repr
    ####################################################################
    def __repr__(self) -> str:
        """Return a representation of the class.

        Returns:
            The representation as how the class is instantiated

        :Example: instantiate a throttle for 20 requests per 1/2 minute

         >>> from scottbrian_throttle.throttle import Throttle
        >>> request_throttle = ThrottleAsync(requests=30,
        ...                                  seconds=30)
        ...
        >>> repr(request_throttle)
        'ThrottleAsync(requests=30, seconds=30.0, async_q_size=4096)'

        >>> request_throttle.start_shutdown()

        """
        if TYPE_CHECKING:
            __class__: Type[ThrottleAsync]  # noqa: F842
        classname = self.__class__.__name__
        parms = (
            f"requests={self.requests}, "
            f"seconds={float(self.seconds)}, "
            f"async_q_size={self.async_q_size}"
        )

        return f"{classname}({parms})"

    ####################################################################
    # ASYNC_MODE send_request
    ####################################################################
    def send_request(self, func: Callable[..., Any], *args: Any, **kwargs: Any) -> int:
        """Send the request.

        Args:
            func: the request function to be run
            args: the request function positional arguments
            kwargs: the request function keyword arguments

        Returns:
            * ``Throttle.RC_OK`` (0) request scheduled
            * ``Throttle.RC_THROTTLE_IS_SHUTDOWN`` (4) - the request was
              rejected because the throttle was shut down.

        """
        # if self.throttle_state != ThrottleAsync._ACTIVE:
        #     return Throttle.RC_THROTTLE_IS_SHUTDOWN

        # TODO: use se_lock
        # We obtain the shutdown lock to protect against the following
        # scenario:
        # 1) send_request is entered for async mode and sees at
        # the while statement that we are *not* in shutdown
        # 2) send_request proceeds to the try statement just
        # before the request will be queued to the async_q
        # 2) shutdown is requested and is detected by
        # schedule_requests
        # 3) schedule_requests cleans up the async_q end exits
        # 4) back here in send_request, we put our request on the
        # async_q - this request will never be processed
        with self.shutdown_lock:
            request_item = Throttle.Request(func, args, kwargs, time.perf_counter_ns())
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
        # either processed (ThrottleAsync.TYPE_SHUTDOWN_SOFT) or dropped
        # (ThrottleAsync.TYPE_SHUTDOWN_HARD). Note that async_q.get will
        # only wait for a second to allow us to detect shutdown in a
        # timely fashion.
        while True:
            # obtained_nowait = False
            # try:
            #     self._check_async_q_time = time.perf_counter_ns()
            #
            #     request_item = self.async_q.get_nowait()
            #     self._next_target_time = (time.perf_counter_ns()
            #                               + self._target_interval_ns)
            #     obtained_nowait = True
            # except queue.Empty:
            try:
                # self._check_async_q_time2 = time.perf_counter_ns()

                request_item = self.async_q.get(block=True, timeout=1)

                self._next_target_time = (
                    time.perf_counter_ns() + self._target_interval_ns
                )
            except queue.Empty:
                if self.throttle_state != ThrottleAsync._ACTIVE:
                    return
                continue  # no need to wait since we already did
            ############################################################
            # Call the request function.
            # We use try/except to log and re-raise any unhandled
            # errors.
            ############################################################
            try:
                if self.throttle_state != ThrottleAsync._HARD_SHUTDOWN_STARTED:
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
            while True:
                # handle shutdown
                if self.throttle_state != ThrottleAsync._ACTIVE:
                    if self.async_q.empty():
                        return  # we are done with shutdown
                    if self.throttle_state == ThrottleAsync._HARD_SHUTDOWN_STARTED:
                        break  # don't sleep for hard shutdown

                # Use min to ensure we don't sleep too long and appear
                # slow to respond to a shutdown request
                sleep_seconds = (
                    self._next_target_time - time.perf_counter_ns()
                ) * Throttle.NS_2_SECS
                if sleep_seconds > 0:  # if still time to go
                    self.pauser.pause(min(1.0, sleep_seconds))
                    # time_trace, stop_time = self.pauser.pause(min(1.0,
                    #                                         sleep_seconds))
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
                       (ThrottleAsync.TYPE_SHUTDOWN_SOFT),
                       the default, stops any additional
                       requests from being queued and cleans up
                       the request queue by scheduling any
                       remaining requests at the normal interval
                       as calculated by the *seconds* and
                       *requests* arguments specified during
                       throttle instantiation.
                     * A hard shutdown
                       (ThrottleAsync.TYPE_SHUTDOWN_HARD) stops
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
            ThrottleAsync.TYPE_SHUTDOWN_SOFT or
            ThrottleAsync.TYPE_SHUTDOWN_HARD

        """
        if shutdown_type not in (
            ThrottleAsync.TYPE_SHUTDOWN_SOFT,
            ThrottleAsync.TYPE_SHUTDOWN_HARD,
        ):
            raise IncorrectShutdownTypeSpecified(
                "For start_shutdown, shutdownType must be specified as "
                "either ThrottleAsync.TYPE_SHUTDOWN_SOFT or "
                "ThrottleAsync.TYPE_SHUTDOWN_HARD"
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

            if self.throttle_state == ThrottleAsync._ACTIVE:
                # We will set the start time only when the first
                # shutdown request is made. More than one shutdown
                # request can be made. Whichever request first detects
                # the completion of the shutdown will calculate the
                # elapsed time.
                self.shutdown_start_time = time.time()

                if shutdown_type == ThrottleAsync.TYPE_SHUTDOWN_SOFT:
                    self.throttle_state = ThrottleAsync._SOFT_SHUTDOWN_STARTED
                else:
                    self.throttle_state = ThrottleAsync._HARD_SHUTDOWN_STARTED
            else:  # shutdown already started or has already completed
                # if currently processing a soft shutdown and a hard
                # shutdown is now being requested, we need to shift to a
                # hard shutdown
                if (
                    self.throttle_state == ThrottleAsync._SOFT_SHUTDOWN_STARTED
                    and shutdown_type == ThrottleAsync.TYPE_SHUTDOWN_HARD
                ):
                    self.throttle_state = ThrottleAsync._HARD_SHUTDOWN_STARTED

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
                return ThrottleAsync.RC_SHUTDOWN_TIMED_OUT

            # if here, throttle is shutdown
            completion_log_msg_needed = False
            if self.throttle_state == ThrottleAsync._SOFT_SHUTDOWN_STARTED:
                self.throttle_state = ThrottleAsync._SOFT_SHUTDOWN_COMPLETED
                completion_log_msg_needed = True
            elif self.throttle_state == ThrottleAsync._HARD_SHUTDOWN_STARTED:
                self.throttle_state = ThrottleAsync._HARD_SHUTDOWN_COMPLETED
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

            if self.throttle_state == ThrottleAsync._SOFT_SHUTDOWN_COMPLETED:
                return ThrottleAsync.RC_SHUTDOWN_SOFT_COMPLETED_OK
            else:
                return ThrottleAsync.RC_SHUTDOWN_HARD_COMPLETED_OK


########################################################################
# Pie Throttle Decorator
########################################################################
F = TypeVar("F", bound=Callable[..., Any])


########################################################################
# FuncWithThrottleSyncAttr class
########################################################################
class FuncWithThrottleSyncAttr(Protocol[F]):
    """Class to allow type checking on function with attribute."""

    throttle: ThrottleSync
    __call__: F


def add_throttle_sync_attr(func: F) -> FuncWithThrottleSyncAttr[F]:
    """Wrapper to add throttle attribute to function.

    Args:
        func: function that has the attribute added

    Returns:
        input function with throttle attached as attribute

    """
    return cast(FuncWithThrottleSyncAttr[F], func)


########################################################################
# FuncWithThrottleSyncEcAttr class
########################################################################
class FuncWithThrottleSyncEcAttr(Protocol[F]):
    """Class to allow type checking on function with attribute."""

    throttle: ThrottleSyncEc
    __call__: F


def add_throttle_sync_ec_attr(func: F) -> FuncWithThrottleSyncEcAttr[F]:
    """Wrapper to add throttle attribute to function.

    Args:
        func: function that has the attribute added

    Returns:
        input function with throttle attached as attribute

    """
    return cast(FuncWithThrottleSyncEcAttr[F], func)


########################################################################
# FuncWithThrottleSyncLbAttr class
########################################################################
class FuncWithThrottleSyncLbAttr(Protocol[F]):
    """Class to allow type checking on function with attribute."""

    throttle: ThrottleSyncLb
    __call__: F


def add_throttle_sync_lb_attr(func: F) -> FuncWithThrottleSyncLbAttr[F]:
    """Wrapper to add throttle attribute to function.

    Args:
        func: function that has the attribute added

    Returns:
        input function with throttle attached as attribute

    """
    return cast(FuncWithThrottleSyncLbAttr[F], func)


########################################################################
# FuncWithThrottleAsyncAttr class
########################################################################
class FuncWithThrottleAsyncAttr(Protocol[F]):
    """Class to allow type checking on function with attribute."""

    throttle: ThrottleAsync
    __call__: F


def add_throttle_async_attr(func: F) -> FuncWithThrottleAsyncAttr[F]:
    """Wrapper to add throttle attribute to function.

    Args:
        func: function that has the attribute added

    Returns:
        input function with throttle attached as attribute

    """
    return cast(FuncWithThrottleAsyncAttr[F], func)


########################################################################
# @throttle_sync
########################################################################
@overload
def throttle_sync(
    wrapped: F, *, requests: int, seconds: IntFloat, name: Optional[str] = None
) -> FuncWithThrottleSyncAttr[F]:
    pass


@overload
def throttle_sync(
    *, requests: int, seconds: IntFloat, name: Optional[str] = None
) -> Callable[[F], FuncWithThrottleSyncAttr[F]]:
    pass


def throttle_sync(
    wrapped: Optional[F] = None,
    *,
    requests: int,
    seconds: Any,
    name: Optional[str] = None,
) -> Union[F, FuncWithThrottleSyncAttr[F]]:
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
        requests: The number of requests that can be made in
                    the interval specified by seconds.
        name: The name used to identify the throttle in log messages
                issued by the throttle. The default name is
                the name of the function being wrapped by the
                throttle_async decorator.
        seconds: The number of seconds in which the number of requests
                   specified in requests can be made.

    Returns:
        A callable function that delays the request as needed in
        accordance with the specified limits.

    :Example: wrap a function with an sync throttle for 1 request
                  per second

    >>> from scottbrian_throttle.throttle import Throttle
    >>> @throttle_sync(requests=1, seconds=1)
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
    #         @throttle(requests=1, seconds=1)
    #         def aFunc():
    #             print('42')
    #
    #     This is what essentially happens under the covers:
    #         def aFunc():
    #             print('42')
    #         aFunc = throttle(requests=1,
    #                          seconds=1)(aFunc)
    #
    #     The call to throttle results in a function being returned that
    #     takes as its first argument the aFunc specification that we
    #     see in parens immediately following the throttle call.
    #
    #     Note that we can also code the above as shown and get the same
    #     result.
    #
    #     Also, we can code the following and get the same result:
    #         def aFunc():
    #             print('42')
    #         aFunc = throttle(aFunc,
    #                          requests=1,
    #                          seconds=1)
    #
    #     What happens is throttle gets control and tests whether aFunc
    #     was specified, and if not returns a call to functools.partial
    #     which is the function that accepts the aFunc
    #     specification and then calls throttle with aFunc as the first
    #     argument with the other args for requests and seconds).
    #
    #     One other complication is that we are also using the
    #     wrapt.decorator for the inner wrapper function which does some
    #     more smoke and mirrors to ensure introspection will work as
    #     expected.
    # ==================================================================

    if wrapped is None:
        return cast(
            FuncWithThrottleSyncAttr[F],
            functools.partial(
                throttle_sync, requests=requests, seconds=seconds, name=name
            ),
        )

    if name is None:
        name = wrapped.__name__
    a_throttle_sync = ThrottleSync(requests=requests, seconds=seconds, name=name)

    @decorator  # type: ignore
    def wrapper(
        func_to_wrap: F,
        instance: Optional[Any],
        args: tuple[Any, ...],
        kwargs2: dict[str, Any],
    ) -> Any:

        return a_throttle_sync.send_request(func_to_wrap, *args, **kwargs2)

    wrapper = wrapper(wrapped)

    wrapper = add_throttle_sync_attr(wrapper)
    wrapper.throttle = a_throttle_sync

    return cast(FuncWithThrottleSyncAttr[F], wrapper)


########################################################################
# @throttle_sync_ec
########################################################################
@overload
def throttle_sync_ec(
    wrapped: F,
    *,
    requests: int,
    seconds: IntFloat,
    name: Optional[str] = None,
    early_count: int,
) -> FuncWithThrottleSyncEcAttr[F]:
    pass


@overload
def throttle_sync_ec(
    *, requests: int, seconds: IntFloat, name: Optional[str] = None, early_count: int
) -> Callable[[F], FuncWithThrottleSyncEcAttr[F]]:
    pass


def throttle_sync_ec(
    wrapped: Optional[F] = None,
    *,
    requests: int,
    seconds: Any,  # : IntFloat,
    name: Optional[str] = None,
    early_count: int,
) -> Union[F, FuncWithThrottleSyncEcAttr[F]]:
    """Decorator to wrap a function in a sync ec throttle.

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
        requests: The number of requests that can be made in
                    the interval specified by seconds.
        seconds: The number of seconds in which the number of requests
                   specified in requests can be made.
        name: The name used to identify the throttle in log messages
                issued by the throttle. The default name is
                the name of the function being wrapped by the
                throttle_async decorator.
        early_count: Specifies the number of requests that are allowed
                       to proceed that arrive earlier than the
                       allowed interval. The count of early requests
                       is incremented, and when it exceeds the
                       early_count, the request will be delayed to
                       align it with its expected arrival time. Any
                       request that arrives at or beyond the
                       allowed interval will cause the count to be
                       reset (included the request that was delayed
                       since it will now be sent at the allowed
                       interval). A specification of zero for the
                       *early_count* will effectively cause all requests
                       that are early to be delayed.

    Returns:
        A callable function that delays the request as needed in
        accordance with the specified limits.


    :Example: wrap a function with a throttle for 20 requests per 2
              minutes using the early count algo

    >>> from scottbrian_throttle.throttle import Throttle
    >>> @throttle_sync_ec(requests=5,
    ...                   seconds=120,
    ...                   early_count=3)
    ... def f3(b=3) -> int:
    ...     print(f'example 3 request function with arg {b}')
    ...     return b * 5


    """
    # ==================================================================
    #  The following code covers cases where throttle is used with or
    #  without the pie character, where the decorated function has or
    #  does not have parameters.
    #
    #     Here's an example of throttle with a function that has no
    #         args:
    #         @throttle(requests=1, seconds=1)
    #         def aFunc():
    #             print('42')
    #
    #     This is what essentially happens under the covers:
    #         def aFunc():
    #             print('42')
    #         aFunc = throttle(requests=1,
    #                          seconds=1)(aFunc)
    #
    #     The call to throttle results in a function being returned that
    #     takes as its first argument the aFunc specification that we
    #     see in parens immediately following the throttle call.
    #
    #     Note that we can also code the above as shown and get the same
    #     result.
    #
    #     Also, we can code the following and get the same result:
    #         def aFunc():
    #             print('42')
    #         aFunc = throttle(aFunc,
    #                          requests=1,
    #                          seconds=1)
    #
    #     What happens is throttle gets control and tests whether aFunc
    #     was specified, and if not returns a call to functools.partial
    #     which is the function that accepts the aFunc
    #     specification and then calls throttle with aFunc as the first
    #     argument with the other args for requests and seconds.
    #
    #     One other complication is that we are also using the
    #     wrapt.decorator for the inner wrapper function which does some
    #     more smoke and mirrors to ensure introspection will work as
    #     expected.
    # ==================================================================

    if wrapped is None:
        return cast(
            FuncWithThrottleSyncEcAttr[F],
            functools.partial(
                throttle_sync_ec,
                requests=requests,
                seconds=seconds,
                name=name,
                early_count=early_count,
            ),
        )

    if name is None:
        name = wrapped.__name__
    a_throttle_sync_ec = ThrottleSyncEc(
        requests=requests, seconds=seconds, name=name, early_count=early_count
    )

    @decorator  # type: ignore
    def wrapper(
        func_to_wrap: F,
        instance: Optional[Any],
        args: tuple[Any, ...],
        kwargs2: dict[str, Any],
    ) -> Any:

        return a_throttle_sync_ec.send_request(func_to_wrap, *args, **kwargs2)

    wrapper = wrapper(wrapped)

    wrapper = add_throttle_sync_ec_attr(wrapper)
    wrapper.throttle = a_throttle_sync_ec

    return cast(FuncWithThrottleSyncEcAttr[F], wrapper)


########################################################################
# @throttle_sync_lb
########################################################################
@overload
def throttle_sync_lb(
    wrapped: F,
    *,
    requests: int,
    seconds: IntFloat,
    name: Optional[str] = None,
    lb_threshold: float,
) -> FuncWithThrottleSyncLbAttr[F]:
    pass


@overload
def throttle_sync_lb(
    *, requests: int, seconds: IntFloat, name: Optional[str] = None, lb_threshold: float
) -> Callable[[F], FuncWithThrottleSyncLbAttr[F]]:
    pass


def throttle_sync_lb(
    wrapped: Optional[F] = None,
    *,
    requests: int,
    seconds: Any,  # : IntFloat,
    name: Optional[str] = None,
    lb_threshold: float,
) -> Union[F, FuncWithThrottleSyncLbAttr[F]]:
    """Decorator to wrap a function in a sync lb throttle.

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
        requests: The number of requests that can be made in
                    the interval specified by seconds.
        seconds: The number of seconds in which the number of requests
                   specified in requests can be made.
        name: The name used to identify the throttle in log messages
                issued by the throttle. The default name is
                the name of the function being wrapped by the
                throttle_async decorator.
        lb_threshold: Specifies the threshold for the leaky bucket.
                        This is the number of requests that can be in
                        the bucket such that the next request is allowed
                        to proceed without delay. That request is
                        added to the bucket, and then the bucket leaks
                        out the requests. When the next request arrives,
                        it will be delayed by whatever amount of time is
                        needed for the bucket to have leaked enough to
                        be at the threshold. A specification of zero for
                        the *lb_threshold* will effectively cause all
                        requests that are early to be delayed.

    Returns:
        A callable function that delays the request as needed in
        accordance with the specified limits.


    :Example: wrap a function with a throttle for 3 requests per
              second using the leaky bucket algo

    >>> from scottbrian_throttle.throttle import Throttle
    >>> @throttle_sync_lb(requests=5,
    ...                   seconds=120,
    ...                   lb_threshold=5)
    ... def f4(a, *, b=4) -> int:
    ...     print(f'example request function with args {a} and {b}')
    ...     return b * 7


    """
    # ==================================================================
    #  The following code covers cases where throttle is used with or
    #  without the pie character, where the decorated function has or
    #  does not have parameters.
    #
    #     Here's an example of throttle with a function that has no
    #         args:
    #         @throttle(requests=1, seconds=1)
    #         def aFunc():
    #             print('42')
    #
    #     This is what essentially happens under the covers:
    #         def aFunc():
    #             print('42')
    #         aFunc = throttle(requests=1,
    #                          seconds=1)(aFunc)
    #
    #     The call to throttle results in a function being returned that
    #     takes as its first argument the aFunc specification that we
    #     see in parens immediately following the throttle call.
    #
    #     Note that we can also code the above as shown and get the same
    #     result.
    #
    #     Also, we can code the following and get the same result:
    #         def aFunc():
    #             print('42')
    #         aFunc = throttle(aFunc,
    #                          requests=1,
    #                          seconds=1)
    #
    #     What happens is throttle gets control and tests whether aFunc
    #     was specified, and if not returns a call to functools.partial
    #     which is the function that accepts the aFunc
    #     specification and then calls throttle with aFunc as the first
    #     argument with the other args for requests and seconds.
    #
    #     One other complication is that we are also using the
    #     wrapt.decorator for the inner wrapper function which does some
    #     more smoke and mirrors to ensure introspection will work as
    #     expected.
    # ==================================================================

    if wrapped is None:
        return cast(
            FuncWithThrottleSyncLbAttr[F],
            functools.partial(
                throttle_sync_lb,
                requests=requests,
                seconds=seconds,
                name=name,
                lb_threshold=lb_threshold,
            ),
        )

    if name is None:
        name = wrapped.__name__
    a_throttle_sync_lb = ThrottleSyncLb(
        requests=requests, seconds=seconds, name=name, lb_threshold=lb_threshold
    )

    @decorator  # type: ignore
    def wrapper(
        func_to_wrap: F,
        instance: Optional[Any],
        args: tuple[Any, ...],
        kwargs2: dict[str, Any],
    ) -> Any:

        return a_throttle_sync_lb.send_request(func_to_wrap, *args, **kwargs2)

    wrapper = wrapper(wrapped)

    wrapper = add_throttle_sync_lb_attr(wrapper)
    wrapper.throttle = a_throttle_sync_lb

    return cast(FuncWithThrottleSyncLbAttr[F], wrapper)


########################################################################
# @throttle_async
########################################################################
@overload
def throttle_async(
    wrapped: F,
    *,
    requests: int,
    seconds: IntFloat,
    name: Optional[str] = None,
    async_q_size: Optional[int] = None,
) -> FuncWithThrottleAsyncAttr[F]:
    pass


@overload
def throttle_async(
    *,
    requests: int,
    seconds: IntFloat,
    name: Optional[str] = None,
    async_q_size: Optional[int] = None,
) -> Callable[[F], FuncWithThrottleAsyncAttr[F]]:
    pass


def throttle_async(
    wrapped: Optional[F] = None,
    *,
    requests: int,
    seconds: Any,  # : IntFloat,
    name: Optional[str] = None,
    async_q_size: Optional[int] = None,
) -> Union[F, FuncWithThrottleAsyncAttr[F]]:
    """Decorator to wrap a function in an async throttle.

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
        requests: The number of requests that can be made in
                    the interval specified by seconds.
        seconds: The number of seconds in which the number of requests
                   specified in requests can be made.
        name: The name used to identify the throttle in log messages
                issued by the throttle. The default name is
                the name of the function being wrapped by the
                throttle_async decorator.
        async_q_size: Specifies the size of the request
                        queue for async requests. When the request
                        queue is totaly populated, any additional
                        calls to send_request will be delayed
                        until queued requests are removed and
                        scheduled. The default is 4096 requests.

    Returns:
        A callable function that queues the request to be scheduled in
        accordance with the specified limits.


    :Example: wrap a function with an async throttle for 1 request
                  per second

    >>> from scottbrian_throttle.throttle import Throttle
    >>> @throttle_async(requests=1, seconds=1)
    ... def f1() -> None:
    ...     print('example 1 request function')
    >>> shutdown_throttle_funcs(f1)


    """
    # ==================================================================
    #  The following code covers cases where throttle is used with or
    #  without the pie character, where the decorated function has or
    #  does not have parameters.
    #
    #     Here's an example of throttle with a function that has no
    #         args:
    #         @throttle(requests=1, seconds=1)
    #         def aFunc():
    #             print('42')
    #
    #     This is what essentially happens under the covers:
    #         def aFunc():
    #             print('42')
    #         aFunc = throttle(requests=1,
    #                          seconds=1)(aFunc)
    #
    #     The call to throttle results in a function being returned that
    #     takes as its first argument the aFunc specification that we
    #     see in parens immediately following the throttle call.
    #
    #     Note that we can also code the above as shown and get the same
    #     result.
    #
    #     Also, we can code the following and get the same result:
    #         def aFunc():
    #             print('42')
    #         aFunc = throttle(aFunc,
    #                          requests=1,
    #                          seconds=1)
    #
    #     What happens is throttle gets control and tests whether aFunc
    #     was specified, and if not returns a call to functools.partial
    #     which is the function that accepts the aFunc
    #     specification and then calls throttle with aFunc as the first
    #     argument with the other args for requests and seconds.
    #
    #     One other complication is that we are also using the
    #     wrapt.decorator for the inner wrapper function which does some
    #     more smoke and mirrors to ensure introspection will work as
    #     expected.
    # ==================================================================

    if wrapped is None:
        return cast(
            FuncWithThrottleAsyncAttr[F],
            functools.partial(
                throttle_async,
                requests=requests,
                seconds=seconds,
                name=name,
                async_q_size=async_q_size,
            ),
        )

    if name is None:
        name = wrapped.__name__

    a_throttle_async = ThrottleAsync(
        requests=requests,
        seconds=seconds,
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

        return a_throttle_async.send_request(func_to_wrap, *args, **kwargs2)

    wrapper = wrapper(wrapped)

    wrapper = add_throttle_async_attr(wrapper)
    wrapper.throttle = a_throttle_async

    return cast(FuncWithThrottleAsyncAttr[F], wrapper)


########################################################################
# shutdown_throttle_funcs
########################################################################
def shutdown_throttle_funcs(
    *args: FuncWithThrottleAsyncAttr[Callable[..., Any]],
    # *args: FuncWithThrottleAttr[Protocol[F]],
    shutdown_type: int = ThrottleAsync.TYPE_SHUTDOWN_SOFT,
    timeout: OptIntFloat = None,
) -> bool:
    """Shutdown the throttle request scheduling for decorated functions.

    The shutdown_throttle_funcs function is used to shutdown one or more
    function that were decorated with the throttle. The arguments apply
    to each of the functions that are specified to be shutdown. If
    timeout is specified, then True is returned if all functions
    were shutdown within the timeout number of second specified.

    Args:
        args: one or more functions to be shutdown
        shutdown_type: specifies whether to do a soft or a hard
                         shutdown:

                         * A soft shutdown
                           (ThrottleAsync.TYPE_SHUTDOWN_SOFT), the
                           default, stops any additional requests from
                           being queued and cleans up the request queue
                           by scheduling any remaining requests at the
                           normal interval as calculated by the seconds
                           and requests that were specified during
                           instantiation.
                         * A hard shutdown
                           (ThrottleAsync.TYPE_SHUTDOWN_HARD) stops any
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
          specified and all of the specified functions completed
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
            if ThrottleAsync.RC_SHUTDOWN_TIMED_OUT != func.throttle.start_shutdown(
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
