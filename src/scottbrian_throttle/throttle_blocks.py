"""Module throttle_blocks.

===============
throttle_blocks
===============

The throttle_blocks module contains the parts need by teh throttle
decorator.

"""

import logging
import threading
import time
########################################################################
# Standard Library
########################################################################
from enum import Enum, auto
from typing import (
    Any,
    Callable,
    Final,
    Optional,
    TYPE_CHECKING,
    Type,
    Union,
)

########################################################################
# Third Party
########################################################################
import scottbrian_locking.se_lock as selk  # noqa F401
from scottbrian_utils.diag_msg import get_formatted_call_sequence as call_seq
from scottbrian_utils.pauser import Pauser
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


class IncorrectReqsPerSecSpecified(ThrottleError):
    """Throttle exception for incorrect reqs_per_sec specification."""

    pass


class IncorrectBucketSizeSpecified(ThrottleError):
    """Throttle exception for incorrect bucket_size specification."""

    pass


class InvalidArgs(ThrottleError):
    """Throttle exception for invalid args."""

    pass


########################################################################
# Throttle class
########################################################################
class Throttle:
    """Throttle class."""

    class Mode(Enum):
        SYNC = auto()
        ASYNC = auto()

    SECS_2_NS: Final[int] = 1000000000
    NS_2_SECS: Final[float] = 0.000000001

    __slots__ = (
        "_arrival_time_ns",
        "_next_target_time_ns",
        "_target_interval",
        "_target_interval_ns",
        "_wait_time_ns",
        "call_count",
        "convert_to_async",
        "bucket_size",
        "lb_adjustment",
        "lb_adjustment_ns",
        "lb_with_one_request",
        "logger",
        "pauser",
        "reqs_per_sec",
        "sent_time_ns",
        "sync_lock",
        "t_name",
    )

    ####################################################################
    # __init__
    ####################################################################
    def __init__(
        self,
        *,
        reqs_per_sec: IntFloat = 1,
        bucket_size: IntFloat = 1,
        convert_to_async: bool = False,
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
                         one for the bucket_size will effectively
                         cause non-leaky bucket behavior, meaning that
                         each request that arrives before the previous
                         request interval has elapsed will be delayed.
                         The bucket_size must be greater than or equal
                         to 1.
            convert_to_async: When True, convert a non-asyncio function to
                          be defined as an async function. This will
                          allow the caller to invoke the decorated
                          function using a proper asyncio method such as
                          *await*. The default is False.
            name: The name used to identify the throttle in log messages
                issued by the throttle. The default name is
                the python id of the Throttle class instance.


        Raises:
            IncorrectReqsPerSecSpecified: The *reqs_per_sec*
                specification must be a positive int or float greater
                than zero.

        """
        ################################################################
        # reqs_per_sec
        ################################################################
        self.logger = logging.getLogger(__name__)

        if isinstance(reqs_per_sec, int | float) and (0 < reqs_per_sec):
            self.reqs_per_sec = reqs_per_sec
        else:
            error_msg = (
                "The reqs_per_sec specification must be a positive "
                "int or float greater than zero. "
                f"Request call sequence: {call_seq(latest=1, depth=2)}"
            )
            self.logger.error(error_msg)
            raise IncorrectReqsPerSecSpecified(error_msg)

        ################################################################
        # bucket_size
        ################################################################
        if isinstance(bucket_size, int | float) and (1 <= bucket_size):
            self.bucket_size = bucket_size
        else:
            error_msg = (
                "The bucket_size specification must be a positive "
                "int or float greater than or equal to 1. "
                f"Request call sequence: {call_seq(latest=1, depth=2)}"
            )
            self.logger.error(error_msg)
            raise IncorrectBucketSizeSpecified(error_msg)

        self.convert_to_async = convert_to_async

        ################################################################
        # name
        ################################################################
        self.t_name = name or str(id(self))

        ################################################################
        # Set remainder of vars
        ################################################################
        self._target_interval = 1 / reqs_per_sec
        self._target_interval_ns: float = self._target_interval * Throttle.SECS_2_NS
        self.sync_lock = threading.Lock()
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

        :Example 5: call __repr__ for Throttle

        .. code-block:: python

            from scottbrian_throttle.throttle import Throttle

            @Throttle(reqs_per_sec=0.5)
            def func5(request_number, time_of_start):
                pass

            print(repr(func5.throttle))

            Expected output for Example 5::

            'Throttle(reqs_per_sec=0.5, bucket_size=1, convert_to_async=False)'



        """
        if TYPE_CHECKING:
            __class__: Type[Throttle]  # noqa: F842
        classname = self.__class__.__name__
        parms = (
            f"reqs_per_sec={self.reqs_per_sec}, "
            f"bucket_size={self.bucket_size}, "
            f"convert_to_async={str(self.convert_to_async)}, "
            f"name={self.t_name}"
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
    def get_completion_time_secs(self, num_requests: int, from_start: bool) -> IntFloat:
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
    def get_completion_time_ns(self, num_requests: int, from_start: bool) -> IntFloat:
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
    def get_expected_num_completed_reqs(self, interval: IntFloat) -> int:
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
        with self.sync_lock:
            self._perform_throttle()

            ########################################################
            # Call the request function and return with the request
            # return value. We use try/except to log and re-raise
            # any unhandled errors.
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
    # perform_throttle
    ####################################################################
    def _perform_throttle(self) -> None:
        """Calculate next target time and wait if needed."""

        ################################################################
        # The leaky bucket algorith uses a virtual bucket into which
        # arriving requests are placed. As time progresses, the bucket
        # leaks the requests out at the rate of the target interval. If
        # the bucket has room for an arriving request, the request is
        # placed into the bucket and is sent immediately. If, instead,
        # the bucket does not have room for the request, the request is
        # delayed until the bucket has leaked enough of the preceding
        # requests such that the new request can fit and be sent. The
        # effect of the bucket is to allow a burst of requests to be
        # sent immediately at a faster rate than the target interval,
        # acting as a shock absorber to the flow of traffic. The number
        # of requests allowed to go immediately is controlled by the
        # size of the bucket which in turn is specified by the
        # bucket_size argument when the throttle is instantiated. Note
        # that a bucket_size of 1 means there will never be enough room
        # in the bucket for more than 1 request at a time.
        #
        # Note that by allowing short bursts to go immediately, the
        # overall effect is that the average interval will be less than
        # the target interval.
        #
        # The actual implementation does not employ a bucket, but
        # instead sets a target time for the next request by adding the
        # target interval and subtracting the size of the bucket. This
        # has the effect of making it appear as if requests are arriving
        # after the target time and are thus in compliance with the
        # target interval. The next target time will eventually exceed
        # the size of the bucket, and requests will get delayed to
        # allow the target time to catch up.
        ################################################################

        ################################################################
        # In the following code we handle three cases:
        # 1) The current request arrives well beyond the last request
        #    such that the bucket is completely empty. We need to start
        #    a new bucket relative to the current arrival time.
        # 2) The current request arrives rapidly on the heels of the
        #    previous request such that the bucket is full enough that
        #    it does not contain enough room to add a new entry. We need
        #    to delay this current request until there is room enough in
        #    the bucket to add this one entry.
        # 3) The current request arrives when the bucket has one or more
        #    previous requests still leaking out, but there is still
        #    enough room in the bucket to add another request without
        #    delay.
        #
        # Note that we update the bucket (i.e., target time) before we
        # call the requested function instead of updating the target
        # time after control returns from the requested function. This
        # means we face a possible scenario where we encounter a delay
        # during the call to the requested function, and upon return we
        # receive the next request which, because of the prior delay,
        # appears ok to send immediately. But this new request might
        # appear early as observed by the called service (i.e.,
        # requested function). If instead we were to update the target
        # time after getting back control from the requested function,
        # we avoid the "too early" scenario. But we would then be adding
        # in the request processing time to the throttle delay with the
        # undesirable effect that all requests will now be throttled
        # more than they need to be. The "too early" scenario seemed
        # less problematic compared to the "extra throttling" effect,
        # so the design choice was made to update the target time before
        # calling the requested function.
        ################################################################
        self._arrival_time_ns = time.perf_counter_ns()
        self._wait_time_ns = max(0.0, self._next_target_time_ns - self._arrival_time_ns)
        if self._next_target_time_ns + self.lb_adjustment_ns < self._arrival_time_ns:
            # we are well beyond the target time - we need to start
            # a new bucket with the first send entry added
            self._next_target_time_ns = self._arrival_time_ns + self.lb_with_one_request

        else:  # still in the range of the bucket
            # Sleep, if needed, until we have room in the bucket for one
            # entry.
            if self._wait_time_ns > 0:
                self.pauser.pause_ns(self._wait_time_ns)

            # add one entry to the bucket
            self._next_target_time_ns += self._target_interval_ns

        self.sent_time_ns = time.perf_counter_ns()


##### @@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@

# import asyncio
# import contextvars  # Native context tracking
# import functools
# import inspect
# import logging
# import time
# from typing import Literal, Optional
#
# logger = logging.getLogger("hybrid_decorator")
#
#
# def hybrid_delayed_execution(
#     delay: float, sync_action: Optional[Literal["keep_sync", "convert_to_async"]] = None
# ):
#     def decorator(func):
#         is_async_func = inspect.iscoroutinefunction(func)
#
#         # ---- VALIDATION GATE ----
#         if is_async_func and sync_action is not None:
#             raise TypeError(
#                 f"Cannot specify 'sync_action' on async function '{func.__name__}'."
#             )
#         if not is_async_func and sync_action is None:
#             raise TypeError(
#                 f"The function '{func.__name__}' is synchronous. Provide 'sync_action'."
#             )
#
#         # Helper to safely log or tag errors for APM systems
#         def capture_apm_error(e: Exception, context_name: str):
#             # 1. Standard structured logging (parsed cleanly by Datadog/ELK)
#             logger.error(
#                 f"Exception in {context_name} for '{func.__name__}': {e}",
#                 exc_info=True,
#                 extra={"function_name": func.__name__, "decorator_delay": delay},
#             )
#
#             # 2. Sentry Explicit Fallback (If the developer uses Sentry)
#             # Many APMs capture unhandled exceptions automatically, but inside
#             # background threads, explicit capture guarantees it isn't dropped.
#             try:
#                 import sentry_sdk
#
#                 sentry_sdk.capture_exception(e)
#             except ImportError:
#                 pass
#
#         # ---- EXECUTION PATHS ----
#
#         # PATH 1: Native Async Function
#         if is_async_func:
#
#             @functools.wraps(func)
#             async def async_wrapper(*args, **kwargs):
#                 await asyncio.sleep(delay)
#                 try:
#                     return await func(*args, **kwargs)
#                 except Exception as e:
#                     capture_apm_error(e, "async context")
#                     raise
#
#             return async_wrapper
#
#         # PATH 2: Sync Function -> Keep Sync (Option A)
#         elif sync_action == "keep_sync":
#
#             @functools.wraps(func)
#             def sync_blocking_wrapper(*args, **kwargs):
#                 try:
#                     asyncio.get_running_loop()
#                     raise RuntimeError(
#                         f"CRITICAL: Called 'keep_sync' function '{func.__name__}' directly on the main loop thread."
#                     )
#                 except RuntimeError as e:
#                     if "CRITICAL" in str(e):
#                         logger.critical(str(e))
#                         raise e
#
#                 time.sleep(delay)
#                 try:
#                     return func(*args, **kwargs)
#                 except Exception as e:
#                     capture_apm_error(e, "pure sync context")
#                     raise
#
#             return sync_blocking_wrapper
#
#         # PATH 3: Sync Function -> Convert to Async (Option B)
#         elif sync_action == "convert_to_async":
#
#             @functools.wraps(func)
#             async def sync_to_async_wrapper(*args, **kwargs):
#                 await asyncio.sleep(delay)
#
#                 # We extract the current execution context explicitly.
#                 # asyncio.to_thread handles this automatically, but doing it explicitly
#                 # guarantees third-party custom tracing hooks remain flawlessly linked.
#                 ctx = contextvars.copy_context()
#
#                 def worker_thread_target():
#                     try:
#                         return func(*args, **kwargs)
#                     except Exception as e:
#                         capture_apm_error(e, "worker thread")
#                         raise
#
#                 # Run the worker thread using the captured main-thread context
#                 return await asyncio.to_thread(lambda: ctx.run(worker_thread_target))
#
#             return sync_to_async_wrapper
#
#     return decorator


##### @@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@


# import asyncio
# import threading
# from contextlib import contextmanager
#
# import wrapt
#
# class MethodStateProxy(wrapt.ObjectProxy):
#     """A proxy wrapper that allows setting custom attributes on a bound method."""
#     def __init__(self, wrapped_method):
#         super().__init__(wrapped_method)
#         # Use object.__setattr__ to bypass the proxy forwarding for our own dict
#         object.__setattr__(self, '__dict__', {})
#
#     def __getattr__(self, name):
#         try:
#             return super().__getattr__(name)
#         except AttributeError:
#             return self.__dict__[name]
#
#     def __setattr__(self, name, value):
#         # Allow setting custom attributes locally on this specific bound proxy
#         self.__dict__[name] = value


# class StatefulMethodProxy(wrapt.ObjectProxy):
#     """A thread-and-async-safe proxy that enables custom states and teardowns."""
#
#     def __init__(self, wrapped_method):
#         super().__init__(wrapped_method)
#         # Internal state dictionary allocation
#         object.__setattr__(
#             self, "__dict__", {"count": 0, "status": "idle", "history": []}
#         )
#         # Thread lock for synchronous execution paths
#         object.__setattr__(self, "_thread_lock", threading.Lock())
#         # Lazy-loaded Asyncio lock for asynchronous execution paths
#         object.__setattr__(self, "_async_lock", None)
#
#     def __getattr__(self, name):
#         try:
#             return super().__getattr__(name)
#         except AttributeError:
#             return self.__dict__[name]
#
#     def __setattr__(self, name, value):
#         self.__dict__[name] = value
#
#     @contextmanager
#     def teardown_context(self):
#         """Context manager allowing users to cleanly reset state metrics on error."""
#         try:
#             yield self
#         except Exception:
#             # Automatic teardown routine triggered upon code failures
#             with self._thread_lock:
#                 self.status = "idle (recovered via teardown)"
#                 self.history.append("Teardown executed: State automatically cleared.")
#             raise
#
#     def get_async_lock(self):
#         """Lazily initialize the asyncio lock inside the running event loop."""
#         if self._async_lock is None:
#             self._async_lock = asyncio.Lock()
#         return self._async_lock
#
#
# class ConfigurableTracker:
#     """Configurable tracker tracking separate sync & async method calls."""
#
#     def __init__(self, initial_status, increment_by):
#         self.initial_status = initial_status
#         self.increment_by = increment_by
#         self._proxy_cache = weakref.WeakKeyDictionary()
#         self._cache_lock = threading.Lock()
#
#     def __call__(self, wrapped, instance, args, kwargs):
#         if instance is None:
#             return wrapped(*args, **kwargs)
#
#         proxy = self._get_or_create_proxy(instance, wrapped)
#
#         # ROUTE 1: Asynchronous Execution Path
#         if inspect.iscoroutinefunction(wrapped):
#
#             async def async_wrapper():
#                 async_lock = proxy.get_async_lock()
#                 async with async_lock:
#                     proxy.count += self.increment_by
#                     proxy.status = "running"
#                     proxy.history.append(f"Async processing: {args}")
#                 try:
#                     result = await wrapped(*args, **kwargs)
#                     async with async_lock:
#                         proxy.status = "success"
#                     return result
#                 except Exception as e:
#                     async with async_lock:
#                         proxy.status = f"failed: {type(e).__name__}"
#                     raise e
#
#             return async_wrapper()
#
#         # ROUTE 2: Synchronous Execution Path
#         else:
#             with proxy._thread_lock:
#                 proxy.count += self.increment_by
#                 proxy.status = "running"
#                 proxy.history.append(f"Sync processing: {args}")
#             try:
#                 result = wrapped(*args, **kwargs)
#                 with proxy._thread_lock:
#                     proxy.status = "success"
#                 return result
#             except Exception as e:
#                 with proxy._thread_lock:
#                     proxy.status = f"failed: {type(e).__name__}"
#                 raise e
#
#     def _get_or_create_proxy(self, instance, wrapped):
#         with self._cache_lock:
#             if instance not in self._proxy_cache:
#                 bound_method = getattr(instance, wrapped.__name__)
#                 proxy = StatefulMethodProxy(bound_method)
#                 proxy.status = self.initial_status
#                 self._proxy_cache[instance] = proxy
#             return self._proxy_cache[instance]
#
#     def __get__(self, instance, owner):
#         if instance is None:
#             return self
#         return self._get_or_create_proxy(instance, self._self_wrapped)
#
#
# class CustomDecoratorWrapper(wrapt.FunctionWrapper):
#     """Exposes descriptor bindings natively past wrapt core restrictions."""
#
#     def __get__(self, instance, owner):
#         return self._self_wrapper.__get__(instance, owner)
#
#
# def track_state(initial_status="initialized", increment_by=1):
#     """The master decorator factory supporting parameters, sync, and async."""
#
#     def decorator(wrapped):
#         tracker = ConfigurableTracker(
#             initial_status=initial_status, increment_by=increment_by
#         )
#         return CustomDecoratorWrapper(wrapped, tracker)
#
#     return decorator
#
#
#
# #####################################
# # latest
# #####################################
# """
#
# To handle failed states and execute custom callback functions,
# pass the callbacks directly as arguments into the outermost @track_state
# decorator factory.
# To make this architecture production-grade, the tracker must dynamically
# inspect if the provided callbacks are synchronous functions or asynchronous coroutines.
#  This prevents blocking errors when mixing execution contexts.
#  Enhanced Parameterized Architecture with CallbacksHere is the complete
#  implementation incorporating on-success and on-failure callbacks,
#  supporting both sync and async operations seamlessly:
# """
#
#
# pythonimport asyncio
# import inspect
# import threading
# import weakref
# import wrapt
#
# class StatefulMethodProxy(wrapt.ObjectProxy):
#     """A thread-and-async-safe proxy that holds instance-isolated state data."""
#     def __init__(self, wrapped_method):
#         super().__init__(wrapped_method)
#         object.__setattr__(self, '__dict__', {
#             'count': 0,
#             'status': 'idle',
#             'history': [],
#             'last_exception': None
#         })
#         object.__setattr__(self, '_thread_lock', threading.Lock())
#         object.__setattr__(self, '_async_lock', None)
#
#     def __getattr__(self, name):
#         try:
#             return super().__getattr__(name)
#         except AttributeError:
#             return self.__dict__[name]
#
#     def __setattr__(self, name, value):
#         self.__dict__[name] = value
#
#     def get_async_lock(self):
#         if self._async_lock is None:
#             self._async_lock = asyncio.Lock()
#         return self._async_lock
#
#
# class ConfigurableTracker:
#     """Tracks state and safely invokes user-defined callback hooks."""
#     def __init__(self, initial_status, increment_by, on_success=None, on_failure=None):
#         self.initial_status = initial_status
#         self.increment_by = increment_by
#         self.on_success_callback = on_success
#         self.on_failure_callback = on_failure
#
#         self._proxy_cache = weakref.WeakKeyDictionary()
#         self._cache_lock = threading.Lock()
#
#     def _execute_callback(self, callback, instance, proxy, exception=None):
#         """Helper to invoke a callback safely based on its sync/async signature."""
#         if not callback:
#             return
#
#         # Build the payload to feed into the user's custom callback
#         kwargs = {'instance': instance, 'proxy': proxy}
#         if exception:
#             kwargs['exception'] = exception
#
#         if inspect.iscoroutinefunction(callback):
#             # If the callback is async, schedule it safely on the active event loop
#             try:
#                 loop = asyncio.get_running_loop()
#                 loop.create_task(callback(**kwargs))
#             except RuntimeError:
#                 # Fallback if no loop is running in the current thread
#                 asyncio.run(callback(**kwargs))
#         else:
#             # Standard synchronous callback execution
#             callback(**kwargs)
#
#     def __call__(self, wrapped, instance, args, kwargs):
#         if instance is None:
#             return wrapped(*args, **kwargs)
#
#         proxy = self._get_or_create_proxy(instance, wrapped)
#
#         # ROUTE 1: Asynchronous Execution Path
#         if inspect.iscoroutinefunction(wrapped):
#             async def async_wrapper():
#                 async_lock = proxy.get_async_lock()
#                 async with async_lock:
#                     proxy.count += self.increment_by
#                     proxy.status = 'running'
#                 try:
#                     result = await wrapped(*args, **kwargs)
#                     async with async_lock:
#                         proxy.status = 'success'
#                         proxy.last_exception = None
#                     self._execute_callback(self.on_success_callback, instance, proxy)
#                     return result
#                 except Exception as e:
#                     async with async_lock:
#                         proxy.status = 'failed'
#                         proxy.last_exception = e
#                     self._execute_callback(self.on_failure_callback, instance, proxy, exception=e)
#                     raise e
#             return async_wrapper()
#
#         # ROUTE 2: Synchronous Execution Path
#         else:
#             with proxy._thread_lock:
#                 proxy.count += self.increment_by
#                 proxy.status = 'running'
#             try:
#                 result = wrapped(*args, **kwargs)
#                 with proxy._thread_lock:
#                     proxy.status = 'success'
#                     proxy.last_exception = None
#                 self._execute_callback(self.on_success_callback, instance, proxy)
#                 return result
#             except Exception as e:
#                 with proxy._thread_lock:
#                     proxy.status = 'failed'
#                     proxy.last_exception = e
#                 self._execute_callback(self.on_failure_callback, instance, proxy, exception=e)
#                 raise e
#
#     def _get_or_create_proxy(self, instance, wrapped):
#         with self._cache_lock:
#             if instance not in self._proxy_cache:
#                 bound_method = getattr(instance, wrapped.__name__)
#                 proxy = StatefulMethodProxy(bound_method)
#                 proxy.status = self.initial_status
#                 self._proxy_cache[instance] = proxy
#             return self._proxy_cache[instance]
#
#     def __get__(self, instance, owner):
#         if instance is None:
#             return self
#         return self._get_or_create_proxy(instance, self._self_wrapped)
#
#
# class CustomDecoratorWrapper(wrapt.FunctionWrapper):
#     def __get__(self, instance, owner):
#         return self._self_wrapper.__get__(instance, owner)
#
#
# def track_state(initial_status='initialized', increment_by=1, on_success=None, on_failure=None):
#     """The master factory decorator allowing configuration and callback injection."""
#     def decorator(wrapped):
#         tracker = ConfigurableTracker(
#             initial_status=initial_status,
#             increment_by=increment_by,
#             on_success=on_success,
#             on_failure=on_failure
#         )
#         return CustomDecoratorWrapper(wrapped, tracker)

# import asyncio
# import contextvars
# import queue
# import threading
# import time
# import wrapt
#
# active_state_ctx = contextvars.ContextVar("active_state")
#
# class LeakyBucketThrottleState:
#     def __init__(self, reqs_per_sec, bucket_size, mode="sync"):
#         self.reqs_per_sec = reqs_per_sec
#         self.bucket_size = bucket_size
#         self.capacity = float(bucket_size)
#         self.last_leak_time = time.monotonic()
#         self.mode = mode  # "sync", "thread_queue", or "asyncio"
#         self.call_count = 0
#
#         # Mode 2: Thread Queue Infrastructure
#         self._work_queue = None
#         self._worker_thread = None
#         self._stop_signal = threading.Event()
#
#         # Thread safety lock for calculations across modes 1 and 2
#         self._lock = threading.Lock()
#
#         if self.mode == "thread_queue":
#             self._start_background_worker()
#
#     def leak_unlocked(self):
#         """Calculates token regeneration based on elapsed time."""
#         now = time.monotonic()
#         elapsed = now - self.last_leak_time
#         leaked_amount = elapsed * self.reqs_per_sec
#         self.capacity = min(float(self.bucket_size), self.capacity + leaked_amount)
#         self.last_leak_time = now
#
#     def get_wait_time(self) -> float:
#         """
#         Determines if a token is ready. If not, returns the exact duration
#         (in seconds) needed until the next token regenerates.
#         """
#         with self._lock:
#             self.leak_unlocked()
#             if self.capacity >= 1.0:
#                 self.capacity -= 1.0
#                 return 0.0  # Immediate execution
#
#             # Calculate time needed to recover missing token fraction
#             needed_tokens = 1.0 - self.capacity
#             wait_time = needed_tokens / self.reqs_per_sec
#
#             # Pretend we consumed it ahead of time so next calls stack appropriately
#             self.capacity = 0.0
#             self.last_leak_time = self.last_leak_time + wait_time
#             return wait_time
#
#     # ---- Mode 2: Async Thread + Queue Operations ----
#     def _start_background_worker(self):
#         self._work_queue = queue.Queue()
#         self._worker_thread = threading.Thread(target=self._worker_loop, daemon=True)
#         self._worker_thread.start()
#
#     def _worker_loop(self):
#         """Background thread consumes tasks from queue and applies rate limits sequentially."""
#         while not self._stop_signal.is_set():
#             try:
#                 # Block briefly checking for new work packets
#                 func, args, kwargs = self._work_queue.get(timeout=0.2)
#             except queue.Empty:
#                 continue
#
#             # Calculate and apply blocking time.sleep within this private thread context
#             wait_time = self.get_wait_time()
#             if wait_time > 0:
#                 time.sleep(wait_time)
#
#             try:
#                 func(*args, **kwargs)
#             except Exception as e:
#                 print(f"[Thread Worker Exception]: {e}")
#             finally:
#                 self._work_queue.task_done()
#
#     def enqueue_work(self, func, args, kwargs):
#         """Pushes work execution payload to background thread line."""
#         if self._stop_signal.is_set():
#             raise RuntimeError("Cannot enqueue work. Throttle cleanup already executed.")
#         self._work_queue.put((func, args, kwargs))
#
#     def start_cleanup(self):
#         """Shuts down background queue workers and safely terminates threads."""
#         if self.mode == "thread_queue" and not self._stop_signal.is_set():
#             print(f"\n[Cleanup] Signaling background worker thread to stop...")
#             self._stop_signal.set()
#             if self._worker_thread:
#                 self._worker_thread.join(timeout=2.0)
#             print("[Cleanup] Background thread closed down safely.")
#
#
# # ---- Wrapt Descriptors (Preserved from yesterday) ----
# class StatefulBoundWrapper(wrapt.BoundFunctionWrapper):
#     @property
#     def throttle(self):
#         try: return active_state_ctx.get()
#         except LookupError: pass
#         w = self._self_parent
#         inst = self._self_instance
#         c_type = inst if isinstance(inst, type) else inst.__class__
#         key = f"_th_{w._method_name}_{c_type.__name__}_{id(w)}"
#         if not hasattr(inst, key):
#             setattr(inst, key, LeakyBucketThrottleState(w._reqs_per_sec, w._bucket_size, w._mode))
#         return getattr(inst, key)
#
# class StatefulFunctionWrapper(wrapt.FunctionWrapper):
#     __bound_function_wrapper__ = StatefulBoundWrapper
#     def __init__(self, wrapped, wrapper_func, method_name, reqs_per_sec, bucket_size, mode):
#         super().__init__(wrapped, wrapper_func)
#         self._method_name = method_name
#         self._reqs_per_sec = reqs_per_sec
#         self._bucket_size = bucket_size
#         self._mode = mode
#     @property
#     def throttle(self):
#         try: return active_state_ctx.get()
#         except LookupError: pass
#         key = f"_th_{self._method_name}_static_{id(self)}"
#         if not hasattr(self.__wrapped__, key):
#             setattr(self.__wrapped__, key, LeakyBucketThrottleState(self._reqs_per_sec, self._bucket_size, self._mode))
#         return getattr(self.__wrapped__, key)
#
#
# # ---- Decorator Parameter Factory ----
# def throttle(reqs_per_sec, bucket_size, mode="sync"):
#     def decorator(wrapped):
#         method_name = wrapped.__name__
#
#         def _core_execution_logic(wrapped_func, instance, args, kwargs):
#             # Resolve target mapping
#             if instance is not None:
#                 c_type = instance if isinstance(instance, type) else instance.__class__
#                 key = f"_th_{method_name}_{c_type.__name__}_{id(proxy)}"
#                 target = instance
#             else:
#                 key = f"_th_{method_name}_static_{id(proxy)}"
#                 target = wrapped_func
#
#             if not hasattr(target, key):
#                 setattr(target, key, LeakyBucketThrottleState(reqs_per_sec, bucket_size, mode))
#             state = getattr(target, key)
#
#             # -------------------------------------------------------------
#             # ENVIRONMENT MODE 2: Thread Queue Mode (Fire-and-forget)
#             # -------------------------------------------------------------
#             if mode == "thread_queue":
#                 # Bypass normal direct call route completely; strip 'self' if bound method
#                 if instance is not None:
#                     # Pass bound method invocation blueprint to worker queue
#                     bound_call = getattr(instance, wrapped_func.__name__)
#                     state.enqueue_work(bound_call, args, kwargs)
#                 else:
#                     state.enqueue_work(wrapped_func, args, kwargs)
#                 return None  # Returns control back to caller instantly!
#
#             # -------------------------------------------------------------
#             # ENVIRONMENT MODE 3: Asyncio Mode (Non-blocking Cooperative Sleep)
#             # -------------------------------------------------------------
#             elif mode == "asyncio":
#                 async def async_exec():
#                     wait_time = state.get_wait_time()
#                     if wait_time > 0:
#                         await asyncio.sleep(wait_time)
#
#                     state.call_count += 1
#                     token = active_state_ctx.set(state)
#                     try:
#                         return await wrapped_func(*args, **kwargs)
#                     finally:
#                         active_state_ctx.reset(token)
#                 return async_exec()
#
#             # -------------------------------------------------------------
#             # ENVIRONMENT MODE 1: Synchronous Mode (Standard time.sleep Blocking)
#             # -------------------------------------------------------------
#             else:
#                 wait_time = state.get_wait_time()
#                 if wait_time > 0:
#                     time.sleep(wait_time)
#
#                 state.call_count += 1
#                 token = active_state_ctx.set(state)
#                 try:
#                     return wrapped_func(*args, **kwargs)
#                 finally:
#                     active_state_ctx.reset(token)
#
#         proxy = StatefulFunctionWrapper(wrapped, _core_execution_logic, method_name, reqs_per_sec, bucket_size, mode)
#         return proxy
#     return decorator
