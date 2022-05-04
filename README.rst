===================
scottbrian-throttle
===================

Intro
=====


The throttle allows you to limit the rate at which a function is executed. This is helpful to avoid exceeding a limit,
such as when sending requests to an internet service that specifies a limit as to the number of requests that can be
sent in a specific time interval.

The throttle package include four different algorithms for the limiting control, each provided as a decorator or as
a class:

  1. **@throttle_sync** decorator and **ThrottleSync** class provide a synchronous algorithm.
                   For synchronous throttling, you specify the *requests* and *seconds* which determine the send rate
                   limit. The throttle keeps track of the intervals between each request and will block only as needed
                   to ensure the send rate limit is not exceeded. This algorithm provides a strict adherence to the
                   send rate limit for those cases that need it.

  2. **@throttle_sync_ec** decorator and **ThrottleSyncEc** class provide an early arrival algorithm.
                   For synchronous throttling with the early arrival algorithm, you specify the *requests* and
                   *seconds* which determine the send rate limit. You also specify an *early_count*, the number of
                   requests the throttle will send immediately without delay. Once the *early_count* is reached, the
                   throttle kicks in and, if needed, delays the next request by a cumulative amount that reflects the
                   current request and the requests that were sent early. This will ensure that the average send rate
                   for all requests stay within the send rate limit. This algorithm is best used when you
                   have a steady stream of requests within the send rate limit, and an occasional burst of requests that
                   the target service will tolerate.

  3. **@throttle_sync_lb** decorator and **ThrottleSyncLb** class provide a leaky bucket algorithm.
                   For synchronous throttling with the leaky bucket algorithm, you specify the *requests* and *seconds*
                   which determine the send rate limit. You also specify an *lb_threshold* value, the number of requests
                   that will fit into a conceptual bucket. As each request is received, if it fits, it is placed into
                   the bucket and is sent. The bucket leaks at a fixed rate that reflects the send rate limit such
                   such that each new request will fit given it does not exceed the send rate limit. If the bucket
                   becomes full, the next request will be delayed until the bucket has leaked enough to hold it, at
                   which time it will be sent. Unlike the early count algorithm, the leaky bucket algorithm results in
                   an average send rate that slightly exceeds the send rate limit. This algorithm is best used when you
                   have a steady stream of requests within the send rate limit, and an occasional burst of requests that
                   the target service will tolerate.

  4. **@throttle_async** decorator and **ThrottleAsync** class provide an asynchronous algorithm.
                   With asynchronous throttling, you specify the *requests* and *seconds* which determine the send rate
                   limit. As each request is received, it is placed on a queue and control returns to the caller. A
                   separate request schedular thread pulls the requests from the queue and sends them at a steady
                   interval to achieve the specified send rate limit. You may also specify an *async_q_size* that
                   determines the number of requests that can build up on the queue before the caller is blocked while
                   trying to add requests. This algorithm provides a strict adherence to the send rate limit without
                   having the delay the user (unless the queue become full). This is best used when you have a steady
                   stream of requests within the send rate limit, and an occasional burst of requests that you do not
                   want to be delayed for. It has an added responsibility that you need to perform a shutdown of the
                   throttle when your program ends to ensure that request schedular thread is properly ended.


Examples
========

Here we are using the **@throttle_sync** decorator to wrap a function that needs to be limited to no more
than 2 executions per second. In the following code, make_request will be called 10 times in rapid succession. The
**@throttle_sync** keeps track of the time for each invocation and will insert a wait as needed to stay within the
limit. The first execution of make_request will be done immediately while the remaining executions will each be delayed
by 1/2 second as seen in the output messages.

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


Here's the same example using the **ThrottleSync** class. Note that the loop now calls send_request, passing
in the make_request function and its arguments:

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
