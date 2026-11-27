"""Module test_throttle.

Copyright (C) 2026 Scott Tuttle
All rights reserved
Licensed under the MIT License. See LICENSE file in the project root for
details
"""

import asyncio
import concurrent.futures
import gc
import inspect
import logging
import random
import re
import threading
import time
from collections import deque
from collections.abc import Callable, Coroutine
from dataclasses import dataclass, field

########################################################################
# Standard Library
########################################################################
from enum import Enum, auto
from time import perf_counter_ns
from typing import Any, Final, ParamSpec, TypeVar, cast
from unittest.mock import patch

import pytest

########################################################################
# Third Party
########################################################################
from pydantic import ValidationError
from scottbrian_utils.diag_msg import get_caller_info
from scottbrian_utils.entry_trace import etrace
from scottbrian_utils.flower_box import print_flower_box_msg as flowers
from scottbrian_utils.log_verifier import LogVer
from scottbrian_utils.pauser import Pauser
from scottbrian_utils.testlib_verifier import verify_lib

########################################################################
# Local
########################################################################
import scottbrian_throttle
from scottbrian_throttle.throttle import FuncWithThrottleAttr, throttle
from scottbrian_throttle.throttle_blocks import Throttle

########################################################################


logger = logging.getLogger(__name__)


P = ParamSpec("P")
R = TypeVar("R")
F = TypeVar("F", bound=Callable[..., Any])

########################################################################
# Constants
########################################################################
MAX_RATIO_EXP_VS_ACT_DELAY = 1.10
Max_Diff_Threshold_SECS = 0.5


########################################################################
# Throttle test exceptions
########################################################################
class TestThrottleError(Exception):
    """Base class for exception in this module."""


class Mode(Enum):
    """Choose the test mode for sync or async."""

    SYNC = auto()
    SYNC_CONVERT = auto()
    ASYNC = auto()


class MethodType(Enum):
    """Choose the method type used for test."""

    INSTANCE = auto()
    STATIC = auto()
    CLASS = auto()


class RequestStyle(Enum):
    """Choose the method type used for test."""

    NO_ARGS = 0
    POS_1 = auto()
    POS_2 = auto()
    KW_1 = auto()
    KW_2 = auto()
    POS_1_KW_1 = auto()
    POS_2_KW_2 = auto()


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


@dataclass
class ExpectedAndActualTimes:
    """ExpectedAndActualTimes used to track times and intervals."""

    expected_time_ns: float = 0.0
    actual_time_ns: float = 0.0
    expected_interval_ns: float = 0.0
    actual_interval_ns: float = 0.0
    interval_diff_ns: float = 0.0
    interval_diff_pct: float = 0.0


########################################################################
# RequestItem data class used to track requests
########################################################################
@dataclass
class RequestItem:
    """RequestItem class used to gather times for a request."""

    # the req_id is assigned when the request item is created
    req_id: int = 0

    # arrival_idx is assigned by the req target code when entered
    arrival_idx: int = 0

    # thread_idx identifies the thread where the request is run
    thread_idx: int = 0

    # delays
    expected_pause_delay_ns: float = 0.0
    actual_pause_delay_ns: float = 0.0

    expected_lock_delay_ns: float = 0.0
    actual_lock_delay_ns: float = 0.0

    expected_throttle_delay_ns: float = 0.0
    actual_throttle_delay_ns: float = 0.0

    expected_target_delay_ns: float = 0.0
    actual_target_delay_ns: float = 0.0

    expected_create_delay_ns: float = 0.0
    actual_create_delay_ns: float = 0.0

    # create time is the start of a request before any pause. The
    # create interval is the time from the previous request return time
    # to this request create time
    create_times: ExpectedAndActualTimes = field(default_factory=ExpectedAndActualTimes)

    # start time is when the request is invoked which then calls the
    # throttle. The start interval is the interval from create to start
    # which includes the pause delay for a pause greater than zero
    start_times: ExpectedAndActualTimes = field(default_factory=ExpectedAndActualTimes)

    # throttle_arrival time is when the lock has been obtained
    throttle_arrival_times: ExpectedAndActualTimes = field(
        default_factory=ExpectedAndActualTimes
    )

    # throttle send time is when the throttle calls the target
    throttle_send_times: ExpectedAndActualTimes = field(
        default_factory=ExpectedAndActualTimes
    )

    # request return time is when the target has finished and returns to
    # the caller. The time includes a target delay, if one.
    return_times: ExpectedAndActualTimes = field(default_factory=ExpectedAndActualTimes)

    throttle_arrival_time_ns: float = 0.0

    expected_request_interval_ns: float = 0.0

    throttle_mode: Mode = Mode.SYNC

    # send_interval set by sender when sending request
    send_interval: float = 0.0

    send_time_ns: float = 0.0  # after interval pause

    throttle_sent_time_ns: float = 0.0

    # actual_func_arrival_time_ns assigned by the req target code when
    # entered
    expected_func_arrival_time_ns: float = 0.0
    actual_func_arrival_time_ns: float = 0.0

    throttle_next_target_time_ns: float = 0.0

    throttle_wait_time_ns: float = 0.0

    # delay time that target function will simulate
    target_delay_time_ns: float = 0.0

    # return_time_ns set by sender when req returns
    return_time_ns: float = 0.0


req_style_map: dict[RequestStyle, tuple[str, str, str]] = {
    RequestStyle.NO_ARGS: ("f0", "()", "request_id + 42 + 0"),
    RequestStyle.POS_1: ("f1", "(request_id)", "request_id + 42 + 1"),
    RequestStyle.POS_2: (
        "f2",
        "(request_id, reqs_per_sec_arg)",
        "request_id + 42 + 2",
    ),
    RequestStyle.KW_1: ("f3", "(req_id=request_id)", "request_id + 42 + 3"),
    RequestStyle.KW_2: (
        "f4",
        "(req_id=request_id, interval=s_interval)",
        "request_id + 42 + 4",
    ),
    RequestStyle.POS_1_KW_1: (
        "f5",
        "(req_id=request_id, interval=s_interval)",
        "request_id + 42 + 5",
    ),
    RequestStyle.POS_2_KW_2: (
        "f6",
        "(request_id, reqs_per_sec_arg, bucket_size=1, interval=s_interval)",
        "request_id + 42 + 6",
    ),
}


@dataclass
class MaxDiffs:
    """Contains max differences."""

    max_pause_diff: float = 0.0
    max_arrival_diff: float = 0.0
    max_t_delay_diff: float = 0.0
    max_return_diff: float = 0.0
    max_next_create_diff: float = 0.0


random.seed(42)


########################################################################
# TestThrottleCorrectSource
########################################################################
class TestThrottleCorrectSource:
    """Verify that we are testing with correctly built code."""

    ####################################################################
    # test_unique_ts_correct_source
    ####################################################################
    @staticmethod
    def test_throttle_correct_source() -> None:
        """Test unique_ts correct source."""
        print("TESTING FROM PATH:", scottbrian_throttle.__file__)
        exp_path = (
            "PycharmProjects\\scottbrian_throttle\\dist\\unpacked\\scottbrian_throttle"
        )
        assert exp_path in scottbrian_throttle.__file__

        testlib_path = verify_lib(
            obj_to_check=Throttle,
            str_to_check="PycharmProjects/scottbrian_throttle/dist/unpacked/scottbrian_throttle",
        )
        logger.debug(f"{testlib_path=}")
        assert testlib_path.endswith("throttle_blocks.py")


########################################################################
# TestThrottleBasic class to test Throttle methods
########################################################################
class TestThrottleBasic:
    """Test basic functions of Throttle."""

    ####################################################################
    # repr
    ####################################################################
    @pytest.mark.parametrize("convert_to_async_arg", (True, False))
    @pytest.mark.parametrize("name_arg", ("t1", "t2"))
    # See conftest for additional parametrized args
    @etrace(omit_caller=True)
    @staticmethod
    def test_throttle_repr(
        *,
        reqs_per_sec_arg: float,
        bucket_size_arg: float,
        convert_to_async_arg: bool,
        name_arg: str,
    ) -> None:
        """test_throttle repr with various reqs_per_sec.

        Args:
            reqs_per_sec_arg: request per second
            bucket_size_arg: leaky bucket size
            convert_to_async_arg: choose whether to convert
            name_arg: throttle name


        """
        ################################################################
        # throttle
        ################################################################
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

        assert repr(a_throttle) == expected_repr_str


########################################################################
# TestThrottleDecoratorErrors class
########################################################################
class TestThrottleDecoratorErrors:
    """TestThrottleDecoratorErrors class."""

    @staticmethod
    def test_pie_reqs_to_sec_args() -> None:
        """test_throttle using reqs_to_sec arguments."""
        ################################################################
        # bad reqs_per_sec
        ################################################################
        ml_error_msg = re.escape(
            "1 validation error for throttle\nreqs_per_sec\n  "
            "Input should be greater than 0 "
            "[type=greater_than, input_value=-1, input_type=int]",
        )

        with pytest.raises(ValidationError, match=ml_error_msg):

            @throttle(reqs_per_sec=-1)
            def f1() -> None:
                pass

        ml_error_msg = re.escape(
            "1 validation error for throttle\nreqs_per_sec\n  "
            "Input should be greater than 0 "
            "[type=greater_than, input_value=0, input_type=int]",
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

    @staticmethod
    def test_pie_bucket_size_args() -> None:
        """test_throttle using bucket_size arguments."""
        ################################################################
        # bad bucket_size
        ################################################################
        ml_error_msg = re.escape(
            "1 validation error for throttle\nbucket_size\n  "
            "Input should be greater than or equal to 1 "
            "[type=greater_than_equal, input_value=-1, input_type=int]",
        )
        with pytest.raises(ValidationError, match=ml_error_msg):

            @throttle(bucket_size=-1)
            def f7() -> None:
                pass

        ml_error_msg = re.escape(
            "1 validation error for throttle\nbucket_size\n  "
            "Input should be greater than or equal to 1 "
            "[type=greater_than_equal, input_value=0, input_type=int]",
        )
        with pytest.raises(ValidationError, match=ml_error_msg):

            @throttle(reqs_per_sec=1, bucket_size=0)
            def f8() -> None:
                pass

        ml_error_msg = re.escape(
            "1 validation error for throttle\nbucket_size\n  "
            "Input should be greater than or equal to 1 "
            "[type=greater_than_equal, input_value=0.3, input_type=float]",
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

    @staticmethod
    def test_pie_convert_to_async_args() -> None:  # ruff: ignore[complex-structure]
        """test_throttle using convert_to_async arguments."""
        ################################################################
        # bad convert_to_async
        ################################################################
        ml_error_msg = re.escape(
            "1 validation error for throttle\nconvert_to_async\n  "
            "Input should be a valid boolean, unable to interpret input "
            "[type=bool_parsing, input_value='blue', input_type=str]",
        )
        with pytest.raises(ValidationError, match=ml_error_msg):

            @throttle(convert_to_async="blue")  # type: ignore [call-overload, untyped-decorator]
            def f12() -> None:
                pass

        ml_error_msg = re.escape(
            "1 validation error for throttle\nconvert_to_async\n  "
            "Input should be a valid boolean, unable to interpret input "
            "[type=bool_parsing, input_value=2, input_type=int]",
        )
        with pytest.raises(ValidationError, match=ml_error_msg):

            @throttle(convert_to_async=2)  # type: ignore [call-overload, untyped-decorator]
            def f13() -> None:
                pass

        # the following are valid
        @throttle(convert_to_async=True)
        def f14() -> None:
            pass

        @throttle(convert_to_async=False)
        def f15() -> None:
            pass

        @throttle(convert_to_async="True")  # type: ignore [call-overload, untyped-decorator]
        def f16() -> None:
            pass

        @throttle(convert_to_async="False")  # type: ignore [call-overload, untyped-decorator]
        def f17() -> None:
            pass

        @throttle(convert_to_async=1)  # type: ignore [call-overload, untyped-decorator]
        def f18() -> None:
            pass

        @throttle(convert_to_async=0)  # type: ignore [call-overload, untyped-decorator]
        def f19() -> None:
            pass

        @throttle(convert_to_async="yes")  # type: ignore [call-overload, untyped-decorator]
        def f20() -> None:
            pass

        @throttle(convert_to_async="no")  # type: ignore [call-overload, untyped-decorator]
        def f21() -> None:
            pass

        my_ans = True

        @throttle(convert_to_async=my_ans)
        def f22() -> None:
            pass


########################################################################
# TestThrottleDecoratorErrors class
########################################################################
class TestThrottleDecoratorRequestErrors:
    """TestThrottleDecoratorErrors class."""

    @staticmethod
    def test_pie_throttle_request_errors(
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """test_throttle using request failure.

        Args:
            caplog: pytest fixture to capture log output

        """
        log_ver = LogVer(log_name=__name__)
        logging.getLogger("asyncio").setLevel(logging.WARNING)
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

        @throttle(reqs_per_sec=1)
        def f1() -> None:
            ans = 42 / 0
            print(f"{ans=}")

        with pytest.raises(ZeroDivisionError):
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

        @throttle(reqs_per_sec=1, bucket_size=2)
        def f2() -> None:
            ans = 42 / 0
            print(f"{ans=}")

        with pytest.raises(ZeroDivisionError):
            f2()

        ################################################################
        # sync to async to_thread request failure
        ################################################################
        log_msg = "Exception in sync to async to_thread for 'f3': division by zero"
        log_ver.add_pattern(
            log_name="scottbrian_throttle.throttle_blocks",
            level=logging.DEBUG,
            pattern=log_msg,
        )

        @throttle(reqs_per_sec=1, convert_to_async=True)
        def f3() -> None:
            ans = 42 / 0
            print(f"{ans=}")

        with pytest.raises(ZeroDivisionError):
            asyncio.run(f3())

        ################################################################
        # sync to async to_thread lb request failure
        ################################################################
        log_msg = "Exception in sync to async to_thread for 'f4': division by zero"
        log_ver.add_pattern(
            log_name="scottbrian_throttle.throttle_blocks",
            level=logging.DEBUG,
            pattern=log_msg,
        )

        @throttle(reqs_per_sec=1, bucket_size=2, convert_to_async=True)
        def f4() -> None:
            ans = 42 / 0
            print(f"{ans=}")

        with pytest.raises(ZeroDivisionError):
            asyncio.run(f4())

        ################################################################
        # async context request failure
        ################################################################
        log_msg = "Exception in async context for 'f5': division by zero"
        log_ver.add_pattern(
            log_name="scottbrian_throttle.throttle_blocks",
            level=logging.DEBUG,
            pattern=log_msg,
        )

        @throttle(reqs_per_sec=1)
        async def f5() -> None:  # ruff: ignore[unused-async]
            ans = 42 / 0
            print(f"{ans=}")

        with pytest.raises(ZeroDivisionError):
            asyncio.run(f5())

        ################################################################
        # async context lb request failure
        ################################################################
        log_msg = "Exception in async context for 'f6': division by zero"
        log_ver.add_pattern(
            log_name="scottbrian_throttle.throttle_blocks",
            level=logging.DEBUG,
            pattern=log_msg,
        )

        @throttle(reqs_per_sec=1, bucket_size=2)
        async def f6() -> None:  # ruff: ignore[unused-async]
            ans = 42 / 0
            print(f"{ans=}")

        with pytest.raises(ZeroDivisionError):
            asyncio.run(f6())

        match_results = log_ver.get_match_results(caplog=caplog)
        log_ver.print_match_results(match_results)
        log_ver.verify_match_results(match_results)

    ####################################################################
    # test_sentry_capture_exception
    ####################################################################
    @staticmethod
    def test_sentry_capture_exception() -> None:
        """Test sentry_sdk.capture_exception across contexts."""
        with patch("sentry_sdk.capture_exception") as mock_capture:
            # 1. Sync context

            exc_msg = "sync error"

            @throttle(reqs_per_sec=1)
            def f_sync() -> None:
                raise ValueError(exc_msg)

            with pytest.raises(ValueError, match=exc_msg) as exc_info_sync:
                f_sync()

            mock_capture.assert_called_with(exc_info_sync.value)

            # 2. Sync converted to async (to_thread) context
            mock_capture.reset_mock()

            @throttle(reqs_per_sec=1, convert_to_async=True)
            def f_to_thread() -> None:
                exc_msg = "to_thread error"
                raise RuntimeError(exc_msg)

            with pytest.raises(RuntimeError) as exc_info_to_thread:
                asyncio.run(f_to_thread())

            mock_capture.assert_called_with(exc_info_to_thread.value)

            # 3. Pure async context
            mock_capture.reset_mock()

            @throttle(reqs_per_sec=1)
            async def f_async() -> None:  # ruff: ignore[unused-async]
                exc_msg = "async error"
                raise KeyError(exc_msg)

            with pytest.raises(KeyError) as exc_info_async:
                asyncio.run(f_async())

            mock_capture.assert_called_with(exc_info_async.value)

    ####################################################################
    # define test_sentry_import_error
    ####################################################################
    @staticmethod
    def test_sentry_import_error() -> None:
        """Test graceful fallback when sentry_sdk is not installed."""
        with patch.dict("sys.modules", {"sentry_sdk": None}):
            # Verify exception is still raised properly in sync context

            @throttle(reqs_per_sec=1)
            def f_sync() -> None:
                _ = 1 / 0

            with pytest.raises(ZeroDivisionError):
                f_sync()

            # Verify exception in to_thread context

            @throttle(reqs_per_sec=1, convert_to_async=True)
            def f_to_thread() -> None:
                _ = 1 / 0

            with pytest.raises(ZeroDivisionError):
                asyncio.run(f_to_thread())

            # Verify exception in async context

            @throttle(reqs_per_sec=1)
            async def f_async() -> None:  # ruff: ignore[unused-async]
                _ = 1 / 0

            with pytest.raises(ZeroDivisionError):
                asyncio.run(f_async())

    ####################################################################
    # test_capture_apm_error_structured_logging_extra
    ####################################################################
    @staticmethod
    def test_capture_apm_error_structured_logging_extra(
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """Test structured logging extra fields attached by APM capture.

        Args:
            caplog: pytest fixture to capture log output

        """
        caplog.set_level(logging.DEBUG)

        exc_msg = "structured logging test"

        @throttle(reqs_per_sec=2, bucket_size=1)
        def f_extra() -> None:
            raise ValueError(exc_msg)

        with pytest.raises(ValueError, match=exc_msg):
            f_extra()

        matched_records = [
            r
            for r in caplog.records
            if r.name == "scottbrian_throttle.throttle_blocks"
            and "structured logging test" in r.getMessage()
        ]
        assert len(matched_records) == 1
        record = matched_records[0]
        assert record.function_name == "f_extra"  # type: ignore [attr-defined]
        assert record.throttle_delay >= 0.0  # type: ignore [attr-defined]
        assert record.exc_info is not None


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

    The non-decorator cases will be simpler.


    """

    ####################################################################
    # test_throttle_args_style
    ####################################################################
    @pytest.mark.parametrize("throttle_mode_arg", tuple(Mode))
    @pytest.mark.parametrize("request_style_arg", tuple(RequestStyle))
    def test_throttle_args_style(
        self,
        throttle_mode_arg: Mode,
        request_style_arg: RequestStyle,
    ) -> None:
        """Method to start throttle tests.

        Args:
            throttle_mode_arg: sync or async
            request_style_arg: chooses function args mix

        """
        gc.disable()
        send_interval = 0.0
        self.throttle_router(
            reqs_per_sec=1,
            throttle_mode=throttle_mode_arg,
            bucket_size=1,
            send_interval=send_interval,
            request_style=request_style_arg,
        )
        gc.enable()

    ####################################################################
    # test_throttle_multi_threads1
    ####################################################################
    @pytest.mark.parametrize("throttle_mode_arg", tuple(Mode))
    # See conftest for additional parametrized args
    def test_throttle_multi_threads1(
        self,
        throttle_mode_arg: Mode,
        num_threads_1_arg: int,
        reqs_per_sec_arg: float,
        bucket_size_arg: float,
        send_interval_mult_arg: float,
    ) -> None:
        """Method to start throttle tests.

        Args:
            throttle_mode_arg: choose whether sync or async
            num_threads_1_arg: number of threads to start
            reqs_per_sec_arg: number of requests per second from fixture
            bucket_size_arg: bucket size for throttle
            send_interval_mult_arg: interval between each send of a
                                      request

        """
        send_interval = (1 / reqs_per_sec_arg) * send_interval_mult_arg
        logger.debug(
            f"test_throttle_multi_threads1 entered: {str(throttle_mode_arg)=}, "
            f"{num_threads_1_arg=}, {reqs_per_sec_arg=}, {bucket_size_arg=}, "
            f"{send_interval_mult_arg=}, {send_interval=}",
        )
        self.throttle_router(
            reqs_per_sec=reqs_per_sec_arg,
            throttle_mode=throttle_mode_arg,
            bucket_size=bucket_size_arg,
            send_interval=send_interval,
            request_style=RequestStyle.POS_1,
            num_threads=num_threads_1_arg,
            num_reqs_to_do=8,
        )

    ####################################################################
    # test_throttle_multi_threads2
    ####################################################################
    @pytest.mark.parametrize("throttle_mode_arg", tuple(Mode))
    # See conftest for additional parametrized args
    def test_throttle_multi_threads2(
        self,
        throttle_mode_arg: Mode,
        num_threads_2_arg: int,
        reqs_per_sec_arg: float,
        bucket_size_arg: float,
        send_interval_mult_arg: float,
    ) -> None:
        """Method to start throttle tests.

        Args:
            throttle_mode_arg: choose whether sync or async
            num_threads_2_arg: number of threads to start
            reqs_per_sec_arg: number of requests per second from fixture
            bucket_size_arg: bucket size for throttle
            send_interval_mult_arg: interval between each send of a
                                      request

        """
        send_interval = (1 / reqs_per_sec_arg) * send_interval_mult_arg
        self.throttle_router(
            reqs_per_sec=reqs_per_sec_arg,
            throttle_mode=throttle_mode_arg,
            bucket_size=bucket_size_arg,
            send_interval=send_interval,
            request_style=RequestStyle.POS_1,
            num_threads=num_threads_2_arg,
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
            num_reqs_to_do: number of requests to do

        Returns:
            a list of send intervals

        """
        random.seed(send_interval)

        # the first send interval is always 0.0
        # the remaining are the same value send_interval passed in
        send_intervals = [0.0] + [send_interval] * (num_reqs_to_do // 2 - 1)

        # the second half are random values
        for _ in range(num_reqs_to_do // 2):
            send_intervals.append(send_interval * (random.random() * 2))  # ruff: ignore[suspicious-non-cryptographic-random-usage]

        return send_intervals

    ####################################################################
    # build_intervals
    ####################################################################
    @staticmethod
    def build_intervals(send_interval: float, num_reqs_to_do: int) -> list[float]:
        """Build the list of send intervals.

        Args:
            send_interval: the interval between sends
            num_reqs_to_do: number of requests to do

        Returns:
            a list of send intervals

        """
        # the first send interval is always 0.0
        # the remaining are the same value send_interval passed in
        intervals = [0.0] + [send_interval] * (num_reqs_to_do // 2 - 1)

        # the second half are random values
        for _ in range(num_reqs_to_do // 2):
            intervals.append(send_interval * (random.random() * 2))  # ruff: ignore[suspicious-non-cryptographic-random-usage]

        return intervals

    ##################################################################
    # throttle_router
    ##################################################################
    def throttle_router(
        self,
        *,
        reqs_per_sec: float,
        throttle_mode: Mode,
        bucket_size: float,
        send_interval: float,
        request_style: RequestStyle,
        num_threads: int = 0,
        num_reqs_to_do: int = 8,
    ) -> None:
        """Create the throttle and validator and start the tests.

        Args:
            reqs_per_sec: number of requests per second
            throttle_mode: async or sync
            bucket_size: threshold used with sync leaky bucket algo
            send_interval: interval between each send of a request
            request_style: chooses function args mix
            num_threads: number of threads to issue requests
            num_reqs_to_do: number of requests to do per thread

        """
        logger.debug(
            f"throttle_router entered: {reqs_per_sec=}, {str(throttle_mode)=},"
            f"{bucket_size=}, {send_interval=}, {request_style=}, {num_threads=} ",
        )
        ################################################################
        # get send interval list
        ################################################################
        send_intervals = self.build_intervals(send_interval, num_reqs_to_do)
        targ_delay_intervals = self.build_intervals(send_interval, num_reqs_to_do)
        if num_threads > 1:
            num_reqs_to_do *= num_threads

        ################################################################
        # set sync_convert
        ################################################################
        sync_convert = bool(throttle_mode == Mode.SYNC_CONVERT)
        ##############################################################
        # Instantiate Throttle
        ##############################################################
        a_throttle = Throttle(
            reqs_per_sec=reqs_per_sec,
            bucket_size=bucket_size,
            convert_to_async=sync_convert,
            name="test_name",
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
            self.make_reqs(request_validator, request_style, targ_delay_intervals)
            logger.debug("throttle_router validating series")
            request_validator.validate_series()  # validate for the series
        else:
            if throttle_mode == Mode.SYNC:
                logger.debug("throttle_router creating threads")
                with concurrent.futures.ThreadPoolExecutor() as executor:
                    _ = [
                        executor.submit(
                            self.make_multi_reqs,
                            request_validator,
                            send_intervals,
                            targ_delay_intervals,
                            thread_idx,
                        )
                        for thread_idx in range(num_threads)
                    ]
            else:
                logger.debug("throttle_router running asyncio tasks")

                async def main_loop() -> None:
                    async with asyncio.TaskGroup() as tg:
                        results = [
                            tg.create_task(
                                self.async_make_multi_reqs(
                                    request_validator,
                                    send_intervals,
                                    targ_delay_intervals,
                                    thread_idx,
                                ),
                            )
                            for thread_idx in range(num_threads)
                        ]
                    logger.debug(
                        "throttle_router asyncio results: "
                        f"{[result.result() for result in results]}",
                    )

                asyncio.run(main_loop())

            logger.debug("throttle_router validating series")
            request_validator.validate_series()

        logger.debug("throttle_router exiting")

    ####################################################################
    # make_reqs
    ####################################################################
    @staticmethod
    def make_reqs(
        request_validator: RequestValidator,
        request_style: RequestStyle,
        targ_delay_intervals: list[float],
    ) -> None:
        """Make the requests.

        Args:
            request_validator: the validator for the reqs
            request_style: determine the args to pass
            targ_delay_intervals: delay intervals for target

        """
        pauser = Pauser()
        throttle_mode = request_validator.throttle_mode

        call_args: str

        if throttle_mode == Mode.SYNC:
            send_req = "request_validator.t_throttle.sync_send_request"
        else:
            send_req = "request_validator.t_throttle.async_send_request"

        if throttle_mode in {Mode.SYNC, Mode.SYNC_CONVERT}:
            targ_prefix = ""
        else:
            targ_prefix = "async_"

        req_style_map: dict[RequestStyle, str] = {
            RequestStyle.NO_ARGS: ")",
            RequestStyle.POS_1: ", idx)",
            RequestStyle.POS_2: ", idx, request_validator.reqs_per_sec)",
            RequestStyle.KW_1: ", req_id=idx)",
            RequestStyle.KW_2: ", req_id=idx, "
            "send_interval=request_validator.send_interval)",
            RequestStyle.POS_1_KW_1: ", idx, "
            "send_interval=request_validator.send_interval,)",
            RequestStyle.POS_2_KW_2: ", idx, "
            "request_validator.reqs_per_sec, "
            "bucket_size=request_validator.bucket_size, "
            "send_interval=request_validator.send_interval,)",
        }

        call_args = (
            f"{send_req}(request_validator.{targ_prefix}"
            f"request{request_style.value}b{req_style_map[request_style]}"
        )

        for idx, s_interval in enumerate(request_validator.send_intervals):
            request_item = RequestItem(
                req_id=idx,
                # actual_create_time_ns=perf_counter_ns(),
                throttle_mode=throttle_mode,
                send_interval=s_interval,
                target_delay_time_ns=targ_delay_intervals[idx] * SECS_2_NS,
            )
            request_item.create_times.actual_time_ns = perf_counter_ns()

            if s_interval > 0.0:
                request_item.expected_start_interval_ns = s_interval * SECS_2_NS
                if throttle_mode == Mode.SYNC:
                    pauser.pause(s_interval)
                else:
                    asyncio.run(asyncio.sleep(s_interval))
            request_item.send_time_ns = perf_counter_ns()
            request_validator.request_deque.appendleft(request_item)
            if throttle_mode == Mode.SYNC:
                rc = eval(call_args)  # ruff: ignore[suspicious-eval-usage]
            else:
                rc = asyncio.run(eval(call_args))  # ruff: ignore[suspicious-eval-usage]

            request_item.return_time_ns = perf_counter_ns()
            exp_rc = idx
            assert rc == exp_rc

    ####################################################################
    # make_multi_reqs
    ####################################################################
    @staticmethod
    def make_multi_reqs(
        request_validator: RequestValidator,
        send_intervals: list[float],
        targ_delay_intervals: list[float],
        thread_idx: int,
    ) -> None:
        """Make the requests.

        Args:
            request_validator: the validator for the reqs
            send_intervals: the intervals for the requests
            targ_delay_intervals: delay intervals for target
            thread_idx: index of thread

        """
        pauser = Pauser()
        a_throttle = request_validator.t_throttle
        throttle_mode = request_validator.throttle_mode

        for idx, s_interval in enumerate(send_intervals):
            request_item = RequestItem(
                req_id=idx,
                thread_idx=thread_idx,
                # actual_create_time_ns=perf_counter_ns(),
                throttle_mode=throttle_mode,
                send_interval=s_interval,
                target_delay_time_ns=targ_delay_intervals[idx] * SECS_2_NS,
            )
            request_item.create_times.actual_time_ns = perf_counter_ns()

            if s_interval > 0.0:
                request_item.expected_start_interval_ns = s_interval * SECS_2_NS
                pauser.pause(s_interval)
            request_item.send_time_ns = perf_counter_ns()

            _ = a_throttle.sync_send_request(
                request_validator.request0c,
                request_item=request_item,
            )

            request_item.return_time_ns = perf_counter_ns()

    ####################################################################
    # async_make_multi_reqs
    ####################################################################
    @staticmethod
    async def async_make_multi_reqs(
        request_validator: RequestValidator,
        send_intervals: list[float],
        targ_delay_intervals: list[float],
        thread_idx: int,
    ) -> None:
        """Make the requests.

        Args:
            request_validator: the validator for the reqs
            send_intervals: the request send intervals
            targ_delay_intervals: delay intervals for target
            thread_idx: index of thread for the requests

        """
        a_throttle = request_validator.t_throttle
        throttle_mode = request_validator.throttle_mode

        for idx, s_interval in enumerate(send_intervals):
            request_item = RequestItem(
                req_id=idx,
                thread_idx=thread_idx,
                # actual_create_time_ns=perf_counter_ns(),
                throttle_mode=throttle_mode,
                send_interval=s_interval,
                target_delay_time_ns=targ_delay_intervals[idx] * SECS_2_NS,
            )
            request_item.create_times.actual_time_ns = perf_counter_ns()

            if s_interval > 0.0:
                request_item.expected_start_interval_ns = s_interval * SECS_2_NS
                await asyncio.sleep(s_interval)

            request_item.send_time_ns = perf_counter_ns()
            if throttle_mode == Mode.SYNC_CONVERT:
                await a_throttle.async_send_request(
                    request_validator.request0c,
                    request_item=request_item,
                )
            else:
                await a_throttle.async_send_request(
                    request_validator.async_request0c,
                    request_item=request_item,
                )

            request_item.return_time_ns = perf_counter_ns()


########################################################################
# TestThrottle class
########################################################################
class TestPieThrottle:
    """Class TestPieThrottle."""

    ################################################################
    # get_targ
    ################################################################
    @staticmethod
    def get_targ(  # ruff: ignore[complex-structure, too-many-statements]
        *,
        request_style: RequestStyle,
        throttle_mode: Mode,
        reqs_per_sec: float,
        request_validator: RequestValidator,
    ) -> (
        FuncWithThrottleAttr[Callable[P, R]]
        | FuncWithThrottleAttr[Callable[P, Coroutine[Any, Any, R]]]
    ):

        ################################################################
        # set convert_to_sync
        ################################################################
        convert_to_sync = bool(throttle_mode == Mode.SYNC_CONVERT)

        ################################################################
        # f0
        ################################################################
        @throttle(reqs_per_sec=reqs_per_sec)
        async def async_f0() -> int:
            request_item = request_validator.set_idx_and_times()
            if request_item.target_delay_time_ns > 0:
                await asyncio.sleep(request_item.target_delay_time_ns * NS_2_SECS)
            return request_item.req_id + 42 + 0

        @throttle(reqs_per_sec=reqs_per_sec, convert_to_async=convert_to_sync)
        def f0() -> int:
            request_item = request_validator.set_idx_and_times()
            if request_item.target_delay_time_ns > 0:
                Pauser().pause_ns(request_item.target_delay_time_ns)
            return request_item.req_id + 42 + 0

        ################################################################
        # f1
        ################################################################
        @throttle(reqs_per_sec=reqs_per_sec)
        async def async_f1(req_id: int) -> int:
            request_item = request_validator.set_idx_and_times()
            assert req_id == request_item.req_id
            if request_item.target_delay_time_ns > 0:
                await asyncio.sleep(request_item.target_delay_time_ns * NS_2_SECS)
            return request_item.req_id + 42 + 1

        @throttle(reqs_per_sec=reqs_per_sec, convert_to_async=convert_to_sync)
        def f1(req_id: int) -> int:
            request_item = request_validator.set_idx_and_times()
            assert req_id == request_item.req_id
            if request_item.target_delay_time_ns > 0:
                Pauser().pause_ns(request_item.target_delay_time_ns)
            return request_item.req_id + 42 + 1

        ################################################################
        # f2
        ################################################################
        @throttle(reqs_per_sec=reqs_per_sec)
        async def async_f2(req_id: int, reqs_per_sec: float) -> int:
            request_item = request_validator.set_idx_and_times()
            assert req_id == request_item.req_id
            assert reqs_per_sec == request_validator.reqs_per_sec
            if request_item.target_delay_time_ns > 0:
                await asyncio.sleep(request_item.target_delay_time_ns * NS_2_SECS)
            return request_item.req_id + 42 + 2

        @throttle(reqs_per_sec=reqs_per_sec, convert_to_async=convert_to_sync)
        def f2(req_id: int, reqs_per_sec: float) -> int:
            request_item = request_validator.set_idx_and_times()
            assert req_id == request_item.req_id
            assert reqs_per_sec == request_validator.reqs_per_sec
            if request_item.target_delay_time_ns > 0:
                Pauser().pause_ns(request_item.target_delay_time_ns)
            return request_item.req_id + 42 + 2

        ################################################################
        # f3
        ################################################################
        @throttle(reqs_per_sec=reqs_per_sec)
        async def async_f3(*, req_id: int) -> int:
            request_item = request_validator.set_idx_and_times()
            assert req_id == request_item.req_id
            if request_item.target_delay_time_ns > 0:
                await asyncio.sleep(request_item.target_delay_time_ns * NS_2_SECS)
            return request_item.req_id + 42 + 3

        @throttle(reqs_per_sec=reqs_per_sec, convert_to_async=convert_to_sync)
        def f3(*, req_id: int) -> int:
            request_item = request_validator.set_idx_and_times()
            assert req_id == request_item.req_id
            if request_item.target_delay_time_ns > 0:
                Pauser().pause_ns(request_item.target_delay_time_ns)
            return request_item.req_id + 42 + 3

        ################################################################
        # f4
        ################################################################
        @throttle(reqs_per_sec=reqs_per_sec)
        async def async_f4(*, req_id: int, interval: float) -> int:
            request_item = request_validator.set_idx_and_times()
            assert req_id == request_item.req_id
            assert interval == request_item.send_interval
            if request_item.target_delay_time_ns > 0:
                await asyncio.sleep(request_item.target_delay_time_ns * NS_2_SECS)
            return request_item.req_id + 42 + 4

        @throttle(reqs_per_sec=reqs_per_sec, convert_to_async=convert_to_sync)
        def f4(*, req_id: int, interval: float) -> int:
            request_item = request_validator.set_idx_and_times()
            assert req_id == request_item.req_id
            assert interval == request_item.send_interval
            if request_item.target_delay_time_ns > 0:
                Pauser().pause_ns(request_item.target_delay_time_ns)
            return request_item.req_id + 42 + 4

        ################################################################
        # f5
        ################################################################
        @throttle(reqs_per_sec=reqs_per_sec)
        async def async_f5(req_id: int, *, interval: float) -> int:
            request_item = request_validator.set_idx_and_times()
            assert req_id == request_item.req_id
            assert interval == request_item.send_interval
            if request_item.target_delay_time_ns > 0:
                await asyncio.sleep(request_item.target_delay_time_ns * NS_2_SECS)
            return request_item.req_id + 42 + 5

        @throttle(reqs_per_sec=reqs_per_sec, convert_to_async=convert_to_sync)
        def f5(req_id: int, *, interval: float) -> int:
            request_item = request_validator.set_idx_and_times()
            assert req_id == request_item.req_id
            assert interval == request_item.send_interval
            if request_item.target_delay_time_ns > 0:
                Pauser().pause_ns(request_item.target_delay_time_ns)
            return request_item.req_id + 42 + 5

        ################################################################
        # f6
        ################################################################
        @throttle(reqs_per_sec=reqs_per_sec)
        async def async_f6(
            req_id: int,
            reqs_per_sec: float,
            *,
            bucket_size: float,
            interval: float,
        ) -> int:
            request_item = request_validator.set_idx_and_times()
            assert req_id == request_item.req_id
            assert reqs_per_sec == request_validator.reqs_per_sec
            assert bucket_size == request_validator.bucket_size
            assert interval == request_item.send_interval
            if request_item.target_delay_time_ns > 0:
                await asyncio.sleep(request_item.target_delay_time_ns * NS_2_SECS)
            return request_item.req_id + 42 + 6

        @throttle(reqs_per_sec=reqs_per_sec, convert_to_async=convert_to_sync)
        def f6(
            req_id: int,
            reqs_per_sec: float,
            *,
            bucket_size: float,
            interval: float,
        ) -> int:

            request_item = request_validator.set_idx_and_times()
            assert req_id == request_item.req_id
            assert reqs_per_sec == request_validator.reqs_per_sec
            assert bucket_size == request_validator.bucket_size
            assert interval == request_item.send_interval
            if request_item.target_delay_time_ns > 0:
                Pauser().pause_ns(request_item.target_delay_time_ns)
            return request_item.req_id + 42 + 6

        if throttle_mode == Mode.ASYNC:
            return cast(
                "FuncWithThrottleAttr[Callable[P, Coroutine[Any, Any, R]]]",
                eval(f"async_f{request_style.value}"),  # ruff: ignore[suspicious-eval-usage]
            )
        return cast(
            "FuncWithThrottleAttr[Callable[P, R]]",
            eval(f"f{request_style.value}"),  # ruff: ignore[suspicious-eval-usage]
        )

    ####################################################################
    # test_pie_throttle_args_style
    ####################################################################
    @pytest.mark.parametrize("throttle_mode_arg", tuple(Mode))
    @pytest.mark.parametrize("request_style_arg", tuple(RequestStyle))
    def test_pie_throttle_args_style(
        self,
        throttle_mode_arg: Mode,
        request_style_arg: RequestStyle,
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
        send_intervals = TestThrottle.build_intervals(
            send_interval,
            num_reqs_to_do,
        )

        targ_delay_intervals = TestThrottle.build_intervals(
            send_interval,
            num_reqs_to_do,
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
        )

        ################################################################
        # Get the target function
        ################################################################
        target_func: (
            FuncWithThrottleAttr[Callable[..., int]]
            | FuncWithThrottleAttr[Callable[..., Coroutine[Any, Any, int]]]
        ) = self.get_targ(
            request_style=request_style_arg,
            throttle_mode=throttle_mode_arg,
            reqs_per_sec=reqs_per_sec_arg,
            request_validator=request_validator,
        )
        request_validator.t_throttle = target_func.throttle

        ################################################################
        # Invoke the functions
        ################################################################
        call_args: str

        call_args = f"target_func{req_style_map[request_style_arg][1]}"

        for request_id, s_interval in enumerate(send_intervals):
            request_item = RequestItem(
                req_id=request_id,
                # actual_create_time_ns=perf_counter_ns(),
                throttle_mode=throttle_mode_arg,
                send_interval=s_interval,
                target_delay_time_ns=targ_delay_intervals[request_id] * SECS_2_NS,
            )
            request_item.create_times.actual_time_ns = perf_counter_ns()

            if s_interval > 0.0:
                request_item.expected_start_interval_ns = s_interval * SECS_2_NS
                if throttle_mode_arg == Mode.SYNC:
                    pauser.pause(s_interval)
                else:
                    asyncio.run(asyncio.sleep(s_interval))

            request_item.send_time_ns = perf_counter_ns()
            request_validator.request_deque.appendleft(request_item)
            if throttle_mode_arg == Mode.SYNC:
                rc = eval(call_args)  # ruff: ignore[suspicious-eval-usage]
            else:
                rc = asyncio.run(eval(call_args))  # ruff: ignore[suspicious-eval-usage]

            request_item.return_time_ns = perf_counter_ns()
            assert rc == eval(req_style_map[request_style_arg][2])  # ruff: ignore[suspicious-eval-usage]

        request_validator.validate_series()  # validate for the series

    ####################################################################
    # test_pie_throttle
    ####################################################################
    @pytest.mark.parametrize("throttle_mode_arg", tuple(Mode))
    # See conftest for additional parametrized args
    @staticmethod
    def test_pie_throttle(
        throttle_mode_arg: Mode,
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
        send_intervals = TestThrottle.build_send_intervals(
            send_interval,
            num_reqs_to_do,
        )

        targ_delay_intervals = TestThrottle.build_intervals(
            send_interval,
            num_reqs_to_do,
        )

        ################################################################
        # set sync_convert
        ################################################################
        sync_convert = bool(throttle_mode_arg == Mode.SYNC_CONVERT)

        ################################################################
        # Decorate functions with throttle
        ################################################################
        @throttle(
            reqs_per_sec=reqs_per_sec_arg,
            bucket_size=bucket_size_arg,
        )
        async def async_f0() -> int:  # ruff: ignore[unused-async]
            a_f0_request_item = request_validator.set_idx_and_times()
            if a_f0_request_item.target_delay_time_ns > 0:
                await asyncio.sleep(a_f0_request_item.target_delay_time_ns * NS_2_SECS)
            return 0

        @throttle(
            reqs_per_sec=reqs_per_sec_arg,
            bucket_size=bucket_size_arg,
            convert_to_async=sync_convert,
        )
        def f0() -> int:
            f0_request_item = request_validator.set_idx_and_times()
            if f0_request_item.target_delay_time_ns > 0:
                Pauser().pause_ns(f0_request_item.target_delay_time_ns)
            return 0

        ################################################################
        # Instantiate the validator
        ################################################################
        if throttle_mode_arg in {Mode.SYNC, Mode.SYNC_CONVERT}:
            t_throttle = f0.throttle
        else:
            t_throttle = async_f0.throttle

        request_validator = RequestValidator(
            reqs_per_sec=reqs_per_sec_arg,
            throttle_mode=throttle_mode_arg,
            bucket_size=bucket_size_arg,
            total_requests=num_reqs_to_do,
            send_interval=send_interval,
            send_intervals=send_intervals,
            t_throttle=t_throttle,
        )
        ################################################################
        # Invoke the functions
        ################################################################
        ################################################################
        # Invoke f0
        ################################################################
        for req_id, s_interval in enumerate(send_intervals):
            request_item = RequestItem(
                req_id=req_id,
                # actual_create_time_ns=perf_counter_ns(),
                throttle_mode=throttle_mode_arg,
                send_interval=s_interval,
                target_delay_time_ns=targ_delay_intervals[req_id] * SECS_2_NS,
            )
            request_item.create_times.actual_time_ns = perf_counter_ns()

            if s_interval > 0.0:
                request_item.expected_start_interval_ns = s_interval * SECS_2_NS
                if throttle_mode_arg == Mode.SYNC:
                    pauser.pause(s_interval)
                else:
                    asyncio.run(asyncio.sleep(s_interval))

            request_item.send_time_ns = perf_counter_ns()
            request_validator.request_deque.appendleft(request_item)
            if throttle_mode_arg == Mode.SYNC:
                rc = f0()
            elif throttle_mode_arg == Mode.SYNC_CONVERT:
                rc = asyncio.run(f0())
            else:
                rc = asyncio.run(async_f0())

            request_item.return_time_ns = perf_counter_ns()
            assert rc == 0

        request_validator.validate_series()  # validate for the series

    ####################################################################
    # test_pie_throttle_methods
    ####################################################################
    @pytest.mark.parametrize("throttle_mode_arg", tuple(Mode))
    @pytest.mark.parametrize("method_type_arg", tuple(MethodType))
    # See conftest for additional parametrized args
    @staticmethod
    def test_pie_throttle_methods(  # ruff: ignore[complex-structure]
        *,
        throttle_mode_arg: Mode,
        method_type_arg: MethodType,
        reqs_per_sec_2_arg: float,
        bucket_size_arg: float,
        send_interval_mult_arg: float,
        num_threads_3_arg: int,
    ) -> None:
        """Method to start throttle tests.

        Args:
            throttle_mode_arg: sync or async
            method_type_arg: select which method
            reqs_per_sec_arg: number of requests per second from fixture
            bucket_size_arg: bucket size for the throttle
            send_interval_mult_arg: interval between each send of a
                                      request
            num_threads_3_arg: number of instances to run

        """
        ################################################################
        # Instantiate Request Validator
        ################################################################
        send_interval = (1 / reqs_per_sec_2_arg) * send_interval_mult_arg

        ################################################################
        # get send interval list
        ################################################################
        num_reqs_to_do = 16
        send_intervals = TestThrottle.build_send_intervals(
            send_interval,
            num_reqs_to_do,
        )

        targ_delay_intervals = TestThrottle.build_intervals(
            send_interval,
            num_reqs_to_do,
        )

        total_requests = num_reqs_to_do * num_threads_3_arg

        ################################################################
        # set sync_convert
        ################################################################
        sync_convert = bool(throttle_mode_arg == Mode.SYNC_CONVERT)

        ################################################################
        # Decorate methods with throttle
        ################################################################
        class Class0:
            """Class that will have methods with throttle."""

            num_class0: int = 0
            class0_validator: RequestValidator = RequestValidator(
                reqs_per_sec=reqs_per_sec_2_arg,
                throttle_mode=throttle_mode_arg,
                bucket_size=bucket_size_arg,
                total_requests=total_requests,
                send_interval=send_interval,
                send_intervals=send_intervals,
            )

            ############################################################
            # __init__
            ############################################################
            def __init__(
                self,
                throttle_mode: Mode,
                thread_idx: int,
            ) -> None:
                """Initialize the class.

                Args:
                    throttle_mode: select sync or async
                    thread_idx: index of thread

                """
                self.thread_idx = thread_idx
                self.validator_lock = threading.Lock()
                self.method_type: MethodType = method_type_arg
                if throttle_mode == Mode.ASYNC:
                    if method_type_arg == MethodType.INSTANCE:
                        a_throttle = self.async_m0.throttle
                    elif method_type_arg == MethodType.STATIC:
                        a_throttle = self.async_s0.throttle
                    else:
                        a_throttle = self.async_cm0.throttle

                elif method_type_arg == MethodType.INSTANCE:
                    a_throttle = self.m0.throttle
                elif method_type_arg == MethodType.STATIC:
                    a_throttle = self.s0.throttle
                else:
                    a_throttle = self.cm0.throttle

                with self.validator_lock:
                    if Class0.num_class0 == 0:
                        Class0.class0_validator.t_throttle = a_throttle
                        Class0.num_class0 += 1

                self.pauser = Pauser()

            @throttle(
                reqs_per_sec=reqs_per_sec_2_arg,
                bucket_size=bucket_size_arg,
            )
            async def async_m0(self) -> int:  # ruff: ignore[no-self-use]
                request_item = Class0.class0_validator.set_idx_and_times()
                if request_item.target_delay_time_ns > 0:
                    await asyncio.sleep(request_item.target_delay_time_ns * NS_2_SECS)
                return 0

            @throttle(
                reqs_per_sec=reqs_per_sec_2_arg,
                bucket_size=bucket_size_arg,
                convert_to_async=sync_convert,
            )
            def m0(self) -> int:  # ruff: ignore[no-self-use]
                request_item = Class0.class0_validator.set_idx_and_times()
                if request_item.target_delay_time_ns > 0:
                    Pauser().pause_ns(request_item.target_delay_time_ns)
                return 0

            @throttle(
                reqs_per_sec=reqs_per_sec_2_arg,
                bucket_size=bucket_size_arg,
            )
            @staticmethod
            async def async_s0() -> int:
                request_item = Class0.class0_validator.set_idx_and_times()
                if request_item.target_delay_time_ns > 0:
                    await asyncio.sleep(request_item.target_delay_time_ns * NS_2_SECS)
                return 0

            @throttle(
                reqs_per_sec=reqs_per_sec_2_arg,
                bucket_size=bucket_size_arg,
                convert_to_async=sync_convert,
            )
            @staticmethod
            def s0() -> int:
                request_item = Class0.class0_validator.set_idx_and_times()
                if request_item.target_delay_time_ns > 0:
                    Pauser().pause_ns(request_item.target_delay_time_ns)
                return 0

            @throttle(
                reqs_per_sec=reqs_per_sec_2_arg,
                bucket_size=bucket_size_arg,
            )
            @classmethod
            async def async_cm0(cls) -> int:
                request_item = Class0.class0_validator.set_idx_and_times()
                if request_item.target_delay_time_ns > 0:
                    await asyncio.sleep(request_item.target_delay_time_ns * NS_2_SECS)
                return 0

            @throttle(
                reqs_per_sec=reqs_per_sec_2_arg,
                bucket_size=bucket_size_arg,
                convert_to_async=sync_convert,
            )
            @classmethod
            def cm0(cls: Class0) -> int:
                request_item = Class0.class0_validator.set_idx_and_times()
                if request_item.target_delay_time_ns > 0:
                    Pauser().pause_ns(request_item.target_delay_time_ns)
                return 0

            ################################################################
            # invoke_requests
            ################################################################
            def invoke_requests(self) -> None:
                for req_id, s_interval in enumerate(
                    Class0.class0_validator.send_intervals,
                ):
                    ml_request_item = RequestItem(
                        req_id=req_id,
                        thread_idx=self.thread_idx,
                        # actual_create_time_ns=perf_counter_ns(),
                        throttle_mode=Class0.class0_validator.throttle_mode,
                        send_interval=s_interval,
                        target_delay_time_ns=targ_delay_intervals[req_id] * SECS_2_NS,
                    )
                    ml_request_item.create_times.actual_time_ns = perf_counter_ns()

                    if throttle_mode_arg == Mode.SYNC:
                        if s_interval > 0.0:
                            ml_request_item.expected_start_interval_ns = (
                                s_interval * SECS_2_NS
                            )
                            self.pauser.pause(s_interval)
                        ml_request_item.send_time_ns = perf_counter_ns()
                        Class0.class0_validator.request_deque.appendleft(
                            ml_request_item,
                        )
                        if method_type_arg == MethodType.INSTANCE:
                            rc = self.m0()
                        elif method_type_arg == MethodType.STATIC:
                            rc = self.s0()
                        else:
                            rc = self.cm0()
                        ml_request_item.return_time_ns = perf_counter_ns()
                        assert rc == 0

            ################################################################
            # async_invoke_requests
            ################################################################
            async def async_invoke_requests(self) -> None:
                for req_id, s_interval in enumerate(
                    Class0.class0_validator.send_intervals,
                ):
                    ml_request_item = RequestItem(
                        req_id=req_id,
                        thread_idx=self.thread_idx,
                        # actual_create_time_ns=perf_counter_ns(),
                        throttle_mode=Class0.class0_validator.throttle_mode,
                        send_interval=s_interval,
                        target_delay_time_ns=targ_delay_intervals[req_id] * SECS_2_NS,
                    )
                    ml_request_item.create_times.actual_time_ns = perf_counter_ns()
                    if s_interval > 0.0:
                        ml_request_item.expected_start_interval_ns = (
                            s_interval * SECS_2_NS
                        )
                        await asyncio.sleep(s_interval)

                    ml_request_item.send_time_ns = perf_counter_ns()
                    Class0.class0_validator.request_deque.appendleft(ml_request_item)
                    if throttle_mode_arg == Mode.SYNC_CONVERT:
                        if method_type_arg == MethodType.INSTANCE:
                            rc = await self.m0()
                        elif method_type_arg == MethodType.STATIC:
                            rc = await self.s0()
                        else:
                            rc = await type(self).cm0()
                    elif method_type_arg == MethodType.INSTANCE:
                        rc = await self.async_m0()
                    elif method_type_arg == MethodType.STATIC:
                        rc = await self.async_s0()
                    else:
                        rc = await type(self).async_cm0()

                    ml_request_item.return_time_ns = perf_counter_ns()
                    assert rc == 0

        ################################################################
        # Instantiate the class and run the threads/tasks
        ################################################################
        class0s = [
            Class0(
                throttle_mode=throttle_mode_arg,
                thread_idx=thread_idx,
            )
            for thread_idx in range(num_threads_3_arg)
        ]
        if throttle_mode_arg == Mode.SYNC:
            with concurrent.futures.ThreadPoolExecutor() as executor:
                executor.map(Class0.invoke_requests, class0s)
        else:

            async def main_loop() -> None:
                tasks = [
                    asyncio.create_task(class0.async_invoke_requests())
                    for class0 in class0s
                ]
                await asyncio.gather(*tasks)

            asyncio.run(main_loop())

        Class0.class0_validator.validate_series()


########################################################################
# formatted_time_str
########################################################################
def formatted_time_str(raw_time: float) -> str:
    """Format a time for log output.

    Args:
        raw_time: the time that is to be formatted

    Returns:
        Formatted time.

    """
    return (
        time.strftime("%H:%M:%S", time.localtime(raw_time))
        + (f"{raw_time % 1:.9f}")[1:6]
    )


########################################################################
# formatted_interval_str
########################################################################
def formatted_interval_str(raw_interval: float) -> str:
    """Format an interval time for log output.

    Args:
        raw_interval: the interval time that is to be formatted

    Returns:
        Formatted time.

    """
    return (
        time.strftime("%S", time.localtime(raw_interval))
        + (f"{raw_interval % 1:.9f}")[1:6]
    )


########################################################################
# TestThrottleShutdown
########################################################################
class TestThrottleMisc:
    """Class TestThrottleMisc."""

    ####################################################################
    # test_get_interval_secs
    ####################################################################
    # See conftest for reqs_per_sec_arg parametrized arg
    @staticmethod
    def test_get_interval_secs(reqs_per_sec_arg: float) -> None:
        """Method to test get_interval in seconds.

        Args:
            reqs_per_sec_arg: number of requests per second specified
                for the throttle

        """
        ################################################################
        # create a sync throttle_mode throttle
        ################################################################
        a_throttle1 = Throttle(
            reqs_per_sec=reqs_per_sec_arg,
            bucket_size=1,
            convert_to_async=False,
            name="test_name",
        )

        interval = 1 / reqs_per_sec_arg
        interval_ns = interval * SECS_2_NS
        assert interval == a_throttle1.get_interval_secs()
        assert interval_ns == a_throttle1.get_interval_ns()

    ####################################################################
    # test_get_completion_time_secs
    ####################################################################
    # See conftest for reqs_per_sec_arg parametrized arg
    @staticmethod
    def test_get_completion_time_secs(reqs_per_sec_arg: float) -> None:
        """Method to test get completion time in seconds.

        Args:
            reqs_per_sec_arg: number of requests per second specified
                for the throttle

        """
        ################################################################
        # create a sync throttle_mode throttle
        ################################################################
        a_throttle1 = Throttle(
            reqs_per_sec=reqs_per_sec_arg,
            bucket_size=1,
            convert_to_async=False,
            name="test_name",
        )

        interval = 1 / reqs_per_sec_arg
        for num_reqs in range(1, 10):
            exp_completion_time = (num_reqs - 1) * interval
            exp_completion_time_ns = (num_reqs - 1) * interval * SECS_2_NS
            actual_completion_time = a_throttle1.get_completion_time_secs(
                num_requests=num_reqs,
                from_start=True,
            )
            actual_completion_time_ns = a_throttle1.get_completion_time_ns(
                num_requests=num_reqs,
                from_start=True,
            )
            assert actual_completion_time == exp_completion_time
            assert actual_completion_time_ns == exp_completion_time_ns

        for num_reqs in range(1, 10):
            exp_completion_time = num_reqs * interval
            exp_completion_time_ns = num_reqs * interval * SECS_2_NS
            actual_completion_time = a_throttle1.get_completion_time_secs(
                num_requests=num_reqs,
                from_start=False,
            )
            actual_completion_time_ns = a_throttle1.get_completion_time_ns(
                num_requests=num_reqs,
                from_start=False,
            )
            assert actual_completion_time == exp_completion_time
            assert actual_completion_time_ns == exp_completion_time_ns

    ####################################################################
    # test_decorated_func_get_interval
    ####################################################################
    # See conftest for reqs_per_sec_arg parametrized arg
    @staticmethod
    def test_decorated_func_get_interval(reqs_per_sec_arg: float) -> None:
        """Method to test get_interval on decorated function.

        Args:
            reqs_per_sec_arg: number of requests per second specified
                for the throttle

        """

        @throttle(reqs_per_sec=reqs_per_sec_arg)
        def func_sync() -> None:
            pass

        interval = 1 / reqs_per_sec_arg
        interval_ns = interval * SECS_2_NS
        assert func_sync.throttle.get_interval_secs() == interval
        assert func_sync.throttle.get_interval_ns() == interval_ns

        @throttle(reqs_per_sec=reqs_per_sec_arg)
        async def func_async() -> None:
            pass

        assert func_async.throttle.get_interval_secs() == interval
        assert func_async.throttle.get_interval_ns() == interval_ns

    ####################################################################
    # test_decorated_func_get_completion_time
    ####################################################################
    # See conftest for reqs_per_sec_arg parametrized arg
    @staticmethod
    def test_decorated_func_get_completion_time(reqs_per_sec_arg: float) -> None:
        """Method to test get completion time on decorated function.

        Args:
            reqs_per_sec_arg: number of requests per second specified
                for the throttle

        """

        @throttle(reqs_per_sec=reqs_per_sec_arg)
        def func_sync() -> None:
            pass

        interval = 1 / reqs_per_sec_arg
        for num_reqs in range(1, 10):
            exp_completion_time = (num_reqs - 1) * interval
            exp_completion_time_ns = (num_reqs - 1) * interval * SECS_2_NS
            actual_completion_time = func_sync.throttle.get_completion_time_secs(
                num_requests=num_reqs,
                from_start=True,
            )
            actual_completion_time_ns = func_sync.throttle.get_completion_time_ns(
                num_requests=num_reqs,
                from_start=True,
            )
            assert actual_completion_time == exp_completion_time
            assert actual_completion_time_ns == exp_completion_time_ns

        for num_reqs in range(1, 10):
            exp_completion_time = num_reqs * interval
            exp_completion_time_ns = num_reqs * interval * SECS_2_NS
            actual_completion_time = func_sync.throttle.get_completion_time_secs(
                num_requests=num_reqs,
                from_start=False,
            )
            actual_completion_time_ns = func_sync.throttle.get_completion_time_ns(
                num_requests=num_reqs,
                from_start=False,
            )
            assert actual_completion_time == exp_completion_time
            assert actual_completion_time_ns == exp_completion_time_ns

    ####################################################################
    # test_decorated_method_throttle_methods
    ####################################################################
    # See conftest for reqs_per_sec_arg parametrized arg
    @staticmethod
    def test_decorated_method_throttle_methods(reqs_per_sec_arg: float) -> None:
        """Method to test throttle methods on decorated class method.

        Args:
            reqs_per_sec_arg: number of requests per second specified
                for the throttle

        """

        class ExampleWorker:
            @throttle(reqs_per_sec=reqs_per_sec_arg)
            def work(self) -> None:
                pass

        worker = ExampleWorker()
        interval = 1 / reqs_per_sec_arg
        interval_ns = interval * SECS_2_NS

        assert worker.work.throttle.get_interval_secs() == interval
        assert worker.work.throttle.get_interval_ns() == interval_ns

        comp_secs_from_start = worker.work.throttle.get_completion_time_secs(
            num_requests=5,
            from_start=True,
        )
        assert comp_secs_from_start == 4 * interval

        comp_ns_from_start = worker.work.throttle.get_completion_time_ns(
            num_requests=5,
            from_start=True,
        )
        assert comp_ns_from_start == 4 * interval_ns

        comp_secs_not_start = worker.work.throttle.get_completion_time_secs(
            num_requests=5,
            from_start=False,
        )
        assert comp_secs_not_start == 5 * interval

        comp_ns_not_start = worker.work.throttle.get_completion_time_ns(
            num_requests=5,
            from_start=False,
        )
        assert comp_ns_not_start == 5 * interval_ns


SECS_2_NS: Final[int] = 1000000000
NS_2_SECS: Final[float] = 0.000000001


########################################################################
# RequestValidator class
########################################################################
class RequestValidator:  # ruff: ignore[too-many-public-methods]
    """Class to validate the requests."""

    ####################################################################
    # __init__
    ####################################################################
    def __init__(
        self,
        *,
        reqs_per_sec: float,
        throttle_mode: Mode,
        bucket_size: float,
        total_requests: int,
        send_interval: float,
        send_intervals: list[float],
        t_throttle: Throttle = None,  # type: ignore[assignment]
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

        self.total_exp_throttle_delay_ns: float = 0.0
        self.total_act_throttle_delay_ns: float = 0.0

        self.cumulative_throttle_wait_time_ns: float = 0.0

        self.idx = -1

    ################################################################
    # set_idx_and_times
    ################################################################
    def set_idx_and_times(self, request_item: RequestItem | None = None) -> RequestItem:
        self.idx += 1
        if request_item is None:
            request_item = self.request_deque.pop()
        request_item.arrival_idx = self.idx  # first is zero
        request_item.actual_func_arrival_time_ns = perf_counter_ns()
        request_item.throttle_arrival_time_ns = self.t_throttle._arrival_time_ns
        request_item.throttle_next_target_time_ns = self.t_throttle._next_target_time_ns
        request_item.throttle_wait_time_ns = self.t_throttle._wait_time_ns
        request_item.throttle_sent_time_ns = self.t_throttle.sent_time_ns
        self.request_items.append(request_item)

        def is_async_environment() -> bool:
            try:
                asyncio.get_running_loop()
            except RuntimeError:
                # Raised if there is no running event loop
                return False
            else:
                return True

        caller_frame = inspect.currentframe().f_back.f_back  # type: ignore [union-attr]
        assert caller_frame is not None
        if request_item.throttle_mode in {Mode.SYNC, Mode.SYNC_CONVERT}:
            assert is_async_environment() is False
            if request_item.throttle_mode == Mode.SYNC_CONVERT:
                assert get_caller_info(caller_frame).func_name == "worker_thread_target"
            else:
                assert get_caller_info(caller_frame).func_name == "sync_send_request"
        else:
            assert is_async_environment() is True
            # we need to go back 1 frame for async_request
            if get_caller_info(caller_frame).func_name[0:13] == "async_request":
                caller_frame = caller_frame.f_back

            assert caller_frame is not None
            assert get_caller_info(caller_frame).func_name == "async_send_request"

        del caller_frame

        return request_item

    ####################################################################
    # validate_series
    ####################################################################
    def validate_series(self) -> None:  # ruff: ignore[too-many-locals, too-many-statements]
        """Validate the requests."""
        logger.debug(f"validate_series: {self=}, {id(self)=}")
        assert 0 < self.total_requests
        assert len(self.request_items) == self.total_requests

        # ensure that the request items are in order
        for idx, req_item in enumerate(self.request_items):
            assert idx == req_item.arrival_idx

        ################################################################
        # calculate the request intervals and verify accuracy
        ################################################################
        self.process_request_items()

        first_create_time_ns = self.request_items[0].actual_create_time_ns
        first_send_time = self.request_items[0].send_time_ns

        pauser_intervals_ns = [
            self.request_items[idx].send_time_ns
            - self.request_items[idx].actual_create_time_ns
            for idx in range(len(self.request_items))
        ]

        mean_pauser_interval_ns = sum(pauser_intervals_ns) / self.total_requests
        print(f"{mean_pauser_interval_ns=:.4f}")

        send_arrival_intervals_ns = [
            self.request_items[idx].throttle_arrival_time_ns
            - self.request_items[idx].send_time_ns
            for idx in range(len(self.request_items))
        ]

        mean_send_arrival_interval_ns = (
            sum(send_arrival_intervals_ns) / self.total_requests
        )
        print(f"{mean_send_arrival_interval_ns=:.4f}")

        last_func_arrival_time_ns = self.request_items[-1].actual_func_arrival_time_ns
        actual_mean_interval_ns = (last_func_arrival_time_ns - first_send_time) / (
            self.total_requests
        )
        print(f"{actual_mean_interval_ns=:.4f}")

        mean_send_interval_ns = (
            sum(self.send_intervals) / self.total_requests
        ) * SECS_2_NS
        print(f"{mean_send_interval_ns=:.4f}")
        if mean_send_interval_ns > 0:
            print(f"{mean_pauser_interval_ns / mean_send_interval_ns=:.4f}")

        print(f"{pauser_intervals_ns=}")
        print(f"{self.send_intervals=}")

        mean_min_throttle_interval_ns = (
            self.target_interval_ns * (self.total_requests - self.bucket_size)
        ) / self.total_requests
        print(f"{mean_min_throttle_interval_ns=:.4f}")

        max_send_or_throttle_interval = max(
            mean_send_interval_ns, mean_min_throttle_interval_ns
        )
        print(f"{actual_mean_interval_ns/max_send_or_throttle_interval=:.4f}")

        flowers("Interval Times")
        print(
            "\narrival_idx |  thread |     exp_create |     act_create |        "
            "diff_% |        send |     t arrival "
            "|     exp arrival | "
            "    act arrival |     exp delay |     act delay |        diff ratio |",
        )

        total_series_expected_interval_ns: float = 0.0

        for req_item in self.request_items:
            total_series_expected_interval_ns += req_item.expected_request_interval_ns
            extra_time = 0.0
            if req_item.expected_throttle_delay_ns <= 0.0:
                extra_time = self.target_interval_ns
            expected_actual_diff_ratio = (
                req_item.expected_throttle_delay_ns
                - req_item.expected_throttle_delay_ns
            ) / (req_item.expected_throttle_delay_ns + extra_time)

            exp_create_time_interval_sec = (
                req_item.expected_create_interval_ns * NS_2_SECS
            )
            act_create_time_interval_sec = (
                req_item.actual_create_interval_ns * NS_2_SECS
            )

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
                f"    {req_item.arrival_idx:7} "
                f"|  {req_item.thread_idx:7}"
                f"|    {exp_create_time_interval_sec:11.6f} "
                f"|    {act_create_time_interval_sec:11.6f} "
                f"|   {req_item.create_interval_diff_pct:11.2f} "
                f"| {(req_item.send_time_ns - first_send_time) * NS_2_SECS:11.4f} "
                f"|   {line4_val:11.4f} "
                f"|     {line5_val:11.4f} "
                f"|     {line6_val:11.4f} "
                f"|   {req_item.expected_throttle_delay_ns * NS_2_SECS:11.4f} "
                f"|   {req_item.expected_throttle_delay_ns * NS_2_SECS:11.4f} "
                f"|    {expected_actual_diff_ratio * NS_2_SECS:11.12f} |",
            )

        total_expected_delay_sec = total_series_expected_interval_ns * NS_2_SECS
        print(f"{total_expected_delay_sec=:0.6f}")
        total_series_actual_interval_ns = (
            self.request_items[-1].return_time_ns
            - self.request_items[0].actual_create_time_ns
        )
        total_actual_delay_sec = total_series_actual_interval_ns * NS_2_SECS
        print(f"{total_actual_delay_sec=:0.6f}")
        ratio_total_act_vs_exp_delay = (
            total_series_actual_interval_ns / total_series_expected_interval_ns
        )
        print(f"{ratio_total_act_vs_exp_delay=:0.6f}")

        max_diffs: MaxDiffs = self.display_request_intervals()

        assert 0 <= max_diffs.max_pause_diff < Max_Diff_Threshold_SECS
        assert 0 <= max_diffs.max_arrival_diff < Max_Diff_Threshold_SECS
        assert 0 <= max_diffs.max_t_delay_diff < Max_Diff_Threshold_SECS
        assert 0 <= max_diffs.max_return_diff < Max_Diff_Threshold_SECS
        assert 0 <= max_diffs.max_next_create_diff < Max_Diff_Threshold_SECS

        assert ratio_total_act_vs_exp_delay <= MAX_RATIO_EXP_VS_ACT_DELAY

        total_exp_throttle_delay_sec = self.total_exp_throttle_delay_ns * NS_2_SECS
        total_act_throttle_delay_sec = self.total_act_throttle_delay_ns * NS_2_SECS
        print(f"{total_exp_throttle_delay_sec=:0.6f}")
        print(f"{total_act_throttle_delay_sec=:0.6f}")

        if self.total_exp_throttle_delay_ns > 0:
            ratio_total_throttle_act_vs_exp_delay = (
                self.total_act_throttle_delay_ns / self.total_exp_throttle_delay_ns
            )
            print(f"{ratio_total_throttle_act_vs_exp_delay:0.6f}")
            # assert ratio_total_throttle_act_vs_exp_delay <= 1.07 + (
            #     self.num_threads / 100
            # )

        assert mean_min_throttle_interval_ns <= actual_mean_interval_ns
        assert mean_send_interval_ns <= actual_mean_interval_ns

        # assert actual_mean_interval_ns <= max_send_or_throttle_interval * 1.15

        self.idx = -1

    ####################################################################
    # get_same_thread_next_req_item
    ###################################################################
    def get_same_thread_next_req_item(
        self, req_item: RequestItem
    ) -> RequestItem | None:
        """Get previous request item in same thread.

        Args:
            req_item: the request item whose previous request item is to
                be obtained

        Returns:
              Request_item if a previous item is found, otherwise None
        """
        for idx in range(req_item.arrival_idx + 1, len(self.request_items)):
            if self.request_items[idx].thread_idx == req_item.thread_idx:
                return self.request_items[idx]

        return None

    ####################################################################
    # display_request_intervals
    ###################################################################
    def display_request_intervals(self) -> MaxDiffs:  # ruff: ignore[too-many-branches, too-many-locals, too-many-statements]
        """Built line by line display of each request times.

        Returns:
            MaxDiffs containing the max differences in expected vs
                actual intervals

        """
        flowers("Request Interval Times:")

        max_diffs = MaxDiffs()
        for idx in range(len(self.request_items)):
            print("\n")
            req_item = self.request_items[idx]

            prev_req_item = self.request_items[idx - 1] if idx > 0 else None

            next_req_item = self.get_same_thread_next_req_item(req_item)
            # build line 0
            print(
                f"\n  idx, thread: {req_item.arrival_idx:2}, "
                f"{req_item.thread_idx:2} "
                f"|       pause "
                f"|     arrival "
                f"|     t_delay "
                f"|      return "
                f"| next_create |"
            )

            # build line 1
            exp_pause_interval_sec = req_item.expected_start_interval_ns * NS_2_SECS

            # account for delay waiting behind lock for previous request
            if (
                prev_req_item is not None
                and prev_req_item.return_time_ns > req_item.send_time_ns
            ):
                exp_arrival_interval_sec: float = (
                    prev_req_item.return_time_ns - req_item.send_time_ns
                ) * NS_2_SECS
            else:
                exp_arrival_interval_sec = 0.0

            exp_throttle_delay_sec = req_item.expected_throttle_delay_ns * NS_2_SECS
            exp_return_interval_sec: float = req_item.target_delay_time_ns * NS_2_SECS
            exp_next_create_interval_sec = 0.0
            print(
                f"            expected: "
                f"| {exp_pause_interval_sec:11.6f} "
                f"| {exp_arrival_interval_sec:11.6f} "
                f"| {exp_throttle_delay_sec:11.6f} "
                f"| {exp_return_interval_sec:11.6f} "
                f"| {exp_next_create_interval_sec:11.6f} |"
            )

            # build line 2
            act_pause_interval_sec = (
                req_item.send_time_ns - req_item.actual_create_time_ns
            ) * NS_2_SECS
            act_arrival_interval_sec: float = (
                req_item.throttle_arrival_time_ns - req_item.send_time_ns
            ) * NS_2_SECS
            act_throttle_delay_sec: float = (
                req_item.throttle_sent_time_ns - req_item.throttle_arrival_time_ns
            ) * NS_2_SECS
            act_return_interval_sec: float = (
                req_item.return_time_ns - req_item.throttle_sent_time_ns
            ) * NS_2_SECS
            if next_req_item is not None:
                act_next_create_interval_sec = (
                    next_req_item.actual_create_time_ns - req_item.return_time_ns
                ) * NS_2_SECS
            else:
                act_next_create_interval_sec = 0.0

            print(
                f"              actual: "
                f"| {act_pause_interval_sec:11.6f} "
                f"| {act_arrival_interval_sec:11.6f} "
                f"| {act_throttle_delay_sec:11.6f} "
                f"| {act_return_interval_sec:11.6f} "
                f"| {act_next_create_interval_sec:11.6f} |"
            )

            # build line 3
            diff_pause_interval_sec = act_pause_interval_sec - exp_pause_interval_sec
            max_diffs.max_pause_diff = self.get_max_deviation_from_zero(
                max_diffs.max_pause_diff, diff_pause_interval_sec
            )

            diff_arrival_interval_sec = (
                act_arrival_interval_sec - exp_arrival_interval_sec
            )
            max_diffs.max_arrival_diff = self.get_max_deviation_from_zero(
                max_diffs.max_arrival_diff, diff_arrival_interval_sec
            )

            diff_throttle_delay_sec = act_throttle_delay_sec - exp_throttle_delay_sec

            max_diffs.max_t_delay_diff = self.get_max_deviation_from_zero(
                max_diffs.max_t_delay_diff, diff_throttle_delay_sec
            )

            diff_return_interval_sec = act_return_interval_sec - exp_return_interval_sec
            max_diffs.max_return_diff = self.get_max_deviation_from_zero(
                max_diffs.max_return_diff, diff_return_interval_sec
            )

            diff_next_create_interval_sec = (
                act_next_create_interval_sec - exp_next_create_interval_sec
            )
            max_diffs.max_next_create_diff = self.get_max_deviation_from_zero(
                max_diffs.max_next_create_diff, diff_next_create_interval_sec
            )

            print(
                f"          difference: "
                f"| {diff_pause_interval_sec:11.6f} "
                f"| {diff_arrival_interval_sec:11.6f} "
                f"| {diff_throttle_delay_sec:11.6f} "
                f"| {diff_return_interval_sec:11.6f} "
                f"| {diff_next_create_interval_sec:11.6f} |"
            )

            # build line 4
            if exp_pause_interval_sec > 0.0:
                ratio_pause_interval_sec: float = (
                    act_pause_interval_sec / exp_pause_interval_sec
                )
            else:
                ratio_pause_interval_sec = -1

            if exp_arrival_interval_sec > 0.0:
                ratio_arrival_interval_sec: float = (
                    act_arrival_interval_sec / exp_arrival_interval_sec
                )
            else:
                ratio_arrival_interval_sec = -1

            if exp_throttle_delay_sec > 0:
                ratio_throttle_delay_sec: float = (
                    act_throttle_delay_sec / exp_throttle_delay_sec
                )
            else:
                ratio_throttle_delay_sec = -1

            if exp_return_interval_sec > 0:
                ratio_return_interval_sec: float = (
                    act_return_interval_sec / exp_return_interval_sec
                )
            else:
                ratio_return_interval_sec = -1

            if exp_next_create_interval_sec > 0:
                ratio_next_create_interval_sec: float = (
                    act_next_create_interval_sec / exp_next_create_interval_sec
                )
            else:
                ratio_next_create_interval_sec = -1

            print(
                f"               ratio: "
                f"| {ratio_pause_interval_sec:11.6f} "
                f"| {ratio_arrival_interval_sec:11.6f} "
                f"| {ratio_throttle_delay_sec:11.6f} "
                f"| {ratio_return_interval_sec:11.6f} "
                f"| {ratio_next_create_interval_sec:11.6f} |"
            )

        return max_diffs

    ####################################################################
    # process_request_items
    ####################################################################
    @staticmethod
    def get_max_deviation_from_zero(current_max: float, new_value: float) -> float:
        if abs(new_value) > abs(current_max):
            return new_value

        return current_max

    ####################################################################
    # process_request_items
    ####################################################################
    def process_request_items(self) -> None:
        """Validate the results for sync leaky bucket."""
        # Calculate the interval between request send and exit receive
        # as observed by the requestor.

        self.request_items[0].expected_create_time_ns = self.request_items[
            0
        ].actual_create_time_ns

        self.request_items[0].expected_throttle_delay_ns = 0

        self.request_items[0].expected_func_arrival_time_ns = self.request_items[
            0
        ].throttle_arrival_time_ns

        self.request_items[0].actual_throttle_delay_ns = (
            self.request_items[0].actual_func_arrival_time_ns
            - self.request_items[0].throttle_arrival_time_ns
        )
        amount_in_bucket_ns = self.target_interval_ns  # init with 1st
        max_bucket_amount_ns = self.bucket_size * self.target_interval_ns
        for idx in range(1, len(self.request_items)):
            interval_ns = self.request_items[idx].throttle_arrival_time_ns - (
                self.request_items[idx - 1].throttle_arrival_time_ns
            )
            amount_in_bucket_ns = max(0, amount_in_bucket_ns - interval_ns)

            if max_bucket_amount_ns - amount_in_bucket_ns < self.target_interval_ns:
                self.request_items[idx].expected_throttle_delay_ns = (
                    amount_in_bucket_ns
                    - (max_bucket_amount_ns - self.target_interval_ns)
                )

                # We are calculating the interval from throttle arrival
                # to throttle arrival. But, the actual interval should
                # be from the time of send, after the throttle delay
                # has been done. Note that we add the target interval to
                # the bucket which will actually exceed the max amount.
                # The idea is that after the conceptual throttle delay,
                # the bucket will leak just enough to be full. So, the
                # end result is that the bucket is accurately accounted
                # for using the throttle to throttle delay.
                amount_in_bucket_ns += self.target_interval_ns
            else:  # there is room in the bucket
                self.request_items[idx].expected_throttle_delay_ns = 0
                amount_in_bucket_ns += self.target_interval_ns

            self.request_items[idx].expected_request_interval_ns = (
                self.request_items[idx].expected_start_interval_ns
                + self.request_items[idx].expected_throttle_delay_ns
                + self.request_items[idx].target_delay_time_ns
            )

            self.request_items[idx].expected_create_time_ns = (
                self.request_items[idx - 1].expected_create_time_ns
                + self.request_items[idx - 1].expected_start_interval_ns
                + self.request_items[idx - 1].expected_throttle_delay_ns
            )

            self.request_items[idx].expected_create_interval_ns = (
                self.request_items[idx].expected_create_time_ns
                - self.request_items[idx - 1].expected_create_time_ns
            )

            self.request_items[idx].actual_create_interval_ns = (
                self.request_items[idx].actual_create_time_ns
                - self.request_items[idx - 1].actual_create_time_ns
            )

            self.request_items[idx].create_interval_diff_ns = (
                self.request_items[idx].actual_create_interval_ns
                - self.request_items[idx].expected_create_interval_ns
            )

            exp_create_interval_ns = self.request_items[idx].expected_create_interval_ns
            if exp_create_interval_ns == 0:
                self.request_items[
                    idx
                ].create_interval_diff_pct = 99  # avoid dev by zero
            else:
                self.request_items[idx].create_interval_diff_pct = (
                    self.request_items[idx].create_interval_diff_ns
                    / exp_create_interval_ns
                ) * 100

            self.request_items[idx].expected_func_arrival_time_ns = (
                self.request_items[idx].throttle_arrival_time_ns
                + self.request_items[idx].expected_throttle_delay_ns
            )
            self.request_items[idx].actual_throttle_delay_ns = (
                self.request_items[idx].actual_func_arrival_time_ns
                - self.request_items[idx].throttle_arrival_time_ns
            )

            tolerance_ratio = 0.01
            assert (
                abs(
                    self.request_items[idx].throttle_wait_time_ns
                    - self.request_items[idx].expected_throttle_delay_ns
                )
                / self.target_interval_ns
                < tolerance_ratio
            )

            self.total_exp_throttle_delay_ns += self.request_items[
                idx
            ].expected_throttle_delay_ns
            self.total_act_throttle_delay_ns += self.request_items[
                idx
            ].actual_throttle_delay_ns

            self.cumulative_throttle_wait_time_ns += self.request_items[
                idx
            ].throttle_wait_time_ns

    ####################################################################
    # request0c
    ####################################################################
    async def async_request0c(self, request_item: RequestItem) -> int:
        return self.request0c(request_item)

    def request0c(self, request_item: RequestItem) -> int:
        """Request0 target.

        Returns:
            the index reflected back

        Notes:
              1) this code is serialized by the throttle lock

        """
        request_item = self.set_idx_and_times(request_item=request_item)
        if request_item.target_delay_time_ns > 0:
            Pauser().pause_ns(request_item.target_delay_time_ns)

        return self.idx

    ####################################################################
    # request0b
    ####################################################################
    async def async_request0b(self) -> int:
        request_item = self.set_idx_and_times()  # ruff: ignore[no-indented-block]
        assert request_item.req_id == self.idx
        if request_item.target_delay_time_ns > 0:
            await asyncio.sleep(request_item.target_delay_time_ns * NS_2_SECS)
        return request_item.req_id

    def request0b(self) -> int:
        """Request0 target.

        Returns:
            the index reflected back

        Notes:
              1) this code is serialized by the throttle lock

        """
        request_item = self.set_idx_and_times()
        assert request_item.req_id == self.idx
        if request_item.target_delay_time_ns > 0:
            Pauser().pause_ns(request_item.target_delay_time_ns)
        return request_item.req_id

    ####################################################################
    # request1b
    ####################################################################
    async def async_request1b(self, req_id: int) -> int:
        request_item = self.set_idx_and_times()
        assert request_item.req_id == self.idx
        assert req_id == request_item.req_id
        if request_item.target_delay_time_ns > 0:
            await asyncio.sleep(request_item.target_delay_time_ns * NS_2_SECS)
        return request_item.req_id

    def request1b(self, req_id: int) -> int:
        """Request1 target.

        Args:
            req_id: the req_id in the request

        Returns:
            the index reflected back

        """
        request_item = self.set_idx_and_times()
        assert request_item.req_id == self.idx
        assert req_id == request_item.req_id
        if request_item.target_delay_time_ns > 0:
            Pauser().pause_ns(request_item.target_delay_time_ns)
        return request_item.req_id

    ####################################################################
    # request2b
    ####################################################################
    async def async_request2b(self, req_id: int, reqs_per_sec: float) -> int:
        request_item = self.set_idx_and_times()
        assert req_id == request_item.req_id
        assert reqs_per_sec == self.reqs_per_sec
        if request_item.target_delay_time_ns > 0:
            await asyncio.sleep(request_item.target_delay_time_ns * NS_2_SECS)
        return request_item.req_id

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
        request_item = self.set_idx_and_times()
        assert req_id == request_item.req_id
        assert reqs_per_sec == self.reqs_per_sec
        if request_item.target_delay_time_ns > 0:
            Pauser().pause_ns(request_item.target_delay_time_ns)
        return request_item.req_id

    ####################################################################
    # request3b
    ####################################################################
    async def async_request3b(self, *, req_id: int) -> int:
        request_item = self.set_idx_and_times()
        assert req_id == request_item.req_id
        if request_item.target_delay_time_ns > 0:
            await asyncio.sleep(request_item.target_delay_time_ns * NS_2_SECS)
        return request_item.req_id

    def request3b(self, *, req_id: int) -> int:
        """Request3 target.

        Args:
            req_id: the req_id in the request

        Returns:
            the index reflected back

        """
        request_item = self.set_idx_and_times()
        assert req_id == request_item.req_id
        if request_item.target_delay_time_ns > 0:
            Pauser().pause_ns(request_item.target_delay_time_ns)
        return request_item.req_id

    ####################################################################
    # request4b
    ####################################################################
    async def async_request4b(self, *, req_id: int, send_interval: float) -> int:
        request_item = self.set_idx_and_times()
        assert req_id == request_item.req_id
        assert send_interval == self.send_interval
        if request_item.target_delay_time_ns > 0:
            await asyncio.sleep(request_item.target_delay_time_ns * NS_2_SECS)
        return request_item.req_id

    def request4b(self, *, req_id: int, send_interval: float) -> int:
        """Request4 target.

        Args:
            req_id: the req_id in the request
            send_interval: the interval used between requests

        Returns:
            the index reflected back

        """
        request_item = self.set_idx_and_times()
        assert req_id == request_item.req_id
        assert send_interval == self.send_interval
        if request_item.target_delay_time_ns > 0:
            Pauser().pause_ns(request_item.target_delay_time_ns)
        return request_item.req_id

    ####################################################################
    # request5b
    ####################################################################
    async def async_request5b(self, req_id: int, *, send_interval: float) -> int:
        request_item = self.set_idx_and_times()
        assert req_id == request_item.req_id
        assert send_interval == self.send_interval
        if request_item.target_delay_time_ns > 0:
            await asyncio.sleep(request_item.target_delay_time_ns * NS_2_SECS)
        return request_item.req_id

    def request5b(self, req_id: int, *, send_interval: float) -> int:
        """Request5 target.

        Args:
            req_id: the req_id in the request
            send_interval: the interval used between requests

        Returns:
            the index reflected back

        """
        request_item = self.set_idx_and_times()
        assert req_id == request_item.req_id
        assert send_interval == self.send_interval
        if request_item.target_delay_time_ns > 0:
            Pauser().pause_ns(request_item.target_delay_time_ns)
        return request_item.req_id

    ####################################################################
    # request6b
    ####################################################################
    async def async_request6b(
        self,
        req_id: int,
        reqs_per_sec: float,
        *,
        bucket_size: float,
        send_interval: float,
    ) -> int:
        request_item = self.set_idx_and_times()
        assert req_id == request_item.req_id
        assert reqs_per_sec == self.reqs_per_sec
        assert bucket_size == self.bucket_size
        assert send_interval == self.send_interval
        if request_item.target_delay_time_ns > 0:
            await asyncio.sleep(request_item.target_delay_time_ns * NS_2_SECS)
        return request_item.req_id

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
        request_item = self.set_idx_and_times()
        assert req_id == request_item.req_id
        assert reqs_per_sec == self.reqs_per_sec
        assert bucket_size == self.bucket_size
        assert send_interval == self.send_interval
        if request_item.target_delay_time_ns > 0:
            Pauser().pause_ns(request_item.target_delay_time_ns)
        return request_item.req_id


########################################################################
# TestThrottleDocstrings class
########################################################################
class TestThrottleDocstrings:
    """Class TestThrottleDocstrings."""

    ####################################################################
    # test_throttle_example_1
    ####################################################################
    @staticmethod
    def test_throttle_example_1(capsys: pytest.CaptureFixture[str]) -> None:
        """Method test_throttle_example_1.

        Args:
            capsys: pytest fixture to capture print output

        """
        hdr_str = ":Example 1: Throttle at 1 requests per second:"
        flowers(hdr_str)

        import time

        from scottbrian_throttle.throttle import throttle

        @throttle
        def func1(request_number: int, time_of_start: float) -> str:
            return (
                f"request {request_number} sent at elapsed time: "
                f"{time.time() - time_of_start:0.1f}"
            )

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
    @staticmethod
    def test_throttle_example_2(capsys: pytest.CaptureFixture[str]) -> None:
        """Method test_throttle_example_2.

        Args:
            capsys: pytest fixture to capture print output

        """
        hdr_str = ":Example 2: Throttle at 2 requests per second:"
        flowers(hdr_str)

        import time

        from scottbrian_throttle.throttle import throttle

        @throttle(reqs_per_sec=2)
        def func2(request_number: int, time_of_start: float) -> str:
            return (
                f"request {request_number} sent at elapsed time: "
                f"{time.time() - time_of_start:0.1f}"
            )

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
    @staticmethod
    def test_throttle_example_3(capsys: pytest.CaptureFixture[str]) -> None:
        """Method test_throttle_example_3.

        Args:
            capsys: pytest fixture to capture print output

        """
        hdr_str = ":Example 3: throttle with async function in asyncio environment:"
        flowers(hdr_str)

        import asyncio
        import time

        from scottbrian_throttle.throttle import throttle

        @throttle(reqs_per_sec=2)
        async def func3(request_number: int, time_of_start: float) -> None:  # ruff: ignore[unused-async]
            print(
                f"request {request_number} sent at elapsed time: "
                f"{time.time() - time_of_start:0.1f}",
            )

        async def main_loop() -> None:
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
    @staticmethod
    def test_throttle_example_4(capsys: pytest.CaptureFixture[str]) -> None:
        """Method test_throttle_example_4.

        Args:
            capsys: pytest fixture to capture print output

        """
        hdr_str = ":Example 4: throttle with non-async function in asyncio environment:"
        flowers(hdr_str)

        import asyncio
        import time

        from scottbrian_throttle.throttle import throttle

        @throttle(reqs_per_sec=2)
        def func4(request_number: int, time_of_start: float) -> None:
            print(
                f"request {request_number} sent at elapsed time: "
                f"{time.time() - time_of_start:0.1f}",
            )

        async def main_loop() -> None:
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
    @staticmethod
    def test_throttle_example_5(capsys: pytest.CaptureFixture[str]) -> None:
        """Method test_throttle_example_5.

        Args:
            capsys: pytest fixture to capture print output

        """
        hdr_str = ":Example 5: throttle with convert to async in asyncio environment:"
        flowers(hdr_str)

        import asyncio
        import time

        from scottbrian_throttle.throttle import throttle

        @throttle(reqs_per_sec=2, convert_to_async=True)
        def func5(request_number: int, time_of_start: float) -> None:
            print(
                f"request {request_number} sent at elapsed time: "
                f"{time.time() - time_of_start:0.1f}",
            )

        async def main_loop() -> None:
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
    @staticmethod
    def test_throttle_example_6(capsys: pytest.CaptureFixture[str]) -> None:
        """Method test_throttle_example_6.

        Args:
            capsys: pytest fixture to capture print output

        """
        hdr_str = ":Example 6: Throttle with a *bucket_size* of 3:"
        flowers(hdr_str)

        import time

        from scottbrian_throttle.throttle import throttle

        @throttle(reqs_per_sec=2, bucket_size=3)
        def func4(request_number: int, time_of_start: float) -> None:
            print(
                f"request {request_number} sent at elapsed time: "
                f"{time.time() - time_of_start:0.1f}",
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
    # test_throttle_example_t1
    ####################################################################
    @staticmethod
    def test_throttle_example_t1(capsys: pytest.CaptureFixture[str]) -> None:
        """Method test_throttle_example_t1.

        Args:
            capsys: pytest fixture to capture print output

        """
        hdr_str = ":Example 1: call __repr__ for Throttle"
        flowers(hdr_str)

        from scottbrian_throttle.throttle import throttle

        @throttle(reqs_per_sec=0.5)
        def func1(request_number: int, time_of_start: float) -> None:
            pass

        print(repr(func1.throttle))

        flower_str = ("*" * (len(hdr_str) + 4)) + "\n"

        expected_result = "\n" + flower_str
        expected_result += f"* {hdr_str} *\n"
        expected_result += flower_str
        expected_result += (
            "Throttle(reqs_per_sec=0.5, bucket_size=1.0, "
            "convert_to_async=False, name=func1)\n"
        )

        captured = capsys.readouterr().out

        assert captured == expected_result
