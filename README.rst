===================
scottbrian-throttle
===================

Intro
=====


With **@throttle** you can decorate a function to avoid exceeding a stated limit. This is useful for some
internet services which have a stated limit, such as no more than one request per minute.

:Example: prevent a request loop from exceeding 10 requests per second

In the following code, make_request will be called 30 times. The first 10 calls will happen quickly, one
after the other. The 11th call will be delayed for approximately a second to allow the first 10 calls to
age out. As the code continues for this example, the throttle code will ensure that no more than 10 calls
are made per second.

>>> from scottbrian_throttle.throttle import Throttle
>>> from time import time
>>> @throttle(requests=10, seconds=1)
... def make_request(i, start_i, start_time):
...     if time() - start_time >= 1:
...         print(f'requests {start_i} to {i-1} made in 1 second')
...         return i, time()  # update for next batch
...     return start_i, start_time  # no change

>>> start_i = 0
>>> start_time = time()
>>> for i in range(30):
...     start_i, start_time = make_request(i, start_i, start_time)
requests 0 to 9 made in 1 second
requests 10 to 19 made in 1 second
requests 20 to 29 made in 1 second


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
