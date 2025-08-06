from doctest import ELLIPSIS
from doctest import OutputChecker as BaseOutputChecker

import re

from sybil import Sybil
from sybil.parsers.rest import PythonCodeBlockParser

from scottbrian_utils.time_hdr import get_datetime_match_string
from scottbrian_utils.doc_checker import DocCheckerTestParser, DocCheckerOutputChecker

from typing import Any


class SbtDocCheckerOutputChecker(DocCheckerOutputChecker):
    def __init__(self) -> None:
        """Initialize the output checker object."""
        super().__init__()

    def check_output(self, want: str, got: str, optionflags: int) -> bool:
        """Check the output of the example against expected value.

        Args:
            want: the expected value of the example output
            got: the actual value of the example output
            optionflags: doctest option flags for the Sybil
                BaseOutPutChecker check_output method
        Returns:
            True if the want and got values match, False otherwise
        """
        if self.mod_name == "throttle" or self.mod_name == "README":
            # Many of the code examples are dealing with time values
            # that might vary because of the unpredictability of
            # thread processing. What we want to do here is allow some
            # variance by replacing the expected value with the actual
            # value when the difference is minor.
            wants = want.split(sep="\n")
            gots = got.split(sep="\n")
            if len(wants) == len(gots):
                for idx, got_item in enumerate(gots):
                    ####################################################
                    # handle elapsed time case
                    ####################################################
                    match_str = (
                        "request "
                        + f"{idx}"
                        + " sent at elapsed time: [0-9]{1,2}.[0-9]{1,2}"
                    )
                    found_item = re.match(match_str, got_item)
                    if found_item:
                        if self.time_difference_small(
                            want_item=wants[idx], got_item=got_item
                        ):
                            want = re.sub(match_str, found_item.group(), want)
                        continue

                    ####################################################
                    # handle throttle name case
                    ####################################################
                    # We only want to match on a name that is integers,
                    # meaning the python id of the throttle. We still
                    # want the doctest to fail if the other args are
                    # misspecified, (e.g., requests=2 instead of
                    # requests=3).
                    match_str = " name=[0-9]+"
                    found_item = re.search(match_str, got_item)
                    self.msgs.append(f"{found_item=}, {match_str=}, {got_item=}")
                    if found_item:
                        want = re.sub(match_str, found_item.group(), want)
                        self.msgs.append(
                            f"{found_item=}, {match_str=}, {got_item=}, {want=}"
                        )

        self.msgs.append(f"{want=}, {got=}")
        return super().check_output(want, got, optionflags)

    ####################################################################
    # adjust_time_differences
    ####################################################################
    def time_difference_small(self, want_item: str, got_item: str) -> bool:
        """Adjust the time differences in the want and got strings."""
        want_splits = want_item.split()
        got_splits = got_item.split()
        expected_value = float(want_splits[6])
        actual_value = float(got_splits[6])
        diff_value = abs(expected_value - actual_value)
        if diff_value > 0:
            # we want to avoid divide by zero, and we
            # want to have a way to determine a
            # reasonable variance when the expected or
            # actual value is zero.
            if expected_value == 0:
                expected_value = 1

            # If the difference is withing spec, replace
            # the want with the got so it will pass.
            # Otherwise, leave it as is so it will fail.
            if (diff_value / abs(expected_value)) <= 0.20:
                return True

        return False


pytest_collect_file = Sybil(
    parsers=[
        DocCheckerTestParser(
            optionflags=ELLIPSIS,
            doc_checker_output_checker=SbtDocCheckerOutputChecker(),
        ),
        PythonCodeBlockParser(),
    ],
    patterns=["*.rst", "*.py"],
    # excludes=['log_verifier.py']
).pytest()
