===================
scottbrian-throttle
===================

Intro
=====

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


You can specify the limit with the *reqs_per_sec* parameter as a float
or int of any value greater than 0. The interval is calculated as
1/*reqs_per_sec*. Some examples:

    1) *reqs_per_sec=2* will be an interval of 1/2 seconds.
    2) *reqs_per_sec=1* will be an interval of 1 second
    3) *reqs_per_sec=0.5* will be an interval of 2 seconds


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


:Expected output for Example 2::

.. code-block:: text

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

The throttle can be used on an async defined function or a non-async
function.

When the throttle is used to decorate an async defined function, the
caller is expected to be running in an asyncio environment and to invoke
the function using the proper asyncio method, such as using await. For
this scenario, the throttle will use asyncio.sleep as needed to delay
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
    2) the caller can specify *convert_to_async=True* as an argument to
       the throttle to cause the wrapper to be defined as an async
       function. In this scenario, the caller can invoke the function
       using the proper asyncio method, such as using await. The
       throttle will use asyncio.sleep as needed to delay the function
       and will use asyncio.to_thread to run the sync function in a
       separate thread.

:Example 3: throttle with async function in asyncio environment:

.. code-block:: python

    from scottbrian_throttle.throttle import throttle
    import time
    import asyncio

    @throttle(reqs_per_sec=2)
    async def func3(request_number, time_of_start):
        print(f'request {request_number} sent at elapsed time: '
              f'{time.time() - time_of_start:0.1f}')

    async def main_loop():
        start_time = time.time()
        for idx in range(10):
            await func3(idx, start_time)

    asyncio.run(main_loop())

:Expected output for Example 3::

. code-block:: text

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



:Example 4: throttle with non-async function in asyncio environment:

.. code-block:: python

    from scottbrian_throttle.throttle import throttle
    import time
    import asyncio

    @throttle(reqs_per_sec=2)
    def func4(request_number, time_of_start):
        print(f'request {request_number} sent at elapsed time: '
              f'{time.time() - time_of_start:0.1f}')

    async def main_loop():
        start_time = time.time()
        for idx in range(10):
            await asyncio.to_thread(func4, idx, start_time)

    asyncio.run(main_loop())

:Expected output for Example 4::

.. code-block:: text

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

:Example 5: throttle with convert_to_async in asyncio environment:

.. code-block:: python

    from scottbrian_throttle.throttle import throttle
    import time
    import asyncio

    @throttle(reqs_per_sec=2, convert_to_async=True)
    def func5(request_number, time_of_start):
        print(f'request {request_number} sent at elapsed time: '
              f'{time.time() - time_of_start:0.1f}')

    async def main_loop():
        start_time = time.time()
        for idx in range(10):
            await func5(idx, start_time)

    asyncio.run(main_loop())

:Expected output for Example 5::

.. code-block:: text

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

The throttle as leaky bucket:
=============================

The throttle is implemented as a leaky bucket. Each call to your
throttle decorated function is represented as an interval of time that
is conceptually placed into the bucket. The bucket has a hole in the
bottom that leaks out at the interval rate. The bucket starts out empty.
The first call to your function is "placed" into the empty bucket and
allowed to run without delay. On each subsequent call, if the
bucket still has the previous call leaking out, the new call is delayed
until the bucket has room for it.

You can also specify a larger bucket with the *bucket_size* parameter.
Setting *bucket_size=2*, for example, will allow the first two calls to
run immediately. Subsequent calls will be delayed until the bucket has
leaked out enough to fit a new call. If no calls are made for some time,
the bucket will become empty and allow the full bucket size number of
calls to again run immediately.

A throttle configured as a large bucket will act like a shock absorber,
allowing small bursts of function calls to run without delay. The
limiting action kicks in as additional calls continue to rapidly arrive.
Note that the average request interval will decrease as the size of the
bucket increases.

:Example 6: throttle with a *bucket_size* of 3:

.. code-block:: python

    from scottbrian_throttle.throttle import Throttle
    import time

    @throttle(reqs_per_sec=2, bucket_size=3)
    def func6(request_number, time_of_start):
        print(f'request {request_number} sent at elapsed time: '
              f'{time.time() - time_of_start:0.1f}')
    start_time = time.time()
    for idx in range(10):
        func6(idx, start_time)


:Expected output for Example 4::

.. code-block:: text

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

You can specify *bucket_size* as a float or int greater than 1. A
*bucket_size=2.5*, for example, would mean that given 4 calls in
rapid succession, the first 2 requests would be sent immediately, the
third delayed for half an interval, and the fourth delayed for a full
interval.

.. image:: https://img.shields.io/badge/security-bandit-yellow.svg
    :target: https://github.com/PyCQA/bandit
    :alt: Security Status

.. image:: https://readthedocs.org/projects/pip/badge/?version=stable
    :target: https://pip.pypa.io/en/stable/?badge=stable
    :alt: Documentation Status


Installation
============

Windows:

``pip install scottbrian-throttle``


Development setup
=================

See tox.ini


Release History
===============

* 1.0.0
    * Initial release


Meta
====

Scott Tuttle

Distributed under the MIT license. See ``LICENSE`` for more information.


Contributing
============

1. Fork it (<https://github.com/yourname/yourproject/fork>)
2. Create your feature branch (`git checkout -b feature/fooBar`)
3. Commit your changes (`git commit -am 'Add some fooBar'`)
4. Push to the branch (`git push origin feature/fooBar`)
5. Create a new Pull Request
