"""Module throttle.

========
throttle
========

The Throttle allows you to limit the rate at which a function is
called. An internet service, for example, might have a limit for the
number of requests you can send in a given interval - using the
throttle will help you stay within that limit.

The throttle is a decorator that wraps your function with code that
keeps track of the intervals between each invocation. The throttle will
delay the running of your function to stay within the limit. By default,
the throttle maintains a limit of 1 call per second.

:Example 1: throttle at 1 request per second:

.. code-block:: python

    from scottbrian_throttle.throttle import throttle
    import time

    @throttle()
    def func1(request_number, time_of_start):
        ret_value = (f'request {request_number} sent at elapsed time: '
                     f'{time.time() - time_of_start:0.1f}')
        return ret_value

    start_time = time.time()
    for idx in range(10):
        ret_val = func1(idx, start_time)
        print(ret_val)


    Expected output for Example 1::

        request 0 sent at elapsed time: 0.0
        request 1 sent at elapsed time: 1.0
        request 2 sent at elapsed time: 2.0
        request 3 sent at elapsed time: 3.0
        request 4 sent at elapsed time: 4.0
        request 5 sent at elapsed time: 5.0
        request 6 sent at elapsed time: 6.0
        request 7 sent at elapsed time: 7.0
        request 8 sent at elapsed time: 8.0
        request 9 sent at elapsed time: 9.0


You can specify the limit with the *reqs_per_sec* parameter. The
interval is calculated as 1/*reqs_per_sec*. For example,
*reqs_per_sec=1* will be an interval of 1 second, while
*reqs_per_sec=0.5* will be an interval of 2 seconds, and
*reqs_per_sec=2* will be an interval of 1/2 seconds.

:Example 2: throttle at 2 requests per second:

.. code-block:: python

    from scottbrian_throttle.throttle import throttle
    import time

    @throttle(reqs_per_sec=2)
    def func2(request_number, time_of_start):
        ret_value = (f'request {request_number} sent at elapsed time: '
                     f'{time.time() - time_of_start:0.1f}')
        return ret_value

    start_time = time.time()
    for idx in range(10):
        ret_val = func2(idx, start_time)
        print(ret_val)


    Expected output for Example 1::

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


Using the throttle in asyncio and non-asyncio environments
==========================================================

The throttle will delay the function as needed to ensure the limit is not
exceeded, and this delay will be done with either time.sleep or
asyncio.sleep.

When the throttle is used to decorate an async defined function, the
caller is expected to be running in an asyncio environment and to invoke
the function using the proper asyncio method, such as using await. For
this scenario, the throttle will use asyncio.sleep to as needed to delay
the function. If for some reason the caller is not running in an asyncio
environment, calling an async defined function will fail, as expected.

When the throttle is used to decorate a non-async defined function and
the caller is not running in an asyncio environment, the caller can
simply invoke the function in the usual fashion without needing to do
anything special. For this scenario, the throttle will use time.sleep
as needed to delay the function.

When the throttle is used, however, to decorate a non-asyncio function
and the caller is running in an asyncio environment, special care
must be used when invoking the function to ensure that the event
loop will not be blocked. There are two possible scenarios:
    1) the caller can use asyncio.to_thread from the main loop to
       run the function is a separate thread. In this scenario, the
       throttle will use time.sleep as needed to delay the function.
    2) *sync_action=conver_to_async* can be specified on throttle to
       cause the wrapper to be defined as an async function. In this
       scenario, the caller can invoke the function using the proper
       asyncio method, such as using await. The throttle will use
       asyncio.sleep to as needed to delay the function, and will use
       asyncio.to_thread to run the function in a separate thread.






     decorated function is defined as an
asyncio function (i.e., async def func(...)). If so, asyncio.sleep will
be used to perform any needed delay for the throttling. If the decorated
function is not defined as async, time.sleep will be used instead. The
throttle will also deted from the  *( the th n-asyncio
If ,  the _n a non-asyncio By default, the Throttle is synchronous - when you call your function
you will not get back control until your function has completed. This
means you will observe any delay imposed by the Throttle. The Throttle
also provides an asynchronous mode that queues your function to a queue
to be run from a separate thread. This frees up your application to
perform other work while the throttled functions are being delayed.

:Example 3: asynchronous throttle:

.. code-block:: python

    from scottbrian_throttle.throttle import Throttle
    import time

    @Throttle(reqs_per_sec=2, throttle_mode=Mode.ASYNC)
    def func3(request_number, time_of_start):
        print(f'request {request_number} sent at elapsed time: '
              f'{time.time() - time_of_start:0.1f}')

    start_time = time.time()
    for idx in range(10):
        func3(idx, start_time)

    Expected output for Example 3::

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



Note that since an asynchronous Throttle queues your function to a
separate thread, that thread will need to be ended when your program
ends. To do this, you will need to call the *start_shutdown* method.
When your function is decorated with the Throttle, the Throttle will
attach its instance to your function as a function attribute named
'throttle'. This is then used for the call to *start_shutdown* as shown
here:

.. code-block:: python

    func3.throttle.start_shutdown()


An additional note about asynchronous mode is that the decorated
function cannot pass back a return value as we saw for the synchronous
mode Throttle.


The throttle as leaky bucket:
=============================

The throttle is implemented as a leaky bucket. Each call to your
Throttle decorated function is represented as an interval of time that
is conceptually placed into the bucket. The bucket has a hole in the
bottom that leaks out at the interval rate. The bucket starts out empty.
The first call to your function is "placed" into the empty bucket and
allowed to run without delay. On each subsequent call, if the
bucket still has the previous call leaking out, the new call is delayed
until the bucket has room for it.

You can also specify a larger bucket with the *bucket_size* parameter.
Setting *bucket_size=2*, for example, will allow the first two calls to
run immediately. Subsequent calls will be delayed unless and until the
bucket has leaked out enough to fit each new call. If no calls are made
for some time, the bucket will become empty and allow the next two calls
to again run immediately.

A Throttle configured as large bucket will act like a shock absorber,
allowing small bursts of function calls to run without delay. The
limiting action kicks in as additional calls continue to rapidly
arrive. Note that the average request interval will decrease as
the size of the bucket increases.

:Example 4: Throttle with a *bucket_size* of 3:

.. code-block:: python

    from scottbrian_throttle.throttle import Throttle
    import time

    @Throttle(reqs_per_sec=2, bucket_size=3)
    def func4(request_number, time_of_start):
        print(f'request {request_number} sent at elapsed time: '
              f'{time.time() - time_of_start:0.1f}')
    start_time = time.time()
    for idx in range(10):
        func4(idx, start_time)


    Expected output for Example 4::

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

########################################################################
# Standard Library
########################################################################
from typing import (
    Any,
    Callable,
    cast,
    Optional,
    overload,
    Protocol,
    TypeVar,
    Union,
)

########################################################################
# Third Party
########################################################################
import scottbrian_locking.se_lock as selk  # noqa F401
import wrapt
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


class InvalidShutdownRequested(ThrottleError):
    """Throttle exception for invalid shutdown request."""


class InvalidArgs(ThrottleError):
    """Throttle exception for invalid args."""


########################################################################
# Pie Throttle Decorator
########################################################################
F = TypeVar("F", bound=Callable[..., Any])


########################################################################
# start of experiment1
########################################################################
@wrapt.decorator
def track_state(wrapped, instance, args, kwargs):
    # 1. Check if the decorator is being used on an instance method
    if instance is not None:
        # 2. Define a unique attribute name for this decorator's state
        state_attr = f"_state_{wrapped.__name__}"

        # 3. Initialize the state on the instance if it does not exist
        if not hasattr(instance, state_attr):
            setattr(instance, state_attr, {"call_count": 0})

        # 4. Access and mutate the instance-specific state
        state = getattr(instance, state_attr)
        state["call_count"] += 1
        print(
            f"[Log] {wrapped.__name__} called {state['call_count']} time(s) for {instance}"
        )

    # 5. Execute the original method
    return wrapped(*args, **kwargs)


class MethodStateProxy(wrapt.BaseObjectProxy):
    """A proxy wrapper that allows setting custom attributes on a bound method."""

    def __init__(self, wrapped_method):
        super().__init__(wrapped_method)
        self.__self_dict__ = {}

    def __getattr__(self, name):
        try:
            print(
                f"\n ************** __getattr__ about to try to return super().__getattr__(name) for {name=}"
            )
            return super().__getattr__(name)
        except AttributeError:
            # return self.__dict__[name]
            print(
                f"\n ************** __getattr__ did not find in super, about see if {name=} is in self.__self_dict__"
            )
            if name in self.__self_dict__:
                print(
                    f"\n ******************** __getattr__ found name is in self.__self_dict__ for {name=}"
                )
                return self.__self_dict__[name]
            print(
                f"\n ************** __getattr__ did not find {name=} in self.__self_dict__ will now raise AttributeError "
            )
            raise AttributeError(
                f"'{type(self).__name__}' object has no attribute '{name}'"
            )

    def __setattr__(self, name, value):
        # Allow setting custom attributes locally on this specific bound proxy
        print(
            f"\n ******************** __set_attr__ setting {value=} for attribute {name=}"
        )
        self.__self_dict__[name] = value

    def __delattr__(self, name):
        # 1. Try to delete from the proxy's local dictionary first
        if name in self.__self_dict__:
            del self.__self_dict__[name]
            return

        try:
            # 2. If not local, try to delete from the wrapped method
            super().__delattr__(name)
        except AttributeError:
            # 3. Raise a clean AttributeError if it doesn't exist anywhere
            raise AttributeError(
                f"'{type(self).__name__}' object has no attribute '{name}'"
            )


# class TrackState:
#     def __init__(self, val1: int = 3):
#         # Maps (instance_id, method_name) -> MethodStateProxy instance
#         print(f"\n ######## entered TrackState __init__ with {self=}")
#         self.val1 = val1
#         self._proxies = {}
#
#     # def __call__(self, wrapped, instance, args, kwargs):
#     # def __call__(self, func):
#     @wrapt.decorator
#     def __call__(self, wrapped, instance, args, kwargs):
#
#         def wrapper(wrapped, instance, args, kwargs):
#             print(
#                 f"\n ######## entered TrackState __call__ with {wrapped=} , {instance=}, {args=}, {kwargs=}"
#             )
#             # def call_dec()
#             # Fallback for plain functions/staticmethods
#             if instance is None:
#                 if not hasattr(wrapped, "throttle"):
#                     wrapped.throttle = Throttle()
#                 return wrapped.throttle.send_request(wrapped, *args, **kwargs)
#
#             # Retrieve or create a unique method proxy for this specific class instance
#             proxy_key = (id(instance), wrapped.__name__)
#             if proxy_key not in self._proxies:
#                 # Recreate the native bound method, then wrap it in our proxy
#                 bound_method = getattr(instance, wrapped.__name__)
#                 self._proxies[proxy_key] = MethodStateProxy(bound_method)
#
#             # Increment the state on the proxy object
#             proxy = self._proxies[proxy_key]
#             print(f"\n ######## TrackState now has {proxy=}")
#             if not hasattr(proxy, "throttle"):
#                 print(f"\n ########TrackState about to set the throttle into proxy")
#                 proxy.throttle = Throttle()
#                 print(f"\n*************  TrackState after assignment {proxy.throttle=}")
#                 # wrapped.throttle = proxy.throttle
#                 # print(f"\n*************  TrackState after assignment {wrapped.throttle=}")
#             else:
#                 print(f"\n ########TrackState already has throttle in proxy")
#
#             return proxy.throttle.send_request(wrapped, *args, **kwargs)
#
#         # wrapped_func = wrapper(func)
#         # wrapped_func.throttle =
#         return wrapper


class TrackState:
    def __init__(self, val1: int = 3):
        # Maps (instance_id, method_name) -> MethodStateProxy instance
        print(f"\n ######## entered TrackState __init__ with {self=}")
        self.val1 = val1
        self._proxies = {}

    # def __call__(self, wrapped, instance, args, kwargs):
    # def __call__(self, func):

    def __call__(self, args, kwargs):

        @wrapt.decorator
        def wrapper(wrapped, instance, args, kwargs):
            print(
                f"\n ######## entered TrackState __call__ with {wrapped=} , {instance=}, {args=}, {kwargs=}"
            )
            # def call_dec()
            # Fallback for plain functions/staticmethods
            if instance is None:
                if not hasattr(wrapped, "throttle"):
                    wrapped.throttle = Throttle()
                return wrapped.throttle.send_request(wrapped, *args, **kwargs)

            # Retrieve or create a unique method proxy for this specific class instance
            proxy_key = (id(instance), wrapped.__name__)
            if proxy_key not in self._proxies:
                # Recreate the native bound method, then wrap it in our proxy
                bound_method = getattr(instance, wrapped.__name__)
                self._proxies[proxy_key] = MethodStateProxy(bound_method)

            # Increment the state on the proxy object
            proxy = self._proxies[proxy_key]
            print(f"\n ######## TrackState now has {proxy=}")
            if not hasattr(proxy, "throttle"):
                print(f"\n ########TrackState about to set the throttle into proxy")
                proxy.throttle = Throttle()
                print(f"\n*************  TrackState after assignment {proxy.throttle=}")
                # wrapped.throttle = proxy.throttle
                # print(f"\n*************  TrackState after assignment {wrapped.throttle=}")
            else:
                print(f"\n ########TrackState already has throttle in proxy")

            return proxy.throttle.send_request(wrapped, *args, **kwargs)

        # wrapped_func = wrapper(func)
        # wrapped_func.throttle =
        return wrapper


########################################################################

########################################################################
# Pie Throttle Decorator
########################################################################
F = TypeVar("F", bound=Callable[..., Any])


########################################################################
# _FuncWithThrottleAttr class
########################################################################
class _FuncWithThrottleAttr(Protocol[F]):
    """Class to allow type checking on function with attribute."""

    throttle2: Throttle
    __call__: F


def _add_throttle_attr(func: F) -> _FuncWithThrottleAttr[F]:
    """Wrapper to add throttle attribute to function.

    Args:
        func: function that has the attribute added

    Returns:
        input function with throttle attached as attribute

    """
    return cast(_FuncWithThrottleAttr[F], func)


########################################################################
# @throttle
########################################################################
@overload
def throttle(
    _wrapped: F,
    *,
    reqs_per_sec: IntFloat,
    bucket_size: IntFloat = 1,
    throttle_mode: Throttle.Mode = Throttle.Mode.SYNC,
    async_q_size: Optional[int] = None,
    name: Optional[str] = None,
) -> _FuncWithThrottleAttr[F]:
    pass


@overload
def throttle(
    *,
    reqs_per_sec: IntFloat,
    bucket_size: IntFloat = 1,
    throttle_mode: Throttle.Mode = Throttle.Mode.SYNC,
    async_q_size: Optional[int] = None,
    name: Optional[str] = None,
) -> Callable[[F], _FuncWithThrottleAttr[F]]:
    pass


def throttle(
    _wrapped: Optional[F] = None,
    *,
    reqs_per_sec: IntFloat,
    bucket_size: IntFloat = 1,
    throttle_mode: Throttle.Mode = Throttle.Mode.SYNC,
    async_q_size: Optional[int] = None,
    name: Optional[str] = None,
) -> Union[F, _FuncWithThrottleAttr[F]]:
    """Decorator to wrap a function in a throttle.

    The throttle wraps code around a function to limit the rate that it
    can be called.

    Args:
        _wrapped: the function
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
        throttle_mode: If Throttle.MODE_ASYNC, the throttle is
                asynchronous. If ThrottleeMode.SYNC, the default, the
                throttle is synchronous.
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

    :Example 10: wrap a function with a throttle for 1 request
                  per second

    .. code-block:: python

        from scottbrian_throttle.throttle import throttle
        @throttle(reqs_per_sec=1)
        def f1() -> None:
            print('example 1 request function')


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

    # if _wrapped is None:
    #     return cast(
    #         _FuncWithThrottleAttr[F],
    #         functools.partial(
    #             throttle,
    #             reqs_per_sec=reqs_per_sec,
    #             bucket_size=bucket_size,
    #             throttle_mode=throttle_mode,
    #             async_q_size=async_q_size,
    #             name=name,
    #         ),
    #     )

    if _wrapped is None:
        return wrapt.PartialCallableObjectProxy(
            throttle,
            reqs_per_sec=reqs_per_sec,
            bucket_size=bucket_size,
            throttle_mode=throttle_mode,
            async_q_size=async_q_size,
            name=name,
        )

    if name is None:
        name = _wrapped.__name__
    # a_throttle = Throttle(
    #     reqs_per_sec=reqs_per_sec,
    #     bucket_size=bucket_size,
    #     throttle_mode=throttle_mode,
    #     async_q_size=async_q_size,
    #     name=name,
    # )

    # @wrapt.bind_state_to_wrapper(name="throttle")
    @decorator  # type: ignore
    def wrapper(
        func_to_wrap: F,
        instance: Optional[Any] = None,
        args: Optional[tuple[Any, ...]] = None,
        kwargs2: Optional[dict[str, Any]] = None,
    ) -> Any:
        print("#######  entered wrapper")
        if instance is None:
            if not hasattr(func_to_wrap, "throttle"):
                func_to_wrap.throttle = Throttle()
            return func_to_wrap(*args, **kwargs2)

        bound_method = getattr(instance, func_to_wrap.__name__)

        if not hasattr(bound_method, "count"):
            # bound_method.throttle = Throttle()
            bound_method.count = 0

        state_attr_name = f"_decorator_state_{func_to_wrap.__name__}"
        if not hasattr(instance, state_attr_name):
            a_throttle = Throttle()
            setattr(instance, state_attr_name, {"throttle1": a_throttle})
            # func_to_wrap.throttle2 = a_throttle
        state = getattr(instance, state_attr_name)
        a_throttle = state["throttle1"]
        print(f"{func_to_wrap.__name__} with {bound_method.throttle.call_count=}")

        print(f"about to call send_request for {instance=} {func_to_wrap.__name__=}")
        # return bound_method.throttle._send_request(func_to_wrap, *args, **kwargs2)
        return a_throttle.send_request(func_to_wrap, *args, **kwargs2)

        # return a_throttle._send_request(func_to_wrap, *args, **kwargs2)

    print(f"calling wrapper(_wrapped_) {wrapper=}, {_wrapped=}  ")
    wrapper = wrapper(_wrapped)
    print(f"back from calling wrapper(_wrapped_) {wrapper=}, {_wrapped=}  ")

    wrapper = _add_throttle_attr(wrapper)
    # wrapper.throttle2 = a_throttle

    return cast(_FuncWithThrottleAttr[F], wrapper)
