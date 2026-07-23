"""test_throttle.py module."""

# import gc

########################################################################
# Standard Library
########################################################################
import itertools as it
import logging
import math
import os
import random
import statistics as stats
import threading
import time
from collections import deque
from dataclasses import dataclass, field
from time import perf_counter_ns
from typing import Any, Callable, Final, Optional, Union

########################################################################
# Third Party
########################################################################
import pytest
from scottbrian_utils.entry_trace import etrace
from scottbrian_utils.exc_hook import ExcHook
from scottbrian_utils.flower_box import print_flower_box_msg as flowers
from scottbrian_utils.log_verifier import LogVer
from scottbrian_utils.pauser import Pauser
from scottbrian_utils.testlib_verifier import verify_lib
from typing_extensions import TypeAlias

########################################################################
# Local
########################################################################
from scottbrian_throttle.throttle import (
    Throttle,
    throttle,
    FuncWithThrottleAttr,
    IncorrectReqsPerSecSpecified,
    IncorrectAsyncQSizeSpecified,
    IncorrectBucketSizeSpecified,
    IncorrectShutdownTypeSpecified,
    InvalidAsyncQSizeSpecified,
    InvalidShutdownRequested,
    shutdown_throttle_funcs,
    ThrottleMode,
    ThrottleShutdownType,
)

########################################################################
# type aliases
########################################################################
IntFloat: TypeAlias = Union[int, float]
OptIntFloat: TypeAlias = Optional[IntFloat]

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
    throttle_mode: ThrottleMode = ThrottleMode.SYNC

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

    def test_throttle_bad_args(self, caplog: pytest.LogCaptureFixture) -> None:
        """test_throttle using bad arguments."""

        ################################################################
        # mainline
        ################################################################
        log_ver = LogVer(log_name="scottbrian_throttle.throttle")

        ml_call_seq = (
            "Request call sequence: python.py::pytest_pyfunc_call:[0-9]+ -> "
            "test_throttle.py::TestThrottleErrors.test_throttle_bad_args:[0-9]+"
        )

        ################################################################
        # bad reqs_per_sec SYNC
        ################################################################
        ml_error_msg = (
            "The reqs_per_sec specification must be a positive "
            "int or float greater than zero. "
        ) + ml_call_seq

        log_ver.add_pattern(pattern=ml_error_msg, level=logging.ERROR)
        with pytest.raises(IncorrectReqsPerSecSpecified, match=ml_error_msg):
            _ = Throttle(reqs_per_sec=-1)

        log_ver.add_pattern(pattern=ml_error_msg, level=logging.ERROR)
        with pytest.raises(IncorrectReqsPerSecSpecified, match=ml_error_msg):
            _ = Throttle(reqs_per_sec=0)

        log_ver.add_pattern(pattern=ml_error_msg, level=logging.ERROR)
        with pytest.raises(IncorrectReqsPerSecSpecified, match=ml_error_msg):
            _ = Throttle(reqs_per_sec="1")  # type: ignore

        ################################################################
        # bad reqs_per_sec ASYNC
        ################################################################
        ml_error_msg = (
            "The reqs_per_sec specification must be a positive "
            "int or float greater than zero. "
        ) + ml_call_seq

        log_ver.add_pattern(pattern=ml_error_msg, level=logging.ERROR)
        with pytest.raises(IncorrectReqsPerSecSpecified, match=ml_error_msg):
            _ = Throttle(reqs_per_sec=-1, throttle_mode=ThrottleMode.ASYNC)

        log_ver.add_pattern(pattern=ml_error_msg, level=logging.ERROR)
        with pytest.raises(IncorrectReqsPerSecSpecified, match=ml_error_msg):
            _ = Throttle(reqs_per_sec=0, throttle_mode=ThrottleMode.ASYNC)

        log_ver.add_pattern(pattern=ml_error_msg, level=logging.ERROR)
        with pytest.raises(IncorrectReqsPerSecSpecified, match=ml_error_msg):
            _ = Throttle(
                reqs_per_sec="1", throttle_mode=ThrottleMode.ASYNC
            )  # type: ignore

        ################################################################
        # bad bucket_size SYNC
        ################################################################
        ml_error_msg = (
            "The bucket_size specification must be a positive "
            "int or float greater than or equal to 1. "
        ) + ml_call_seq

        log_ver.add_pattern(pattern=ml_error_msg, level=logging.ERROR)
        with pytest.raises(IncorrectBucketSizeSpecified, match=ml_error_msg):
            _ = Throttle(reqs_per_sec=1, bucket_size=-1)

        log_ver.add_pattern(pattern=ml_error_msg, level=logging.ERROR)
        with pytest.raises(IncorrectBucketSizeSpecified, match=ml_error_msg):
            _ = Throttle(reqs_per_sec=1, bucket_size=0)

        log_ver.add_pattern(pattern=ml_error_msg, level=logging.ERROR)
        with pytest.raises(IncorrectBucketSizeSpecified, match=ml_error_msg):
            _ = Throttle(reqs_per_sec=1, bucket_size=0.3)

        log_ver.add_pattern(pattern=ml_error_msg, level=logging.ERROR)
        with pytest.raises(IncorrectBucketSizeSpecified, match=ml_error_msg):
            _ = Throttle(reqs_per_sec=1, bucket_size="1")  # type: ignore

        ################################################################
        # bad bucket_size ASYNC
        ################################################################
        ml_error_msg = (
            "The bucket_size specification must be a positive "
            "int or float greater than or equal to 1. "
        ) + ml_call_seq

        log_ver.add_pattern(pattern=ml_error_msg, level=logging.ERROR)
        with pytest.raises(IncorrectBucketSizeSpecified, match=ml_error_msg):
            _ = Throttle(
                reqs_per_sec=1, bucket_size=-1, throttle_mode=ThrottleMode.ASYNC
            )

        log_ver.add_pattern(pattern=ml_error_msg, level=logging.ERROR)
        with pytest.raises(IncorrectBucketSizeSpecified, match=ml_error_msg):
            _ = Throttle(
                reqs_per_sec=1, bucket_size=0, throttle_mode=ThrottleMode.ASYNC
            )

        log_ver.add_pattern(pattern=ml_error_msg, level=logging.ERROR)
        with pytest.raises(IncorrectBucketSizeSpecified, match=ml_error_msg):
            _ = Throttle(
                reqs_per_sec=1, bucket_size=0.3, throttle_mode=ThrottleMode.ASYNC
            )

        log_ver.add_pattern(pattern=ml_error_msg, level=logging.ERROR)
        with pytest.raises(IncorrectBucketSizeSpecified, match=ml_error_msg):
            _ = Throttle(
                reqs_per_sec=1, bucket_size="1", throttle_mode=ThrottleMode.ASYNC
            )  # type: ignore

        ################################################################
        # bad async_q_size ASYNC
        ################################################################
        ml_error_msg = (
            "async_q_size must be an integer greater than zero. "
        ) + ml_call_seq

        log_ver.add_pattern(pattern=ml_error_msg, level=logging.ERROR)
        with pytest.raises(IncorrectAsyncQSizeSpecified, match=ml_error_msg):
            _ = Throttle(
                reqs_per_sec=1, throttle_mode=ThrottleMode.ASYNC, async_q_size=-1
            )

        log_ver.add_pattern(pattern=ml_error_msg, level=logging.ERROR)
        with pytest.raises(IncorrectAsyncQSizeSpecified, match=ml_error_msg):
            _ = Throttle(
                reqs_per_sec=1, throttle_mode=ThrottleMode.ASYNC, async_q_size=0
            )

        log_ver.add_pattern(pattern=ml_error_msg, level=logging.ERROR)
        with pytest.raises(IncorrectAsyncQSizeSpecified, match=ml_error_msg):
            _ = Throttle(
                reqs_per_sec=1,
                throttle_mode=ThrottleMode.ASYNC,
                async_q_size=0.5,  # type: ignore
            )

        log_ver.add_pattern(pattern=ml_error_msg, level=logging.ERROR)
        with pytest.raises(IncorrectAsyncQSizeSpecified, match=ml_error_msg):
            _ = Throttle(
                reqs_per_sec=1, throttle_mode=ThrottleMode.ASYNC, async_q_size="1"
            )  # type: ignore

        ################################################################
        # invalid async_q_size SYNC
        ################################################################
        ml_error_msg = (
            "a non_zero async_q_size is not allowed when throttle_mode is "
            "ThrottleMode.SYNC. "
        ) + ml_call_seq

        log_ver.add_pattern(pattern=ml_error_msg, level=logging.ERROR)
        with pytest.raises(InvalidAsyncQSizeSpecified, match=ml_error_msg):
            _ = Throttle(reqs_per_sec=1, async_q_size=-1)

        log_ver.add_pattern(pattern=ml_error_msg, level=logging.ERROR)
        with pytest.raises(InvalidAsyncQSizeSpecified, match=ml_error_msg):
            _ = Throttle(reqs_per_sec=1, async_q_size=0.5)  # type: ignore

        log_ver.add_pattern(pattern=ml_error_msg, level=logging.ERROR)
        with pytest.raises(InvalidAsyncQSizeSpecified, match=ml_error_msg):
            _ = Throttle(reqs_per_sec=1, async_q_size=1)

        log_ver.add_pattern(pattern=ml_error_msg, level=logging.ERROR)
        with pytest.raises(InvalidAsyncQSizeSpecified, match=ml_error_msg):
            _ = Throttle(reqs_per_sec=1, async_q_size="1")  # type: ignore

        ################################################################
        # invalid shutdown request SYNC
        ################################################################
        ml_error_msg = (
            "A shutdown was requested for a synchronous throttle. "
            "Shutdown can only be requested for a throttle that is "
            "created with a throttle_mode of ThrottleMode.ASYNC. "
        ) + ml_call_seq

        log_ver.add_pattern(pattern=ml_error_msg, level=logging.ERROR)

        with pytest.raises(InvalidShutdownRequested, match=ml_error_msg):
            a_throttle = Throttle(reqs_per_sec=1)
            a_throttle.start_shutdown()

        ################################################################
        # incorrect shutdown type ASYNC
        ################################################################
        ml_error_msg = (
            "For start_shutdown, shutdownType must be specified as "
            "either ThrottleShutdownType.SOFT or "
            "ThrottleShutdownType.HARD. "
        ) + ml_call_seq

        log_ver.add_pattern(pattern=ml_error_msg, level=logging.ERROR)
        log_ver.add_pattern(
            pattern=(
                "throttle t1 start_shutdown request "
                "successfully completed in [0-9.]+ seconds"
            ),
            level=logging.INFO,
        )
        with pytest.raises(IncorrectShutdownTypeSpecified, match=ml_error_msg):
            a_throttle = Throttle(
                reqs_per_sec=1, throttle_mode=ThrottleMode.ASYNC, name="t1"
            )
            a_throttle.start_shutdown()
            a_throttle.start_shutdown(shutdown_type=42)  # type: ignore

        ################################################################
        # check log results
        ################################################################
        match_results = log_ver.get_match_results(caplog=caplog)
        log_ver.print_match_results(match_results, print_matched=True)
        log_ver.verify_match_results(match_results)


########################################################################
# TestThrottleBasic class to test Throttle methods
########################################################################
class TestThrottleBasic:
    """Test basic functions of Throttle."""

    ####################################################################
    # len checks throttle_mode=ThrottleMode.SYNC
    ####################################################################
    @pytest.mark.parametrize("num_reqs_to_send_arg", (1, 2, 3))
    @etrace(omit_caller=True)
    def test_throttle_len_non_async(
        self,
        num_reqs_to_send_arg: int,
    ) -> None:
        """Test the len of async throttle.

        Args:
            num_reqs_to_send_arg: number to send for len check

        """
        # create a throttle with a long enough interval to ensure that
        # we can populate the async_q and get the length before we start
        # removing requests from it
        a_throttle = Throttle(
            reqs_per_sec=0.3, throttle_mode=ThrottleMode.SYNC
        )  # 3 sec interval

        assert len(a_throttle) == 0

        def dummy_func(an_event: threading.Event) -> None:
            assert len(a_throttle) == 0
            an_event.set()

        event = threading.Event()

        for i in range(num_reqs_to_send_arg):
            a_throttle.send_request(dummy_func, event)

        event.wait()

        # assert is for 0 because there should be nothing queued
        assert len(a_throttle) == 0

    ####################################################################
    # len checks with throttle_mode=ThrottleMode.ASYNC
    ####################################################################
    @pytest.mark.parametrize("num_reqs_to_send_arg", (2, 3, 6))
    @etrace(omit_caller=True)
    def test_throttle_len_async(
        self,
        num_reqs_to_send_arg: int,
    ) -> None:
        """Test the len of async throttle.

        Args:
            num_reqs_to_send_arg: number to send for len check

        """
        # create a throttle with a long enough interval to ensure that
        # we can populate the async_q and get the length before we start
        # removing requests from it
        a_throttle = Throttle(
            reqs_per_sec=0.3, throttle_mode=ThrottleMode.ASYNC
        )  # 3 sec interval

        def dummy_func(an_event: threading.Event, idx: int) -> None:
            logger.debug(f"dummy_func entered: {idx=}")
            an_event.set()

        event = threading.Event()

        for i in range(num_reqs_to_send_arg):
            a_throttle.send_request(dummy_func, event, i)

        logger.debug("mainline waiting on event")
        event.wait()
        logger.debug("mainline after wait on event")
        # assert is for 1 less than queued because the first request
        # will be scheduled immediately
        try:
            assert len(a_throttle) == num_reqs_to_send_arg - 2
        except Exception:
            a_throttle.start_shutdown()
            raise

        # start_shutdown returns when request_q cleanup completes
        a_throttle.start_shutdown()
        assert len(a_throttle) == 0

        a_throttle.start_shutdown(shutdown_type=ThrottleShutdownType.HARD)

    ####################################################################
    # repr with throttle_mode async
    ####################################################################
    @pytest.mark.parametrize("reqs_per_sec_arg", (0.5, 1, 2))
    @pytest.mark.parametrize("bucket_size_arg", (None, 1, 2.2))
    @pytest.mark.parametrize(
        "throttle_mode_arg", (None, ThrottleMode.SYNC, ThrottleMode.ASYNC)
    )
    @pytest.mark.parametrize("async_q_size_arg", (None, 0, 20))
    @pytest.mark.parametrize("name_arg", (None, "t1", "t2"))
    @etrace(omit_caller=True)
    def test_throttle_repr(
        self,
        reqs_per_sec_arg: int,
        bucket_size_arg: None | float | int,
        throttle_mode_arg: None | ThrottleMode,
        async_q_size_arg: None | int,
        name_arg: None | str,
    ) -> None:
        """test_throttle repr with various reqs_per_sec.

        Args:
            reqs_per_sec_arg: request per second
            bucket_size_arg: leaky bucket size
            throttle_mode_arg: sync/async throttle_mode
            async_q_size_arg: size of async q
            name_arg: throttle name


        """
        ################################################################
        # throttle with async_q_size_arg not specified
        ################################################################

        # 0 0 0 0
        if (
            bucket_size_arg is None
            and throttle_mode_arg is None
            and async_q_size_arg is None
            and name_arg is None
        ):
            a_throttle = Throttle(reqs_per_sec=reqs_per_sec_arg)
            t_id = id(a_throttle)

            expected_repr_str = (
                f"Throttle("
                f"reqs_per_sec={reqs_per_sec_arg}, "
                f"bucket_size=1, "
                f"throttle_mode=ThrottleMode.SYNC, "
                f"async_q_size=0, "
                f"name={t_id})"
            )
        # 0 0 0 1
        elif (
            bucket_size_arg is None
            and throttle_mode_arg is None
            and async_q_size_arg is None
            and name_arg is not None
        ):
            a_throttle = Throttle(reqs_per_sec=reqs_per_sec_arg, name=name_arg)
            t_id = id(a_throttle)

            expected_repr_str = (
                f"Throttle("
                f"reqs_per_sec={reqs_per_sec_arg}, "
                f"bucket_size=1, "
                f"throttle_mode=ThrottleMode.SYNC, "
                f"async_q_size=0, "
                f"name={name_arg})"
            )
        # 0 0 1 0
        elif (
            bucket_size_arg is None
            and throttle_mode_arg is None
            and async_q_size_arg is not None
            and name_arg is None
        ):
            # not a valid combo to have throttle_mode=ThrottleMode.SYNC
            # and async_q_size non-zero
            async_q_size_arg = 0
            a_throttle = Throttle(
                reqs_per_sec=reqs_per_sec_arg, async_q_size=async_q_size_arg
            )
            t_id = id(a_throttle)

            expected_repr_str = (
                f"Throttle("
                f"reqs_per_sec={reqs_per_sec_arg}, "
                f"bucket_size=1, "
                f"throttle_mode=ThrottleMode.SYNC, "
                f"async_q_size=0, "
                f"name={t_id})"
            )
        # 0 0 1 1
        elif (
            bucket_size_arg is None
            and throttle_mode_arg is None
            and async_q_size_arg is not None
            and name_arg is not None
        ):
            # not a valid combo to have throttle_mode=ThrottleMode.SYNC
            # and async_q_size non-zero
            async_q_size_arg = 0
            a_throttle = Throttle(
                reqs_per_sec=reqs_per_sec_arg,
                async_q_size=async_q_size_arg,
                name=name_arg,
            )
            t_id = id(a_throttle)

            expected_repr_str = (
                f"Throttle("
                f"reqs_per_sec={reqs_per_sec_arg}, "
                f"bucket_size=1, "
                f"throttle_mode=ThrottleMode.SYNC, "
                f"async_q_size=0, "
                f"name={name_arg})"
            )
        # 0 1 0 0
        elif (
            bucket_size_arg is None
            and throttle_mode_arg is not None
            and async_q_size_arg is None
            and name_arg is None
        ):
            if throttle_mode_arg == ThrottleMode.ASYNC:
                throttle_mode_str = "ThrottleMode.ASYNC"
                async_q_size_arg = Throttle.DEFAULT_ASYNC_Q_SIZE
            else:
                throttle_mode_str = "ThrottleMode.SYNC"
                async_q_size_arg = 0

            a_throttle = Throttle(
                reqs_per_sec=reqs_per_sec_arg, throttle_mode=throttle_mode_arg
            )
            t_id = id(a_throttle)

            expected_repr_str = (
                f"Throttle("
                f"reqs_per_sec={reqs_per_sec_arg}, "
                f"bucket_size=1, "
                f"throttle_mode={throttle_mode_str}, "
                f"async_q_size={async_q_size_arg}, "
                f"name={t_id})"
            )
        # 0 1 0 1
        elif (
            bucket_size_arg is None
            and throttle_mode_arg is not None
            and async_q_size_arg is None
            and name_arg is not None
        ):
            if throttle_mode_arg == ThrottleMode.ASYNC:
                throttle_mode_str = "ThrottleMode.ASYNC"
                async_q_size_arg = Throttle.DEFAULT_ASYNC_Q_SIZE
            else:
                throttle_mode_str = "ThrottleMode.SYNC"
                async_q_size_arg = 0
            a_throttle = Throttle(
                reqs_per_sec=reqs_per_sec_arg,
                throttle_mode=throttle_mode_arg,
                name=name_arg,
            )
            t_id = id(a_throttle)

            expected_repr_str = (
                f"Throttle("
                f"reqs_per_sec={reqs_per_sec_arg}, "
                f"bucket_size=1, "
                f"throttle_mode={throttle_mode_str}, "
                f"async_q_size={async_q_size_arg}, "
                f"name={name_arg})"
            )
        # 0 1 1 0
        elif (
            bucket_size_arg is None
            and throttle_mode_arg is not None
            and async_q_size_arg is not None
            and name_arg is None
        ):
            if throttle_mode_arg == ThrottleMode.ASYNC:
                throttle_mode_str = "ThrottleMode.ASYNC"
                if async_q_size_arg == 0:
                    async_q_size_arg = 30
            else:
                throttle_mode_str = "ThrottleMode.SYNC"
                async_q_size_arg = 0
            a_throttle = Throttle(
                reqs_per_sec=reqs_per_sec_arg,
                throttle_mode=throttle_mode_arg,
                async_q_size=async_q_size_arg,
            )
            t_id = id(a_throttle)

            expected_repr_str = (
                f"Throttle("
                f"reqs_per_sec={reqs_per_sec_arg}, "
                f"bucket_size=1, "
                f"throttle_mode={throttle_mode_str}, "
                f"async_q_size={async_q_size_arg}, "
                f"name={t_id})"
            )
        # 0 1 1 1
        elif (
            bucket_size_arg is None
            and throttle_mode_arg is not None
            and async_q_size_arg is not None
            and name_arg is not None
        ):
            if throttle_mode_arg == ThrottleMode.ASYNC:
                throttle_mode_str = "ThrottleMode.ASYNC"
                if async_q_size_arg == 0:
                    async_q_size_arg = 30
            else:
                throttle_mode_str = "ThrottleMode.SYNC"
                async_q_size_arg = 0
            a_throttle = Throttle(
                reqs_per_sec=reqs_per_sec_arg,
                throttle_mode=throttle_mode_arg,
                async_q_size=async_q_size_arg,
                name=name_arg,
            )
            t_id = id(a_throttle)

            expected_repr_str = (
                f"Throttle("
                f"reqs_per_sec={reqs_per_sec_arg}, "
                f"bucket_size=1, "
                f"throttle_mode={throttle_mode_str}, "
                f"async_q_size={async_q_size_arg}, "
                f"name={name_arg})"
            )

        # 1 0 0 0
        elif (
            bucket_size_arg is not None
            and throttle_mode_arg is None
            and async_q_size_arg is None
            and name_arg is None
        ):
            a_throttle = Throttle(
                reqs_per_sec=reqs_per_sec_arg, bucket_size=bucket_size_arg
            )
            t_id = id(a_throttle)

            expected_repr_str = (
                f"Throttle("
                f"reqs_per_sec={reqs_per_sec_arg}, "
                f"bucket_size={bucket_size_arg}, "
                f"throttle_mode=ThrottleMode.SYNC, "
                f"async_q_size=0, "
                f"name={t_id})"
            )
        # 1 0 0 1
        elif (
            bucket_size_arg is not None
            and throttle_mode_arg is None
            and async_q_size_arg is None
            and name_arg is not None
        ):
            a_throttle = Throttle(
                reqs_per_sec=reqs_per_sec_arg,
                bucket_size=bucket_size_arg,
                name=name_arg,
            )
            t_id = id(a_throttle)

            expected_repr_str = (
                f"Throttle("
                f"reqs_per_sec={reqs_per_sec_arg}, "
                f"bucket_size={bucket_size_arg}, "
                f"throttle_mode=ThrottleMode.SYNC, "
                f"async_q_size=0, "
                f"name={name_arg})"
            )
        # 1 0 1 0
        elif (
            bucket_size_arg is not None
            and throttle_mode_arg is None
            and async_q_size_arg is not None
            and name_arg is None
        ):
            # not a valid combo to have throttle_mode=ThrottleMode.SYNC
            # and async_q_size non-zero
            async_q_size_arg = 0
            a_throttle = Throttle(
                reqs_per_sec=reqs_per_sec_arg,
                bucket_size=bucket_size_arg,
                async_q_size=async_q_size_arg,
            )
            t_id = id(a_throttle)

            expected_repr_str = (
                f"Throttle("
                f"reqs_per_sec={reqs_per_sec_arg}, "
                f"bucket_size={bucket_size_arg}, "
                f"throttle_mode=ThrottleMode.SYNC, "
                f"async_q_size=0, "
                f"name={t_id})"
            )
        # 1 0 1 1
        elif (
            bucket_size_arg is not None
            and throttle_mode_arg is None
            and async_q_size_arg is not None
            and name_arg is not None
        ):
            # not a valid combo to have throttle_mode=ThrottleMode.SYNC
            # and async_q_size non-zero
            async_q_size_arg = 0
            a_throttle = Throttle(
                reqs_per_sec=reqs_per_sec_arg,
                bucket_size=bucket_size_arg,
                async_q_size=async_q_size_arg,
                name=name_arg,
            )
            t_id = id(a_throttle)

            expected_repr_str = (
                f"Throttle("
                f"reqs_per_sec={reqs_per_sec_arg}, "
                f"bucket_size={bucket_size_arg}, "
                f"throttle_mode=ThrottleMode.SYNC, "
                f"async_q_size=0, "
                f"name={name_arg})"
            )
        # 1 1 0 0
        elif (
            bucket_size_arg is not None
            and throttle_mode_arg is not None
            and async_q_size_arg is None
            and name_arg is None
        ):
            if throttle_mode_arg == ThrottleMode.ASYNC:
                throttle_mode_str = "ThrottleMode.ASYNC"
                async_q_size_arg = Throttle.DEFAULT_ASYNC_Q_SIZE
            else:
                throttle_mode_str = "ThrottleMode.SYNC"
                async_q_size_arg = 0

            a_throttle = Throttle(
                reqs_per_sec=reqs_per_sec_arg,
                bucket_size=bucket_size_arg,
                throttle_mode=throttle_mode_arg,
            )
            t_id = id(a_throttle)

            expected_repr_str = (
                f"Throttle("
                f"reqs_per_sec={reqs_per_sec_arg}, "
                f"bucket_size={bucket_size_arg}, "
                f"throttle_mode={throttle_mode_str}, "
                f"async_q_size={async_q_size_arg}, "
                f"name={t_id})"
            )
        # 1 1 0 1
        elif (
            bucket_size_arg is not None
            and throttle_mode_arg is not None
            and async_q_size_arg is None
            and name_arg is not None
        ):
            if throttle_mode_arg == ThrottleMode.ASYNC:
                throttle_mode_str = "ThrottleMode.ASYNC"
                async_q_size_arg = Throttle.DEFAULT_ASYNC_Q_SIZE
            else:
                throttle_mode_str = "ThrottleMode.SYNC"
                async_q_size_arg = 0
            a_throttle = Throttle(
                reqs_per_sec=reqs_per_sec_arg,
                bucket_size=bucket_size_arg,
                throttle_mode=throttle_mode_arg,
                name=name_arg,
            )
            t_id = id(a_throttle)

            expected_repr_str = (
                f"Throttle("
                f"reqs_per_sec={reqs_per_sec_arg}, "
                f"bucket_size={bucket_size_arg}, "
                f"throttle_mode={throttle_mode_str}, "
                f"async_q_size={async_q_size_arg}, "
                f"name={name_arg})"
            )
        # 1 1 1 0
        elif (
            bucket_size_arg is not None
            and throttle_mode_arg is not None
            and async_q_size_arg is not None
            and name_arg is None
        ):
            if throttle_mode_arg == ThrottleMode.ASYNC:
                throttle_mode_str = "ThrottleMode.ASYNC"
                if async_q_size_arg == 0:
                    async_q_size_arg = 30
            else:
                throttle_mode_str = "ThrottleMode.SYNC"
                async_q_size_arg = 0
            a_throttle = Throttle(
                reqs_per_sec=reqs_per_sec_arg,
                bucket_size=bucket_size_arg,
                throttle_mode=throttle_mode_arg,
                async_q_size=async_q_size_arg,
            )
            t_id = id(a_throttle)

            expected_repr_str = (
                f"Throttle("
                f"reqs_per_sec={reqs_per_sec_arg}, "
                f"bucket_size={bucket_size_arg}, "
                f"throttle_mode={throttle_mode_str}, "
                f"async_q_size={async_q_size_arg}, "
                f"name={t_id})"
            )
        # 1 1 1 1
        elif (
            bucket_size_arg is not None
            and throttle_mode_arg is not None
            and async_q_size_arg is not None
            and name_arg is not None
        ):
            if throttle_mode_arg == ThrottleMode.ASYNC:
                throttle_mode_str = "ThrottleMode.ASYNC"
                if async_q_size_arg == 0:
                    async_q_size_arg = 30
            else:
                throttle_mode_str = "ThrottleMode.SYNC"
                async_q_size_arg = 0
            a_throttle = Throttle(
                reqs_per_sec=reqs_per_sec_arg,
                bucket_size=bucket_size_arg,
                throttle_mode=throttle_mode_arg,
                async_q_size=async_q_size_arg,
                name=name_arg,
            )
            t_id = id(a_throttle)

            expected_repr_str = (
                f"Throttle("
                f"reqs_per_sec={reqs_per_sec_arg}, "
                f"bucket_size={bucket_size_arg}, "
                f"throttle_mode={throttle_mode_str}, "
                f"async_q_size={async_q_size_arg}, "
                f"name={name_arg})"
            )
        else:
            # cause failure since we should never reach this else
            a_throttle = Throttle(reqs_per_sec=-1)
            expected_repr_str = (
                "Throttle("
                "reqs_per_sec=None, "
                "bucket_size=None, "
                "throttle_mode=None, "
                "async_q_size=None, "
                "name=None, "
            )

        assert repr(a_throttle) == expected_repr_str

        if throttle_mode_arg == ThrottleMode.ASYNC:
            a_throttle.start_shutdown()

    ####################################################################
    # test_throttle_async_queue_full
    ####################################################################
    def test_throttle_async_queue_full(
        self,
    ) -> None:
        """test that throttle handles queue full condition."""

        def f1() -> None:
            print("42")

        a_throttle = Throttle(
            reqs_per_sec=1, throttle_mode=ThrottleMode.ASYNC, async_q_size=1
        )

        for _ in range(5):
            a_throttle.send_request(f1)

        a_throttle.start_shutdown()

    ####################################################################
    # test_throttle_async_queue_full_shutdown
    ####################################################################
    def test_throttle_async_queue_full_shutdown(
        self,
    ) -> None:
        """test that throttle abandons queueing for shutdown."""

        @dataclass
        class MainlineCount:
            """MainlineCount."""

            count: int = 0

        ml_count = MainlineCount()
        ml_event1 = threading.Event()
        ml_event2 = threading.Event()

        def f1(f1_idx: int, f1_count: MainlineCount) -> None:
            f1_count.count += 1
            logger.debug(f"{f1_idx=}, {f1_count.count=}")

        def f2() -> None:
            ml_event1.wait()
            a_throttle.start_shutdown(timeout=0.001)
            ml_event2.set()

        a_throttle = Throttle(
            reqs_per_sec=0.3, throttle_mode=ThrottleMode.ASYNC, async_q_size=1
        )

        f2_thread = threading.Thread(target=f2)
        f2_thread.start()

        for idx in range(6):
            if idx == 3:  # we queued 3 so far (i.e., idx 0, 1, 2)
                ml_event1.set()
                ml_event2.wait()
            a_throttle.send_request(f1, idx, f1_count=ml_count)

        a_throttle.start_shutdown()

        logger.debug(f"mainline: {ml_count.count=}")

        assert ml_count.count == 3


########################################################################
# TestThrottleDecoratorErrors class
########################################################################
class TestThrottleDecoratorErrors:
    """TestThrottleDecoratorErrors class."""

    def test_pie_throttle_bad_args(self, caplog: pytest.LogCaptureFixture) -> None:
        """test_throttle using bad arguments."""

        log_ver = LogVer(log_name="scottbrian_throttle.throttle")

        ml_call_seq = (
            "Request call sequence: test_throttle.py::TestThrottleDecoratorErrors."
            "test_pie_throttle_bad_args:[0-9]+ -> throttle.py::throttle:[0-9]+"
        )
        ml_call_seq2 = (
            "Request call sequence: python.py::pytest_pyfunc_call:[0-9]+ -> "
            "test_throttle.py::TestThrottleDecoratorErrors."
            "test_pie_throttle_bad_args:[0-9]+"
        )

        ################################################################
        # bad reqs_per_sec SYNC
        ################################################################
        ml_error_msg = (
            "The reqs_per_sec specification must be a positive "
            "int or float greater than zero. "
        ) + ml_call_seq

        log_ver.add_pattern(pattern=ml_error_msg, level=logging.ERROR)
        with pytest.raises(IncorrectReqsPerSecSpecified, match=ml_error_msg):

            @throttle(reqs_per_sec=-1)
            def f1() -> None:
                print("42")

            f1()

        log_ver.add_pattern(pattern=ml_error_msg, level=logging.ERROR)
        with pytest.raises(IncorrectReqsPerSecSpecified, match=ml_error_msg):

            @throttle(reqs_per_sec=0)
            def f2() -> None:
                print("42")

            f2()

        log_ver.add_pattern(pattern=ml_error_msg, level=logging.ERROR)
        with pytest.raises(IncorrectReqsPerSecSpecified, match=ml_error_msg):

            @throttle(reqs_per_sec="1")  # type: ignore
            def f3() -> None:
                print("42")

            f3()

        ################################################################
        # bad reqs_per_sec ASYNC
        ################################################################
        ml_error_msg = (
            "The reqs_per_sec specification must be a positive "
            "int or float greater than zero. "
        ) + ml_call_seq

        log_ver.add_pattern(pattern=ml_error_msg, level=logging.ERROR)
        with pytest.raises(IncorrectReqsPerSecSpecified, match=ml_error_msg):

            @throttle(reqs_per_sec=-1, throttle_mode=ThrottleMode.ASYNC)
            def f4() -> None:
                print("42")

            f4()

        log_ver.add_pattern(pattern=ml_error_msg, level=logging.ERROR)
        with pytest.raises(IncorrectReqsPerSecSpecified, match=ml_error_msg):

            @throttle(reqs_per_sec=0, throttle_mode=ThrottleMode.ASYNC)
            def f5() -> None:
                print("42")

            f5()

        log_ver.add_pattern(pattern=ml_error_msg, level=logging.ERROR)
        with pytest.raises(IncorrectReqsPerSecSpecified, match=ml_error_msg):

            @throttle(
                reqs_per_sec="1", throttle_mode=ThrottleMode.ASYNC
            )  # type: ignore
            def f6() -> None:
                print("42")

            f6()

        ################################################################
        # bad bucket_size SYNC
        ################################################################
        ml_error_msg = (
            "The bucket_size specification must be a positive "
            "int or float greater than or equal to 1. "
        ) + ml_call_seq

        log_ver.add_pattern(pattern=ml_error_msg, level=logging.ERROR)
        with pytest.raises(IncorrectBucketSizeSpecified, match=ml_error_msg):

            @throttle(reqs_per_sec=1, bucket_size=-1)
            def f7() -> None:
                print("42")

            f7()

        log_ver.add_pattern(pattern=ml_error_msg, level=logging.ERROR)
        with pytest.raises(IncorrectBucketSizeSpecified, match=ml_error_msg):

            @throttle(reqs_per_sec=1, bucket_size=0)
            def f8() -> None:
                print("42")

            f8()

        log_ver.add_pattern(pattern=ml_error_msg, level=logging.ERROR)
        with pytest.raises(IncorrectBucketSizeSpecified, match=ml_error_msg):

            @throttle(reqs_per_sec=1, bucket_size=0.3)
            def f9() -> None:
                print("42")

            f9()

        log_ver.add_pattern(pattern=ml_error_msg, level=logging.ERROR)
        with pytest.raises(IncorrectBucketSizeSpecified, match=ml_error_msg):

            @throttle(reqs_per_sec=1, bucket_size="1")  # type: ignore
            def f10() -> None:
                print("42")

            f10()

        ################################################################
        # bad bucket_size ASYNC
        ################################################################
        ml_error_msg = (
            "The bucket_size specification must be a positive "
            "int or float greater than or equal to 1. "
        ) + ml_call_seq

        log_ver.add_pattern(pattern=ml_error_msg, level=logging.ERROR)
        with pytest.raises(IncorrectBucketSizeSpecified, match=ml_error_msg):

            @throttle(reqs_per_sec=1, bucket_size=-1, throttle_mode=ThrottleMode.ASYNC)
            def f11() -> None:
                print("42")

            f11()

        log_ver.add_pattern(pattern=ml_error_msg, level=logging.ERROR)
        with pytest.raises(IncorrectBucketSizeSpecified, match=ml_error_msg):

            @throttle(reqs_per_sec=1, bucket_size=0, throttle_mode=ThrottleMode.ASYNC)
            def f12() -> None:
                print("42")

            f12()

        log_ver.add_pattern(pattern=ml_error_msg, level=logging.ERROR)
        with pytest.raises(IncorrectBucketSizeSpecified, match=ml_error_msg):

            @throttle(reqs_per_sec=1, bucket_size=0.3, throttle_mode=ThrottleMode.ASYNC)
            def f13() -> None:
                print("42")

            f13()

        log_ver.add_pattern(pattern=ml_error_msg, level=logging.ERROR)
        with pytest.raises(IncorrectBucketSizeSpecified, match=ml_error_msg):

            @throttle(
                reqs_per_sec=1, bucket_size="1", throttle_mode=ThrottleMode.ASYNC
            )  # type: ignore
            def f14() -> None:
                print("42")

            f14()

        ################################################################
        # bad async_q_size ASYNC
        ################################################################
        ml_error_msg = (
            "async_q_size must be an integer greater than zero. "
        ) + ml_call_seq

        log_ver.add_pattern(pattern=ml_error_msg, level=logging.ERROR)
        with pytest.raises(IncorrectAsyncQSizeSpecified, match=ml_error_msg):

            @throttle(reqs_per_sec=1, throttle_mode=ThrottleMode.ASYNC, async_q_size=-1)
            def f15() -> None:
                print("42")

            f15()

        log_ver.add_pattern(pattern=ml_error_msg, level=logging.ERROR)
        with pytest.raises(IncorrectAsyncQSizeSpecified, match=ml_error_msg):

            @throttle(reqs_per_sec=1, throttle_mode=ThrottleMode.ASYNC, async_q_size=0)
            def f16() -> None:
                print("42")

            f16()

        log_ver.add_pattern(pattern=ml_error_msg, level=logging.ERROR)
        with pytest.raises(IncorrectAsyncQSizeSpecified, match=ml_error_msg):

            @throttle(
                reqs_per_sec=1,
                throttle_mode=ThrottleMode.ASYNC,
                async_q_size=0.5,  # type: ignore
            )
            def f17() -> None:
                print("42")

            f17()

        log_ver.add_pattern(pattern=ml_error_msg, level=logging.ERROR)
        with pytest.raises(IncorrectAsyncQSizeSpecified, match=ml_error_msg):

            @throttle(
                reqs_per_sec=1, throttle_mode=ThrottleMode.ASYNC, async_q_size="1"
            )  # type: ignore
            def f18() -> None:
                print("42")

            f18()

        ################################################################
        # invalid async_q_size SYNC
        ################################################################
        ml_error_msg = (
            "a non_zero async_q_size is not allowed when throttle_mode is "
            "ThrottleMode.SYNC. "
        ) + ml_call_seq

        log_ver.add_pattern(pattern=ml_error_msg, level=logging.ERROR)
        with pytest.raises(InvalidAsyncQSizeSpecified, match=ml_error_msg):

            @throttle(reqs_per_sec=1, throttle_mode=ThrottleMode.SYNC, async_q_size=-1)
            def f19() -> None:
                print("42")

            f19()

        log_ver.add_pattern(pattern=ml_error_msg, level=logging.ERROR)
        with pytest.raises(InvalidAsyncQSizeSpecified, match=ml_error_msg):

            @throttle(
                reqs_per_sec=1, throttle_mode=ThrottleMode.SYNC, async_q_size=0.5
            )  # type: ignore
            def f20() -> None:
                print("42")

            f20()

        log_ver.add_pattern(pattern=ml_error_msg, level=logging.ERROR)
        with pytest.raises(InvalidAsyncQSizeSpecified, match=ml_error_msg):

            @throttle(reqs_per_sec=1, throttle_mode=ThrottleMode.SYNC, async_q_size=1)
            def f21() -> None:
                print("42")

            f21()

        log_ver.add_pattern(pattern=ml_error_msg, level=logging.ERROR)
        with pytest.raises(InvalidAsyncQSizeSpecified, match=ml_error_msg):

            @throttle(
                reqs_per_sec=1, throttle_mode=ThrottleMode.SYNC, async_q_size="1"
            )  # type: ignore
            def f22() -> None:
                print("42")

            f22()

        ################################################################
        # invalid shutdown request SYNC
        ################################################################
        ml_error_msg = (
            "A shutdown was requested for a synchronous throttle. "
            "Shutdown can only be requested for a throttle that is "
            "created with a throttle_mode of ThrottleMode.ASYNC. "
        ) + ml_call_seq2

        log_ver.add_pattern(pattern=ml_error_msg, level=logging.ERROR)
        with pytest.raises(InvalidShutdownRequested, match=ml_error_msg):

            @throttle(reqs_per_sec=1)
            def f23() -> None:
                print("42")

            f23.throttle.start_shutdown()

        ################################################################
        # incorrect shutdown type ASYNC
        ################################################################
        ml_error_msg = (
            "For start_shutdown, shutdownType must be specified as "
            "either ThrottleShutdownType.SOFT or "
            "ThrottleShutdownType.HARD. "
        ) + ml_call_seq2

        log_ver.add_pattern(pattern=ml_error_msg, level=logging.ERROR)
        log_ver.add_pattern(
            pattern=(
                "throttle t1 start_shutdown request "
                "successfully completed in [0-9.]+ seconds"
            ),
            level=logging.INFO,
        )
        with pytest.raises(IncorrectShutdownTypeSpecified, match=ml_error_msg):

            @throttle(reqs_per_sec=1, throttle_mode=ThrottleMode.ASYNC, name="t1")
            def f24() -> None:
                print("42")

            f24()
            f24.throttle.start_shutdown()
            f24.throttle.start_shutdown(shutdown_type=42)  # type: ignore

        ################################################################
        # check log results
        ################################################################
        match_results = log_ver.get_match_results(caplog=caplog)
        log_ver.print_match_results(match_results, print_matched=True)
        log_ver.verify_match_results(match_results)


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
        log_msg = (
            "throttle f1 send_request unhandled exception in request: division by zero"
        )
        log_ver.add_pattern(
            log_name="scottbrian_throttle.throttle",
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
        log_msg = (
            "throttle f2 send_request unhandled exception in request: division by zero"
        )
        log_ver.add_pattern(
            log_name="scottbrian_throttle.throttle",
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

    def test_async_pie_throttle_request_errors(
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
            ".test_async_pie_throttle_request_errors"
        )
        log_ver.add_call_seq(name="alpha", seq=alpha_call_seq)

        ################################################################
        # async request failure
        ################################################################
        log_msg = (
            "throttle f2 schedule_requests unhandled exception in "
            "request: division by zero"
        )
        log_ver.add_pattern(
            log_name="scottbrian_throttle.throttle",
            level=logging.DEBUG,
            pattern=log_msg,
        )

        zero_div_err_pattern = (
            "Test case excepthook: args.exc_type=<class "
            "'ZeroDivisionError'>, "
            r"args.exc_value=ZeroDivisionError\('division by "
            r"zero'\), "
            "args.exc_traceback=<traceback object at 0x[0-9A-F]+>, "
            r"args.thread=<Thread\(Thread-[0-9]+ "
            r"\(schedule_requests\), started [0-9]+\)>"
        )

        log_ver.add_pattern(
            log_name="scottbrian_utils.exc_hook",
            pattern="caller test_throttle.py::"
            "TestThrottleDecoratorRequestErrors."
            "test_async_pie_throttle_request_errors:[0-9]+ is raising Exception: "
            f'"{zero_div_err_pattern}"',
        )
        with pytest.raises(ZeroDivisionError, match=zero_div_err_pattern):

            @throttle(reqs_per_sec=1, throttle_mode=ThrottleMode.ASYNC)
            def f2() -> None:
                ans = 42 / 0
                print(f"{ans=}")

            f2()
            f2()
            f2.throttle.start_shutdown()
            log_msg = (
                "throttle f2 start_shutdown request successfully completed "
                f"in {f2.throttle.shutdown_elapsed_time:.4f} "
                "seconds"
            )
            log_ver.add_pattern(
                log_name="scottbrian_throttle.throttle",
                level=logging.INFO,
                pattern=log_msg,
            )
            log_ver.test_msg("about to call thread_exc.raise_exc_if_one()")
            thread_exc.raise_exc_if_one()

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
        "throttle_mode_arg", (ThrottleMode.SYNC, ThrottleMode.ASYNC)
    )
    @pytest.mark.parametrize("request_style_arg", (0, 1, 2, 3, 4, 5, 6))
    def test_throttle_args_style(
        self, throttle_mode_arg: ThrottleMode, request_style_arg: int
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
        "throttle_mode_arg", (ThrottleMode.SYNC, ThrottleMode.ASYNC)
    )
    @pytest.mark.parametrize("num_threads_arg", (0, 1, 2))
    @pytest.mark.parametrize("reqs_per_sec_arg", (0.25, 0.33, 0.5))
    @pytest.mark.parametrize("bucket_size_arg", (1, 1.25, 1.5, 2))
    @pytest.mark.parametrize("send_interval_mult_arg", (0.0, 0.9, 1.0, 1.1))
    def test_throttle_multi_threads1(
        self,
        throttle_mode_arg: ThrottleMode,
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
        "throttle_mode_arg", (ThrottleMode.SYNC, ThrottleMode.ASYNC)
    )
    @pytest.mark.parametrize("num_threads_arg", (0, 2, 8))
    @pytest.mark.parametrize("reqs_per_sec_arg", (1, 2, 3))
    @pytest.mark.parametrize("bucket_size_arg", (1, 1.5, 2, 3))
    @pytest.mark.parametrize("send_interval_mult_arg", (0.0, 0.9, 1.0, 1.1))
    def test_throttle_multi_threads2(
        self,
        throttle_mode_arg: ThrottleMode,
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
        throttle_mode: ThrottleMode,
        bucket_size: IntFloat,
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
            if throttle_mode == ThrottleMode.ASYNC:
                logger.debug("throttle_router doing throttle shutdown")
                a_throttle.start_shutdown(shutdown_type=ThrottleShutdownType.SOFT)
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

            if throttle_mode == ThrottleMode.ASYNC:
                logger.debug("throttle_router doing throttle shutdown")
                a_throttle.start_shutdown(shutdown_type=ThrottleShutdownType.SOFT)

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
            exp_rc = idx if throttle_mode != ThrottleMode.ASYNC else Throttle.RC_OK
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
        "throttle_mode_arg", (ThrottleMode.SYNC, ThrottleMode.ASYNC)
    )
    @pytest.mark.parametrize("request_style_arg", (0, 1, 2, 3, 4, 5, 6))
    def test_pie_throttle_args_style(
        self, throttle_mode_arg: ThrottleMode, request_style_arg: int
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

            if request_validator.t_throttle.throttle_mode == ThrottleMode.ASYNC:
                return None
            return request_item.req_id + 42 + 0

        if throttle_mode_arg == ThrottleMode.ASYNC:
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

            if request_validator.t_throttle.throttle_mode == ThrottleMode.ASYNC:
                return None
            return request_item.req_id + 42 + 1

        if throttle_mode_arg == ThrottleMode.ASYNC:
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

            if request_validator.t_throttle.throttle_mode == ThrottleMode.ASYNC:
                return None
            return request_item.req_id + 42 + 2

        if throttle_mode_arg == ThrottleMode.ASYNC:
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

            if request_validator.t_throttle.throttle_mode == ThrottleMode.ASYNC:
                return None
            return request_item.req_id + 42 + 3

        if throttle_mode_arg == ThrottleMode.ASYNC:
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

            if request_validator.t_throttle.throttle_mode == ThrottleMode.ASYNC:
                return None
            return request_item.req_id + 42 + 4

        if throttle_mode_arg == ThrottleMode.ASYNC:
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

            if request_validator.t_throttle.throttle_mode == ThrottleMode.ASYNC:
                return None
            return request_item.req_id + 42 + 5

        if throttle_mode_arg == ThrottleMode.ASYNC:
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
            req_id: int, reqs_per_sec: IntFloat, *, bucket_size: float, interval: float
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

            if request_validator.t_throttle.throttle_mode == ThrottleMode.ASYNC:
                return None
            return request_item.req_id + 42 + 6

        if throttle_mode_arg == ThrottleMode.ASYNC:
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

        if throttle_mode_arg == ThrottleMode.ASYNC:
            shutdown_throttle_funcs(f0, f1, f2, f3, f4, f5, f6)
        request_validator.validate_series()  # validate for the series

    ####################################################################
    # test_pie_throttle
    ####################################################################
    @pytest.mark.parametrize(
        "throttle_mode_arg", (ThrottleMode.SYNC, ThrottleMode.ASYNC)
    )
    @pytest.mark.parametrize("reqs_per_sec_arg", (1, 2, 3))
    @pytest.mark.parametrize("bucket_size_arg", (1, 1.3, 2, 3))
    @pytest.mark.parametrize("send_interval_mult_arg", (0.0, 0.9, 1.0, 1.1))
    def test_pie_throttle(
        self,
        throttle_mode_arg: ThrottleMode,
        reqs_per_sec_arg: IntFloat,
        bucket_size_arg: IntFloat,
        send_interval_mult_arg: IntFloat,
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

            if request_validator.t_throttle.throttle_mode == ThrottleMode.ASYNC:
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

        if throttle_mode_arg == ThrottleMode.ASYNC:
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
            f"{time_str} ({expected_time}), interval={f_interval_str} ({req_time.interval})"
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
        "throttle_mode_arg", (ThrottleMode.SYNC, ThrottleMode.ASYNC)
    )
    @pytest.mark.parametrize("reqs_per_sec_arg", (0.5, 1, 2, 3))
    def test_get_interval_secs(
        self, throttle_mode_arg: ThrottleMode, reqs_per_sec_arg: IntFloat
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

        if throttle_mode_arg == ThrottleMode.ASYNC:
            a_throttle1.start_shutdown()

    ####################################################################
    # test_get_completion_time_secs
    ####################################################################
    @pytest.mark.parametrize(
        "throttle_mode_arg", (ThrottleMode.SYNC, ThrottleMode.ASYNC)
    )
    @pytest.mark.parametrize("reqs_per_sec_arg", (0.2, 1, 2, 3))
    def test_get_completion_time_secs(
        self, throttle_mode_arg: ThrottleMode, reqs_per_sec_arg: IntFloat
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

        if throttle_mode_arg == ThrottleMode.ASYNC:
            a_throttle1.start_shutdown()


########################################################################
# TestThrottleShutdown
########################################################################
class TestThrottleShutdownErrors:
    """Class TestThrottle error cases."""

    ####################################################################
    # test_attempt_sync_throttle_shutdown
    ####################################################################
    def test_attempt_sync_throttle_shutdown(
        self,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """Method to test attempted shutdown in sync throttle_mode."""

        ################################################################
        # setup the log verifier
        ################################################################
        log_ver = LogVer(log_name=__name__)
        alpha_call_seq = (
            "test_throttle.py::TestThrottleShutdown.test_attempt_sync_throttle_shutdown"
        )
        log_ver.add_call_seq(name="alpha", seq=alpha_call_seq)
        ml_call_seq = (
            "Request call sequence: python.py::pytest_pyfunc_call:[0-9]+ -> "
            "test_throttle.py::TestThrottleShutdownErrors."
            "test_attempt_sync_throttle_shutdown:[0-9]+"
        )

        ################################################################
        # create a sync throttle_mode throttle
        ################################################################
        reqs_per_sec_arg = 4
        a_throttle1 = Throttle(
            reqs_per_sec=reqs_per_sec_arg, throttle_mode=ThrottleMode.SYNC
        )

        ################################################################
        # do some requests
        ################################################################
        interval = a_throttle1.get_interval_secs()
        start_time = time.time()
        a_req_time = ReqTime(
            num_reqs=0, f_time=start_time, start_time=start_time, interval=interval
        )

        def f1(req_time: ReqTime) -> None:
            issue_shutdown_log_entry(func_name="f1", req_time=req_time, log_ver=log_ver)

        num_requests_a = 4
        for i in range(num_requests_a):
            a_throttle1.send_request(f1, a_req_time)

        assert a_req_time.num_reqs == num_requests_a

        ################################################################
        # attempt to shutdown the sync throttle
        ################################################################
        log_error_msg = (
            "A shutdown was requested for a synchronous throttle. "
            "Shutdown can only be requested for a throttle that is "
            "created with a throttle_mode of ThrottleMode.ASYNC. "
        ) + ml_call_seq
        log_ver.add_pattern(
            log_name="scottbrian_throttle.throttle",
            level=logging.ERROR,
            pattern=log_error_msg,
        )
        with pytest.raises(InvalidShutdownRequested, match=log_error_msg):
            a_throttle1.start_shutdown(shutdown_type=100)  # type: ignore

        ################################################################
        # ensure that throttle is still OK
        ################################################################
        # the following requests should not get ignored
        num_requests_b = 6
        for i in range(num_requests_b):
            a_throttle1.send_request(f1, a_req_time)

        # the count should now reflect the additional requests
        assert a_req_time.num_reqs == num_requests_a + num_requests_b

        ################################################################
        # verify the log messages
        ################################################################
        match_results = log_ver.get_match_results(caplog=caplog)
        log_ver.print_match_results(match_results)
        log_ver.verify_log_results(match_results)

    ####################################################################
    # test_incorrect_shutdown_type
    ####################################################################
    def test_incorrect_shutdown_type(
        self,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """Method to test incorrect shutdown type."""

        ################################################################
        # setup the log verifier
        ################################################################
        log_ver = LogVer(log_name=__name__)
        alpha_call_seq = (
            "test_throttle.py::TestThrottleShutdown.test_incorrect_shutdown_type"
        )
        log_ver.add_call_seq(name="alpha", seq=alpha_call_seq)
        ml_call_seq = (
            "Request call sequence: python.py::pytest_pyfunc_call:[0-9]+ -> "
            "test_throttle.py::TestThrottleShutdownErrors."
            "test_incorrect_shutdown_type:[0-9]+"
        )
        ################################################################
        # create an async throttle_mode throttle
        ################################################################
        reqs_per_sec_arg = 6
        a_throttle1 = Throttle(
            reqs_per_sec=reqs_per_sec_arg,
            throttle_mode=ThrottleMode.ASYNC,
            name="test1",
        )

        ################################################################
        # do some requests
        ################################################################
        interval = a_throttle1.get_interval_secs()
        start_time = time.time()
        a_req_time = ReqTime(
            num_reqs=0, f_time=start_time, start_time=start_time, interval=interval
        )

        def f1(req_time: ReqTime) -> None:
            issue_shutdown_log_entry(func_name="f1", req_time=req_time, log_ver=log_ver)

        num_requests_a = 4
        for i in range(num_requests_a):
            a_throttle1.send_request(f1, a_req_time)

        completion_time = a_throttle1.get_completion_time_secs(
            num_requests_a, from_start=True
        ) + (0.5 * a_throttle1.get_interval_secs())
        log_ver.test_msg(f"about to sleep1 for {completion_time} seconds")
        time.sleep(completion_time)  # make sure requests are done
        assert a_req_time.num_reqs == num_requests_a

        ################################################################
        # attempt to shutdown the incorrect shutdown_type
        ################################################################
        log_error_msg = (
            "For start_shutdown, shutdownType must be specified as "
            "either ThrottleShutdownType.SOFT or "
            "ThrottleShutdownType.HARD. "
        ) + ml_call_seq
        log_ver.add_pattern(
            log_name="scottbrian_throttle.throttle",
            level=logging.ERROR,
            pattern=log_error_msg,
        )
        with pytest.raises(IncorrectShutdownTypeSpecified, match=log_error_msg):
            a_throttle1.start_shutdown(shutdown_type=100)  # type: ignore

        ################################################################
        # ensure that throttle is still OK
        ################################################################
        # the following requests should not get ignored
        num_requests_b = 6
        for i in range(num_requests_b):
            a_throttle1.send_request(f1, a_req_time)

        completion_time = a_throttle1.get_completion_time_secs(
            num_requests_b, from_start=True
        ) + (0.5 * a_throttle1.get_interval_secs())
        log_ver.test_msg(f"about to sleep2 for {completion_time} seconds")
        time.sleep(completion_time)  # make sure requests are done
        # the count should be updated
        assert a_req_time.num_reqs == num_requests_a + num_requests_b

        a_throttle1.start_shutdown()  # must do a real shutdown

        log_msg = (
            "throttle test1 start_shutdown request successfully completed "
            f"in {a_throttle1.shutdown_elapsed_time:.4f} "
            "seconds"
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
    reqs_per_sec: IntFloat, async_q_size: int, name: Optional[str] = None
) -> tuple[Throttle, float]:
    """Obtain an async throttle and return it.

    Args:
        reqs_per_sec: number of requests per second
        async_q_size: max number of reqs_per_sec that will be queued
        name: throttle name used in log messages

    """
    a_throttle = Throttle(
        reqs_per_sec=reqs_per_sec,
        throttle_mode=ThrottleMode.ASYNC,
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
            shutdown_type=ThrottleShutdownType.HARD, timeout=60
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


class TestThrottleShutdown:
    """Class TestThrottle."""

    log_ver: LogVer
    ####################################################################
    # test_throttle_shutdown
    ####################################################################
    short_long_items = ("Short", "Long")
    short_long_combos = it.product(short_long_items, repeat=3)

    @pytest.mark.parametrize("reqs_per_sec_arg", (1, 2, 3))
    @pytest.mark.parametrize("short_long_timeout_arg", short_long_combos)
    @etrace(omit_parms="caplog", omit_caller=True, log_ver=True)
    def test_throttle_hard_shutdown_timeout(
        self,
        reqs_per_sec_arg: int,
        short_long_timeout_arg: str,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """Method to test shutdown scenarios.

        Args:
            reqs_per_sec_arg: how many requests per second
            short_long_timeout_arg: whether to do short or long timeout
            caplog: pytest fixture to capture log output


        """
        sleep_delay_arg = 0.0001
        num_reqs_to_make = 1_000_000

        log_ver = self.log_ver
        alpha_call_seq = (
            "test_throttle.py::TestThrottleShutdown"
            ".test_throttle_hard_shutdown_timeout"
        )
        log_ver.add_call_seq(name="alpha", seq=alpha_call_seq)

        a_throttle, interval = get_async_throttle(
            reqs_per_sec=reqs_per_sec_arg,
            name="hard",
            async_q_size=num_reqs_to_make,
        )
        log_ver.test_msg(f"{num_reqs_to_make=}, {sleep_delay_arg=}, {interval=}")

        ################################################################
        # calculate sleep times
        ################################################################
        sleep_reqs_to_do = min(
            num_reqs_to_make, math.floor(num_reqs_to_make * sleep_delay_arg)
        )
        log_ver.test_msg(f"{sleep_reqs_to_do=}")

        ################################################################
        # We need a try/finally to make sure we can shut down the
        # throttle in the event that an assertion fails. In an earlier
        # version of this code before adding the try/finally, there were
        # test cases failing and leaving the throttle active with its
        # requests showing up in the next test case logs.
        ################################################################
        ret_code = Throttle.RC_SHUTDOWN_TIMED_OUT
        try:
            num_first_batch = sleep_reqs_to_do * 2

            start_time, a_req_time = queue_first_batch_requests(
                throttle=a_throttle,
                num_reqs=num_first_batch,
                num_sleep_reqs=sleep_reqs_to_do,
                log_ver=log_ver,
            )

            num_second_batch = num_reqs_to_make - num_first_batch

            queue_more_requests(
                throttle=a_throttle,
                num_reqs=num_second_batch,
                req_time=a_req_time,
                log_ver=log_ver,
            )

            issue_remaining_requests_log_entry(throttle=a_throttle, log_ver=log_ver)

            num_reqs_done_before_shutdown = 0
            for short_long in short_long_timeout_arg:
                if short_long == "Short":
                    timeout = 0.001
                    if ret_code == Throttle.RC_SHUTDOWN_TIMED_OUT:
                        exp_ret_code = Throttle.RC_SHUTDOWN_TIMED_OUT
                    else:
                        exp_ret_code = Throttle.RC_SHUTDOWN_HARD_COMPLETED_OK
                else:
                    timeout = 10
                    exp_ret_code = Throttle.RC_SHUTDOWN_HARD_COMPLETED_OK

                log_ver.test_msg(f"about to shutdown with {timeout=}")

                # expect no additional reqs done since hard shutdown

                # do the verify check only once before the shutdown
                # because the number of expected reqs will increase
                # since it is based off start_time, but no reqs should
                # be processed once the shutdown is started
                if num_reqs_done_before_shutdown == 0:
                    num_reqs_done_before_shutdown = a_req_time.num_reqs

                ret_code = a_throttle.start_shutdown(
                    shutdown_type=ThrottleShutdownType.HARD, timeout=timeout
                )

                async_q_empty, num_reqs = issue_remaining_requests_log_entry(
                    throttle=a_throttle, log_ver=log_ver
                )

                # verify that the throttle did not process any reqs
                # after the shutdown was started
                assert abs(num_reqs_done_before_shutdown - a_req_time.num_reqs) <= 1

                assert ret_code == exp_ret_code
                if ret_code == Throttle.RC_SHUTDOWN_TIMED_OUT:
                    assert async_q_empty is False

                    log_msg = (
                        "throttle hard start_shutdown request timed out with "
                        f"{timeout=:.4f}"
                    )
                    log_ver.add_pattern(
                        log_name="scottbrian_throttle.throttle",
                        level=logging.DEBUG,
                        pattern=log_msg,
                    )

                else:  # retcode is RC_SHUTDOWN_HARD_COMPLETED_OK
                    assert async_q_empty is True

            final_shutdown_and_verification(
                throttle=a_throttle,
                req_time=a_req_time,
                log_ver=log_ver,
                ret_code=ret_code,
                caplog=caplog,
            )

        finally:
            a_throttle.start_shutdown(ThrottleShutdownType.HARD)

    ####################################################################
    # test_throttle_shutdown
    ####################################################################
    @pytest.mark.parametrize("reqs_per_sec_arg", (1, 2, 3))
    @pytest.mark.parametrize("sleep_delay_arg", (0.10, 0.30, 1.25))
    @pytest.mark.parametrize("timeout3_arg", (0.10, 0.75, 1.25))
    @etrace(omit_parms="caplog", omit_caller=True, log_ver=True)
    def test_throttle_soft_shutdown_timeout(
        self,
        reqs_per_sec_arg: int,
        sleep_delay_arg: float,
        timeout3_arg: float,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """Method to test shutdown scenarios.

        Args:
            reqs_per_sec_arg: how many requests per second
            sleep_delay_arg: how many requests as a ratio to total
                               requests to schedule before starting
                               shutdown
            timeout3_arg: timeout value to use
            caplog: pytest fixture to capture log output


        """
        num_reqs_to_make = 100

        log_ver = self.log_ver
        alpha_call_seq = (
            "test_throttle.py::TestThrottleShutdown"
            ".test_throttle_soft_shutdown_timeout"
        )
        log_ver.add_call_seq(name="alpha", seq=alpha_call_seq)

        a_throttle, interval = get_async_throttle(
            reqs_per_sec=reqs_per_sec_arg,
            name="soft_timeout",
            async_q_size=num_reqs_to_make,
        )
        log_ver.test_msg(f"{num_reqs_to_make=}, {sleep_delay_arg=}, {interval=}")

        ################################################################
        # calculate sleep times
        ################################################################
        sleep_reqs_to_do = min(
            num_reqs_to_make, math.floor(num_reqs_to_make * sleep_delay_arg)
        )
        log_ver.test_msg(f"{sleep_reqs_to_do=}")

        # calculate the subsequent sleep time to use by adding one
        # interval since the first request zero delay is no longer true
        sleep_seconds2 = a_throttle.get_completion_time_secs(
            sleep_reqs_to_do, from_start=False
        ) + (interval / 2)

        ################################################################
        # calculate timeout times
        ################################################################
        timeout_reqs_to_do = min(
            num_reqs_to_make, math.floor(num_reqs_to_make * timeout3_arg)
        )
        log_ver.test_msg(f"{timeout_reqs_to_do=}")
        timeout_seconds = a_throttle.get_completion_time_secs(
            timeout_reqs_to_do, from_start=False
        )  # +(interval / 2)
        log_ver.test_msg(f"{timeout_seconds=}")

        ################################################################
        # We need a try/finally to make sure we can shut down the
        # throttle in the event that an assertion fails. In an earlier
        # version of this code before adding the try/finally, there were
        # test cases failing and leaving the throttle active with its
        # requests showing up in the next test case logs.
        ################################################################
        try:
            start_time, a_req_time = queue_first_batch_requests(
                throttle=a_throttle,
                num_reqs=num_reqs_to_make,
                num_sleep_reqs=sleep_reqs_to_do,
                log_ver=log_ver,
            )

            prev_reqs_done = sleep_reqs_to_do

            while True:
                shutdown_start_time = time.time()
                timeout = timeout_seconds - (shutdown_start_time - a_req_time.f_time)

                log_ver.test_msg(f"about to shutdown with {timeout=}")

                ret_code = a_throttle.start_shutdown(
                    shutdown_type=ThrottleShutdownType.SOFT, timeout=timeout
                )

                shutdown_elapsed_time = time.time() - shutdown_start_time
                exp_reqs_done = min(
                    num_reqs_to_make, timeout_reqs_to_do + prev_reqs_done
                )

                assert abs(a_req_time.num_reqs - exp_reqs_done) <= 1

                prev_reqs_done = exp_reqs_done

                if ret_code == Throttle.RC_SHUTDOWN_TIMED_OUT:
                    log_msg = (
                        "throttle soft_timeout start_shutdown request timed out with "
                        f"{timeout=:.4f}"
                    )
                    log_ver.add_pattern(
                        log_name="scottbrian_throttle.throttle",
                        level=logging.DEBUG,
                        pattern=log_msg,
                    )
                    assert timeout <= shutdown_elapsed_time <= (timeout * 1.10)

                if exp_reqs_done == num_reqs_to_make:
                    assert (
                        Throttle.RC_SHUTDOWN_SOFT_COMPLETED_OK
                        == a_throttle.start_shutdown(
                            shutdown_type=ThrottleShutdownType.SOFT,
                            timeout=timeout,
                        )
                    )
                    break

                sleep_time = sleep_seconds2 - (time.time() - a_req_time.f_time)
                log_ver.test_msg(f"about to sleep for {sleep_time=}")
                time.sleep(sleep_time)

                exp_reqs_done = min(num_reqs_to_make, sleep_reqs_to_do + prev_reqs_done)
                assert abs(a_req_time.num_reqs - exp_reqs_done) <= 1

                prev_reqs_done = exp_reqs_done

            final_shutdown_and_verification(
                throttle=a_throttle,
                req_time=a_req_time,
                log_ver=log_ver,
                ret_code=ret_code,
                caplog=caplog,
            )

        finally:
            a_throttle.start_shutdown(ThrottleShutdownType.HARD)

    ####################################################################
    # test_throttle_shutdown
    ####################################################################
    timeout_items = (0.0, 0.10, 0.75, 1.25)
    multi_timeout_combos = it.combinations_with_replacement(timeout_items, 3)

    @pytest.mark.parametrize("reqs_per_sec_arg", (1, 2, 3))
    @pytest.mark.parametrize("multi_timeout_arg", multi_timeout_combos)
    @etrace(omit_parms="caplog", omit_caller=True, log_ver=True)
    def test_throttle_mutil_soft_shutdown(
        self,
        reqs_per_sec_arg: int,
        multi_timeout_arg: tuple[float, float, float],
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """Method to test multi soft shutdown scenarios.

        Args:
            reqs_per_sec_arg: how many requests per second
            multi_timeout_arg: timeout time factors
            caplog: pytest fixture to capture log output


        """
        sleep_delay_arg = 0.1
        num_reqs_to_make = 100

        log_ver = self.log_ver
        alpha_call_seq = (
            "test_throttle.py::TestThrottleShutdown"
            ".test_throttle_hard_shutdown_timeout"
        )
        log_ver.add_call_seq(name="alpha", seq=alpha_call_seq)

        a_throttle, interval = get_async_throttle(
            reqs_per_sec=reqs_per_sec_arg,
            name="multi soft",
            async_q_size=num_reqs_to_make,
        )
        log_ver.test_msg(f"{num_reqs_to_make=}, {sleep_delay_arg=}, {interval=}")

        # shutdown_completed = False
        ret_code = Throttle.RC_SHUTDOWN_TIMED_OUT

        def soft_shutdown(ss_timeout: float) -> None:
            """Do soft shutdown.

            Args:
                ss_timeout: whether to issue timeout
            """
            # nonlocal shutdown_completed
            nonlocal ret_code
            rc = a_throttle.start_shutdown(
                shutdown_type=ThrottleShutdownType.SOFT, timeout=ss_timeout
            )

            log_ver.test_msg(f"soft shutdown {rc=} with {ss_timeout=:.4f}")
            # if shutdown_completed:
            #     return

            if ss_timeout == 0.0 or ss_timeout == no_timeout_secs:
                assert rc == Throttle.RC_SHUTDOWN_SOFT_COMPLETED_OK
                ret_code = Throttle.RC_SHUTDOWN_SOFT_COMPLETED_OK
                # shutdown_completed = True
            else:
                if rc == Throttle.RC_SHUTDOWN_TIMED_OUT:
                    l_msg = (
                        "throttle multi soft start_shutdown request timed out with "
                        f"timeout={ss_timeout:.4f}"
                    )

                    log_ver.add_pattern(
                        log_name="scottbrian_throttle.throttle",
                        level=logging.DEBUG,
                        pattern=l_msg,
                    )

        ################################################################
        # calculate sleep times
        ################################################################
        sleep_reqs_to_do = math.floor(num_reqs_to_make * sleep_delay_arg)
        log_ver.test_msg(f"{sleep_reqs_to_do=}")

        ################################################################
        # calculate timeout times
        ################################################################
        timeout_values = []
        no_timeout_secs = -1.0
        for timeout_factor in multi_timeout_arg:
            if timeout_factor == 0.0:
                timeout_values.append(0.0)
            else:
                timeout_reqs_to_do = math.floor(num_reqs_to_make * timeout_factor)
                timeout_seconds = a_throttle.get_completion_time_secs(
                    timeout_reqs_to_do, from_start=False
                )  # +(interval / 2)
                timeout_values.append(timeout_seconds)

                if timeout_factor > 1.0:
                    no_timeout_secs = timeout_seconds

                log_ver.test_msg(
                    f"for {timeout_factor=}, "
                    f"{timeout_reqs_to_do=}, "
                    f"{timeout_seconds=}"
                )

        ################################################################
        # We need a try/finally to make sure we can shut down the
        # throttle in the event that an assertion fails. In an earlier
        # version of this code before adding the try/finally, there were
        # test cases failing and leaving the throttle active with its
        # requests showing up in the next test case logs.
        ################################################################
        try:
            start_time, a_req_time = queue_first_batch_requests(
                throttle=a_throttle,
                num_reqs=num_reqs_to_make,
                num_sleep_reqs=sleep_reqs_to_do,
                log_ver=log_ver,
            )

            assert abs(a_req_time.num_reqs - sleep_reqs_to_do) <= 1

            # start_time = time.time()

            shutdown_threads = []
            for idx, timeout in enumerate(timeout_values):
                shutdown_threads.append(
                    threading.Thread(target=soft_shutdown, args=(timeout,))
                )

                log_ver.test_msg(f"about to shutdown with {timeout=}")

                shutdown_threads[idx].start()

            ############################################################
            # wait for shutdowns to complete. Note that the three
            # threads may have all timed out. Since this is a soft
            # shutdown we will simply wait for the requests to be
            # completed.
            ############################################################
            while a_req_time.num_reqs < num_reqs_to_make:
                time.sleep(1)

            ############################################################
            # make sure all thread came back home
            ############################################################
            for idx in range(len(timeout_values)):
                shutdown_threads[idx].join()

            final_shutdown_and_verification(
                throttle=a_throttle,
                req_time=a_req_time,
                log_ver=log_ver,
                ret_code=ret_code,
                caplog=caplog,
            )

        finally:
            a_throttle.start_shutdown(ThrottleShutdownType.HARD)

    ####################################################################
    # test_throttle_shutdown
    ####################################################################
    short_long_items = ("Short", "Long")
    short_long_combos = it.product(short_long_items, repeat=3)

    hard_soft_items = ("Hard", "Soft")
    hard_soft_combos = it.product(hard_soft_items, repeat=3)

    @pytest.mark.parametrize("reqs_per_sec_arg", (1, 2, 3))
    @pytest.mark.parametrize("short_long_timeout_arg", short_long_combos)
    @pytest.mark.parametrize("hard_soft_combo_arg", hard_soft_combos)
    @etrace(omit_parms="caplog", omit_caller=True, log_ver=True)
    def test_throttle_shutdown_combos(
        self,
        reqs_per_sec_arg: int,
        short_long_timeout_arg: str,
        hard_soft_combo_arg: str,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """Method to test shutdown scenarios.

        Args:
            reqs_per_sec_arg: how many requests per second
            short_long_timeout_arg: whether to do short or long timeout
            hard_soft_combo_arg: whether to do hard of soft
            caplog: pytest fixture to capture log output


        """
        num_reqs_to_make = 1_000_000
        sleep_reqs_to_do = 10

        # The following code will limit the number of requests to a
        # smaller number if we will be doing a soft shutdown to
        # completion without an intervening hard shutdown. We do not
        # want to process a large number of reqs unless we are going
        # to toss them.
        found_hard = False
        for short_long, hard_soft in zip(short_long_timeout_arg, hard_soft_combo_arg):
            if hard_soft == "Soft":
                if short_long == "Long":
                    if not found_hard:
                        num_reqs_to_make = 100
            else:
                found_hard = True

        log_ver = self.log_ver
        alpha_call_seq = (
            "test_throttle.py::TestThrottleShutdown"
            ".test_throttle_hard_shutdown_timeout"
        )
        log_ver.add_call_seq(name="alpha", seq=alpha_call_seq)

        a_throttle, interval = get_async_throttle(
            reqs_per_sec=reqs_per_sec_arg,
            name="shutdown combos",
            async_q_size=num_reqs_to_make,
        )
        log_ver.test_msg(f"{num_reqs_to_make=}, {interval=}, {sleep_reqs_to_do=}")

        ################################################################
        # We need a try/finally to make sure we can shut down the
        # throttle in the event that an assertion fails. In an earlier
        # version of this code before adding the try/finally, there were
        # test cases failing and leaving the throttle active with its
        # requests showing up in the next test case logs.
        ################################################################
        ret_code = Throttle.RC_SHUTDOWN_TIMED_OUT
        try:
            num_first_batch = sleep_reqs_to_do * 2
            start_time, a_req_time = queue_first_batch_requests(
                throttle=a_throttle,
                num_reqs=num_first_batch,
                num_sleep_reqs=sleep_reqs_to_do,
                log_ver=log_ver,
            )

            # queue remainder of requests
            num_second_batch = num_reqs_to_make - num_first_batch

            queue_more_requests(
                throttle=a_throttle,
                num_reqs=num_second_batch,
                req_time=a_req_time,
                log_ver=log_ver,
            )

            hard_shutdown_issued = False
            last_num_reqs_done = -1
            exp_ret_code = Throttle.RC_SHUTDOWN_TIMED_OUT
            for short_long, hard_soft in zip(
                short_long_timeout_arg, hard_soft_combo_arg
            ):
                if hard_soft == "Soft":
                    shutdown_type = ThrottleShutdownType.SOFT
                    if short_long == "Short":
                        timeout = 0.0001
                    else:
                        timeout = None
                        if exp_ret_code == Throttle.RC_SHUTDOWN_TIMED_OUT:
                            if hard_shutdown_issued is True:
                                exp_ret_code = Throttle.RC_SHUTDOWN_HARD_COMPLETED_OK
                            else:
                                exp_ret_code = Throttle.RC_SHUTDOWN_SOFT_COMPLETED_OK
                else:
                    shutdown_type = ThrottleShutdownType.HARD
                    hard_shutdown_issued = True
                    if short_long == "Short":
                        timeout = 0.0001
                    else:
                        timeout = None
                        if exp_ret_code == Throttle.RC_SHUTDOWN_TIMED_OUT:
                            exp_ret_code = Throttle.RC_SHUTDOWN_HARD_COMPLETED_OK

                log_ver.test_msg(
                    f"about to shutdown with {timeout=} and {shutdown_type=}"
                )

                if hard_shutdown_issued is True:
                    # once we do hard shutdown, no more reqs should be
                    # processed
                    if last_num_reqs_done == -1:
                        last_num_reqs_done = a_req_time.num_reqs
                    assert abs(last_num_reqs_done - a_req_time.num_reqs) <= 1

                ret_code = a_throttle.start_shutdown(
                    shutdown_type=shutdown_type, timeout=timeout
                )

                assert ret_code == exp_ret_code
                if ret_code == Throttle.RC_SHUTDOWN_TIMED_OUT:
                    log_msg = (
                        "throttle shutdown combos start_shutdown request timed "
                        f"out with {timeout=:.4f}"
                    )
                    log_ver.add_pattern(
                        log_name="scottbrian_throttle.throttle",
                        level=logging.DEBUG,
                        pattern=log_msg,
                    )
                else:
                    assert a_throttle.async_q.empty()

                issue_remaining_requests_log_entry(throttle=a_throttle, log_ver=log_ver)

            final_shutdown_and_verification(
                throttle=a_throttle,
                req_time=a_req_time,
                log_ver=log_ver,
                ret_code=ret_code,
                caplog=caplog,
            )

        finally:
            a_throttle.start_shutdown(ThrottleShutdownType.HARD)

    ####################################################################
    # test_throttle_shutdown
    ####################################################################
    @pytest.mark.parametrize("reqs_per_sec_arg", (1, 2, 3))
    @pytest.mark.parametrize("timeout1_arg", (True, False))
    @etrace(omit_parms="caplog", omit_caller=True, log_ver=True)
    def test_throttle_soft_shutdown_terminated_by_hard(
        self,
        reqs_per_sec_arg: int,
        timeout1_arg: bool,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """Method to test shutdown scenarios.

        Args:
            reqs_per_sec_arg: how many requests per second
            timeout1_arg: whether to issue timeout
            caplog: pytest fixture to capture log output

        """
        num_reqs_to_make = 100
        sleep_reqs_to_do = 10

        log_ver = self.log_ver
        alpha_call_seq = (
            "test_throttle.py::TestThrottleShutdown"
            ".test_throttle_hard_shutdown_timeout"
        )
        log_ver.add_call_seq(name="alpha", seq=alpha_call_seq)

        a_throttle, interval = get_async_throttle(
            reqs_per_sec=reqs_per_sec_arg,
            name="soft hard",
            async_q_size=num_reqs_to_make,
        )
        log_ver.test_msg(f"{num_reqs_to_make=}, {sleep_reqs_to_do=}, {interval=}")

        def soft_shutdown(timeout_tf: bool) -> None:
            """Do soft shutdown.

            Args:
                timeout_tf: whether to issue timeout
            """
            if timeout_tf:
                rc = a_throttle.start_shutdown(
                    shutdown_type=ThrottleShutdownType.SOFT,
                    timeout=max_timeout_seconds,
                )
            else:
                rc = a_throttle.start_shutdown(shutdown_type=ThrottleShutdownType.SOFT)

            log_ver.test_msg(f"soft shutdown {rc=} with {timeout_tf=}")
            assert rc == Throttle.RC_SHUTDOWN_HARD_COMPLETED_OK

        soft_shutdown_thread = threading.Thread(
            target=soft_shutdown, args=(timeout1_arg,)
        )

        ################################################################
        # calculate timeout times
        ################################################################
        timeout_seconds = a_throttle.get_completion_time_secs(
            sleep_reqs_to_do, from_start=False
        )
        log_ver.test_msg(f"{timeout_seconds=}")

        max_timeout_seconds = (
            a_throttle.get_completion_time_secs(num_reqs_to_make, from_start=False) + 60
        )

        ################################################################
        # We need a try/finally to make sure we can shut down the
        # throttle in the event that an assertion fails. In an earlier
        # version of this code before adding the try/finally, there were
        # test cases failing and leaving the throttle active with its
        # requests showing up in the next test case logs.
        ################################################################
        try:
            start_time, a_req_time = queue_first_batch_requests(
                throttle=a_throttle,
                num_reqs=num_reqs_to_make,
                num_sleep_reqs=sleep_reqs_to_do,
                log_ver=log_ver,
            )

            # get the soft shutdown started

            log_ver.test_msg("about to do soft shutdown")
            soft_shutdown_thread.start()

            # calculate sleep_time to allow shutdown of some requests

            sleep_time = timeout_seconds - (time.time() - a_req_time.f_time)
            time.sleep(sleep_time)

            exp_reqs_done = sleep_reqs_to_do * 2
            assert abs(a_req_time.num_reqs - exp_reqs_done) <= 1

            # issue hard shutdown to terminate the soft shutdown

            log_ver.test_msg("about to do hard shutdown")

            # we expect to get the soft shutdown terminated log msg
            log_ver.test_msg(
                "Hard shutdown request now replacing previously "
                "started soft shutdown."
            )
            ret_code = a_throttle.start_shutdown(
                shutdown_type=ThrottleShutdownType.HARD
            )
            assert ret_code == Throttle.RC_SHUTDOWN_HARD_COMPLETED_OK
            assert abs(a_req_time.num_reqs - exp_reqs_done) <= 1

            # wait for the soft_shutdown thread to end
            soft_shutdown_thread.join()

            final_shutdown_and_verification(
                throttle=a_throttle,
                req_time=a_req_time,
                log_ver=log_ver,
                ret_code=ret_code,
                caplog=caplog,
            )

        finally:
            a_throttle.start_shutdown(ThrottleShutdownType.HARD)

    ####################################################################
    # test_shutdown_throttle_funcs
    ####################################################################
    @pytest.mark.parametrize("sleep2_delay_arg", (0.3, 1.1))
    @pytest.mark.parametrize("num_shutdown1_funcs_arg", (0, 1, 2, 3, 4))
    @pytest.mark.parametrize("f1_num_reqs_arg", (0, 16, 32))
    @pytest.mark.parametrize("f2_num_reqs_arg", (0, 16, 32))
    @pytest.mark.parametrize("f3_num_reqs_arg", (0, 16, 32))
    @pytest.mark.parametrize("f4_num_reqs_arg", (0, 16, 32))
    @etrace(omit_parms="caplog", omit_caller=True, log_ver=True)
    def test_shutdown_throttle_funcs(
        self,
        sleep2_delay_arg: float,
        num_shutdown1_funcs_arg: int,
        f1_num_reqs_arg: int,
        f2_num_reqs_arg: int,
        f3_num_reqs_arg: int,
        f4_num_reqs_arg: int,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """Test shutdown processing for pie throttles using function.

        Args:
            sleep2_delay_arg: percentage of reqs to sleep before
                                shutdown
            num_shutdown1_funcs_arg: number of funcs in first shutdown
            f1_num_reqs_arg: number of reqs to make
            f2_num_reqs_arg: number of reqs to make
            f3_num_reqs_arg: number of reqs to make
            f4_num_reqs_arg: number of reqs to make

        """
        log_ver = self.log_ver
        alpha_call_seq = (
            "test_throttle.py::TestThrottleShutdown.test_shutdown_throttle_funcs"
        )
        log_ver.add_call_seq(name="alpha", seq=alpha_call_seq)

        ################################################################
        # f1
        ################################################################
        f1_reqs = 1
        f2_reqs = 5
        f3_reqs = 2
        f4_reqs = 4

        @throttle(
            reqs_per_sec=f1_reqs, throttle_mode=ThrottleMode.ASYNC, name="my_best_f1"
        )
        def f1(req_time: ReqTime) -> None:
            issue_shutdown_log_entry(func_name="f1", req_time=req_time, log_ver=log_ver)

        ################################################################
        # f2
        ################################################################
        @throttle(reqs_per_sec=f2_reqs, throttle_mode=ThrottleMode.ASYNC)
        def f2(req_time: ReqTime) -> None:
            issue_shutdown_log_entry(func_name="f2", req_time=req_time, log_ver=log_ver)

        ################################################################
        # f3
        ################################################################
        @throttle(reqs_per_sec=f3_reqs, throttle_mode=ThrottleMode.ASYNC)
        def f3(req_time: ReqTime) -> None:
            issue_shutdown_log_entry(func_name="f3", req_time=req_time, log_ver=log_ver)

        ################################################################
        # f4
        ################################################################
        @throttle(reqs_per_sec=f4_reqs, throttle_mode=ThrottleMode.ASYNC)
        def f4(req_time: ReqTime) -> None:
            issue_shutdown_log_entry(func_name="f4", req_time=req_time, log_ver=log_ver)

        start_time = time.time()
        f1_req_time = ReqTime(
            num_reqs=0,
            f_time=start_time,
            start_time=start_time,
            interval=f1.throttle.get_interval_secs(),
        )
        f2_req_time = ReqTime(
            num_reqs=0,
            f_time=start_time,
            start_time=start_time,
            interval=f2.throttle.get_interval_secs(),
        )
        f3_req_time = ReqTime(
            num_reqs=0,
            f_time=start_time,
            start_time=start_time,
            interval=f3.throttle.get_interval_secs(),
        )
        f4_req_time = ReqTime(
            num_reqs=0,
            f_time=start_time,
            start_time=start_time,
            interval=f4.throttle.get_interval_secs(),
        )

        interval = 1 / stats.mean([1, 2, 3, 4, 5])

        num_reqs_to_make = [
            f1_num_reqs_arg,
            f2_num_reqs_arg,
            f3_num_reqs_arg,
            f4_num_reqs_arg,
        ]
        mean_reqs_to_make = stats.mean(num_reqs_to_make)

        if 0 <= mean_reqs_to_make <= 22:
            shutdown1_type_arg = None
        elif 22 <= mean_reqs_to_make <= 43:
            shutdown1_type_arg = ThrottleShutdownType.SOFT
        else:
            shutdown1_type_arg = ThrottleShutdownType.HARD

        log_ver.test_msg(f"{mean_reqs_to_make=}, {shutdown1_type_arg=}")

        f1_interval = 1 / f1_reqs
        f2_interval = 1 / f2_reqs
        f3_interval = 1 / f3_reqs

        f1_exp_elapsed_seconds = f1_interval * f1_num_reqs_arg
        f2_exp_elapsed_seconds = f2_interval * f2_num_reqs_arg
        f3_exp_elapsed_seconds = f3_interval * f3_num_reqs_arg

        timeout_arg = None
        if (
            (shutdown1_type_arg != ThrottleShutdownType.HARD)
            and (num_shutdown1_funcs_arg == 2)
            and (f1_num_reqs_arg > 0)
            and (f2_num_reqs_arg > 0)
        ):
            timeout_arg = min(f1_exp_elapsed_seconds, f2_exp_elapsed_seconds) / 2
        elif (
            (shutdown1_type_arg != ThrottleShutdownType.HARD)
            and (num_shutdown1_funcs_arg == 3)
            and (f1_num_reqs_arg > 0)
            and (f2_num_reqs_arg > 0)
            and (f3_num_reqs_arg > 0)
        ):
            timeout_arg = (
                min(
                    f1_exp_elapsed_seconds,
                    f2_exp_elapsed_seconds,
                    f3_exp_elapsed_seconds,
                )
                / 2
            )

        if timeout_arg:
            sleep_time: IntFloat = 0
        else:
            sleep_time = mean_reqs_to_make * sleep2_delay_arg * interval

        log_ver.test_msg(f"{timeout_arg=}, {sleep_time=}")

        funcs_to_shutdown = list([f1, f2, f3, f4][0:num_shutdown1_funcs_arg])
        log_ver.test_msg(f"{funcs_to_shutdown=}")
        ################################################################
        # start the requests
        ################################################################
        timeout_start_time = time.time()
        for i in range(f1_num_reqs_arg):
            assert Throttle.RC_OK == f1(f1_req_time)

        for i in range(f2_num_reqs_arg):
            assert Throttle.RC_OK == f2(f2_req_time)

        for i in range(f3_num_reqs_arg):
            assert Throttle.RC_OK == f3(f3_req_time)

        for i in range(f4_num_reqs_arg):
            assert Throttle.RC_OK == f4(f4_req_time)

        ################################################################
        # allow some requests to be made
        ################################################################
        time.sleep(sleep_time)

        ################################################################
        # start shutdowns supress
        ################################################################
        if shutdown1_type_arg:
            if timeout_arg:
                log_ver.test_msg(
                    f"1 about to shutdown with: "
                    f"{shutdown1_type_arg=}, "
                    f"{timeout_arg=}, "
                    f"{funcs_to_shutdown=}, "
                    f"{len(funcs_to_shutdown)=} "
                )
                ret_code = shutdown_throttle_funcs(
                    *funcs_to_shutdown,
                    shutdown_type=shutdown1_type_arg,
                    timeout=timeout_arg,
                )
                log_ver.test_msg(f"1 {ret_code=}")
            else:
                log_ver.test_msg(
                    f"2 about to shutdown with: "
                    f"{shutdown1_type_arg=}, "
                    f"{timeout_arg=}, "
                    f"{funcs_to_shutdown=}, "
                    f"{len(funcs_to_shutdown)=} "
                )
                ret_code = shutdown_throttle_funcs(
                    *funcs_to_shutdown, shutdown_type=shutdown1_type_arg
                )
                log_ver.test_msg(f"2 {ret_code=}")
        else:
            if timeout_arg:
                log_ver.test_msg(
                    f"3 about to shutdown with: "
                    f"{shutdown1_type_arg=}, "
                    f"{timeout_arg=}, "
                    f"{funcs_to_shutdown=}, "
                    f"{len(funcs_to_shutdown)=} "
                )
                ret_code = shutdown_throttle_funcs(
                    *funcs_to_shutdown, timeout=timeout_arg
                )
                log_ver.test_msg(f"3 {ret_code=}")
            else:
                log_ver.test_msg(
                    f"4 about to shutdown with: "
                    f"{shutdown1_type_arg=}, "
                    f"{timeout_arg=}, "
                    f"{funcs_to_shutdown=}, "
                    f"{len(funcs_to_shutdown)=} "
                )
                ret_code = shutdown_throttle_funcs(*funcs_to_shutdown)
                log_ver.test_msg(f"4 {ret_code=}")

        log_ver.test_msg(f"x {ret_code=}")
        if not funcs_to_shutdown:
            assert ret_code is True
        else:
            if timeout_arg:
                assert ret_code is False
                assert (
                    timeout_arg <= time.time() - timeout_start_time <= timeout_arg + 1
                )
            else:
                assert ret_code is True

        funcs_shutdown_complete_msg_added: list[
            FuncWithThrottleAttr[Callable[..., Any]]
        ] = []
        for func in funcs_to_shutdown:
            if func.throttle.shutdown_elapsed_time == 0.0:
                timeout = timeout_arg
                log_msg = (
                    f"Throttle {func.throttle.t_name} "
                    f"shutdown_throttle_funcs request timed out with "
                    f"{timeout=:.4f}"
                )
                log_level = logging.DEBUG
            else:
                funcs_shutdown_complete_msg_added.append(func)
                log_msg = (
                    f"throttle {func.throttle.t_name} start_shutdown request "
                    "successfully completed in "
                    f"{func.throttle.shutdown_elapsed_time:.4f} seconds"
                )
                log_level = logging.INFO

            log_ver.add_pattern(
                log_name="scottbrian_throttle.throttle",
                level=log_level,
                pattern=log_msg,
            )

        if shutdown1_type_arg:
            log_ver.test_msg(
                f"5 about to shutdown with: "
                f"{shutdown1_type_arg=}, "
                f"{timeout_arg=}, "
                f"{funcs_to_shutdown=}, "
                f"{len(funcs_to_shutdown)=} "
            )
            assert shutdown_throttle_funcs(
                f1, f2, f3, f4, shutdown_type=shutdown1_type_arg
            )
            # expect success log msg only once for the hard shutdown

        else:
            log_ver.test_msg(
                f"6 about to shutdown with: "
                f"{shutdown1_type_arg=}, "
                f"{timeout_arg=}, "
                f"{funcs_to_shutdown=}, "
                f"{len(funcs_to_shutdown)=} "
            )
            assert shutdown_throttle_funcs(f1, f2, f3, f4)

        for a_func in (f1, f2, f3, f4):
            if a_func not in funcs_shutdown_complete_msg_added:
                log_msg = (
                    f"throttle {a_func.throttle.t_name} start_shutdown "
                    "request successfully completed in "
                    f"{a_func.throttle.shutdown_elapsed_time:.4f} "
                    "seconds"
                )
                log_ver.add_pattern(
                    log_name="scottbrian_throttle.throttle",
                    level=logging.INFO,
                    pattern=log_msg,
                )

        ################################################################
        # verify all funcs are shutdown
        ################################################################
        ################################################################
        # the following requests should get rejected
        ################################################################
        assert Throttle.RC_THROTTLE_IS_SHUTDOWN == f1(f1_req_time)
        assert Throttle.RC_THROTTLE_IS_SHUTDOWN == f2(f2_req_time)
        assert Throttle.RC_THROTTLE_IS_SHUTDOWN == f3(f3_req_time)
        assert Throttle.RC_THROTTLE_IS_SHUTDOWN == f4(f4_req_time)
        # assert Throttle.RC_THROTTLE_IS_SHUTDOWN == f5(f5_req_time)

        assert f1.throttle.async_q
        assert f1.throttle.async_q.empty()

        assert f2.throttle.async_q
        assert f2.throttle.async_q.empty()

        assert f3.throttle.async_q
        assert f3.throttle.async_q.empty()

        assert f4.throttle.async_q
        assert f4.throttle.async_q.empty()
        # assert f5.throttle.async_q.empty()

        assert f1.throttle.request_scheduler_thread
        assert not f1.throttle.request_scheduler_thread.is_alive()

        assert f2.throttle.request_scheduler_thread
        assert not f2.throttle.request_scheduler_thread.is_alive()

        assert f3.throttle.request_scheduler_thread
        assert not f3.throttle.request_scheduler_thread.is_alive()

        assert f4.throttle.request_scheduler_thread
        assert not f4.throttle.request_scheduler_thread.is_alive()
        # assert not f5.throttle.request_scheduler_thread.is_alive()

        ################################################################
        # verify the log messages
        ################################################################
        match_results = log_ver.get_match_results(caplog=caplog)
        log_ver.print_match_results(match_results, print_matched=True)
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
        reqs_per_sec: IntFloat,
        throttle_mode: ThrottleMode,
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
        assert ratio_delay_time <= 0.05

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

        hdr_str = (
            ":Example 1: instantiate a synchronous throttle at 2 requests per second:"
        )
        flowers(hdr_str)

        from scottbrian_throttle.throttle import Throttle

        throttle = Throttle(reqs_per_sec=2)
        print(f"{throttle.get_interval_secs()}")

        flower_str = ("*" * (len(hdr_str) + 4)) + "\n"
        expected_result = "\n" + flower_str
        expected_result += f"* {hdr_str} *\n"
        expected_result += flower_str
        expected_result += "0.5\n"

        captured = capsys.readouterr().out

        assert captured == expected_result

    ####################################################################
    # test_throttle_example_2
    ####################################################################
    def test_throttle_example_2(self, capfd: Any) -> None:
        """Method test_throttle_example_2.

        Args:
            capsys: pytest fixture to capture print output

        """

        hdr_str = ":Example 2: send requests through synchronous throttle:"
        flowers(hdr_str)

        from scottbrian_throttle.throttle import Throttle
        import time

        throttle = Throttle(reqs_per_sec=2)

        def target_rtn1(request_number: int, time_of_start: float) -> str:
            ret_value = (
                f"request {request_number} sent at elapsed time: "
                f"{time.time() - time_of_start:0.1f}"
            )
            return ret_value

        pauser = Pauser()
        pauser.pause(3)

        start_time = time.time()
        for i in range(10):
            ret_val = throttle.send_request(target_rtn1, i, start_time)
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

        # captured = capsys.readouterr().out
        captured = capfd.readouterr().out

        assert captured == expected_result

    ####################################################################
    # test_throttle_example_3
    ####################################################################
    def test_throttle_example_3(self, capfd: Any) -> None:
        """Method test_throttle_example_3.

        Args:
            capsys: pytest fixture to capture print output

        """

        hdr_str = ":Example 3: send requests through asynchronous throttle:"
        flowers(hdr_str)

        from scottbrian_throttle.throttle import Throttle
        import time

        async_throttle = Throttle(reqs_per_sec=2, throttle_mode=ThrottleMode.ASYNC)

        def target_rtn2(request_number: int, time_of_start: float) -> None:
            print(
                f"request {request_number} sent at elapsed time: "
                f"{time.time() - time_of_start:0.1f}"
            )

        start_time = time.time()
        for i in range(10):
            async_throttle.send_request(target_rtn2, i, start_time)
        # do other processing since not waiting for return from throttle
        # after other processing, do a shutdown of the throttle
        async_throttle.start_shutdown()

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

        # sys.stdout.flush()

        # captured = capsys.readouterr().out
        captured = capfd.readouterr().out

        assert captured == expected_result

    ####################################################################
    # test_throttle_example_4
    ####################################################################
    def test_throttle_example_4(self, capsys: Any) -> None:
        """Method test_throttle_example_4.

        Args:
            capsys: pytest fixture to capture print output

        """

        hdr_str = (
            ":Example 4: instantiate a leaky bucket throttle and send some requests:"
        )
        flowers(hdr_str)

        from scottbrian_throttle.throttle import Throttle
        import time

        lb_throttle = Throttle(reqs_per_sec=2, name="t1", bucket_size=3)

        def target_rtn3(request_number: int, time_of_start: float) -> None:
            print(
                f"request {request_number} sent at elapsed time: "
                f"{time.time() - time_of_start:0.1f}"
            )

        start_time = time.time()
        for i in range(10):
            lb_throttle.send_request(target_rtn3, i, start_time)

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
    # test_throttle_example_5
    ####################################################################
    def test_throttle_example_5(self, capsys: Any) -> None:
        """Method test_throttle_example_5.

        Args:
            capsys: pytest fixture to capture print output

        """
        hdr_str = ":Example 5: Wrapping a function with the **@throttle** decorator"
        flowers(hdr_str)

        from scottbrian_throttle.throttle import throttle
        import time

        @throttle(reqs_per_sec=2)
        def func1(request_number: int, time_of_start: float) -> None:
            print(
                f"request {request_number} sent at elapsed time: "
                f"{time.time() - time_of_start:0.1f}"
            )

        start_time = time.time()
        for i in range(10):
            func1(i, start_time)

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

        hdr_str = (
            ":Example 6: Wrapping a function with the **@throttle** decorator for async"
        )
        flowers(hdr_str)

        # from scottbrian_throttle.throttle import throttle
        # import time
        #
        # @throttle(reqs_per_sec=0.5, throttle_mode=ThrottleMode.ASYNC)
        # def func2(request_number: int, time_of_start: float) -> None:
        #     print(
        #         f"request {request_number} sent at elapsed time: "
        #         f"{time.time() - time_of_start:0.1f}"
        #     )
        #
        # Pauser().pause(3)
        # start_time = time.time()
        # for i in range(10):
        #     func2(i, start_time)
        # # do other processing since not waiting for return from throttle
        # # after other processing, do a shutdown of the throttle
        # func2.throttle.start_shutdown()

        from scottbrian_throttle.throttle import throttle, ThrottleMode
        import time

        @throttle(reqs_per_sec=0.5, throttle_mode=ThrottleMode.ASYNC)
        def func2(request_number, time_of_start):
            print(
                f"request {request_number} sent at elapsed time: "
                f"{time.time() - time_of_start:0.1f}"
            )

        start_time = time.time()
        for i in range(10):
            func2(i, start_time)
        func2.throttle.start_shutdown()

        flower_str = ("*" * (len(hdr_str) + 4)) + "\n"

        expected_result = "\n" + flower_str
        expected_result += f"* {hdr_str} *\n"
        expected_result += flower_str
        expected_result += "request 0 sent at elapsed time: 0.0\n"
        expected_result += "request 1 sent at elapsed time: 2.0\n"
        expected_result += "request 2 sent at elapsed time: 4.0\n"
        expected_result += "request 3 sent at elapsed time: 6.0\n"
        expected_result += "request 4 sent at elapsed time: 8.0\n"
        expected_result += "request 5 sent at elapsed time: 10.0\n"
        expected_result += "request 6 sent at elapsed time: 12.0\n"
        expected_result += "request 7 sent at elapsed time: 14.0\n"
        expected_result += "request 8 sent at elapsed time: 16.0\n"
        expected_result += "request 9 sent at elapsed time: 18.0\n"

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

        hdr_str = (
            ":Example 7: Wrapping a function with the **@throttle** decorator for "
            "async with leaky bucket"
        )
        flowers(hdr_str)

        from scottbrian_throttle.throttle import throttle
        import time

        @throttle(reqs_per_sec=0.75, bucket_size=5, throttle_mode=ThrottleMode.ASYNC)
        def func3(request_number: int, time_of_start: float) -> None:
            print(
                f"request {request_number} sent at elapsed time: "
                f"{time.time() - time_of_start:0.1f}"
            )

        start_time = time.time()
        for i in range(10):
            func3(i, start_time)
        # do other processing since not waiting for return from throttle
        # after other processing, do a shutdown of the throttle
        func3.throttle.start_shutdown()

        flower_str = ("*" * (len(hdr_str) + 4)) + "\n"

        expected_result = "\n" + flower_str
        expected_result += f"* {hdr_str} *\n"
        expected_result += flower_str
        expected_result += "request 0 sent at elapsed time: 0.0\n"
        expected_result += "request 1 sent at elapsed time: 0.0\n"
        expected_result += "request 2 sent at elapsed time: 0.0\n"
        expected_result += "request 3 sent at elapsed time: 0.0\n"
        expected_result += "request 4 sent at elapsed time: 0.0\n"
        expected_result += "request 5 sent at elapsed time: 1.3\n"
        expected_result += "request 6 sent at elapsed time: 2.7\n"
        expected_result += "request 7 sent at elapsed time: 4.0\n"
        expected_result += "request 8 sent at elapsed time: 5.3\n"
        expected_result += "request 9 sent at elapsed time: 6.7\n"

        captured = capsys.readouterr().out

        assert captured == expected_result

    ####################################################################
    # test_throttle_example_8
    ####################################################################
    def test_throttle_example_8(self, capsys: Any) -> None:
        """Method test_throttle_example_8.

        Args:
            capsys: pytest fixture to capture print output

        """

        hdr_str = ":Example 8: instantiate a throttle for 1 requests every 2 seconds "
        flowers(hdr_str)

        from scottbrian_throttle.throttle import Throttle

        request_throttle = Throttle(reqs_per_sec=0.5)
        repr(request_throttle)

        flower_str = ("*" * (len(hdr_str) + 4)) + "\n"

        expected_result = "\n" + flower_str
        expected_result += f"* {hdr_str} *\n"
        expected_result += flower_str

        captured = capsys.readouterr().out

        assert captured == expected_result

    ####################################################################
    # test_throttle_example_9
    ####################################################################
    def test_throttle_example_9(self, capsys: Any) -> None:
        """Method test_throttle_example_9.

        Args:
            capsys: pytest fixture to capture print output

        """

        hdr_str = (
            ":Example 9: instantiate an asynchronous throttle for 1 request per second"
        )
        flowers(hdr_str)

        from scottbrian_throttle.throttle import Throttle
        import time

        def my_request(idx: int) -> None:
            pass

        request_throttle = Throttle(reqs_per_sec=1, throttle_mode=ThrottleMode.ASYNC)
        for idx in range(3):  # quickly queue up 3 items
            _ = request_throttle.send_request(my_request, idx)
        time.sleep(0.5)  # allow first two requests to be dequeued
        num_on_q = len(request_throttle)
        print(f"{num_on_q=}")

        request_throttle.start_shutdown()

        flower_str = ("*" * (len(hdr_str) + 4)) + "\n"

        expected_result = "\n" + flower_str
        expected_result += f"* {hdr_str} *\n"
        expected_result += flower_str
        expected_result += "num_on_q=1\n"

        captured = capsys.readouterr().out

        assert captured == expected_result

    ####################################################################
    # test_throttle_readme_example_1
    ####################################################################
    def test_throttle_readme_example_1(self, capsys: Any) -> None:
        """Method test_throttle_readme_example_1.

        Args:
            capsys: pytest fixture to capture print output

        """

        hdr_str = ":README example 1:"
        flowers(hdr_str)

        from scottbrian_throttle.throttle import throttle
        import time

        @throttle(reqs_per_sec=2)
        def make_request(request_number: int, time_of_start: float) -> None:
            print(
                f"request {request_number} sent at elapsed time: "
                f"{time.time() - time_of_start:0.1f}"
            )

        start_time = time.time()
        for i in range(10):
            make_request(i, start_time)

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

        captured = capsys.readouterr().out

        assert captured == expected_result

    ####################################################################
    # test_throttle_readme_example_2
    ####################################################################
    def test_throttle_readme_example_2(self, capsys: Any) -> None:
        """Method test_throttle_readme_example_2.

        Args:
            capsys: pytest fixture to capture print output

        """

        hdr_str = ":README example 2:"
        flowers(hdr_str)

        from scottbrian_throttle.throttle import Throttle
        import time

        def make_request(request_number: int, time_of_start: float) -> None:
            print(
                f"request {request_number} sent at elapsed time: "
                f"{time.time() - time_of_start:0.1f}"
            )

        a_throttle = Throttle(reqs_per_sec=2)
        start_time = time.time()
        for i in range(10):
            a_throttle.send_request(make_request, i, start_time)

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

        captured = capsys.readouterr().out

        assert captured == expected_result
