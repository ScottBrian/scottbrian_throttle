import asyncio
import threading
from contextlib import contextmanager

import wrapt


class StatefulMethodProxy(wrapt.ObjectProxy):
    """A thread-and-async-safe proxy that enables custom states and teardowns."""

    def __init__(self, wrapped_method):
        super().__init__(wrapped_method)
        # Internal state dictionary allocation
        object.__setattr__(
            self, "__dict__", {"count": 0, "status": "idle", "history": []}
        )
        # Thread lock for synchronous execution paths
        object.__setattr__(self, "_thread_lock", threading.Lock())
        # Lazy-loaded Asyncio lock for asynchronous execution paths
        object.__setattr__(self, "_async_lock", None)

    def __getattr__(self, name):
        try:
            return super().__getattr__(name)
        except AttributeError:
            return self.__dict__[name]

    def __setattr__(self, name, value):
        self.__dict__[name] = value

    @contextmanager
    def teardown_context(self):
        """Context manager allowing users to cleanly reset state metrics on error."""
        try:
            yield self
        except Exception:
            # Automatic teardown routine triggered upon code failures
            with self._thread_lock:
                self.status = "idle (recovered via teardown)"
                self.history.append("Teardown executed: State automatically cleared.")
            raise

    def get_async_lock(self):
        """Lazily initialize the asyncio lock inside the running event loop."""
        if self._async_lock is None:
            self._async_lock = asyncio.Lock()
        return self._async_lock


class ConfigurableTracker:
    """Configurable tracker tracking separate sync & async method calls."""

    def __init__(self, initial_status, increment_by):
        self.initial_status = initial_status
        self.increment_by = increment_by
        self._proxy_cache = weakref.WeakKeyDictionary()
        self._cache_lock = threading.Lock()

    def __call__(self, wrapped, instance, args, kwargs):
        if instance is None:
            return wrapped(*args, **kwargs)

        proxy = self._get_or_create_proxy(instance, wrapped)

        # ROUTE 1: Asynchronous Execution Path
        if inspect.iscoroutinefunction(wrapped):

            async def async_wrapper():
                async_lock = proxy.get_async_lock()
                async with async_lock:
                    proxy.count += self.increment_by
                    proxy.status = "running"
                    proxy.history.append(f"Async processing: {args}")
                try:
                    result = await wrapped(*args, **kwargs)
                    async with async_lock:
                        proxy.status = "success"
                    return result
                except Exception as e:
                    async with async_lock:
                        proxy.status = f"failed: {type(e).__name__}"
                    raise e

            return async_wrapper()

        # ROUTE 2: Synchronous Execution Path
        else:
            with proxy._thread_lock:
                proxy.count += self.increment_by
                proxy.status = "running"
                proxy.history.append(f"Sync processing: {args}")
            try:
                result = wrapped(*args, **kwargs)
                with proxy._thread_lock:
                    proxy.status = "success"
                return result
            except Exception as e:
                with proxy._thread_lock:
                    proxy.status = f"failed: {type(e).__name__}"
                raise e

    def _get_or_create_proxy(self, instance, wrapped):
        with self._cache_lock:
            if instance not in self._proxy_cache:
                bound_method = getattr(instance, wrapped.__name__)
                proxy = StatefulMethodProxy(bound_method)
                proxy.status = self.initial_status
                self._proxy_cache[instance] = proxy
            return self._proxy_cache[instance]

    def __get__(self, instance, owner):
        if instance is None:
            return self
        return self._get_or_create_proxy(instance, self._self_wrapped)


class CustomDecoratorWrapper(wrapt.FunctionWrapper):
    """Exposes descriptor bindings natively past wrapt core restrictions."""

    def __get__(self, instance, owner):
        return self._self_wrapper.__get__(instance, owner)


def track_state(initial_status="initialized", increment_by=1):
    """The master decorator factory supporting parameters, sync, and async."""

    def decorator(wrapped):
        tracker = ConfigurableTracker(
            initial_status=initial_status, increment_by=increment_by
        )
        return CustomDecoratorWrapper(wrapped, tracker)

    return decorator



#####################################
# latest
#####################################
"""

To handle failed states and execute custom callback functions, 
pass the callbacks directly as arguments into the outermost @track_state 
decorator factory.
To make this architecture production-grade, the tracker must dynamically 
inspect if the provided callbacks are synchronous functions or asynchronous coroutines.
 This prevents blocking errors when mixing execution contexts.
 Enhanced Parameterized Architecture with CallbacksHere is the complete 
 implementation incorporating on-success and on-failure callbacks, 
 supporting both sync and async operations seamlessly:
"""


pythonimport asyncio
import inspect
import threading
import weakref
import wrapt

class StatefulMethodProxy(wrapt.ObjectProxy):
    """A thread-and-async-safe proxy that holds instance-isolated state data."""
    def __init__(self, wrapped_method):
        super().__init__(wrapped_method)
        object.__setattr__(self, '__dict__', {
            'count': 0,
            'status': 'idle',
            'history': [],
            'last_exception': None
        })
        object.__setattr__(self, '_thread_lock', threading.Lock())
        object.__setattr__(self, '_async_lock', None)

    def __getattr__(self, name):
        try:
            return super().__getattr__(name)
        except AttributeError:
            return self.__dict__[name]

    def __setattr__(self, name, value):
        self.__dict__[name] = value

    def get_async_lock(self):
        if self._async_lock is None:
            self._async_lock = asyncio.Lock()
        return self._async_lock


class ConfigurableTracker:
    """Tracks state and safely invokes user-defined callback hooks."""
    def __init__(self, initial_status, increment_by, on_success=None, on_failure=None):
        self.initial_status = initial_status
        self.increment_by = increment_by
        self.on_success_callback = on_success
        self.on_failure_callback = on_failure

        self._proxy_cache = weakref.WeakKeyDictionary()
        self._cache_lock = threading.Lock()

    def _execute_callback(self, callback, instance, proxy, exception=None):
        """Helper to invoke a callback safely based on its sync/async signature."""
        if not callback:
            return

        # Build the payload to feed into the user's custom callback
        kwargs = {'instance': instance, 'proxy': proxy}
        if exception:
            kwargs['exception'] = exception

        if inspect.iscoroutinefunction(callback):
            # If the callback is async, schedule it safely on the active event loop
            try:
                loop = asyncio.get_running_loop()
                loop.create_task(callback(**kwargs))
            except RuntimeError:
                # Fallback if no loop is running in the current thread
                asyncio.run(callback(**kwargs))
        else:
            # Standard synchronous callback execution
            callback(**kwargs)

    def __call__(self, wrapped, instance, args, kwargs):
        if instance is None:
            return wrapped(*args, **kwargs)

        proxy = self._get_or_create_proxy(instance, wrapped)

        # ROUTE 1: Asynchronous Execution Path
        if inspect.iscoroutinefunction(wrapped):
            async def async_wrapper():
                async_lock = proxy.get_async_lock()
                async with async_lock:
                    proxy.count += self.increment_by
                    proxy.status = 'running'
                try:
                    result = await wrapped(*args, **kwargs)
                    async with async_lock:
                        proxy.status = 'success'
                        proxy.last_exception = None
                    self._execute_callback(self.on_success_callback, instance, proxy)
                    return result
                except Exception as e:
                    async with async_lock:
                        proxy.status = 'failed'
                        proxy.last_exception = e
                    self._execute_callback(self.on_failure_callback, instance, proxy, exception=e)
                    raise e
            return async_wrapper()

        # ROUTE 2: Synchronous Execution Path
        else:
            with proxy._thread_lock:
                proxy.count += self.increment_by
                proxy.status = 'running'
            try:
                result = wrapped(*args, **kwargs)
                with proxy._thread_lock:
                    proxy.status = 'success'
                    proxy.last_exception = None
                self._execute_callback(self.on_success_callback, instance, proxy)
                return result
            except Exception as e:
                with proxy._thread_lock:
                    proxy.status = 'failed'
                    proxy.last_exception = e
                self._execute_callback(self.on_failure_callback, instance, proxy, exception=e)
                raise e

    def _get_or_create_proxy(self, instance, wrapped):
        with self._cache_lock:
            if instance not in self._proxy_cache:
                bound_method = getattr(instance, wrapped.__name__)
                proxy = StatefulMethodProxy(bound_method)
                proxy.status = self.initial_status
                self._proxy_cache[instance] = proxy
            return self._proxy_cache[instance]

    def __get__(self, instance, owner):
        if instance is None:
            return self
        return self._get_or_create_proxy(instance, self._self_wrapped)


class CustomDecoratorWrapper(wrapt.FunctionWrapper):
    def __get__(self, instance, owner):
        return self._self_wrapper.__get__(instance, owner)


def track_state(initial_status='initialized', increment_by=1, on_success=None, on_failure=None):
    """The master factory decorator allowing configuration and callback injection."""
    def decorator(wrapped):
        tracker = ConfigurableTracker(
            initial_status=initial_status,
            increment_by=increment_by,
            on_success=on_success,
            on_failure=on_failure
        )
        return CustomDecoratorWrapper(wrapped, tracker)