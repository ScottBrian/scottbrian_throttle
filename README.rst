===================
scottbrian-throttle
===================

Intro
=====


The throttle allows you to limit the rate at which a function is
called. An internet service, for example, might have a limit for the
number of requests you can send in a given interval - using the
throttle will help you stay within that limit.

The throttle can be used as a class or as a decorator, can be
synchronous or asynchronous, and can be optionally configured for a
leaky bucket implementation.

As a class: when you instantiate a throttle, you specify
*reqs_per_sec* to establish the limit. You then call method
*send_request* with the name of the function that is to be limited
along with any args or kwargs that it needs. The *send_request* method
keeps track of the intervals between calls and will sleep as needed to
ensure the limit is not exceeded.

:Example 1: Instantiate a throttle and send some requests:

.. code-block:: python

    from scottbrian_throttle.throttle import Throttle
    import time
    throttle_1 = Throttle(reqs_per_sec=2)
    def target_rtn1(request_number, time_of_start):
        ret_value = (f'request {request_number} sent at elapsed time: '
                     f'{time.time() - time_of_start:0.1f}')
        return ret_value
    start_time = time.time()
    for idx in range(10):
        ret_val = throttle_1.send_request(target_rtn1, idx, start_time)
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


As a decorator: you place the decorator above the function that needs
to be limited and specify the *reqs_per_sec*. When you call the
function, the throttle keeps track of the intervals between calls and
will sleep as needed to ensure the limit is not exceeded.

:Example 2: Decorate a function with the throttle and call it a few
            times:

.. code-block:: python

    from scottbrian_throttle.throttle import Throttle
    import time
    @throttle(reqs_per_sec=2)
    def target_rtn2(request_number, time_of_start):
        ret_value = (f'request {request_number} sent at elapsed time: '
                     f'{time.time() - time_of_start:0.1f}')
        return ret_value
    start_time = time.time()
    for idx in range(10):
        ret_val = target_rtn2(idx, start_time)
        print(ret_val)


Expected output for Example 2::

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


In the above examples, the throttle was used in synchronous mode, the
default. With synchronous mode, the throttle returns control to the
caller after the target function is called and returns. This means the
caller is delayed by the throttling and the execution of the target
function. Note also that the target function can return a value which
the throttle will return to the caller.

For an asynchronous throttle, you specify
*throttle_mode=ThrottleMode.ASYNC*. With asynchronous mode, when you
call *send_request* or call the decorated target function, the throttle
will queue the request and return control immediately. A separate
thread will take care of calling the target function and applying the
throttling. Note that the target function will not be able to pass back
a return value with asynchronous mode - you will need to devise some
protocol if that is needed. Also, when it is time to end the
application, you will need to call *start_shutdown* to cause the
throttle to end the asynchronous thread.

:Example 3: Instantiate an asynchronous throttle and send some requests:

.. code-block:: python

    from scottbrian_throttle.throttle import Throttle
    import time
    throttle_3 = Throttle(reqs_per_sec=2,
                          throttle_mode=ThrottleMode.ASYNC)
    def target_rtn3(request_number, time_of_start):
        print(f'request {request_number} sent at elapsed time: '
              f'{time.time() - time_of_start:0.1f}')
    start_time = time.time()
    for idx in range(10):
        throttle_3.send_request(target_rtn3, idx, start_time)
    throttle_3.start_shutdown()


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


Note that the decorated function will have the throttle attached to it
as an attribute to allow you to call *start_shutdown* as shown in the
following example.

:Example 4: Decorate a function with an asynchronous throttle and call
            it a few times:

.. code-block:: python

    from scottbrian_throttle.throttle import Throttle
    import time
    @throttle(reqs_per_sec=2, throttle_mode=ThrottleMode.ASYNC)
    def target_rtn4(request_number, time_of_start):
        print(f'request {request_number} sent at elapsed time: '
              f'{time.time() - time_of_start:0.1f}')
    start_time = time.time()
    for idx in range(10):
        target_rtn4(idx, start_time)
    target_rtn4.throttle.start_shutdown()


Expected output for Example 4::

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


You can also specify a *bucket_size* argument greater than 1 to
configure the throttle in a leaky bucket configuration. The bucket is a
conceptual mechanism where requests are placed. The bucket has a hole
in the bottom and leaks out at the rate limit specified by
the *reqs_per_sec* argument. The idea is that the *bucket_size* specifies
how many requests will fit into the bucket. When *send_request* is
called, or when the decorated function is called, the throttle will
see if the new request will fit into the bucket. If not, the request is
delayed until the bucket leaks out enough to fit the new request. Once
placed into the bucket, the request is sent on its way. This allows some
number of initial requests to be sent immediately until the bucket is
filled up, at which point the throttle kicks in like a shock absorber to
start delaying the requests.The leaky bucket algorithm results in an
average send rate that is slightly faster than the send rate limit. This
algorithm is best used when you have an occasional burst of requests
that the target service will tolerate, with the limiting kicking in if
more request continue to be sent immediately following the burst.

:Example 5: Instantiate a leaky bucket throttle and send some requests:

.. code-block:: python

    from scottbrian_throttle.throttle import Throttle
    import time
    throttle_5 = Throttle(reqs_per_sec=2, bucket_size=3)
    def target_rtn5(request_number, time_of_start):
        print(f'request {request_number} sent at elapsed time: '
              f'{time.time() - time_of_start:0.1f}')
    start_time = time.time()
    for idx in range(10):
        throttle_5.send_request(target_rtn5, idx, start_time)


Expected output for Example 5::

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


As you can see, with *bucket_size=3*, the first three requests just
filled the bucket and were immediately sent, while the remaining
were each delayed to allow the bucket to leak just enough to fit each
new request.

:Example 6: Decorate a function with a leaky bucket throttle and call
            it a few times:

.. code-block:: python

    from scottbrian_throttle.throttle import Throttle
    import time
    @throttle(reqs_per_sec=2, bucket_size=3)
    def target_rtn6(request_number, time_of_start):
        print(f'request {request_number} sent at elapsed time: '
              f'{time.time() - time_of_start:0.1f}')
    start_time = time.time()
    for idx in range(10):
        target_rtn6(idx, start_time)


Expected output for Example 6::

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


The leaky_bucket can also be used with an asynchronous throttle if that
is deemed useful.

Some additional thoughts:
You can specify *reqs_per_sec* as a float or int of any value. For
example, *reqs_per_sec=0.5* will mean a limit of 1 request every 2
seconds, or perhaps *reqs_per_sec=1.33* for a limit close to 1 request
every 3/4 of a second. The rate interval is calculated as
1/*reqs_per_sec*. You can obtain the interval by calling
*get_interval_secs* or, in nanoseconds, *get_interval_ns*.

You can specify *bucket_size* as a float or int greater than 1. A
*bucket_size=2.5*, for example, would mean that given 4 requests in
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
