===================
scottbrian-throttle
===================

Intro
=====

The Throttle allows you to limit the rate at which a function is
called. An internet service, for example, might have a limit for the
number of requests you can send in a given interval - using the
Throttle will help you stay within that limit.

The Throttle is a decorator that wraps your function with code that
keeps track of the intervals between each invocation. The Throttle will
delay the running of your function to stay within the limit. By default,
the Throttle maintains a limit of 1 call per second.

:Example 1: Throttle at 1 requests per second:

.. code-block:: python

    from scottbrian_throttle.throttle import Throttle

    @Throttle
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

:Example 2: Throttle at 2 requests per second:

.. code-block:: python

    from scottbrian_throttle.throttle import Throttle
    import time

    @Throttle(reqs_per_sec=2)
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


Using an asynchronous Throttle
==============================

By default, the Throttle is synchronous - when you call your function
you will not get back control until your function has completed. This
means you will observe any delay imposed by the Throttle. The Throttle
also provides an asynchronous mode that queues your function to a queue
to be run from a separate thread. This frees up your application to
perform other work while the throttled functions are being delayed.

:Example 3: asynchronous throttle:

.. code-block:: python

    from scottbrian_throttle.throttle import Throttle
    import time

    @Throttle(reqs_per_sec=2, throttle_mode=ThrottleMode.ASYNC)
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


Some additional thoughts:
You can specify *reqs_per_sec* as a float or int of any value. For
example, *reqs_per_sec=0.5* will mean a limit of 1 request every 2
seconds, or perhaps *reqs_per_sec=1.33* for a limit close to 1 request
every 3/4 of a second. The rate interval is calculated as
1/*reqs_per_sec*. You can obtain the interval by calling
*get_interval_secs* or, in nanoseconds, *get_interval_ns*.

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
