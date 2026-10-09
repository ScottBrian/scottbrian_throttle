"""Module throttle.

Copyright (C) 2026 Scott Tuttle
All rights reserved
Licensed under the MIT License. See LICENSE file in the project root for
details

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

    @throttle
    def func1(request_number, time_of_start):
        ret_value = (f'request {request_number} sent at elapsed time: '
                     f'{time.time() - time_of_start:0.1f}')
        return ret_value

    start_time = time.time()
    for idx in range(10):
        ret_val = func1(idx, start_time)
        print(ret_val)


:Expected output for Example 1::

.. code-block:: text

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

"""

########################################################################
# Standard Library
########################################################################
import inspect
from collections.abc import (
    Callable,  # , Coroutine
    Coroutine,
)
from typing import (
    Any,
    Concatenate,
    Literal,
    ParamSpec,
    Protocol,
    TypeVar,
    cast,
    overload,
)

from pydantic import Field, InstanceOf, validate_call

########################################################################
# Third Party
########################################################################
from wrapt import FunctionWrapper, PartialCallableObjectProxy, decorator

from scottbrian_throttle.throttle_blocks import Throttle

########################################################################
# Local
########################################################################

########################################################################
# Pie Throttle Decorator
########################################################################
P = ParamSpec("P")
R = TypeVar("R")
F = TypeVar("F", bound=Callable[..., Any])

_P1 = ParamSpec("_P1")
_R1_co = TypeVar("_R1_co", covariant=True)

SelfT = TypeVar("SelfT")  # Tracks the class instance type
########################################################################
# back to wrapt
########################################################################

########################################################################
# Pie Throttle Decorator
########################################################################


########################################################################
# FuncWithThrottleAttr[F] class
########################################################################
class FuncWithThrottleAttr(Protocol[F]):
    """Class to allow type checking on function with attribute."""

    throttle: Throttle
    __call__: F

    def __get__(
        self,
        instance: Any,  # noqa: ANN401
        owner: type[Any],
    ) -> FuncWithThrottleAttr[Any]:
        """Satisfy typing."""
        ...


# ======================================================================
# GROUP 1: Direct Decoration via `@throttle` (On the OUTSIDE/ABOVE)
# ======================================================================


# 1a. Explicitly handle @classmethod descriptors
@overload
def throttle[**P, R](
    _wrapped: classmethod[Any, P, R],
    *,
    reqs_per_sec: float = 1,
    bucket_size: float = 1,
    convert_to_async: Literal[True],
) -> FuncWithThrottleAttr[Callable[P, Coroutine[Any, Any, R]]]: ...


@overload
def throttle[**P, R](
    _wrapped: classmethod[Any, P, R],
    *,
    reqs_per_sec: float = 1,
    bucket_size: float = 1,
    convert_to_async: Literal[False] = False,
) -> FuncWithThrottleAttr[Callable[P, R]]: ...


# 1b. Explicitly handle @staticmethod descriptors
@overload
def throttle[**P, R](
    _wrapped: staticmethod[P, R],
    *,
    reqs_per_sec: float = 1,
    bucket_size: float = 1,
    convert_to_async: Literal[True],
) -> FuncWithThrottleAttr[Callable[P, Coroutine[Any, Any, R]]]: ...


@overload
def throttle[**P, R](
    _wrapped: staticmethod[P, R],
    *,
    reqs_per_sec: float = 1,
    bucket_size: float = 1,
    convert_to_async: Literal[False] = False,
) -> FuncWithThrottleAttr[Callable[P, R]]: ...


# 1d. Standard Functions -> Keep Sync behavior
@overload
def throttle[F: Callable[..., Any]](
    _wrapped: F,
    *,
    reqs_per_sec: float = 1,
    bucket_size: float = 1,
    convert_to_async: Literal[False] = False,
) -> FuncWithThrottleAttr[F]: ...


# 1e. Instance Methods -> Async Conversion
@overload
def throttle[SelfT, **P, R](
    _wrapped: Callable[Concatenate[SelfT, P], R],
    *,
    reqs_per_sec: float = 1,
    bucket_size: float = 1,
    convert_to_async: Literal[True],
) -> FuncWithThrottleAttr[Callable[P, Coroutine[Any, Any, R]]]: ...


# 1f. Instance Methods -> Keep Sync behavior
@overload
def throttle[SelfT, **P, R](
    _wrapped: Callable[Concatenate[SelfT, P], R],
    *,
    reqs_per_sec: float = 1,
    bucket_size: float = 1,
    convert_to_async: Literal[False] = False,
) -> FuncWithThrottleAttr[Callable[P, R]]: ...


# 1g. Fallback for dynamic booleans (Direct decoration)
@overload
def throttle[F: Callable[..., Any]](
    _wrapped: F,
    *,
    reqs_per_sec: float = 1,
    bucket_size: float = 1,
    convert_to_async: bool = False,
) -> FuncWithThrottleAttr[Any]: ...


# ======================================================================
# GROUP 2: Factory Decoration via `@throttle(reqs_per_sec=2)`
# ======================================================================


# 2a. Factory -> Async Conversion (Handles both functions and methods
# seamlessly)
@overload
def throttle(
    _wrapped: None = None,
    *,
    reqs_per_sec: float = 1,
    bucket_size: float = 1,
    convert_to_async: Literal[True],
) -> Callable[[F], FuncWithThrottleAttr[Any]]: ...


# 2b. Factory -> Keep Sync behavior (Preserves original F signature
# accurately)
@overload
def throttle(
    _wrapped: None = None,
    *,
    reqs_per_sec: float = 1,
    bucket_size: float = 1,
    convert_to_async: Literal[False] = False,
) -> Callable[[F], FuncWithThrottleAttr[F]]: ...


# 2c. Fallback for dynamic booleans (Factory style)
@overload
def throttle(
    _wrapped: None = None,
    *,
    reqs_per_sec: float = 1,
    bucket_size: float = 1,
    convert_to_async: bool = False,
) -> Callable[[F], FuncWithThrottleAttr[Any]]: ...


@validate_call
def throttle[F: Callable[..., Any]](
    _wrapped: (
        InstanceOf[classmethod[Any, Any, Any]]
        | InstanceOf[staticmethod[Any, Any]]
        | F
        | None
    ) = None,
    *,
    reqs_per_sec: float = Field(gt=0, default=1),
    bucket_size: float = Field(ge=1, default=1),
    convert_to_async: bool = Field(default=False),
) -> Any:
    """Wrap function in a throttle.

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
        convert_to_async: When True, convert a non-asyncio function to
                          be defined as an async function. This will
                          allow the caller to invoke the decorated
                          function using a proper asyncio method such as
                          *await*. The default is False.

    Returns:
        A callable or awaitable function that delays the request as
        needed in accordance with the specified limits.


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
    #     args:
    #
    # >> line 1:  @throttle
    # >> line 2:  def a_func():
    # >> line 3:      print('42')
    #
    #     This is what essentially happens under the covers:
    # >> line 1:  def a_func():
    # >> line 2:      print('42')
    # >> line 3:  a_func = throttle()(a_func)
    #
    #     The call to throttle results in a function being returned that
    #     takes as its first argument the a_func specification that we
    #     see in parens immediately following the throttle call.
    #
    #     Here's another variation will accomplish the same thing:
    # >> line 1:  def a_func():
    # >> line 2:      print('42')
    # >> line 1:  a_func = throttle(a_func)
    #
    #     What happens is throttle gets control and tests whether a_func
    #     was specified, and if not returns a call to functools.partial
    #     which is the function that accepts the a_func
    #     specification and then calls throttle with a_func as the first
    #     argument.
    #
    #     Note that wrapt constructs are employed to ensure correct
    #     introspection and support different cases, such as static
    #     and class methods.
    # ==================================================================

    if _wrapped is None:
        return PartialCallableObjectProxy(
            throttle,
            reqs_per_sec=reqs_per_sec,
            bucket_size=bucket_size,
            convert_to_async=convert_to_async,
        )

    wrapped_func = getattr(_wrapped, "__func__", _wrapped)
    func_name = getattr(wrapped_func, "__name__", "unknown_callable")
    a_throttle = Throttle(
        reqs_per_sec=reqs_per_sec,
        bucket_size=bucket_size,
        convert_to_async=convert_to_async,
        name=func_name,
    )

    def t_decorator(
        wrapped: classmethod[Any, Any, Any] | staticmethod[Any, Any] | F,
    ) -> FunctionWrapper[
        _P1,
        _R1_co,
    ]:
        target = getattr(wrapped, "__func__", wrapped)
        is_async_func = inspect.iscoroutinefunction(target)

        @decorator
        def sync_wrapper(
            wrapped_func: Callable[P, Any],
            instance: Any,  # noqa: ANN401, ARG001
            args: tuple[Any, ...],
            kwargs: dict[str, Any],
        ) -> Any:  # noqa: ANN401

            return a_throttle.sync_send_request(wrapped_func, *args, **kwargs)

        @decorator
        async def async_wrapper(
            wrapped_func: Callable[P, Coroutine[Any, Any, Any]],
            instance: Any,  # noqa: ANN401, ARG001
            args: tuple[Any, ...],
            kwargs: dict[str, Any],
        ) -> Any:  # noqa: ANN401

            return await a_throttle.async_send_request(wrapped_func, *args, **kwargs)

        if is_async_func or convert_to_async:
            return async_wrapper(wrapped)
        return sync_wrapper(wrapped)

    wrapper = cast("FuncWithThrottleAttr[Any]", t_decorator(_wrapped))

    wrapper.throttle = a_throttle

    return wrapper
