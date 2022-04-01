===================
scottbrian-throttle
===================

Intro
=====


With **@throttle** you can control the frequency at which a function is executed to avoid exceeding a limit.
This is useful for internet services that have a stated limit, such as "no more than one request per second".

The @throttle decorator wraps a method that makes requests to ensure that the limit is not exceeded. The @throttle
keeps track of the time for each request and will insert a wait as needed to stay within the limit. Note that the
Throttle class provides the same service to allow you to use the throttle where a decorator is not the optimal choice.

To use the throttle, you specify the number of requests, the number of seconds, and one of four modes that control the
throttle behavior:

    1) **mode=Throttle.MODE_ASYNC** specifies asynchronous mode.
                   With asynchronous throttling,
                   each request is placed on a queue and control returns
                   to the caller. A separate thread then executes each
                   request at a steady interval to achieve the specified
                   number of requests per the specified number of seconds.
    2) **mode=Throttle.MODE_SYNC** specifies synchronous mode.
                   For synchronous throttling, the caller may be blocked to
                   delay the request in order to achieve the specified
                   number of requests per the specified number of seconds.
    3) **mode=Throttle.MODE_SYNC_EC** specifies synchronous mode using an early arrival algorithm.
                   For synchronous throttling with the early
                   arrival algorithm, you specify an *early_count* which is the number of requests that can be sent
                   immediately without delay. Once the *early_count* is reached, the throttle kicks in and the next
                   request is delayed by a cumulative amount that will ensure that the average sent rate for the
                   requests sent up to this point is within the rate as specified by the number of requests per number
                   of seconds.
    4) **mode=Throttle.MODE_SYNC_LB** specifies synchronous mode
                   using a leaky bucket algorithm.
                   For synchronous throttling with the leaky bucket
                   algorithm, you specify the *lb_threshold* value which is the number of requests that will fit into
                   the bucket. As each request is received, it is placed in the bucket and sent. The bucket leaks at a
                   fixed rate such that each new request will fit given the send rate is within the limit specifed by
                   the number of requests per number of seconds. If the bucket become full and can not hold any
                   additional requests, the request will be delayed until the bucket can hold them. Unlike the early
                   count algorithm, the leaky bucket algorithm results in an average send rate that is less than
                   the rate as specified by the *requests* and *seconds* arguments.

:Example: throttle a request loop to 3 requests per second

In the following code, make_request will be called 10 times in rapid succession. The first request will be sent
immediately, and the remaining requests will each be delayed by 1/2 second.

>>> from scottbrian_throttle.throttle import Throttle, throttle
>>> import time
>>> @throttle(requests=2, seconds=1, mode=Throttle.MODE_SYNC)
... def make_request(request_number, time_of_start):
...     print(f'request {request_number} sent at elapsed time: {time.time() - time_of_start:0.1f}')
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


.. image:: https://img.shields.io/badge/security-bandit-yellow.svg
    :target: https://github.com/PyCQA/bandit
    :alt: Security Status

.. image:: https://readthedocs.org/projects/pip/badge/?version=stable
    :target: https://pip.pypa.io/en/stable/?badge=stable
    :alt: Documentation Status


Installation
============

Linux:

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
