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
import logging
from collections.abc import Coroutine
from typing import (
    Any,
    Callable,
    cast,
    # Concatenate,
    # Literal,
    # overload,
    ParamSpec,
    Protocol,
    TypeVar,
)

from pydantic import Field, validate_call, InstanceOf
from wrapt import PartialCallableObjectProxy
########################################################################
# Third Party
########################################################################
from wrapt import decorator

from scottbrian_throttle.throttle_blocks import Throttle

logger = logging.getLogger(__name__)
########################################################################
# Local
########################################################################

########################################################################
# Pie Throttle Decorator
########################################################################
P = ParamSpec("P")
R = TypeVar("R")
F = TypeVar("F", bound=Callable[..., Any])

_T = TypeVar("_T")
_P2 = ParamSpec("_P2")
_R2 = TypeVar("_R2")

########################################################################
# back to wrapt
########################################################################

########################################################################
# Pie Throttle Decorator
########################################################################
# F = TypeVar("F", bound=Callable[..., Any])


########################################################################
# FuncWithThrottleAttr[F] class
########################################################################
class FuncWithThrottleAttr[F](Protocol[F]):
    """Class to allow type checking on function with attribute."""

    throttle: Throttle
    __call__: F


def add_throttle_sync_attr(func: F) -> FuncWithThrottleAttr[F]:
    """Wrapper to add throttle attribute to function.

    Args:
        func: function that has the attribute added

    Returns:
        input function with throttle attached as attribute

    """
    return cast(FuncWithThrottleAttr[F], func)


# @overload
# def throttle(
#     _wrapped: Callable[P, R],
#     *,
#     reqs_per_sec: float = 1,
#     bucket_size: float = 1,
#     convert_to_async: Literal[True],
# ) -> _StatefulFunctionWrapper[P, Coroutine[Any, Any, R]]: ...
#
#
# @overload
# def throttle(
#     _wrapped: Callable[P, R],
#     *,
#     reqs_per_sec: float = 1,
#     bucket_size: float = 1,
#     convert_to_async: Literal[False] = False,
# ) -> _StatefulFunctionWrapper[P, R]: ...
#
#
# @overload
# def throttle(
#     _wrapped: Callable[P, R],
#     *,
#     reqs_per_sec: float = 1,
#     bucket_size: float = 1,
#     convert_to_async: bool = False,
# ) -> _StatefulFunctionWrapper[P, Any]: ...
#
#
# @overload
# def throttle(
#     _wrapped: None = None,
#     *,
#     reqs_per_sec: float = 1,
#     bucket_size: float = 1,
#     convert_to_async: Literal[True],
# ) -> Callable[
#     [Callable[P, R]], [P, Coroutine[Any, Any, R]]
# ]: ...
#
#
# @overload
# def throttle(
#     _wrapped: None = None,
#     *,
#     reqs_per_sec: float = 1,
#     bucket_size: float = 1,
#     convert_to_async: Literal[False] = False,
# ) -> Callable[[Callable[P, R]], FuncWithThrottleAttr[F]]: ...
#
#
# @overload
# def throttle(
#     _wrapped: None = None,
#     *,
#     reqs_per_sec: float = 1,
#     bucket_size: float = 1,
#     convert_to_async: bool = False,
# ) -> Callable[[Callable[P, R]], FuncWithThrottleAttr[F]]: ...


@validate_call
def throttle(
    _wrapped: InstanceOf[classmethod] | InstanceOf[staticmethod] | F | None = None,
    *,
    reqs_per_sec: float = Field(gt=0, default=1),
    bucket_size: float = Field(ge=1, default=1),
    convert_to_async: bool = Field(default=False),
) -> Any:
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
    #         args:
    #         @throttle
    #         def a_func():
    #             print('42')
    #
    #     This is what essentially happens under the covers:
    #         def a_func():
    #             print('42')
    #         a_func = throttle()(a_func)
    #
    #     The call to throttle results in a function being returned that
    #     takes as its first argument the a_func specification that we
    #     see in parens immediately following the throttle call.
    #
    #     Here's another variation will accomplish the same thing:
    #         def a_func():
    #             print('42')
    #         a_func = throttle(a_func)
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

    a_throttle = Throttle(
        reqs_per_sec=reqs_per_sec,
        bucket_size=bucket_size,
        convert_to_async=convert_to_async,
        name=_wrapped.__name__,
    )

    def t_decorator(wrapped: F) -> Callable[P, R] | Coroutine[Any, Any, R]:
        is_async_func = inspect.iscoroutinefunction(wrapped)

        @decorator
        def sync_wrapper(
            wrapped_func: F,
            instance: object,
            args: tuple[Any, ...],
            kwargs: dict[str, Any],
        ) -> Any:

            return a_throttle.sync_send_request(wrapped_func, *args, **kwargs)

        @decorator
        async def async_wrapper(
            wrapped_func: F,
            instance: object,
            args: tuple[Any, ...],
            kwargs: dict[str, Any],
        ) -> Any:

            return await a_throttle.async_send_request(wrapped_func, *args, **kwargs)

        if is_async_func or convert_to_async:
            return async_wrapper(wrapped)
        else:
            return sync_wrapper(wrapped)

    wrapper = t_decorator(_wrapped)

    wrapper = add_throttle_sync_attr(wrapper)

    wrapper.throttle = a_throttle

    return wrapper

    # return cast(FuncWithThrottleAttr[F], wrapper)
