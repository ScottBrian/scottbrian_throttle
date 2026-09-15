"""test_throttle.py module."""

# import gc

########################################################################
# Standard Library
########################################################################
import logging
import math
import os
import random
import re
import threading
import time
from collections import deque
from dataclasses import dataclass, field
from time import perf_counter_ns
from typing import Any, Final, Optional

import pytest
########################################################################
# Third Party
########################################################################
from pydantic import ValidationError
from scottbrian_utils.entry_trace import etrace
from scottbrian_utils.exc_hook import ExcHook
from scottbrian_utils.flower_box import print_flower_box_msg as flowers
from scottbrian_utils.log_verifier import LogVer
from scottbrian_utils.pauser import Pauser
from scottbrian_utils.testlib_verifier import verify_lib

########################################################################
# Local
########################################################################
from scottbrian_throttle.throttle import throttle
from scottbrian_throttle.throttle_blocks import Throttle

########################################################################
# set up logging
########################################################################
logger = logging.getLogger(__name__)


########################################################################
# Throttle test exceptions
########################################################################
class ErrorTstThrottle(Exception):
    """Base class for exception in this module."""

    pass


class InvalidRouteNum(ErrorTstThrottle):
    """InvalidRouteNum exception class."""

    pass


class BadRequestStyleArg(ErrorTstThrottle):
    """BadRequestStyleArg exception class."""

    pass


class IncorrectWhichThrottle(ErrorTstThrottle):
    """IncorrectWhichThrottle exception class."""

    pass


########################################################################
# ReqTime data class used for shutdown testing
########################################################################
@dataclass
class ReqTime:
    """ReqTime class for number of completed requests and last time."""

    num_reqs: int = 0
    f_time: float = 0.0
    start_time: float = 0.0
    interval: float = 0.0
    arrival_time: float = 0.0


########################################################################
# RequestItem data class used to track requests
########################################################################
@dataclass
class RequestItem:
    """RequestItem class used to gather times for a request."""

    req_id: int = 0
    create_time_ns: float = 0.0  # also the start time
    throttle_mode: Throttle.Mode = Throttle.Mode.SYNC

    # send_interval set by sender when sending request
    send_interval: float = 0.0

    send_time_ns: float = 0.0  # after interval pause

    throttle_sent_time_ns: float = 0.0

    # arrival_idx is assigned by the req target code when entered
    arrival_idx: int = 0

    # throttle_arrival time obtained by req target from throttle
    # instance
    throttle_arrival_time_ns: float = 0.0

    # actual_func_arrival_time_ns assigned by the req target code when
    # entered
    expected_func_arrival_time_ns: float = 0.0
    actual_func_arrival_time_ns: float = 0.0

    throttle_next_target_time_ns: float = 0.0

    throttle_wait_time_ns: float = 0.0

    # return_time_ns set by sender when req returns
    return_time_ns: float = 0.0

    actual_delay_ns: float = 0.0
    expected_delay_ns: float = 0.0


########################################################################
# RequestThreadItem used to track requests in a thread
########################################################################
@dataclass
class RequestThreadItem:
    """RequestThreadItem class to track requests for a thread."""

    thread_item: threading.Thread
    thread_item_idx: int = 0
    thread_create_time_ns: float = 0.0
    num_reqs: int = 0
    send_intervals: list[float | int] = field(default_factory=list)


########################################################################
# verify_throttle_expected_reqs
########################################################################
def verify_throttle_expected_reqs(
    throttle: Throttle, start_time: float, req_time: ReqTime, log_ver: LogVer
) -> None:
    elapsed_time_from_start = time.time() - start_time
    num_reqs_done = req_time.num_reqs
    arrival_time = req_time.arrival_time
    elapsed_time_from_arrival = arrival_time - start_time

    exp_reqs_done = throttle.get_expected_num_completed_reqs(
        interval=elapsed_time_from_start
    )

    exp_reqs_done2 = throttle.get_expected_num_completed_reqs(
        interval=elapsed_time_from_arrival
    )

    start_time_str = formatted_time_str(raw_time=start_time)
    arrival_time_str = formatted_time_str(raw_time=arrival_time)
    elapsed_time_from_start_str = formatted_interval_str(
        raw_interval=elapsed_time_from_start
    )
    elapsed_time_from_arrival_str = formatted_interval_str(
        raw_interval=elapsed_time_from_arrival
    )

    log_ver.test_msg(
        log_msg=(
            f"{start_time_str=}, {arrival_time_str=}, "
            f"{elapsed_time_from_arrival_str=}, "
            f"{elapsed_time_from_start_str=}, "
            f"{exp_reqs_done=}, {exp_reqs_done2=}, "
            f"{num_reqs_done=}"
        )
    )

    assert abs(exp_reqs_done - exp_reqs_done2) <= 1
    assert abs(num_reqs_done - (exp_reqs_done + exp_reqs_done2) / 2) <= 1


########################################################################
# TestThrottleCorrectSource
########################################################################
class TestThrottleCorrectSource:
    """Verify that we are testing with correctly built code."""

    ####################################################################
    # test_unique_ts_correct_source
    ####################################################################
    def test_throttle_correct_source(self) -> None:
        """Test unique_ts correct source."""
        if "TOX_ENV_NAME" in os.environ:
            testlib_path = verify_lib(obj_to_check=Throttle)
            logger.debug(f"{testlib_path=}")
            assert testlib_path.endswith("throttle.py")


########################################################################
# TestThrottleBasic class to test Throttle methods
########################################################################
class TestThrottleErrors:
    """TestThrottle class."""

    def test_throttle_bad_args(self) -> None:
        """test_throttle using bad arguments."""

        ################################################################
        # mainline
        ################################################################

        ################################################################
        # bad reqs_per_sec
        ################################################################
        ml_error_msg = re.escape(
            "1 validation error for Throttle\nreqs_per_sec\n  "
            "Input should be greater than 0 "
            "[type=greater_than, input_value=-1, input_type=int]"
        )

        with pytest.raises(ValidationError, match=ml_error_msg):
            _ = Throttle(reqs_per_sec=-1)

        ml_error_msg = re.escape(
            "1 validation error for Throttle\nreqs_per_sec\n  "
            "Input should be greater than 0 "
            "[type=greater_than, input_value=0, input_type=int]"
        )
        with pytest.raises(ValidationError, match=ml_error_msg):
            _ = Throttle(reqs_per_sec=0)

        ml_error_msg = re.escape(
            "1 validation error for Throttle\nreqs_per_sec\n  "
            "Input should be a valid number, unable to parse string as a number "
            "[type=float_parsing, input_value='one', input_type=str]"
        )
        with pytest.raises(ValidationError, match=ml_error_msg):
            _ = Throttle(reqs_per_sec="one")  # type: ignore

        # the following are valid
        _ = Throttle(reqs_per_sec=0.1)
        _ = Throttle(reqs_per_sec=1)
        _ = Throttle(reqs_per_sec=1.1)
        ################################################################
        # bad bucket_size SYNC
        ################################################################
        ml_error_msg = re.escape(
            "1 validation error for Throttle\nbucket_size\n  "
            "Input should be greater than or equal to 1 "
            "[type=greater_than_equal, input_value=-1, input_type=int]"
        )

        with pytest.raises(ValidationError, match=ml_error_msg):
            _ = Throttle(bucket_size=-1)

        ml_error_msg = re.escape(
            "1 validation error for Throttle\nbucket_size\n  "
            "Input should be greater than or equal to 1 "
            "[type=greater_than_equal, input_value=0, input_type=int]"
        )
        with pytest.raises(ValidationError, match=ml_error_msg):
            _ = Throttle(bucket_size=0)

        ml_error_msg = re.escape(
            "1 validation error for Throttle\nbucket_size\n  "
            "Input should be greater than or equal to 1 "
            "[type=greater_than_equal, input_value=0.3, input_type=float]"
        )
        with pytest.raises(ValidationError, match=ml_error_msg):
            _ = Throttle(bucket_size=0.3)

        ml_error_msg = re.escape(
            "1 validation error for Throttle\nbucket_size\n  "
            "Input should be a valid number, unable to parse string as a number "
            "[type=float_parsing, input_value='two', input_type=str]"
        )
        with pytest.raises(ValidationError, match=ml_error_msg):
            _ = Throttle(bucket_size="two")  # type: ignore

        # the following are valid
        _ = Throttle(bucket_size=1)
        _ = Throttle(bucket_size=1.1)
        ################################################################
        # bad convert_to_async
        ################################################################
        ml_error_msg = re.escape(
            "1 validation error for Throttle\nconvert_to_async\n  "
            "Input should be a valid boolean, unable to interpret input "
            "[type=bool_parsing, input_value='blue', input_type=str]"
        )
        with pytest.raises(ValidationError, match=ml_error_msg):
            _ = Throttle(convert_to_async="blue")  # type: ignore

        ml_error_msg = re.escape(
            "1 validation error for Throttle\nconvert_to_async\n  "
            "Input should be a valid boolean, unable to interpret input "
            "[type=bool_parsing, input_value=2, input_type=int]"
        )
        with pytest.raises(ValidationError, match=ml_error_msg):
            _ = Throttle(convert_to_async=2)  # type: ignore

        # the following are valid
        _ = Throttle(convert_to_async=True)
        _ = Throttle(convert_to_async=False)
        _ = Throttle(convert_to_async="True")  # type: ignore
        _ = Throttle(convert_to_async="False")  # type: ignore
        _ = Throttle(convert_to_async=1)  # type: ignore
        _ = Throttle(convert_to_async=0)  # type: ignore
        _ = Throttle(convert_to_async="yEs")  # type: ignore
        _ = Throttle(convert_to_async="No")  # type: ignore

        ################################################################
        # bad name
        ################################################################
        ml_error_msg = re.escape(
            "1 validation error for Throttle\nname\n  "
            "Input should be a valid string "
            "[type=string_type, input_value=0, input_type=int]"
        )
        with pytest.raises(ValidationError, match=ml_error_msg):
            _ = Throttle(name=0)  # type: ignore

        ml_error_msg = re.escape(
            "1 validation error for Throttle\nname\n  "
            "Input should be a valid string "
            "[type=string_type, input_value=1.1, input_type=float]"
        )
        with pytest.raises(ValidationError, match=ml_error_msg):
            _ = Throttle(name=1.1)  # type: ignore

        ml_error_msg = re.escape(
            "1 validation error for Throttle\nname\n  "
            "Input should be a valid string "
            "[type=string_type, input_value=True, input_type=bool]"
        )
        with pytest.raises(ValidationError, match=ml_error_msg):
            _ = Throttle(name=True)  # type: ignore

        # the following are valid
        _ = Throttle(name="blue")
        _ = Throttle(name=b"blue")  # type: ignore


########################################################################
# TestThrottleBasic class to test Throttle methods
########################################################################
class TestThrottleBasic:
    """Test basic functions of Throttle."""

    ####################################################################
    # repr
    ####################################################################
    @pytest.mark.parametrize("reqs_per_sec_arg", (None, 0.5, 1, 2))
    @pytest.mark.parametrize("bucket_size_arg", (None, 1, 2.2))
    @pytest.mark.parametrize("convert_to_async_arg", (None, True, False))
    @pytest.mark.parametrize("name_arg", (None, "t1", "t2"))
    @etrace(omit_caller=True)
    def test_throttle_repr(
        self,
        reqs_per_sec_arg: None | float,
        bucket_size_arg: None | float,
        convert_to_async_arg: None | bool,
        name_arg: None | str,
    ) -> None:
        """test_throttle repr with various reqs_per_sec.

        Args:
            reqs_per_sec_arg: request per second
            bucket_size_arg: leaky bucket size
            name_arg: throttle name


        """
        ################################################################
        # throttle
        ################################################################

        if bucket_size_arg is not None:
            bucket_size_arg = float(bucket_size_arg)
        # 0 0 0 0
        if (
            reqs_per_sec_arg is None
            and bucket_size_arg is None
            and convert_to_async_arg is None
            and name_arg is None
        ):
            a_throttle = Throttle()
            expected_repr_str = (
                f"Throttle("
                f"reqs_per_sec=1, "
                f"bucket_size=1, "
                f"convert_to_async=False, "
                f"name=None)"
            )
        # 0 0 0 1
        elif (
            reqs_per_sec_arg is None
            and bucket_size_arg is None
            and convert_to_async_arg is None
            and name_arg is not None
        ):
            a_throttle = Throttle(name=name_arg)

            expected_repr_str = (
                f"Throttle("
                f"reqs_per_sec=1, "
                f"bucket_size=1, "
                f"convert_to_async=False, "
                f"name={name_arg})"
            )
        # 0 0 1 0
        elif (
            reqs_per_sec_arg is None
            and bucket_size_arg is None
            and convert_to_async_arg is not None
            and name_arg is None
        ):
            a_throttle = Throttle(convert_to_async=convert_to_async_arg)

            expected_repr_str = (
                f"Throttle("
                f"reqs_per_sec=1, "
                f"bucket_size=1, "
                f"convert_to_async={convert_to_async_arg}, "
                f"name=None)"
            )
        # 0 0 1 1
        elif (
            reqs_per_sec_arg is None
            and bucket_size_arg is None
            and convert_to_async_arg is not None
            and name_arg is not None
        ):
            a_throttle = Throttle(convert_to_async=convert_to_async_arg, name=name_arg)

            expected_repr_str = (
                f"Throttle("
                f"reqs_per_sec=1, "
                f"bucket_size=1, "
                f"convert_to_async={convert_to_async_arg}, "
                f"name={name_arg})"
            )
        # 0 1 0 0
        elif (
            reqs_per_sec_arg is None
            and bucket_size_arg is not None
            and convert_to_async_arg is None
            and name_arg is None
        ):
            a_throttle = Throttle(bucket_size=bucket_size_arg)

            expected_repr_str = (
                f"Throttle("
                f"reqs_per_sec=1, "
                f"bucket_size={bucket_size_arg}, "
                f"convert_to_async=False, "
                f"name=None)"
            )
        # 0 1 0 1
        elif (
            reqs_per_sec_arg is None
            and bucket_size_arg is not None
            and convert_to_async_arg is None
            and name_arg is not None
        ):
            a_throttle = Throttle(bucket_size=bucket_size_arg, name=name_arg)

            expected_repr_str = (
                f"Throttle("
                f"reqs_per_sec=1, "
                f"bucket_size={bucket_size_arg}, "
                f"convert_to_async=False, "
                f"name={name_arg})"
            )
        # 0 1 1 0
        elif (
            reqs_per_sec_arg is None
            and bucket_size_arg is not None
            and convert_to_async_arg is not None
            and name_arg is None
        ):
            a_throttle = Throttle(
                bucket_size=bucket_size_arg, convert_to_async=convert_to_async_arg
            )

            expected_repr_str = (
                f"Throttle("
                f"reqs_per_sec=1, "
                f"bucket_size={bucket_size_arg}, "
                f"convert_to_async={convert_to_async_arg}, "
                f"name=None)"
            )
        # 0 1 1 1
        elif (
            reqs_per_sec_arg is None
            and bucket_size_arg is not None
            and convert_to_async_arg is not None
            and name_arg is not None
        ):
            a_throttle = Throttle(
                bucket_size=bucket_size_arg,
                convert_to_async=convert_to_async_arg,
                name=name_arg,
            )

            expected_repr_str = (
                f"Throttle("
                f"reqs_per_sec=1, "
                f"bucket_size={bucket_size_arg}, "
                f"convert_to_async={convert_to_async_arg}, "
                f"name={name_arg})"
            )
        # 1 0 0 0
        elif (
            reqs_per_sec_arg is not None
            and bucket_size_arg is None
            and convert_to_async_arg is None
            and name_arg is None
        ):
            a_throttle = Throttle(reqs_per_sec=reqs_per_sec_arg)
            expected_repr_str = (
                f"Throttle("
                f"reqs_per_sec={reqs_per_sec_arg}, "
                f"bucket_size=1, "
                f"convert_to_async=False, "
                f"name=None)"
            )
        # 1 0 0 1
        elif (
            reqs_per_sec_arg is not None
            and bucket_size_arg is None
            and convert_to_async_arg is None
            and name_arg is not None
        ):
            a_throttle = Throttle(reqs_per_sec=reqs_per_sec_arg, name=name_arg)

            expected_repr_str = (
                f"Throttle("
                f"reqs_per_sec={reqs_per_sec_arg}, "
                f"bucket_size=1, "
                f"convert_to_async=False, "
                f"name={name_arg})"
            )
        # 1 0 1 0
        elif (
            reqs_per_sec_arg is not None
            and bucket_size_arg is None
            and convert_to_async_arg is not None
            and name_arg is None
        ):
            a_throttle = Throttle(
                reqs_per_sec=reqs_per_sec_arg, convert_to_async=convert_to_async_arg
            )

            expected_repr_str = (
                f"Throttle("
                f"reqs_per_sec={reqs_per_sec_arg}, "
                f"bucket_size=1, "
                f"convert_to_async={convert_to_async_arg}, "
                f"name=None)"
            )
        # 1 0 1 1
        elif (
            reqs_per_sec_arg is not None
            and bucket_size_arg is None
            and convert_to_async_arg is not None
            and name_arg is not None
        ):
            a_throttle = Throttle(
                reqs_per_sec=reqs_per_sec_arg,
                convert_to_async=convert_to_async_arg,
                name=name_arg,
            )

            expected_repr_str = (
                f"Throttle("
                f"reqs_per_sec={reqs_per_sec_arg}, "
                f"bucket_size=1, "
                f"convert_to_async={convert_to_async_arg}, "
                f"name={name_arg})"
            )
        # 1 1 0 0
        elif (
            reqs_per_sec_arg is not None
            and bucket_size_arg is not None
            and convert_to_async_arg is None
            and name_arg is None
        ):
            a_throttle = Throttle(
                reqs_per_sec=reqs_per_sec_arg, bucket_size=bucket_size_arg
            )

            expected_repr_str = (
                f"Throttle("
                f"reqs_per_sec={reqs_per_sec_arg}, "
                f"bucket_size={bucket_size_arg}, "
                f"convert_to_async=False, "
                f"name=None)"
            )
        # 1 1 0 1
        elif (
            reqs_per_sec_arg is not None
            and bucket_size_arg is not None
            and convert_to_async_arg is None
            and name_arg is not None
        ):
            a_throttle = Throttle(
                reqs_per_sec=reqs_per_sec_arg,
                bucket_size=bucket_size_arg,
                name=name_arg,
            )

            expected_repr_str = (
                f"Throttle("
                f"reqs_per_sec={reqs_per_sec_arg}, "
                f"bucket_size={bucket_size_arg}, "
                f"convert_to_async=False, "
                f"name={name_arg})"
            )
        # 1 1 1 0
        elif (
            reqs_per_sec_arg is not None
            and bucket_size_arg is not None
            and convert_to_async_arg is not None
            and name_arg is None
        ):
            a_throttle = Throttle(
                reqs_per_sec=reqs_per_sec_arg,
                bucket_size=bucket_size_arg,
                convert_to_async=convert_to_async_arg,
            )

            expected_repr_str = (
                f"Throttle("
                f"reqs_per_sec={reqs_per_sec_arg}, "
                f"bucket_size={bucket_size_arg}, "
                f"convert_to_async={convert_to_async_arg}, "
                f"name=None)"
            )
        # 1 1 1 1
        elif (
            reqs_per_sec_arg is not None
            and bucket_size_arg is not None
            and convert_to_async_arg is not None
            and name_arg is not None
        ):
            a_throttle = Throttle(
                reqs_per_sec=reqs_per_sec_arg,
                bucket_size=bucket_size_arg,
                convert_to_async=convert_to_async_arg,
                name=name_arg,
            )

            expected_repr_str = (
                f"Throttle("
                f"reqs_per_sec={reqs_per_sec_arg}, "
                f"bucket_size={bucket_size_arg}, "
                f"convert_to_async={convert_to_async_arg}, "
                f"name={name_arg})"
            )

        else:
            # cause failure since we should never reach this else
            a_throttle = Throttle(reqs_per_sec=-1)
            expected_repr_str = (
                "Throttle(" "reqs_per_sec=None, " "bucket_size=None, " "name=None, "
            )

        if reqs_per_sec_arg is None:
            assert repr(a_throttle) == expected_repr_str


########################################################################
# TestThrottleDecoratorErrors class
########################################################################
class TestThrottleDecoratorErrors:
    """TestThrottleDecoratorErrors class."""

    def test_pie_throttle_bad_args(self) -> None:
        """test_throttle using bad arguments."""

        ################################################################
        # bad reqs_per_sec
        ################################################################
        ml_error_msg = re.escape(
            "1 validation error for throttle\nreqs_per_sec\n  "
            "Input should be greater than 0 "
            "[type=greater_than, input_value=-1, input_type=int]"
        )

        with pytest.raises(ValidationError, match=ml_error_msg):

            @throttle(reqs_per_sec=-1)
            def f1() -> None:
                pass

        ml_error_msg = re.escape(
            "1 validation error for throttle\nreqs_per_sec\n  "
            "Input should be greater than 0 "
            "[type=greater_than, input_value=0, input_type=int]"
        )
        with pytest.raises(ValidationError, match=ml_error_msg):

            @throttle(reqs_per_sec=0)
            def f2() -> None:
                pass

        # the following are valid
        @throttle(reqs_per_sec=0.1)
        def f3() -> None:
            pass

        @throttle(reqs_per_sec=1)
        def f4() -> None:
            pass

        @throttle(reqs_per_sec=1.1)
        def f5() -> None:
            pass

        ################################################################
        # bad bucket_size
        ################################################################
        ml_error_msg = re.escape(
            "1 validation error for throttle\nbucket_size\n  "
            "Input should be greater than or equal to 1 "
            "[type=greater_than_equal, input_value=-1, input_type=int]"
        )
        with pytest.raises(ValidationError, match=ml_error_msg):

            @throttle(bucket_size=-1)
            def f7() -> None:
                pass

        ml_error_msg = re.escape(
            "1 validation error for throttle\nbucket_size\n  "
            "Input should be greater than or equal to 1 "
            "[type=greater_than_equal, input_value=0, input_type=int]"
        )
        with pytest.raises(ValidationError, match=ml_error_msg):

            @throttle(reqs_per_sec=1, bucket_size=0)
            def f8() -> None:
                pass

        ml_error_msg = re.escape(
            "1 validation error for throttle\nbucket_size\n  "
            "Input should be greater than or equal to 1 "
            "[type=greater_than_equal, input_value=0.3, input_type=float]"
        )
        with pytest.raises(ValidationError, match=ml_error_msg):

            @throttle(reqs_per_sec=1, bucket_size=0.3)
            def f9() -> None:
                pass

        # the following are valid
        @throttle(bucket_size=1)
        def f10() -> None:
            pass

        @throttle(bucket_size=1.1)
        def f11() -> None:
            pass

        ################################################################
        # bad convert_to_async
        ################################################################
        ml_error_msg = re.escape(
            "1 validation error for throttle\nconvert_to_async\n  "
            "Input should be a valid boolean, unable to interpret input "
            "[type=bool_parsing, input_value='blue', input_type=str]"
        )
        with pytest.raises(ValidationError, match=ml_error_msg):

            @throttle(convert_to_async="blue")  # type: ignore
            def f12() -> None:
                pass

        ml_error_msg = re.escape(
            "1 validation error for throttle\nconvert_to_async\n  "
            "Input should be a valid boolean, unable to interpret input "
            "[type=bool_parsing, input_value=2, input_type=int]"
        )
        with pytest.raises(ValidationError, match=ml_error_msg):

            @throttle(convert_to_async=2)  # type: ignore
            def f13() -> None:
                pass

        # the following are valid
        @throttle(convert_to_async=True)  # type: ignore
        def f14() -> None:
            pass

        @throttle(convert_to_async=False)  # type: ignore
        def f15() -> None:
            pass

        @throttle(convert_to_async="True")  # type: ignore
        def f16() -> None:
            pass

        @throttle(convert_to_async="False")  # type: ignore
        def f17() -> None:
            pass

        @throttle(convert_to_async=1)  # type: ignore
        def f18() -> None:
            pass

        @throttle(convert_to_async=0)  # type: ignore
        def f19() -> None:
            pass

        @throttle(convert_to_async="yes")  # type: ignore
        def f19() -> None:
            pass

        @throttle(convert_to_async="no")  # type: ignore
        def f19() -> None:
            pass

        my_ans = True

        @throttle(convert_to_async=my_ans)  # type: ignore
        def f20() -> None:
            pass


########################################################################
# TestThrottleDecoratorErrors class
########################################################################
class TestThrottleDecoratorRequestErrors:
    """TestThrottleDecoratorErrors class."""

    def test_pie_throttle_request_errors(
        self, caplog: pytest.LogCaptureFixture, thread_exc: ExcHook
    ) -> None:
        """test_throttle using request failure.

        Args:
            caplog: pytest fixture to capture log output
            thread_exc: contains any uncaptured errors from thread

        """
        log_ver = LogVer(log_name=__name__)
        alpha_call_seq = (
            "test_throttle.py::TestThrottleDecoratorRequestErrors"
            ".test_pie_throttle_request_errors"
        )
        log_ver.add_call_seq(name="alpha", seq=alpha_call_seq)
        ################################################################
        # sync request failure
        ################################################################
        log_msg = "Exception in pure sync context for 'f1': division by zero"
        log_ver.add_pattern(
            log_name="scottbrian_throttle.throttle_blocks",
            level=logging.DEBUG,
            pattern=log_msg,
        )
        with pytest.raises(ZeroDivisionError):

            @throttle(reqs_per_sec=1)
            def f1() -> None:
                ans = 42 / 0
                print(f"{ans=}")

            f1()

        ################################################################
        # sync_lb request failure
        ################################################################
        log_msg = "Exception in pure sync context for 'f2': division by zero"
        log_ver.add_pattern(
            log_name="scottbrian_throttle.throttle_blocks",
            level=logging.DEBUG,
            pattern=log_msg,
        )
        with pytest.raises(ZeroDivisionError):

            @throttle(reqs_per_sec=1, bucket_size=2)
            def f2() -> None:
                ans = 42 / 0
                print(f"{ans=}")

            f2()

        match_results = log_ver.get_match_results(caplog=caplog)
        log_ver.print_match_results(match_results)
        log_ver.verify_log_results(match_results)


########################################################################
# TestThrottle class
########################################################################
class TestThrottle:
    """Class TestThrottle.

    The following section tests each combination of arguments to the
    throttle.

    For the decorator, there are three styles of decoration (using pie,
    calling with the function as the first parameter, and calling the
    decorator with the function specified after the call. This test is
    especially useful to ensure that the type hints are working
    correctly, and that python accepts all combinations.

    The non-decorator cases will be simpler, except for the explicit
    calls to shutdown the throttle (which is not possible with the
    decorator style - for this, we can set the start_shutdown_event).

    The following keywords with various values and in all combinations
    are tested:
        reqs_per_sec - various increments
        throttle_enabled - true/false

    """

    ####################################################################
    # test_throttle_args_style
    ####################################################################
    @pytest.mark.parametrize(
        "throttle_mode_arg", (Throttle.Mode.SYNC, Throttle.Mode.ASYNC)
    )
    @pytest.mark.parametrize("request_style_arg", (0, 1, 2, 3, 4, 5, 6))
    def test_throttle_args_style(
        self, throttle_mode_arg: int, request_style_arg: int
    ) -> None:
        """Method to start throttle tests.

        Args:
            throttle_mode_arg: sync or async
            request_style_arg: chooses function args mix
        """
        # gc.disable()
        send_interval = 0.0
        self.throttle_router(
            reqs_per_sec=1,
            throttle_mode=throttle_mode_arg,
            bucket_size=1,
            send_interval=send_interval,
            request_style=request_style_arg,
        )
        # gc.enable()
        # time.sleep(4)

    ####################################################################
    # test_throttle_multi_threads1
    ####################################################################
    @pytest.mark.parametrize(
        "throttle_mode_arg", (Throttle.Mode.SYNC, Throttle.Mode.ASYNC)
    )
    @pytest.mark.parametrize("num_threads_arg", (0, 1, 2))
    @pytest.mark.parametrize("reqs_per_sec_arg", (0.25, 0.33, 0.5))
    @pytest.mark.parametrize("bucket_size_arg", (1, 1.25, 1.5, 2))
    @pytest.mark.parametrize("send_interval_mult_arg", (0.0, 0.9, 1.0, 1.1))
    def test_throttle_multi_threads1(
        self,
        throttle_mode_arg: int,
        num_threads_arg: int,
        reqs_per_sec_arg: float,
        bucket_size_arg: float,
        send_interval_mult_arg: float,
    ) -> None:
        """Method to start throttle tests.

        Args:
            reqs_per_sec_arg: number of requests per second from fixture
            send_interval_mult_arg: interval between each send of a
                                      request
        """
        send_interval = (1 / reqs_per_sec_arg) * send_interval_mult_arg
        self.throttle_router(
            reqs_per_sec=reqs_per_sec_arg,
            throttle_mode=throttle_mode_arg,
            bucket_size=bucket_size_arg,
            send_interval=send_interval,
            request_style=1,
            num_threads=num_threads_arg,
            num_reqs_to_do=8,
        )

    ####################################################################
    # test_throttle_multi_threads2
    ####################################################################
    @pytest.mark.parametrize(
        "throttle_mode_arg", (Throttle.Mode.SYNC, Throttle.Mode.ASYNC)
    )
    @pytest.mark.parametrize("num_threads_arg", (0, 2, 8))
    @pytest.mark.parametrize("reqs_per_sec_arg", (1, 2, 3))
    @pytest.mark.parametrize("bucket_size_arg", (1, 1.5, 2, 3))
    @pytest.mark.parametrize("send_interval_mult_arg", (0.0, 0.9, 1.0, 1.1))
    def test_throttle_multi_threads2(
        self,
        throttle_mode_arg: int,
        num_threads_arg: int,
        reqs_per_sec_arg: float,
        bucket_size_arg: float,
        send_interval_mult_arg: float,
    ) -> None:
        """Method to start throttle tests.

        Args:
            reqs_per_sec_arg: number of requests per second from fixture
            send_interval_mult_arg: interval between each send of a
                                      request
        """
        send_interval = (1 / reqs_per_sec_arg) * send_interval_mult_arg
        self.throttle_router(
            reqs_per_sec=reqs_per_sec_arg,
            throttle_mode=throttle_mode_arg,
            bucket_size=bucket_size_arg,
            send_interval=send_interval,
            request_style=1,
            num_threads=num_threads_arg,
            num_reqs_to_do=16,
        )

    ####################################################################
    # build_send_intervals
    ####################################################################
    @staticmethod
    def build_send_intervals(send_interval: float, num_reqs_to_do: int) -> list[float]:
        """Build the list of send intervals.

        Args:
            send_interval: the interval between sends

        Returns:
            a list of send intervals

        """
        random.seed(send_interval)

        # the first send interval is always 0.0
        # the remaining are the same value send_interval passed in
        send_intervals = [0.0] + [send_interval] * (num_reqs_to_do // 2 - 1)

        # the second half are random values
        for _ in range(num_reqs_to_do // 2):
            send_intervals.append(send_interval * (random.random() * 2))

        return send_intervals

    ##################################################################
    # throttle_router
    ##################################################################
    def throttle_router(
        self,
        reqs_per_sec: float,
        throttle_mode: Throttle.Mode,
        bucket_size: float,
        send_interval: float,
        request_style: int,
        num_threads: int = 0,
        num_reqs_to_do: int = 8,
    ) -> None:
        """Method test_throttle_router.

        Args:
            reqs_per_sec: number of requests per second
            throttle_mode: async or sync
            bucket_size: threshold used with sync leaky bucket algo
            send_interval: interval between each send of a request
            request_style: chooses function args mix
            num_threads: number of threads to issue requests

        """
        logger.debug(
            f"throttle_router entered: {reqs_per_sec=}, {str(throttle_mode)=},"
            f"{bucket_size=}, {send_interval=}, {request_style=}, {num_threads=} "
        )
        ################################################################
        # get send interval list
        ################################################################
        num_reqs_to_do = num_reqs_to_do
        send_intervals = self.build_send_intervals(send_interval, num_reqs_to_do)
        if num_threads > 1:
            num_reqs_to_do *= num_threads

        ##############################################################
        # Instantiate Throttle
        ##############################################################
        a_throttle = Throttle(
            reqs_per_sec=reqs_per_sec,
            bucket_size=bucket_size,
            throttle_mode=throttle_mode,
        )

        ################################################################
        # Instantiate Request Validator
        ################################################################
        request_validator = RequestValidator(
            reqs_per_sec=reqs_per_sec,
            throttle_mode=throttle_mode,
            bucket_size=bucket_size,
            total_requests=num_reqs_to_do,
            send_interval=send_interval,
            send_intervals=send_intervals,
            t_throttle=a_throttle,
            num_threads=num_threads,
        )

        ################################################################
        # pauser for 3 seconds to avoid extra time is second request
        ################################################################
        pauser = Pauser()
        pauser.pause(3)

        if num_threads == 0:
            logger.debug("throttle_router making requests")
            self.make_reqs(request_validator, request_style)
            if throttle_mode == Throttle.Mode.ASYNC:
                logger.debug("throttle_router doing throttle shutdown")
                a_throttle.start_shutdown(shutdown_type=Throttle.SHUTDOWN_SOFT)
            logger.debug("throttle_router validating series")
            request_validator.validate_series()  # validate for the series
        else:
            logger.debug("throttle_router creating threads")
            for t_num in range(num_threads):
                req_thread_item = RequestThreadItem(
                    thread_item=threading.Thread(target=self.make_multi_reqs),
                    thread_item_idx=t_num,
                    thread_create_time_ns=perf_counter_ns(),
                    num_reqs=len(send_intervals),
                    send_intervals=send_intervals.copy(),
                )
                req_thread_item.thread_item._args = (  # type: ignore[attr-defined]
                    request_validator,
                    req_thread_item,
                )
                request_validator.thread_items.append(req_thread_item)

            logger.debug("throttle_router starting threads")
            for thread_item in request_validator.thread_items:
                thread_item.thread_item.start()

            logger.debug("throttle_router joining threads")
            for thread_item in request_validator.thread_items:
                thread_item.thread_item.join()

            if throttle_mode == Throttle.Mode.ASYNC:
                logger.debug("throttle_router doing throttle shutdown")
                a_throttle.start_shutdown(shutdown_type=Throttle.SHUTDOWN_SOFT)

            logger.debug("throttle_router validating series")
            request_validator.validate_series()

        logger.debug("throttle_router exiting")

    ####################################################################
    # make_reqs
    ####################################################################
    @staticmethod
    def make_reqs(request_validator: "RequestValidator", request_style: int) -> None:
        """Make the requests.

        Args:
            request_validator: the validator for the reqs
            request_style: determine the args to pass

        Raises:
            BadRequestStyleArg: The request style arg must be 0 to 6

        """

        pauser = Pauser()
        a_throttle = request_validator.t_throttle
        throttle_mode = a_throttle.throttle_mode

        call_args: str

        if request_style == 0:
            call_args = "a_throttle.send_request(request_validator.request0b)"
        elif request_style == 1:
            call_args = "a_throttle.send_request(request_validator.request1b, idx)"
        elif request_style == 2:
            call_args = (
                "a_throttle.send_request(request_validator.request2b, idx, "
                "request_validator.reqs_per_sec)"
            )
        elif request_style == 3:
            call_args = (
                "a_throttle.send_request(request_validator.request3b, req_id=idx)"
            )
        elif request_style == 4:
            call_args = (
                "a_throttle.send_request(request_validator.request4b, "
                "req_id=idx, send_interval=request_validator.send_interval)"
            )
        elif request_style == 5:
            call_args = (
                "a_throttle.send_request(request_validator.request5b, idx, "
                "send_interval=request_validator.send_interval,)"
            )
        elif request_style == 6:
            call_args = (
                "a_throttle.send_request(request_validator.request6b, "
                "idx, "
                "request_validator.reqs_per_sec, "
                "bucket_size=request_validator.bucket_size, "
                "send_interval=request_validator.send_interval,)"
            )
        else:
            raise BadRequestStyleArg("The request style arg must be 0 to 6")

        for idx, s_interval in enumerate(request_validator.send_intervals):
            request_item = RequestItem(
                req_id=idx,
                create_time_ns=perf_counter_ns(),
                throttle_mode=throttle_mode,
                send_interval=s_interval,
            )

            if s_interval > 0.0:
                pauser.pause(s_interval)
            request_item.send_time_ns = perf_counter_ns()
            request_validator.request_deque.appendleft(request_item)
            rc = eval(call_args)
            request_item.return_time_ns = perf_counter_ns()
            exp_rc = idx if throttle_mode != Throttle.Mode.ASYNC else Throttle.RC_OK
            assert rc == exp_rc

    ####################################################################
    # make_multi_reqs
    ####################################################################
    @staticmethod
    def make_multi_reqs(
        request_validator: "RequestValidator", request_thread_item: RequestThreadItem
    ) -> None:
        """Make the requests.

        Args:
            request_validator: the validator for the reqs
            request_thread_item: the request thread item

        """
        pauser = Pauser()
        a_throttle = request_validator.t_throttle

        for idx, s_interval in enumerate(request_thread_item.send_intervals):
            request_item = RequestItem(
                req_id=idx,
                create_time_ns=perf_counter_ns(),
                throttle_mode=request_validator.throttle_mode,
                send_interval=s_interval,
            )

            if s_interval > 0.0:
                pauser.pause(s_interval)
            request_item.send_time_ns = perf_counter_ns()
            _ = a_throttle.send_request(
                request_validator.request0c, request_item=request_item
            )
            request_item.return_time_ns = perf_counter_ns()

    ####################################################################
    # test_pie_throttle_args_style
    ####################################################################
    @pytest.mark.parametrize(
        "throttle_mode_arg", (Throttle.Mode.SYNC, Throttle.Mode.ASYNC)
    )
    @pytest.mark.parametrize("request_style_arg", (0, 1, 2, 3, 4, 5, 6))
    def test_pie_throttle_args_style(
        self, throttle_mode_arg: int, request_style_arg: int
    ) -> None:
        """Method to start throttle tests.

        Args:
            throttle_mode_arg: sync or async
            request_style_arg: chooses which function args to use

        """
        ################################################################
        # Instantiate Request Validator
        ################################################################
        pauser = Pauser()
        reqs_per_sec_arg = 4
        send_interval = 0.1

        ################################################################
        # get send interval list
        ################################################################
        num_reqs_to_do = 16
        send_intervals = self.build_send_intervals(send_interval, num_reqs_to_do)

        ################################################################
        # Decorate functions with throttle
        ################################################################
        call_list: list[tuple[str, str, str]] = []

        ################################################################
        # f0
        ################################################################
        @throttle(reqs_per_sec=reqs_per_sec_arg, throttle_mode=throttle_mode_arg)
        def f0() -> Any:
            request_validator.idx += 1
            request_item = request_validator.request_deque.pop()
            assert request_item.req_id == request_validator.idx
            request_item.arrival_idx = request_validator.idx  # first is zero
            request_item.actual_func_arrival_time_ns = perf_counter_ns()
            request_item.throttle_arrival_time_ns = (
                request_validator.t_throttle._arrival_time_ns
            )
            request_item.throttle_next_target_time_ns = (
                request_validator.t_throttle._next_target_time_ns
            )
            request_item.throttle_wait_time_ns = (
                request_validator.t_throttle._wait_time_ns
            )
            request_item.throttle_sent_time_ns = (
                request_validator.t_throttle.sent_time_ns
            )
            request_validator.request_items.append(request_item)

            if request_validator.t_throttle.throttle_mode == Throttle.Mode.ASYNC:
                return None
            return request_item.req_id + 42 + 0

        if throttle_mode_arg == Throttle.Mode.ASYNC:
            call_list.append(("f0", "()", "0"))
        else:
            call_list.append(("f0", "()", "request_id + 42 + 0"))

        ################################################################
        # f1
        ################################################################
        @throttle(reqs_per_sec=reqs_per_sec_arg, throttle_mode=throttle_mode_arg)
        def f1(req_id: int) -> Any:
            request_validator.idx += 1
            request_item = request_validator.request_deque.pop()
            request_item.arrival_idx = request_validator.idx  # first is zero
            request_item.actual_func_arrival_time_ns = perf_counter_ns()
            request_item.throttle_arrival_time_ns = (
                request_validator.t_throttle._arrival_time_ns
            )
            request_item.throttle_next_target_time_ns = (
                request_validator.t_throttle._next_target_time_ns
            )
            request_item.throttle_wait_time_ns = (
                request_validator.t_throttle._wait_time_ns
            )
            request_item.throttle_sent_time_ns = (
                request_validator.t_throttle.sent_time_ns
            )
            request_validator.request_items.append(request_item)
            assert req_id == request_item.req_id

            if request_validator.t_throttle.throttle_mode == Throttle.Mode.ASYNC:
                return None
            return request_item.req_id + 42 + 1

        if throttle_mode_arg == Throttle.Mode.ASYNC:
            call_list.append(("f1", "(request_id)", "0"))
        else:
            call_list.append(("f1", "(request_id)", "request_id + 42 + 1"))

        ################################################################
        # f2
        ################################################################
        @throttle(reqs_per_sec=reqs_per_sec_arg, throttle_mode=throttle_mode_arg)
        def f2(req_id: int, reqs_per_sec: float) -> Any:
            request_validator.idx += 1
            request_item = request_validator.request_deque.pop()
            request_item.arrival_idx = request_validator.idx  # first is zero
            request_item.actual_func_arrival_time_ns = perf_counter_ns()
            request_item.throttle_arrival_time_ns = (
                request_validator.t_throttle._arrival_time_ns
            )
            request_item.throttle_next_target_time_ns = (
                request_validator.t_throttle._next_target_time_ns
            )
            request_item.throttle_wait_time_ns = (
                request_validator.t_throttle._wait_time_ns
            )
            request_item.throttle_sent_time_ns = (
                request_validator.t_throttle.sent_time_ns
            )
            request_validator.request_items.append(request_item)

            assert req_id == request_item.req_id
            assert reqs_per_sec == request_validator.reqs_per_sec

            if request_validator.t_throttle.throttle_mode == Throttle.Mode.ASYNC:
                return None
            return request_item.req_id + 42 + 2

        if throttle_mode_arg == Throttle.Mode.ASYNC:
            call_list.append(("f2", "(request_id, reqs_per_sec_arg)", "0"))
        else:
            call_list.append(
                ("f2", "(request_id, reqs_per_sec_arg)", "request_id + 42 + 2")
            )

        ################################################################
        # f3
        ################################################################
        @throttle(reqs_per_sec=reqs_per_sec_arg, throttle_mode=throttle_mode_arg)
        def f3(*, req_id: int) -> Any:
            request_validator.idx += 1
            request_item = request_validator.request_deque.pop()
            request_item.arrival_idx = request_validator.idx  # first is zero
            request_item.actual_func_arrival_time_ns = perf_counter_ns()
            request_item.throttle_arrival_time_ns = (
                request_validator.t_throttle._arrival_time_ns
            )
            request_item.throttle_next_target_time_ns = (
                request_validator.t_throttle._next_target_time_ns
            )
            request_item.throttle_wait_time_ns = (
                request_validator.t_throttle._wait_time_ns
            )
            request_item.throttle_sent_time_ns = (
                request_validator.t_throttle.sent_time_ns
            )
            request_validator.request_items.append(request_item)

            assert req_id == request_item.req_id

            if request_validator.t_throttle.throttle_mode == Throttle.Mode.ASYNC:
                return None
            return request_item.req_id + 42 + 3

        if throttle_mode_arg == Throttle.Mode.ASYNC:
            call_list.append(("f3", "(req_id=request_id)", "0"))
        else:
            call_list.append(("f3", "(req_id=request_id)", "request_id + 42 + 3"))

        ################################################################
        # f4
        ################################################################
        @throttle(reqs_per_sec=reqs_per_sec_arg, throttle_mode=throttle_mode_arg)
        def f4(*, req_id: int, interval: float) -> Any:
            request_validator.idx += 1
            request_item = request_validator.request_deque.pop()
            request_item.arrival_idx = request_validator.idx  # first is zero
            request_item.actual_func_arrival_time_ns = perf_counter_ns()
            request_item.throttle_arrival_time_ns = (
                request_validator.t_throttle._arrival_time_ns
            )
            request_item.throttle_next_target_time_ns = (
                request_validator.t_throttle._next_target_time_ns
            )
            request_item.throttle_wait_time_ns = (
                request_validator.t_throttle._wait_time_ns
            )
            request_item.throttle_sent_time_ns = (
                request_validator.t_throttle.sent_time_ns
            )
            request_validator.request_items.append(request_item)

            assert req_id == request_item.req_id
            assert interval == request_item.send_interval

            if request_validator.t_throttle.throttle_mode == Throttle.Mode.ASYNC:
                return None
            return request_item.req_id + 42 + 4

        if throttle_mode_arg == Throttle.Mode.ASYNC:
            call_list.append(("f4", "(req_id=request_id, interval=s_interval)", "0"))
        else:
            call_list.append(
                (
                    "f4",
                    "(req_id=request_id, interval=s_interval)",
                    "request_id + 42 + 4",
                )
            )

        ################################################################
        # f5
        ################################################################
        @throttle(reqs_per_sec=reqs_per_sec_arg, throttle_mode=throttle_mode_arg)
        def f5(req_id: int, *, interval: float) -> Any:
            request_validator.idx += 1
            request_item = request_validator.request_deque.pop()
            request_item.arrival_idx = request_validator.idx  # first is zero
            request_item.actual_func_arrival_time_ns = perf_counter_ns()
            request_item.throttle_arrival_time_ns = (
                request_validator.t_throttle._arrival_time_ns
            )
            request_item.throttle_next_target_time_ns = (
                request_validator.t_throttle._next_target_time_ns
            )
            request_item.throttle_wait_time_ns = (
                request_validator.t_throttle._wait_time_ns
            )
            request_item.throttle_sent_time_ns = (
                request_validator.t_throttle.sent_time_ns
            )
            request_validator.request_items.append(request_item)

            assert req_id == request_item.req_id
            assert interval == request_item.send_interval

            if request_validator.t_throttle.throttle_mode == Throttle.Mode.ASYNC:
                return None
            return request_item.req_id + 42 + 5

        if throttle_mode_arg == Throttle.Mode.ASYNC:
            call_list.append(("f5", "(req_id=request_id, interval=s_interval)", "0"))
        else:
            call_list.append(
                (
                    "f5",
                    "(req_id=request_id, interval=s_interval)",
                    "request_id + 42 + 5",
                )
            )

        ################################################################
        # f6
        ################################################################
        @throttle(reqs_per_sec=reqs_per_sec_arg, throttle_mode=throttle_mode_arg)
        def f6(
            req_id: int, reqs_per_sec: float, *, bucket_size: float, interval: float
        ) -> Any:
            request_validator.idx += 1
            request_item = request_validator.request_deque.pop()
            request_item.arrival_idx = request_validator.idx  # first is zero
            request_item.actual_func_arrival_time_ns = perf_counter_ns()
            request_item.throttle_arrival_time_ns = (
                request_validator.t_throttle._arrival_time_ns
            )
            request_item.throttle_next_target_time_ns = (
                request_validator.t_throttle._next_target_time_ns
            )
            request_item.throttle_wait_time_ns = (
                request_validator.t_throttle._wait_time_ns
            )
            request_item.throttle_sent_time_ns = (
                request_validator.t_throttle.sent_time_ns
            )
            request_validator.request_items.append(request_item)

            assert req_id == request_item.req_id
            assert reqs_per_sec == request_validator.reqs_per_sec
            assert bucket_size == request_validator.bucket_size
            assert interval == request_item.send_interval

            if request_validator.t_throttle.throttle_mode == Throttle.Mode.ASYNC:
                return None
            return request_item.req_id + 42 + 6

        if throttle_mode_arg == Throttle.Mode.ASYNC:
            call_list.append(
                (
                    "f6",
                    "(request_id, reqs_per_sec_arg, bucket_size=1, "
                    "interval=s_interval)",
                    "0",
                )
            )
        else:
            call_list.append(
                (
                    "f6",
                    "(request_id, reqs_per_sec_arg, bucket_size=1, "
                    "interval=s_interval)",
                    "request_id + 42 + 6",
                )
            )

        ################################################################
        # Instantiate the validator
        ################################################################
        request_validator = RequestValidator(
            reqs_per_sec=reqs_per_sec_arg,
            throttle_mode=throttle_mode_arg,
            bucket_size=1,
            total_requests=num_reqs_to_do,
            send_interval=send_interval,
            send_intervals=send_intervals,
            t_throttle=eval(call_list[request_style_arg][0]).throttle,
        )
        ################################################################
        # Invoke the functions
        ################################################################
        for request_id, s_interval in enumerate(send_intervals):

            ml_request_item = RequestItem(
                req_id=request_id,
                create_time_ns=perf_counter_ns(),
                throttle_mode=throttle_mode_arg,
                send_interval=s_interval,
            )

            if s_interval > 0.0:
                pauser.pause(s_interval)
            ml_request_item.send_time_ns = perf_counter_ns()
            request_validator.request_deque.appendleft(ml_request_item)
            rc = eval(call_list[request_style_arg][0] + call_list[request_style_arg][1])
            ml_request_item.return_time_ns = perf_counter_ns()
            assert rc == eval(call_list[request_style_arg][2])

        if throttle_mode_arg == Throttle.Mode.ASYNC:
            shutdown_throttle_funcs(f0, f1, f2, f3, f4, f5, f6)
        request_validator.validate_series()  # validate for the series

    ####################################################################
    # test_pie_throttle
    ####################################################################
    @pytest.mark.parametrize(
        "throttle_mode_arg", (Throttle.Mode.SYNC, Throttle.Mode.ASYNC)
    )
    @pytest.mark.parametrize("reqs_per_sec_arg", (1, 2, 3))
    @pytest.mark.parametrize("bucket_size_arg", (1, 1.3, 2, 3))
    @pytest.mark.parametrize("send_interval_mult_arg", (0.0, 0.9, 1.0, 1.1))
    def test_pie_throttle(
        self,
        throttle_mode_arg: int,
        reqs_per_sec_arg: float,
        bucket_size_arg: float,
        send_interval_mult_arg: float,
    ) -> None:
        """Method to start throttle tests.

        Args:
            throttle_mode_arg: sync or async
            reqs_per_sec_arg: number of requests per second from fixture
            bucket_size_arg: bucket size for the throttle
            send_interval_mult_arg: interval between each send of a
                                      request
        """
        ################################################################
        # Instantiate Request Validator
        ################################################################
        pauser = Pauser()
        send_interval = (1 / reqs_per_sec_arg) * send_interval_mult_arg

        ################################################################
        # get send interval list
        ################################################################
        num_reqs_to_do = 16
        send_intervals = self.build_send_intervals(send_interval, num_reqs_to_do)

        ################################################################
        # Decorate functions with throttle
        ################################################################
        @throttle(
            reqs_per_sec=reqs_per_sec_arg,
            bucket_size=bucket_size_arg,
            throttle_mode=throttle_mode_arg,
        )
        def f0() -> Any:
            request_validator.idx += 1
            request_item = request_validator.request_deque.pop()
            assert request_item.req_id == request_validator.idx
            request_item.arrival_idx = request_validator.idx  # first is zero
            request_item.actual_func_arrival_time_ns = perf_counter_ns()
            request_item.throttle_arrival_time_ns = (
                request_validator.t_throttle._arrival_time_ns
            )
            request_item.throttle_next_target_time_ns = (
                request_validator.t_throttle._next_target_time_ns
            )
            request_item.throttle_wait_time_ns = (
                request_validator.t_throttle._wait_time_ns
            )
            request_item.throttle_sent_time_ns = (
                request_validator.t_throttle.sent_time_ns
            )
            request_validator.request_items.append(request_item)

            if request_validator.t_throttle.throttle_mode == Throttle.Mode.ASYNC:
                return None
            return 0

        ################################################################
        # Instantiate the validator
        ################################################################
        request_validator = RequestValidator(
            reqs_per_sec=reqs_per_sec_arg,
            throttle_mode=throttle_mode_arg,
            bucket_size=bucket_size_arg,
            total_requests=num_reqs_to_do,
            send_interval=send_interval,
            send_intervals=send_intervals,
            t_throttle=f0.throttle,
        )
        ################################################################
        # Invoke the functions
        ################################################################
        ################################################################
        # Invoke f0
        ################################################################
        for req_id, s_interval in enumerate(send_intervals):
            ml_request_item = RequestItem(
                req_id=req_id,
                create_time_ns=perf_counter_ns(),
                throttle_mode=throttle_mode_arg,
                send_interval=s_interval,
            )

            if s_interval > 0.0:
                pauser.pause(s_interval)
            ml_request_item.send_time_ns = perf_counter_ns()
            request_validator.request_deque.appendleft(ml_request_item)
            rc = f0()
            ml_request_item.return_time_ns = perf_counter_ns()
            assert rc == 0

        if throttle_mode_arg == Throttle.Mode.ASYNC:
            shutdown_throttle_funcs(f0)

        request_validator.validate_series()  # validate for the series


########################################################################
# issue_shutdown_log_entry
########################################################################
def issue_shutdown_log_entry(
    func_name: str, req_time: ReqTime, log_ver: LogVer
) -> None:
    """Log the shutdown progress message.

    Args:
        func_name: name of function for log message
        req_time: number of requests and time
        log_ver: log verifier used to test log messages

    """
    t = time.time()
    req_time.arrival_time = t
    req_time.num_reqs += 1
    prev_t = req_time.f_time
    f_interval = t - prev_t
    assert f_interval >= 0

    f_interval_str = formatted_interval_str(raw_interval=f_interval)

    req_time.f_time = t

    time_str = formatted_time_str(raw_time=t)

    expected_req = math.floor((t - req_time.start_time) / req_time.interval) + 1

    expected_t = req_time.start_time + (req_time.num_reqs - 1) * req_time.interval
    expected_time = formatted_time_str(raw_time=expected_t)

    # next_expected_t = req_time.start_time + req_time.num_reqs *
    # req_time.interval
    # next_expected_time = formatted_time_str(raw_time=next_expected_t)

    if req_time.num_reqs % 5000 == 0:
        log_msg = (
            f"{func_name} processing request #{req_time.num_reqs} ({expected_req}) at "
            f"{time_str} ({expected_time}), interval={f_interval_str} "
            f"({req_time.interval})"
        )

        log_ver.test_msg(log_msg)


########################################################################
# issue_remaining_requests_log_entry
########################################################################
def issue_remaining_requests_log_entry(
    throttle: Throttle, log_ver: LogVer
) -> tuple[bool, int]:
    """Log the remaining requests log message.

    Args:
        throttle: the Throttle being tested
        log_ver: log verifier used to test log messages

    Returns:
        tuple containing the async_q_empty bool and the number of
        remaining requests on the async queue
    """
    async_q_empty = throttle.async_q.empty()
    num_reqs_remaining = throttle.async_q.qsize()
    log_ver.test_msg(
        f"{async_q_empty=} with {num_reqs_remaining} remaining requests on asynq"
    )
    return async_q_empty, num_reqs_remaining


########################################################################
# formatted_time_str
########################################################################
def formatted_time_str(raw_time: float) -> str:
    """Format a time for log output..

    Args:
        raw_time: the time that is to be formatted

    """
    return (
        time.strftime("%H:%M:%S", time.localtime(raw_time))
        + ("%.9f" % (raw_time % 1,))[1:6]
    )


########################################################################
# formatted_interval_str
########################################################################
def formatted_interval_str(raw_interval: float) -> str:
    """Format an interval time for log output..

    Args:
        raw_interval: the interval time that is to be formatted

    """
    return (
        time.strftime("%S", time.localtime(raw_interval))
        + ("%.9f" % (raw_interval % 1,))[1:6]
    )


########################################################################
# TestThrottleShutdown
########################################################################
class TestThrottleMisc:
    """Class TestThrottleMisc."""

    ####################################################################
    # test_get_interval_secs
    ####################################################################
    @pytest.mark.parametrize(
        "throttle_mode_arg", (Throttle.Mode.SYNC, Throttle.Mode.ASYNC)
    )
    @pytest.mark.parametrize("reqs_per_sec_arg", (0.5, 1, 2, 3))
    def test_get_interval_secs(
        self, throttle_mode_arg: int, reqs_per_sec_arg: float
    ) -> None:
        """Method to test get_interval in seconds.

        Args:
            throttle_mode_arg: sync or async
            reqs_per_sec_arg: number of requests per second specified
                for the throttle

        """
        ################################################################
        # create a sync throttle_mode throttle
        ################################################################
        a_throttle1 = Throttle(
            reqs_per_sec=reqs_per_sec_arg, throttle_mode=throttle_mode_arg
        )

        interval = 1 / reqs_per_sec_arg
        interval_ns = interval * SECS_2_NS
        assert interval == a_throttle1.get_interval_secs()
        assert interval_ns == a_throttle1.get_interval_ns()

        if throttle_mode_arg == Throttle.Mode.ASYNC:
            a_throttle1.start_shutdown()

    ####################################################################
    # test_get_completion_time_secs
    ####################################################################
    @pytest.mark.parametrize(
        "throttle_mode_arg", (Throttle.Mode.SYNC, Throttle.Mode.ASYNC)
    )
    @pytest.mark.parametrize("reqs_per_sec_arg", (0.2, 1, 2, 3))
    def test_get_completion_time_secs(
        self, throttle_mode_arg: int, reqs_per_sec_arg: float
    ) -> None:
        """Method to test get completion time in seconds.

        Args:
            throttle_mode_arg: sync or async
            reqs_per_sec_arg: number of requests per second specified
                for the throttle

        """
        ################################################################
        # create a sync throttle_mode throttle
        ################################################################
        a_throttle1 = Throttle(
            reqs_per_sec=reqs_per_sec_arg, throttle_mode=throttle_mode_arg
        )

        interval = 1 / reqs_per_sec_arg
        for num_reqs in range(1, 10):
            exp_completion_time = (num_reqs - 1) * interval
            exp_completion_time_ns = (num_reqs - 1) * interval * SECS_2_NS
            actual_completion_time = a_throttle1.get_completion_time_secs(
                num_requests=num_reqs, from_start=True
            )
            actual_completion_time_ns = a_throttle1.get_completion_time_ns(
                num_requests=num_reqs, from_start=True
            )
            assert actual_completion_time == exp_completion_time
            assert actual_completion_time_ns == exp_completion_time_ns

        for num_reqs in range(1, 10):
            exp_completion_time = num_reqs * interval
            exp_completion_time_ns = num_reqs * interval * SECS_2_NS
            actual_completion_time = a_throttle1.get_completion_time_secs(
                num_requests=num_reqs, from_start=False
            )
            actual_completion_time_ns = a_throttle1.get_completion_time_ns(
                num_requests=num_reqs, from_start=False
            )
            assert actual_completion_time == exp_completion_time
            assert actual_completion_time_ns == exp_completion_time_ns

        if throttle_mode_arg == Throttle.Mode.ASYNC:
            a_throttle1.start_shutdown()


########################################################################
# f2_target
########################################################################
def f2_target(req_time: ReqTime, log_ver: LogVer) -> None:
    """F2 request function.

    Args:
        req_time: contains request number and time
        log_ver: log verifier to use

    """
    issue_shutdown_log_entry(func_name="f2_target", req_time=req_time, log_ver=log_ver)


########################################################################
# get_throttle
########################################################################
def get_async_throttle(
    reqs_per_sec: float, async_q_size: int, name: Optional[str] = None
) -> tuple[Throttle, float]:
    """Obtain an async throttle and return it.

    Args:
        reqs_per_sec: number of requests per second
        async_q_size: max number of reqs_per_sec that will be queued
        name: throttle name used in log messages

    """
    a_throttle = Throttle(
        reqs_per_sec=reqs_per_sec,
        throttle_mode=Throttle.Mode.ASYNC,
        name=name,
        async_q_size=async_q_size,
    )

    assert a_throttle.async_q
    assert a_throttle.request_scheduler_thread

    interval = a_throttle.get_interval_secs()

    return a_throttle, interval


########################################################################
# queue_first_batch_requests
########################################################################
def queue_first_batch_requests(
    throttle: Throttle, num_reqs: int, num_sleep_reqs: int, log_ver: LogVer
) -> tuple[float, ReqTime]:
    """Queue the request to the async throttle.

    Args:
        throttle: the async throttle
        num_reqs: number of requests to queue
        num_sleep_reqs: number of requests to allow to be processed
        log_ver: log verifier to use

    """
    interval = throttle.get_interval_secs()

    log_ver.test_msg(
        "queue_first_batch_requests about to add " f"{num_reqs=} with {num_sleep_reqs=}"
    )

    # Calculate the first sleep time to use
    # the get_completion_time_secs calculation is for the start of
    # a series where the first request has no delay.
    # Note that we add 1/2 interval to ensure we are between
    # requests when we come out of the sleep and verify the number
    # of requests. Without the extra time, we could come out of the
    # sleep just a fraction before the last request of the series
    # is made because of timing randomness.
    sleep_seconds = throttle.get_completion_time_secs(
        num_sleep_reqs, from_start=True
    ) + (interval / 2)

    start_time = time.time()
    a_req_time = ReqTime(
        num_reqs=0, f_time=start_time, start_time=start_time, interval=interval
    )

    for _ in range(num_reqs):
        assert Throttle.RC_OK == throttle.send_request(f2_target, a_req_time, log_ver)

    log_ver.test_msg(
        f"{num_reqs} requests added, elapsed time = {time.time() - start_time} seconds"
    )

    sleep_time = sleep_seconds - (time.time() - start_time)

    log_ver.test_msg(f"about to sleep for {sleep_time=} for {num_sleep_reqs=}")
    time.sleep(sleep_time)

    verify_throttle_expected_reqs(
        throttle=throttle,
        start_time=start_time,
        req_time=a_req_time,
        log_ver=log_ver,
    )

    return start_time, a_req_time


########################################################################
# queue_more_requests
########################################################################
def queue_more_requests(
    throttle: Throttle, num_reqs: int, req_time: ReqTime, log_ver: LogVer
) -> None:
    """Queue the request to the asyn throttle.

    Args:
        throttle: the async throttle
        num_reqs: number of requests to queue
        req_time: req_time from queue_first_batch_requests
        log_ver: log verifier to use

    """
    start_time = time.time()
    for _ in range(num_reqs):
        assert Throttle.RC_OK == throttle.send_request(f2_target, req_time, log_ver)

    log_ver.test_msg(
        f"{num_reqs} requests added, elapsed time = {time.time() - start_time} seconds"
    )


########################################################################
# final_shutdown_and_verification
########################################################################
def final_shutdown_and_verification(
    throttle: Throttle,
    req_time: ReqTime,
    log_ver: LogVer,
    ret_code: int,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Make sure throttle is shutdown and verify results.

    Args:
        throttle: the async throttle
        req_time: req_time from queue_first_batch_requests
        log_ver: log verifier to use
        ret_code: the ret_code from mainline
        caplog: contained the log messages to verify

    """
    ############################################################
    # verify new requests are rejected, q empty, and thread is
    # done @sbt
    ############################################################
    issue_remaining_requests_log_entry(throttle=throttle, log_ver=log_ver)

    assert Throttle.RC_THROTTLE_IS_SHUTDOWN == throttle.send_request(
        f2_target, req_time, log_ver
    )

    # make sure request schedular is gone so that any lagging
    # f1 messages are logged. This is needed to ensure the
    # verify log results below will be able to match the added
    # pattern for the lagging message
    if ret_code == Throttle.RC_SHUTDOWN_TIMED_OUT:
        ret_code = throttle.start_shutdown(
            shutdown_type=Throttle.SHUTDOWN_HARD, timeout=60
        )
    assert ret_code != Throttle.RC_SHUTDOWN_TIMED_OUT

    assert throttle.async_q.empty()
    assert not throttle.request_scheduler_thread.is_alive()

    ############################################################
    # we now know that shutdown is done one way or another
    ############################################################
    log_msg = (
        f"throttle {throttle.t_name} start_shutdown request "
        f"successfully completed in "
        f"{throttle.shutdown_elapsed_time:.4f} seconds"
    )
    log_ver.add_pattern(
        log_name="scottbrian_throttle.throttle",
        level=logging.INFO,
        pattern=log_msg,
    )

    ################################################################
    # verify the log messages
    ################################################################
    match_results = log_ver.get_match_results(caplog=caplog)
    log_ver.print_match_results(match_results)
    log_ver.verify_log_results(match_results)


SECS_2_NS: Final[int] = 1000000000
NS_2_SECS: Final[float] = 0.000000001


########################################################################
# RequestValidator class
########################################################################
class RequestValidator:
    """Class to validate the requests."""

    ####################################################################
    # __init__
    ####################################################################
    def __init__(
        self,
        reqs_per_sec: float,
        throttle_mode: Throttle.Mode,
        bucket_size: float,
        total_requests: int,
        send_interval: float,
        send_intervals: list[float],
        t_throttle: Throttle,
        num_threads: int = 0,
    ) -> None:
        """Initialize the RequestValidator object.

        Args:
            reqs_per_sec: number of requests per second
            throttle_mode: specifies whether async or sync
            bucket_size: the leaky bucket threshold
            total_requests: specifies how many requests to make for the
                              test
            send_interval: the interval between sends
            send_intervals: the list of send intervals
            t_throttle: the throttle being used for this test
            num_threads: number of threads issuing requests

        """
        self.t_throttle = t_throttle
        self.reqs_per_sec = reqs_per_sec
        self.throttle_mode = throttle_mode
        self.num_threads = num_threads
        self.bucket_size = bucket_size
        self.send_interval = send_interval
        self.send_intervals = send_intervals

        self.thread_items: list[RequestThreadItem] = []

        # Single request item passed to exit. We need this
        # to be able to test an exit without args (i.e., request0)
        self.request_deque: deque[RequestItem] = deque()

        # list of request items from each thread
        self.request_items: list[RequestItem] = []

        self.idx = -1

        # calculate parms

        self.total_requests: int = total_requests

        self.target_interval = 1 / reqs_per_sec

        self.target_interval_ns = self.target_interval * SECS_2_NS

        self.cumulative_expected_delay_ns: float = 0.0
        self.cumulative_actual_delay_ns: float = 0.0

        self.cumulative_throttle_wait_time_ns: float = 0.0

        self.reset()

    ####################################################################
    # reset
    ####################################################################
    def reset(self) -> None:
        """Reset the variables to starting values."""
        self.idx = -1

    ####################################################################
    # validate_series
    ####################################################################
    def validate_series(self) -> None:
        """Validate the requests.

        Raises:
            InvalidModeNum: Mode must be 1, 2, 3, or 4

        """
        assert 0 < self.total_requests
        assert len(self.request_items) == self.total_requests

        # ensure that the request items are in order
        for idx, req_item in enumerate(self.request_items):
            assert idx == req_item.arrival_idx

        ################################################################
        # calculate the request intervals and verify accuracy
        ################################################################
        self.process_request_items()
        print("Interval Times:\n")
        print(
            "\nreq_ID | arrival idx |    send | t arrival | exp arrival | "
            "act arrival | exp delay | act delay |        diff ratio |"
        )

        first_send_time = self.request_items[0].send_time_ns
        for req_item in self.request_items:
            extra_time = 0.0
            if req_item.expected_delay_ns == 0.0:
                extra_time = self.target_interval_ns
            expected_actual_diff_ratio = (
                req_item.actual_delay_ns - req_item.expected_delay_ns
            ) / (req_item.expected_delay_ns + extra_time)

            line4_val = (
                req_item.throttle_arrival_time_ns - first_send_time
            ) * NS_2_SECS
            line5_val = (
                req_item.expected_func_arrival_time_ns - first_send_time
            ) * NS_2_SECS
            line6_val = (
                req_item.actual_func_arrival_time_ns - first_send_time
            ) * NS_2_SECS
            print(
                f"    {req_item.req_id:2} "
                f"|          {req_item.arrival_idx:2} "
                f"| {(req_item.send_time_ns - first_send_time) * NS_2_SECS:7.4f} "
                f"|   {line4_val:7.4f} "
                f"|     {line5_val:7.4f} "
                f"|     {line6_val:7.4f} "
                f"|   {req_item.expected_delay_ns * NS_2_SECS:7.4f} "
                f"|   {req_item.actual_delay_ns * NS_2_SECS:7.4f} "
                f"|    {expected_actual_diff_ratio * NS_2_SECS:7.12f} |"
            )

        print(f"{self.cumulative_expected_delay_ns=}")
        print(f"{self.cumulative_actual_delay_ns=}")

        ratio_delay_time = (
            self.cumulative_actual_delay_ns - self.cumulative_expected_delay_ns
        ) / (self.target_interval_ns * self.total_requests)
        print(f"ratio diff expected/actual: {ratio_delay_time:.4f}")

        # assert throttle_verifier.num_excessive_request_delays < 4
        assert ratio_delay_time <= 0.06

        self.reset()

    ####################################################################
    # process_request_items
    ####################################################################
    def process_request_items(self) -> None:
        """Validate the results for sync leaky bucket."""
        # Calculate the interval between request send and exit receive
        # as observed by the requestor.

        self.request_items[0].expected_delay_ns = 0

        # self.request_items[0].expected_func_arrival_time_ns =
        # self.request_items[
        #     0
        # ].send_time_ns
        # self.request_items[0].actual_delay_ns = (
        #     self.request_items[0].actual_func_arrival_time_ns
        #     - self.request_items[0].send_time_ns
        # )
        self.request_items[0].expected_func_arrival_time_ns = self.request_items[
            0
        ].throttle_arrival_time_ns

        self.request_items[0].actual_delay_ns = (
            self.request_items[0].actual_func_arrival_time_ns
            - self.request_items[0].throttle_arrival_time_ns
        )
        amount_in_bucket_ns = self.target_interval_ns  # init with 1st
        max_bucket_amount_ns = self.bucket_size * self.target_interval_ns
        for idx in range(1, len(self.request_items)):
            # interval_ns = self.request_items[idx].
            # throttle_arrival_time_ns - (
            #     self.request_items[idx - 1].throttle_sent_time_ns
            # )
            interval_ns = self.request_items[idx].throttle_arrival_time_ns - (
                self.request_items[idx - 1].throttle_arrival_time_ns
            )
            logger.debug(f"e1: {idx=}, {interval_ns=}, {amount_in_bucket_ns=}")
            amount_in_bucket_ns = max(0, amount_in_bucket_ns - interval_ns)
            logger.debug(f"e2: {idx=}, {interval_ns=}, {amount_in_bucket_ns=}")

            if max_bucket_amount_ns - amount_in_bucket_ns < self.target_interval_ns:
                exp_delay_ns = amount_in_bucket_ns - (
                    max_bucket_amount_ns - self.target_interval_ns
                )

                # set bucket to full since we will wait before sending
                # at which time it will be full
                # amount_in_bucket_ns = max_bucket_amount_ns
                amount_in_bucket_ns += self.target_interval_ns
                logger.debug(f"e3: {idx=}, {exp_delay_ns=}, {amount_in_bucket_ns=}")
            else:  # there is room in the bucket
                exp_delay_ns = 0
                amount_in_bucket_ns += self.target_interval_ns
                logger.debug(f"e4: {idx=}, {exp_delay_ns=}, {amount_in_bucket_ns=}")

            self.request_items[idx].expected_delay_ns = exp_delay_ns

            # self.request_items[idx].expected_delay_ns = max(
            #     0,
            #     self.request_items[idx - 1].
            #     throttle_next_target_time_ns
            #     - self.request_items[idx].send_time_ns,
            # )
            # self.request_items[idx].expected_func_arrival_time_ns = (
            #     self.request_items[idx].send_time_ns
            #     + self.request_items[idx].expected_delay_ns
            # )
            self.request_items[idx].expected_func_arrival_time_ns = (
                self.request_items[idx].throttle_arrival_time_ns
                + self.request_items[idx].expected_delay_ns
            )
            # self.request_items[idx].actual_delay_ns = (
            #     self.request_items[idx].actual_func_arrival_time_ns
            #     - self.request_items[idx].send_time_ns
            # )
            self.request_items[idx].actual_delay_ns = (
                self.request_items[idx].actual_func_arrival_time_ns
                - self.request_items[idx].throttle_arrival_time_ns
            )

            assert (
                abs((self.request_items[idx].throttle_wait_time_ns - exp_delay_ns))
                / self.target_interval_ns
                < 0.01
            )

            # assert (
            #     self.request_items[idx].expected_delay_ns
            #     <= self.request_items[idx].actual_delay_ns
            # )

            self.cumulative_expected_delay_ns += self.request_items[
                idx
            ].expected_delay_ns
            self.cumulative_actual_delay_ns += self.request_items[idx].actual_delay_ns

            self.cumulative_throttle_wait_time_ns += self.request_items[
                idx
            ].throttle_wait_time_ns

    ####################################################################
    # request0c
    ####################################################################
    def request0c(self, request_item: RequestItem) -> int:
        """Request0 target.

        Returns:
            the index reflected back

        Notes:
              1) this code is serialized by the throttle lock
        """

        self.idx += 1
        request_item.arrival_idx = self.idx  # first is zero
        request_item.actual_func_arrival_time_ns = perf_counter_ns()
        request_item.throttle_arrival_time_ns = self.t_throttle._arrival_time_ns
        request_item.throttle_next_target_time_ns = self.t_throttle._next_target_time_ns
        request_item.throttle_wait_time_ns = self.t_throttle._wait_time_ns
        request_item.throttle_sent_time_ns = self.t_throttle.sent_time_ns
        self.request_items.append(request_item)
        # logger.debug(f"{self.idx=}: {self.request_items=}")

        return self.idx

    ####################################################################
    # request0b
    ####################################################################
    def request0b(self) -> int:
        """Request0 target.

        Returns:
            the index reflected back

        Notes:
              1) this code is serialized by the throttle lock
        """

        # logger.debug("request0b entered")
        # logger.debug(f"{self.request_item=}")
        self.idx += 1
        request_item = self.request_deque.pop()
        assert request_item.req_id == self.idx
        request_item.arrival_idx = self.idx  # first is zero
        request_item.actual_func_arrival_time_ns = perf_counter_ns()
        request_item.throttle_arrival_time_ns = self.t_throttle._arrival_time_ns
        request_item.throttle_next_target_time_ns = self.t_throttle._next_target_time_ns
        request_item.throttle_wait_time_ns = self.t_throttle._wait_time_ns
        request_item.throttle_sent_time_ns = self.t_throttle.sent_time_ns
        self.request_items.append(request_item)

        # logger.debug("request0b exiting")
        return request_item.req_id

    ####################################################################
    # request1b
    ####################################################################
    def request1b(self, req_id: int) -> int:
        """Request1 target.

        Args:
            req_id: the req_id in the request

        Returns:
            the index reflected back
        """
        self.idx += 1
        request_item = self.request_deque.pop()
        request_item.arrival_idx = self.idx  # first is zero
        request_item.actual_func_arrival_time_ns = perf_counter_ns()
        request_item.throttle_arrival_time_ns = self.t_throttle._arrival_time_ns
        request_item.throttle_next_target_time_ns = self.t_throttle._next_target_time_ns
        request_item.throttle_wait_time_ns = self.t_throttle._wait_time_ns
        request_item.throttle_sent_time_ns = self.t_throttle.sent_time_ns
        self.request_items.append(request_item)
        assert req_id == request_item.req_id

        return request_item.req_id

    ####################################################################
    # request2b
    ####################################################################
    # def request2b(self, idx: int, requests: int,
    # obtained_nowait: bool) -> int:
    def request2b(self, req_id: int, reqs_per_sec: float) -> int:
        """Request2 target.

        Args:
            req_id: the req_id in the request
            reqs_per_sec: number of requests per second for the throttle

        Returns:
            the index reflected back
        """
        self.idx += 1
        request_item = self.request_deque.pop()
        request_item.arrival_idx = self.idx  # first is zero
        request_item.actual_func_arrival_time_ns = perf_counter_ns()
        request_item.throttle_arrival_time_ns = self.t_throttle._arrival_time_ns
        request_item.throttle_next_target_time_ns = self.t_throttle._next_target_time_ns
        request_item.throttle_wait_time_ns = self.t_throttle._wait_time_ns
        request_item.throttle_sent_time_ns = self.t_throttle.sent_time_ns
        self.request_items.append(request_item)

        assert req_id == request_item.req_id
        assert reqs_per_sec == self.reqs_per_sec
        return request_item.req_id

    ####################################################################
    # request3b
    ####################################################################
    def request3b(self, *, req_id: int) -> int:
        """Request3 target.

        Args:
            req_id: the req_id in the request

        Returns:
            the index reflected back
        """
        self.idx += 1
        request_item = self.request_deque.pop()
        request_item.arrival_idx = self.idx  # first is zero
        request_item.actual_func_arrival_time_ns = perf_counter_ns()
        request_item.throttle_arrival_time_ns = self.t_throttle._arrival_time_ns
        request_item.throttle_next_target_time_ns = self.t_throttle._next_target_time_ns
        request_item.throttle_wait_time_ns = self.t_throttle._wait_time_ns
        request_item.throttle_sent_time_ns = self.t_throttle.sent_time_ns
        self.request_items.append(request_item)

        assert req_id == request_item.req_id

        return request_item.req_id

    ####################################################################
    # request4b
    ####################################################################
    def request4b(self, *, req_id: int, send_interval: float) -> int:
        """Request4 target.

        Args:
            req_id: the req_id in the request
            send_interval: the interval used between requests

        Returns:
            the index reflected back
        """
        self.idx += 1
        request_item = self.request_deque.pop()
        request_item.arrival_idx = self.idx  # first is zero
        request_item.actual_func_arrival_time_ns = perf_counter_ns()
        request_item.throttle_arrival_time_ns = self.t_throttle._arrival_time_ns
        request_item.throttle_next_target_time_ns = self.t_throttle._next_target_time_ns
        request_item.throttle_wait_time_ns = self.t_throttle._wait_time_ns
        request_item.throttle_sent_time_ns = self.t_throttle.sent_time_ns
        self.request_items.append(request_item)

        assert req_id == request_item.req_id
        assert send_interval == self.send_interval
        return request_item.req_id

    ####################################################################
    # request5b
    ####################################################################
    def request5b(self, req_id: int, *, send_interval: float) -> int:
        """Request5 target.

        Args:
            req_id: the req_id in the request
            send_interval: the interval used between requests

        Returns:
            the index reflected back
        """
        self.idx += 1
        request_item = self.request_deque.pop()
        request_item.arrival_idx = self.idx  # first is zero
        request_item.actual_func_arrival_time_ns = perf_counter_ns()
        request_item.throttle_arrival_time_ns = self.t_throttle._arrival_time_ns
        request_item.throttle_next_target_time_ns = self.t_throttle._next_target_time_ns
        request_item.throttle_wait_time_ns = self.t_throttle._wait_time_ns
        request_item.throttle_sent_time_ns = self.t_throttle.sent_time_ns
        self.request_items.append(request_item)

        assert req_id == request_item.req_id
        assert send_interval == self.send_interval
        return request_item.req_id

    ####################################################################
    # request6b
    ####################################################################
    def request6b(
        self,
        req_id: int,
        reqs_per_sec: float,
        *,
        bucket_size: float,
        send_interval: float,
    ) -> int:
        """Request5 target.

         Args:
            req_id: the req_id in the request
            reqs_per_sec: number of requests per second for the throttle
            bucket_size: bucket size for throttle
            send_interval: the interval used between requests

        Returns:
            the index reflected back
        """
        self.idx += 1
        request_item = self.request_deque.pop()
        request_item.arrival_idx = self.idx  # first is zero
        request_item.actual_func_arrival_time_ns = perf_counter_ns()
        request_item.throttle_arrival_time_ns = self.t_throttle._arrival_time_ns
        request_item.throttle_next_target_time_ns = self.t_throttle._next_target_time_ns
        request_item.throttle_wait_time_ns = self.t_throttle._wait_time_ns
        request_item.throttle_sent_time_ns = self.t_throttle.sent_time_ns
        self.request_items.append(request_item)

        assert req_id == request_item.req_id
        assert reqs_per_sec == self.reqs_per_sec
        assert bucket_size == self.bucket_size
        assert send_interval == self.send_interval
        return request_item.req_id


########################################################################
# TestThrottleDocstrings class
########################################################################
class TestThrottleDocstrings:
    """Class TestThrottleDocstrings."""

    ####################################################################
    # test_throttle_example_1
    ####################################################################
    def test_throttle_example_1(self, capsys: Any) -> None:
        """Method test_throttle_example_1.

        Args:
            capsys: pytest fixture to capture print output

        """
        hdr_str = ":Example 1: Throttle at 1 requests per second:"
        flowers(hdr_str)

        from scottbrian_throttle.throttle import throttle
        import time

        @throttle
        def func1(request_number: int, time_of_start: float):
            ret_value = (
                f"request {request_number} sent at elapsed time: "
                f"{time.time() - time_of_start:0.1f}"
            )
            return ret_value

        start_time = time.time()
        for idx in range(10):
            ret_val = func1(idx, start_time)
            print(ret_val)

        flower_str = ("*" * (len(hdr_str) + 4)) + "\n"

        expected_result = "\n" + flower_str
        expected_result += f"* {hdr_str} *\n"
        expected_result += flower_str
        expected_result += "request 0 sent at elapsed time: 0.0\n"
        expected_result += "request 1 sent at elapsed time: 1.0\n"
        expected_result += "request 2 sent at elapsed time: 2.0\n"
        expected_result += "request 3 sent at elapsed time: 3.0\n"
        expected_result += "request 4 sent at elapsed time: 4.0\n"
        expected_result += "request 5 sent at elapsed time: 5.0\n"
        expected_result += "request 6 sent at elapsed time: 6.0\n"
        expected_result += "request 7 sent at elapsed time: 7.0\n"
        expected_result += "request 8 sent at elapsed time: 8.0\n"
        expected_result += "request 9 sent at elapsed time: 9.0\n"

        captured = capsys.readouterr().out

        assert captured == expected_result

    ####################################################################
    # test_throttle_example_2
    ####################################################################
    def test_throttle_example_2(self, capsys: Any) -> None:
        """Method test_throttle_example_2.

        Args:
            capsys: pytest fixture to capture print output

        """

        hdr_str = ":Example 2: Throttle at 2 requests per second:"
        flowers(hdr_str)

        from scottbrian_throttle.throttle import throttle
        import time

        @throttle(reqs_per_sec=2)
        def func2(request_number: int, time_of_start: float):
            ret_value = (
                f"request {request_number} sent at elapsed time: "
                f"{time.time() - time_of_start:0.1f}"
            )
            return ret_value

        start_time = time.time()
        for idx in range(10):
            ret_val = func2(idx, start_time)
            print(ret_val)

        flower_str = ("*" * (len(hdr_str) + 4)) + "\n"

        expected_result = "\n" + flower_str
        expected_result += f"* {hdr_str} *\n"
        expected_result += flower_str
        expected_result += "request 0 sent at elapsed time: 0.0\n"
        expected_result += "request 1 sent at elapsed time: 0.5\n"
        expected_result += "request 2 sent at elapsed time: 1.0\n"
        expected_result += "request 3 sent at elapsed time: 1.5\n"
        expected_result += "request 4 sent at elapsed time: 2.0\n"
        expected_result += "request 5 sent at elapsed time: 2.5\n"
        expected_result += "request 6 sent at elapsed time: 3.0\n"
        expected_result += "request 7 sent at elapsed time: 3.5\n"
        expected_result += "request 8 sent at elapsed time: 4.0\n"
        expected_result += "request 9 sent at elapsed time: 4.5\n"

        time.sleep(1)
        captured = capsys.readouterr().out

        assert captured == expected_result

    ####################################################################
    # test_throttle_example_3
    ####################################################################
    def test_throttle_example_3(self, capsys: Any) -> None:
        """Method test_throttle_example_3.

        Args:
            capsys: pytest fixture to capture print output

        """

        hdr_str = ":Example 3: throttle with async function in asyncio environment:"
        flowers(hdr_str)

        from scottbrian_throttle.throttle import throttle
        import asyncio
        import time

        @throttle(reqs_per_sec=2)
        async def func3(request_number: int, time_of_start: float):
            print(
                f"request {request_number} sent at elapsed time: "
                f"{time.time() - time_of_start:0.1f}"
            )

        async def main_loop():
            start_time = time.time()
            for idx in range(10):
                await func3(idx, start_time)

        asyncio.run(main_loop())

        flower_str = ("*" * (len(hdr_str) + 4)) + "\n"

        expected_result = "\n" + flower_str
        expected_result += f"* {hdr_str} *\n"
        expected_result += flower_str
        expected_result += "request 0 sent at elapsed time: 0.0\n"
        expected_result += "request 1 sent at elapsed time: 0.5\n"
        expected_result += "request 2 sent at elapsed time: 1.0\n"
        expected_result += "request 3 sent at elapsed time: 1.5\n"
        expected_result += "request 4 sent at elapsed time: 2.0\n"
        expected_result += "request 5 sent at elapsed time: 2.5\n"
        expected_result += "request 6 sent at elapsed time: 3.0\n"
        expected_result += "request 7 sent at elapsed time: 3.5\n"
        expected_result += "request 8 sent at elapsed time: 4.0\n"
        expected_result += "request 9 sent at elapsed time: 4.5\n"

        time.sleep(1)
        captured = capsys.readouterr().out

        assert captured == expected_result

    ####################################################################
    # test_throttle_example_4
    ####################################################################
    def test_throttle_example_4(self, capsys: Any) -> None:
        """Method test_throttle_example_4.

        Args:
            capsys: pytest fixture to capture print output

        """

        hdr_str = ":Example 4: throttle with non-async function in asyncio environment:"
        flowers(hdr_str)

        from scottbrian_throttle.throttle import throttle
        import asyncio
        import time

        @throttle(reqs_per_sec=2)
        def func4(request_number: int, time_of_start: float):
            print(
                f"request {request_number} sent at elapsed time: "
                f"{time.time() - time_of_start:0.1f}"
            )

        async def main_loop():
            start_time = time.time()
            for idx in range(10):
                await asyncio.to_thread(func4, idx, start_time)

        asyncio.run(main_loop())

        flower_str = ("*" * (len(hdr_str) + 4)) + "\n"

        expected_result = "\n" + flower_str
        expected_result += f"* {hdr_str} *\n"
        expected_result += flower_str
        expected_result += "request 0 sent at elapsed time: 0.0\n"
        expected_result += "request 1 sent at elapsed time: 0.5\n"
        expected_result += "request 2 sent at elapsed time: 1.0\n"
        expected_result += "request 3 sent at elapsed time: 1.5\n"
        expected_result += "request 4 sent at elapsed time: 2.0\n"
        expected_result += "request 5 sent at elapsed time: 2.5\n"
        expected_result += "request 6 sent at elapsed time: 3.0\n"
        expected_result += "request 7 sent at elapsed time: 3.5\n"
        expected_result += "request 8 sent at elapsed time: 4.0\n"
        expected_result += "request 9 sent at elapsed time: 4.5\n"

        time.sleep(1)
        captured = capsys.readouterr().out

        assert captured == expected_result

    ####################################################################
    # test_throttle_example_5
    ####################################################################
    def test_throttle_example_5(self, capsys: Any) -> None:
        """Method test_throttle_example_5.

        Args:
            capsys: pytest fixture to capture print output

        """

        hdr_str = ":Example 5: throttle with convert to async in asyncio environment:"
        flowers(hdr_str)

        from scottbrian_throttle.throttle import throttle
        import asyncio
        import time

        @throttle(reqs_per_sec=2, convert_to_async=True)
        def func5(request_number: int, time_of_start: float):
            print(
                f"request {request_number} sent at elapsed time: "
                f"{time.time() - time_of_start:0.1f}"
            )

        async def main_loop():
            start_time = time.time()
            for idx in range(10):
                await func5(idx, start_time)

        asyncio.run(main_loop())

        flower_str = ("*" * (len(hdr_str) + 4)) + "\n"

        expected_result = "\n" + flower_str
        expected_result += f"* {hdr_str} *\n"
        expected_result += flower_str
        expected_result += "request 0 sent at elapsed time: 0.0\n"
        expected_result += "request 1 sent at elapsed time: 0.5\n"
        expected_result += "request 2 sent at elapsed time: 1.0\n"
        expected_result += "request 3 sent at elapsed time: 1.5\n"
        expected_result += "request 4 sent at elapsed time: 2.0\n"
        expected_result += "request 5 sent at elapsed time: 2.5\n"
        expected_result += "request 6 sent at elapsed time: 3.0\n"
        expected_result += "request 7 sent at elapsed time: 3.5\n"
        expected_result += "request 8 sent at elapsed time: 4.0\n"
        expected_result += "request 9 sent at elapsed time: 4.5\n"

        time.sleep(1)
        captured = capsys.readouterr().out

        assert captured == expected_result

    ####################################################################
    # test_throttle_example_6
    ####################################################################
    def test_throttle_example_6(self, capsys: Any) -> None:
        """Method test_throttle_example_6.

        Args:
            capsys: pytest fixture to capture print output

        """

        hdr_str = ":Example 6: Throttle with a *bucket_size* of 3:"
        flowers(hdr_str)

        from scottbrian_throttle.throttle import throttle
        import time

        @throttle(reqs_per_sec=2, bucket_size=3)
        def func4(request_number, time_of_start):
            print(
                f"request {request_number} sent at elapsed time: "
                f"{time.time() - time_of_start:0.1f}"
            )

        start_time = time.time()
        for idx in range(10):
            func4(idx, start_time)

        flower_str = ("*" * (len(hdr_str) + 4)) + "\n"

        expected_result = "\n" + flower_str
        expected_result += f"* {hdr_str} *\n"
        expected_result += flower_str
        expected_result += "request 0 sent at elapsed time: 0.0\n"
        expected_result += "request 1 sent at elapsed time: 0.0\n"
        expected_result += "request 2 sent at elapsed time: 0.0\n"
        expected_result += "request 3 sent at elapsed time: 0.5\n"
        expected_result += "request 4 sent at elapsed time: 1.0\n"
        expected_result += "request 5 sent at elapsed time: 1.5\n"
        expected_result += "request 6 sent at elapsed time: 2.0\n"
        expected_result += "request 7 sent at elapsed time: 2.5\n"
        expected_result += "request 8 sent at elapsed time: 3.0\n"
        expected_result += "request 9 sent at elapsed time: 3.5\n"

        captured = capsys.readouterr().out

        assert captured == expected_result

    ####################################################################
    # test_throttle_example_T1
    ####################################################################
    def test_throttle_example_T1(self, capsys: Any) -> None:
        """Method test_throttle_example_T1.

        Args:
            capsys: pytest fixture to capture print output

        """

        hdr_str = ":Example 1: call __repr__ for Throttle"
        flowers(hdr_str)

        from scottbrian_throttle.throttle import throttle

        @throttle(reqs_per_sec=0.5)
        def func1(request_number, time_of_start):
            pass

        print(repr(func1.throttle))

        flower_str = ("*" * (len(hdr_str) + 4)) + "\n"

        expected_result = "\n" + flower_str
        expected_result += f"* {hdr_str} *\n"
        expected_result += flower_str
        expected_result += "Throttle(reqs_per_sec=0.5, bucket_size=1.0, convert_to_async=False, name=func1)\n"

        captured = capsys.readouterr().out

        assert captured == expected_result

    ####################################################################
    # test_throttle_example_7
    ####################################################################
    def test_throttle_example_7(self, capsys: Any) -> None:
        """Method test_throttle_example_7.

        Args:
            capsys: pytest fixture to capture print output

        """

        hdr_str = ":Example 7: get length for an asynchronous throttle"
        flowers(hdr_str)

        from scottbrian_throttle.throttle import throttle

        class Funky:
            def __init__(self, a_var: int):
                self.funky_var = a_var

            @throttle(reqs_per_sec=2)
            def func7a(self):
                self.funky_var += 1

            @throttle(reqs_per_sec=3)
            def func7b(self):
                self.funky_var += 10

        funky1 = Funky(a_var=2)
        funky2 = Funky(a_var=102)

        funky1.func7a()

        funky1.func7b()
        funky1.func7b()

        funky2.func7a()
        funky2.func7a()
        funky2.func7a()

        funky2.func7b()
        funky2.func7b()
        funky2.func7b()
        funky2.func7b()

        print(
            f"\n{funky1.func7a.throttle.reqs_per_sec=}, {funky1.func7a.throttle.call_count=}, {funky1.funky_var=}, {id(funky1.func7a.throttle)=}\n"
        )
        print(
            f"\n{funky1.func7b.throttle.reqs_per_sec=}, {funky1.func7b.throttle.call_count=}, {funky1.funky_var=}, {id(funky1.func7b.throttle)=}\n"
        )

        print(
            f"\n{funky2.func7a.throttle.reqs_per_sec=}, {funky2.func7a.throttle.call_count=}, {funky2.funky_var=}, {id(funky2.func7a.throttle)=}\n"
        )
        print(
            f"\n{funky2.func7b.throttle.reqs_per_sec=}, {funky2.func7b.throttle.call_count=}, {funky2.funky_var=}, {id(funky2.func7b.throttle)=}\n"
        )
