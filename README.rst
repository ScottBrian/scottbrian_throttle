===================
scottbrian-throttle
===================

Intro
=====


The throttle allows you to limit the rate at which a function is executed. This is helpful to avoid exceeding a limit,
such as when sending requests to an internet service that specifies a limit as to the number of requests that can be
sent in a specific time interval.

The throttle can be used as a class or as a decorator, and can also be synchronous or asynchronous. The req_per_sec
specifies how many requests can be processed per second. The send_request method is used to call the routine that is
being throttled. The throttle_mode specifies whether the each request is processed before returning to the caller
of send_request (throttle_mode=ThrottleMode.SYNC), or each request is queued to processed by another thread
(throttle_mode=ThrottleMode.ASYNC). The throttle also providees a leaky bucket implementation where some number of
requests are allow to be sent immediately before the throttle kicks in. This is controlled with bucket_size which
species the number of requests that can fit into a conceptual bucket before being limited. The bucket leaks as the
request rate and will need to leak out at least one request before the neext request can be placed into the bucket and
sent.


1. Synchronous limiting with strict rate limiting:
       For synchronous throttling, you specify *reqs_per_sec* which determines the send rate limit.
       The throttle keeps track of the intervals between each request and will block only as needed
       to ensure the send rate limit is not exceeded. This algorithm provides a strict adherence to the
       send rate limit for those cases that need it.

1. Synchronous limiting with the leaky buckeet algorithm:
       For synchronous throttling with the leaky bucket algorithm, you specify a *bucket_size* value
       greater than 1. This is the number of requests that will fit into a conceptual bucket.
       You also specify the *reqs_per_sec* which determines the send rate limit. As each request is received,
       if it fits, it is placed into the bucket and is sent. The bucket leaks at a fixed rate that reflects
       the send rate limit such that each new request will fit given it does not exceed the send rate limit.
       If the bucket becomes full, the next request will be delayed until the bucket has leaked enough to hold it,
       at which time it will be sent. The leaky bucket algorithm results in an average send rate that is slightly
       faster than the send rate limit. This algorithm is best used when you have an occasional burst of requests
       that the target service will tolerate, with the limiting kicking in if more request continue to be sent
       immediately following the burst.

2. Asynchronous limiting:
       With asynchronous throttling, you specify *throttle_mode=ThrottleMode.ASYNC*. The *reqs_per_sec*
       is specified for the send rate limit. The *bucket_size* can be 1 for normal rate limiting or greater
       than 1 for the leaky bucket algorithm. As each request is received, it is placed on a queue and
       control returns to the caller. A separate request schedular thread pulls the requests from the
       queue and sends them in as described above, either at a strict rate limit, or by using the leaky bucket
       algorithm. You may also specify an *async_q_size* to set the the number of requests that can build
       up on the queue before the caller is blocked while trying to add requests. When you are done, you need to
       perform a shutdown of the throttle when your program ends to ensure that the request schedular thread is
       properly ended.


Examples
========

Here we are using the **@throttle** decorator to wrap a function that needs to be limited to no more
than 2 requests per second. In the following code, make_request will be called 10 times in rapid succession. The
**@throttle** keeps track of the time for each invocation and will insert a wait as needed to stay within the
limit. The first execution of make_request will be done immediately while the remaining executions will each be delayed
by 1/2 second as seen in the output messages.

>>> from scottbrian_throttle.throttle import throttle
>>> import time
>>> @throttle(reqs_per_sec=2)
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


Here's the same example using the **Throttle** class. Note that the loop now calls send_request, passing
in the make_request function and its arguments:

>>> from scottbrian_throttle.throttle import Throttle
>>> import time
>>> def make_request(request_number, time_of_start):
...     print(f'request {request_number} sent at elapsed time: '
...           f'{time.time() - time_of_start:0.1f}')
>>> a_throttle = Throttle(reqs_per_sec=2)
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
