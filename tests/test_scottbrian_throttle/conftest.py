"""Module _conftest.

Copyright (C) 2026 Scott Tuttle
All rights reserved
Licensed under the MIT License. See LICENSE file in the project root for
details
"""

########################################################################
# Standard Library
########################################################################
import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Generator

import pytest

########################################################################
# Local
########################################################################
from scottbrian_utils.exc_hook import ExcHook

########################################################################
# Third Party
########################################################################

########################################################################
# logging
########################################################################
logging.basicConfig(
    filename="MyLogFile.log",
    filemode="w",
    level=logging.DEBUG,
    format=(
        "%(asctime)s "
        "[%(levelname)8s] "
        "(Thread ID: %(thread)d) "
        "(Name: %(threadName)s) "
        "%(name)s "
        "%(filename)s:"
        "%(funcName)s:"
        "%(lineno)d -> "
        "%(message)s"
    ),
    datefmt="%H:%M:%S",
)

logger = logging.getLogger(__name__)


########################################################################
# thread_exc
#
# Usage:
# The thread_exc is an autouse fixture which means it does not need to
# be specified as an argument in the test case methods. If a thread
# fails, such as an assertion error, then thread_exc will capture the
# error and raise it for the thread, and will also raise it during
# cleanup processing for the mainline to ensure the test case fails.
# Without thread_exc, any uncaptured thread failure will appear in the
# output, but the test case itself will not fail.
#
########################################################################
@pytest.fixture(autouse=True)  # ruff: ignore[pytest-fixture-autouse]
def thread_exc(
    monkeypatch: pytest.MonkeyPatch,
    request: pytest.FixtureRequest,
) -> Generator[ExcHook]:
    """Instantiate and return a ThreadExc for testing.

    Args:
        monkeypatch: pytest fixture used to modify code for testing
        request: for pytest

    Yields:
        a thread exception handler

    """
    logger.debug(f"thread_exc established for {request.node=}")
    with ExcHook(monkeypatch) as exc_hook:
        yield exc_hook


########################################################################
# parameter sets
########################################################################
def pytest_addoption(parser):
    parser.addoption("--all", action="store_true", help="run all combinations")


def pytest_generate_tests(metafunc):
    if "reqs_per_sec_arg" in metafunc.fixturenames:
        if metafunc.config.getoption("all"):
            reqs_per_sec_values = (0.2, 0.5, 1, 2, 3)
        else:
            reqs_per_sec_values = (3,)
        metafunc.parametrize("reqs_per_sec_arg", reqs_per_sec_values)

    if "bucket_size_arg" in metafunc.fixturenames:
        if metafunc.config.getoption("all"):
            bucket_size_values = (1, 1.4, 2, 3)
        else:
            bucket_size_values = (1, 3)
        metafunc.parametrize("bucket_size_arg", bucket_size_values)

    if "send_interval_mult_arg" in metafunc.fixturenames:
        if metafunc.config.getoption("all"):
            send_interval_mult_values = (0.0, 0.9, 1.0, 1.1)
        else:
            send_interval_mult_values = (0.0, 1.1)
        metafunc.parametrize("send_interval_mult_arg", send_interval_mult_values)

    if "num_threads_1_arg" in metafunc.fixturenames:
        if metafunc.config.getoption("all"):
            num_threads_1_values = (0, 1, 2)
        else:
            num_threads_1_values = (0, 1)
        metafunc.parametrize("num_threads_1_arg", num_threads_1_values)

    if "num_threads_2_arg" in metafunc.fixturenames:
        if metafunc.config.getoption("all"):
            num_threads_2_values = (0, 2, 8)
        else:
            num_threads_2_values = (0, 1)
        metafunc.parametrize("num_threads_2_arg", num_threads_2_values)

    if "num_threads_3_arg" in metafunc.fixturenames:
        if metafunc.config.getoption("all"):
            num_threads_3_values = (1, 2, 16)
        else:
            num_threads_3_values = (1,)
        metafunc.parametrize("num_threads_3_arg", num_threads_3_values)
