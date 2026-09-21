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
import contextvars
import inspect
from collections.abc import Coroutine
from typing import (
    Any,
    Callable,
    cast,
    Concatenate,
    Literal,
    overload,
    ParamSpec,
    TypeVar,
)

from pydantic import validate_call, Field
########################################################################
# Third Party
########################################################################
from wrapt import PartialCallableObjectProxy
from wrapt.wrappers import BoundFunctionWrapper
from wrapt.wrappers import FunctionWrapper

from scottbrian_throttle.throttle_blocks import Throttle

########################################################################
# Local
########################################################################


active_state_ctx: contextvars.ContextVar[Throttle] = contextvars.ContextVar(
    "active_state"
)

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
# _StatefulBoundWrapper
########################################################################
class _StatefulBoundWrapper(BoundFunctionWrapper[P, R]):
    @property
    def throttle(self) -> Throttle:
        try:
            return active_state_ctx.get()
        except LookupError:
            pass
        w = self._self_parent
        inst = self._self_instance
        c_type = inst if isinstance(inst, type) else inst.__class__
        key = f"_th_{w._method_name}_{c_type.__name__}_{id(w)}"
        if not hasattr(inst, key):
            setattr(
                inst,
                key,
                Throttle(
                    reqs_per_sec=w._reqs_per_sec,
                    bucket_size=w._bucket_size,
                    convert_to_async=w._convert_to_async,
                    name=w._method_name,
                ),
            )
        return cast(Throttle, getattr(inst, key))


########################################################################
# _StatefulFunctionWrapper
########################################################################
class _StatefulFunctionWrapper(FunctionWrapper[P, R]):
    __bound_function_wrapper__: Any = _StatefulBoundWrapper

    def __init__(
        self,
        wrapped: Any,
        wrapper_func: Any,
        method_name: str,
        reqs_per_sec: float,
        bucket_size: float,
        convert_to_async: bool,
        name: str,
    ) -> None:
        super().__init__(wrapped, wrapper_func)
        self._method_name = method_name
        self._reqs_per_sec = reqs_per_sec
        self._bucket_size = bucket_size
        self._convert_to_async = convert_to_async
        self.name = name

    @property
    def throttle(self) -> Throttle:
        try:
            return active_state_ctx.get()
        except LookupError:
            pass
        key = f"_th_{self._method_name}_static_{id(self)}"
        if not hasattr(self.__wrapped__, key):
            setattr(
                self.__wrapped__,
                key,
                Throttle(
                    reqs_per_sec=self._reqs_per_sec,
                    bucket_size=self._bucket_size,
                    convert_to_async=self._convert_to_async,
                    name=self._method_name,
                ),
            )
        return cast(Throttle, getattr(self.__wrapped__, key))

    @overload
    def __get__(
        self: _StatefulFunctionWrapper[Concatenate[_T, _P2], _R2],
        instance: _T,
        owner: type[Any] | None = None,
        /,
    ) -> _StatefulBoundWrapper[_P2, _R2]:
        ...

    @overload
    def __get__(
        self: _StatefulFunctionWrapper[Concatenate[_T, _P2], _R2],
        instance: _T,
        owner: type[_T] | None = None,
        /,
    ) -> _StatefulBoundWrapper[_P2, _R2]:
        ...

    @overload
    def __get__(
        self,
        instance: None,
        owner: type[Any] | None = None,
        /,
    ) -> _StatefulFunctionWrapper[P, R]:
        ...

    @overload
    def __get__(
        self,
        instance: Any,
        owner: type[Any] | None = None,
        /,
    ) -> _StatefulBoundWrapper[Any, Any]:
        ...

    def __get__(
        self,
        instance: Any,
        owner: type[Any] | None = None,
        /,
    ) -> Any:
        return super().__get__(instance, owner)


########################################################################
# @throttle
########################################################################
@overload
def throttle(
    _wrapped: Callable[P, R],
    *,
    reqs_per_sec: float = 1,
    bucket_size: float = 1,
    convert_to_async: Literal[True],
) -> _StatefulFunctionWrapper[P, Coroutine[Any, Any, R]]:
    ...


@overload
def throttle(
    _wrapped: Callable[P, R],
    *,
    reqs_per_sec: float = 1,
    bucket_size: float = 1,
    convert_to_async: Literal[False] = False,
) -> _StatefulFunctionWrapper[P, R]:
    ...


@overload
def throttle(
    _wrapped: Callable[P, R],
    *,
    reqs_per_sec: float = 1,
    bucket_size: float = 1,
    convert_to_async: bool = False,
) -> _StatefulFunctionWrapper[P, Any]:
    ...


@overload
def throttle(
    _wrapped: None = None,
    *,
    reqs_per_sec: float = 1,
    bucket_size: float = 1,
    convert_to_async: Literal[True],
) -> Callable[
    [Callable[P, R]], _StatefulFunctionWrapper[P, Coroutine[Any, Any, R]]
]:
    ...


@overload
def throttle(
    _wrapped: None = None,
    *,
    reqs_per_sec: float = 1,
    bucket_size: float = 1,
    convert_to_async: Literal[False] = False,
) -> Callable[[Callable[P, R]], _StatefulFunctionWrapper[P, R]]:
    ...


@overload
def throttle(
    _wrapped: None = None,
    *,
    reqs_per_sec: float = 1,
    bucket_size: float = 1,
    convert_to_async: bool = False,
) -> Callable[[Callable[P, R]], _StatefulFunctionWrapper[P, Any]]:
    ...


@validate_call
def throttle(
    _wrapped: F | None = None,
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

    def t_decorator(wrapped: F) -> _StatefulFunctionWrapper[Any, Any]:
        method_name = wrapped.__name__
        is_async_func = inspect.iscoroutinefunction(wrapped)

        def sync__core_execution_logic(
            wrapped_func: F,
            instance: object,
            args: tuple[Any, ...],
            kwargs: dict[str, Any],
        ) -> Any:
            # Resolve target mapping
            if instance is not None:
                c_type = instance if isinstance(instance, type) else instance.__class__
                key = f"_th_{method_name}_{c_type.__name__}_{id(proxy)}"
                target = instance
            else:
                key = f"_th_{method_name}_static_{id(proxy)}"
                target = wrapped_func

            if not hasattr(target, key):
                setattr(
                    target,
                    key,
                    Throttle(
                        reqs_per_sec=reqs_per_sec,
                        bucket_size=bucket_size,
                        convert_to_async=convert_to_async,
                        name=method_name,
                    ),
                )
            state = getattr(target, key)

            token = active_state_ctx.set(state)
            try:
                # return wrapped_func(*args, **kwargs)
                return state.sync_send_request(wrapped_func, *args, **kwargs)
            finally:
                active_state_ctx.reset(token)

        async def async__core_execution_logic(
            wrapped_func: F,
            instance: object,
            args: tuple[Any, ...],
            kwargs: dict[str, Any],
        ) -> Any:
            # Resolve target mapping
            if instance is not None:
                c_type = instance if isinstance(instance, type) else instance.__class__
                key = f"_th_{method_name}_{c_type.__name__}_{id(proxy)}"
                target = instance
            else:
                key = f"_th_{method_name}_static_{id(proxy)}"
                target = wrapped_func

            if not hasattr(target, key):
                setattr(
                    target,
                    key,
                    Throttle(
                        reqs_per_sec=reqs_per_sec,
                        bucket_size=bucket_size,
                        convert_to_async=convert_to_async,
                        name=method_name,
                    ),
                )
            state = getattr(target, key)

            token = active_state_ctx.set(state)
            try:
                # return wrapped_func(*args, **kwargs)
                return await state.async_send_request(wrapped_func, *args, **kwargs)
            finally:
                active_state_ctx.reset(token)

        if is_async_func or convert_to_async:
            _core_execution_logic = async__core_execution_logic
        else:
            _core_execution_logic = sync__core_execution_logic

        proxy: _StatefulFunctionWrapper[Any, Any] = _StatefulFunctionWrapper(
            _wrapped,
            _core_execution_logic,
            method_name,
            reqs_per_sec,
            bucket_size,
            convert_to_async,
            method_name,
        )
        return proxy

    return t_decorator(_wrapped)
