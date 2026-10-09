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
@pytest.fixture(autouse=True)
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
