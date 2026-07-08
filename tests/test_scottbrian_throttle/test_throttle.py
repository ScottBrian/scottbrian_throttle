"""test_throttle.py module."""

import itertools as it
# from itertools import accumulate
import logging
import math
import os
import random
import statistics as stats
import threading
import time
########################################################################
# Standard Library
########################################################################
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
    shutdown_throttle_funcs,
    ThrottleMode,
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


class InvalidModeNum(ErrorTstThrottle):
    """InvalidModeNum exception class."""

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
    """ReqTime class for number of completed requests and last time."""

    req_id: int = 0
    create_time: float = 0.0  # also the start time
    throttle_mode: int = 0

    # send_interval set by sender when sending request
    send_interval: float = 0.0

    send_time_ns: float = 0.0  # after interval pause

    # arrival_idx is assigned by the req target code when entered
    arrival_idx: int = 0

    # throttle_arrival time obtained by req target from throttle
    # instance
    throttle_arrival_time: float = 0.0

    # actual_func_arrival_time_ns assigned by the req target code when entered
    expected_func_arrival_time_ns: float = 0.0
    actual_func_arrival_time_ns: float = 0.0

    throttle_next_target_time: float = 0.0

    throttle_wait_time_ns: float = 0.0

    # return_time set by sender when req returns
    return_time: float = 0.0

    actual_delay_ns: float = 0.0
    expected_delay_ns: float = 0.0


########################################################################
# RequestThreadItem used to track requests in a thread
########################################################################
@dataclass
class RequestThreadItem:
    """RequestThreadItem class to track requests for a thread."""

    thread_item: threading.Thread = None
    thread_item_idx: int = 0
    thread_create_time: float = 0.0
    num_reqs: int = 0
    send_intervals: list[float | int] = field(default_factory=list)


########################################################################
# mode_arg fixture
########################################################################
MODE_ASYNC: Final[int] = 1
MODE_SYNC: Final[int] = 2
MODE_SYNC_LB: Final[int] = 3


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
        # bad requests
        ################################################################
        with pytest.raises(IncorrectReqsPerSecSpecified):
            _ = Throttle(reqs_per_sec=0)
        with pytest.raises(IncorrectReqsPerSecSpecified):
            _ = Throttle(reqs_per_sec=-1)
        with pytest.raises(IncorrectReqsPerSecSpecified):
            _ = Throttle(reqs_per_sec="1")  # type: ignore

        ################################################################
        # bad async_q_size
        ################################################################
        with pytest.raises(IncorrectAsyncQSizeSpecified):
            _ = Throttle(
                reqs_per_sec=1, throttle_mode=ThrottleMode.ASYNC, async_q_size=-1
            )
        with pytest.raises(IncorrectAsyncQSizeSpecified):
            _ = Throttle(
                reqs_per_sec=1, throttle_mode=ThrottleMode.ASYNC, async_q_size=0
            )
        with pytest.raises(IncorrectAsyncQSizeSpecified):
            _ = Throttle(reqs_per_sec=1, throttle_mode=ThrottleMode.ASYNC, async_q_size="1")  # type: ignore

        ################################################################
        # invalid async_q_size
        ################################################################
        with pytest.raises(InvalidAsyncQSizeSpecified):
            _ = Throttle(reqs_per_sec=1, async_q_size=-1)
        with pytest.raises(InvalidAsyncQSizeSpecified):
            _ = Throttle(reqs_per_sec=1, async_q_size=1)
        with pytest.raises(InvalidAsyncQSizeSpecified):
            _ = Throttle(reqs_per_sec=1, async_q_size="1")  # type: ignore

        ################################################################
        # bad bucket_size
        ################################################################
        with pytest.raises(IncorrectBucketSizeSpecified):
            _ = Throttle(reqs_per_sec=1, bucket_size=-1)
        with pytest.raises(IncorrectBucketSizeSpecified):
            _ = Throttle(reqs_per_sec=1, bucket_size="1")  # type: ignore


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
    @pytest.mark.parametrize("num_reqs_to_send_arg", (1, 2, 3))
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

        def dummy_func(an_event: threading.Event) -> None:
            an_event.set()

        event = threading.Event()

        for i in range(num_reqs_to_send_arg):
            a_throttle.send_request(dummy_func, event)

        event.wait()
        # assert is for 1 less than queued because the first request
        # will be scheduled immediately
        assert len(a_throttle) == num_reqs_to_send_arg - 1
        # start_shutdown returns when request_q cleanup completes
        a_throttle.start_shutdown()
        assert len(a_throttle) == 0

        a_throttle.start_shutdown(shutdown_type=Throttle.TYPE_SHUTDOWN_HARD)

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
        """test_throttle repr with various requests and seconds.

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
            # not a valid combo to have throttle_mode=ThrottleMode.SYNC and async_q_size non-zero
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
            # not a valid combo to have throttle_mode=ThrottleMode.SYNC and async_q_size non-zero
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
            # not a valid combo to have throttle_mode=ThrottleMode.SYNC and async_q_size non-zero
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
            # not a valid combo to have throttle_mode=ThrottleMode.SYNC and async_q_size non-zero
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
                f"Throttle("
                f"reqs_per_sec=None, "
                f"bucket_size=None, "
                f"throttle_mode=None, "
                f"async_q_size=None, "
                f"name=None, "
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

        def f1(f1_idx: int, f1_count: MainlineCount) -> None:
            f1_count.count += 1
            logger.debug(f"{f1_idx=}, {f1_count.count=}")

        def f2() -> None:
            time.sleep(1)
            a_throttle.start_shutdown(timeout=0.001)

        a_throttle = Throttle(
            reqs_per_sec=0.3, throttle_mode=ThrottleMode.ASYNC, async_q_size=1
        )

        f2_thread = threading.Thread(target=f2)
        f2_thread.start()

        for idx in range(3):
            a_throttle.send_request(f1, idx, f1_count=ml_count)

        a_throttle.start_shutdown()

        logger.debug(f"mainline: {ml_count.count=}")

        assert ml_count.count < 3


########################################################################
# TestThrottleDecoratorErrors class
########################################################################
class TestThrottleDecoratorErrors:
    """TestThrottleDecoratorErrors class."""

    def test_pie_throttle_bad_args(self) -> None:
        """test_throttle using bad arguments."""
        ################################################################
        # bad requests
        ################################################################
        with pytest.raises(IncorrectReqsPerSecSpecified):

            @throttle(reqs_per_sec=0)
            def f1() -> None:
                print("42")

            f1()

        with pytest.raises(IncorrectReqsPerSecSpecified):

            @throttle(reqs_per_sec=-1)
            def f2() -> None:
                print("42")

            f2()

        with pytest.raises(IncorrectReqsPerSecSpecified):

            @throttle(reqs_per_sec="1")  # type: ignore
            def f3() -> None:
                print("42")

            f3()
        with pytest.raises(IncorrectReqsPerSecSpecified):

            @throttle(reqs_per_sec=0, throttle_mode=ThrottleMode.ASYNC)
            def f4() -> None:
                print("42")

            f4()

        with pytest.raises(IncorrectReqsPerSecSpecified):

            @throttle(reqs_per_sec=-1, throttle_mode=ThrottleMode.ASYNC)
            def f5() -> None:
                print("42")

            f5()

        with pytest.raises(IncorrectReqsPerSecSpecified):

            @throttle(reqs_per_sec="1", throttle_mode=ThrottleMode.ASYNC)  # type: ignore
            def f6() -> None:
                print("42")

            f6()

        ################################################################
        # bad async_q_size
        ################################################################
        with pytest.raises(IncorrectAsyncQSizeSpecified):

            @throttle(reqs_per_sec=1, throttle_mode=ThrottleMode.ASYNC, async_q_size=-1)
            def f7() -> None:
                print("42")

            f7()
        with pytest.raises(IncorrectAsyncQSizeSpecified):

            @throttle(reqs_per_sec=1, throttle_mode=ThrottleMode.ASYNC, async_q_size=0)
            def f8() -> None:
                print("42")

            f8()
        with pytest.raises(IncorrectAsyncQSizeSpecified):

            @throttle(reqs_per_sec=1, throttle_mode=ThrottleMode.ASYNC, async_q_size="1")  # type: ignore
            def f9() -> None:
                print("42")

            f9()

        ################################################################
        # bad bucket_size
        ################################################################
        with pytest.raises(IncorrectBucketSizeSpecified):

            @throttle(reqs_per_sec=1, bucket_size=-1)
            def f10() -> None:
                print("42")

            f10()
        with pytest.raises(IncorrectBucketSizeSpecified):

            @throttle(reqs_per_sec=1, bucket_size="1")  # type: ignore
            def f11() -> None:
                print("42")

            f11()


########################################################################
# TestThrottleDecoratorErrors class
########################################################################
class TestThrottleDecoratorRequestErrors:
    """TestThrottleDecoratorErrors class."""

    @pytest.mark.skip_thread_exc
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

            @throttle(reqs_per_sec=1, throttle_mode=ThrottleMode.ASYNC)
            def f1() -> None:
                ans = 42 / 0
                print(f"{ans=}")

            f1()

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
            "test_pie_throttle_request_errors:[0-9]+ is raising Exception: "
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
                level=logging.DEBUG,
                pattern=log_msg,
            )
            thread_exc.raise_exc_if_one()

        ################################################################
        # sync_lb request failure
        ################################################################
        log_msg = (
            "throttle f4 send_request unhandled exception in request: division by zero"
        )
        log_ver.add_pattern(
            log_name="scottbrian_throttle.throttle",
            level=logging.DEBUG,
            pattern=log_msg,
        )
        with pytest.raises(ZeroDivisionError):

            @throttle(reqs_per_sec=1, bucket_size=2)
            def f4() -> None:
                ans = 42 / 0
                print(f"{ans=}")

            f4()

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
                level=logging.DEBUG,
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
    correctly, and that all combinations are accepted by python.

    The non-decorator cases will be simpler, with the exception of
    doing some explicit calls to shutdown the throttle (which is not
    possible with the decorator style - for this, we can set the
    start_shutdown_event).

    The following keywords with various values and in all combinations
    are tested:
        requests - various increments
        seconds - various increments, both int and float
        throttle_enabled - true/false

    """

    ####################################################################
    # test_throttle_async_args_style
    ####################################################################
    @pytest.mark.parametrize("request_style_arg", (0, 1, 2, 3, 4, 5, 6))
    def test_throttle_async_args_style(self, request_style_arg: int) -> None:
        """Method to start throttle mode1 tests.

        Args:
            request_style_arg: chooses function args mix
        """
        send_interval = 0.0
        self.throttle_router(
            reqs_per_sec=1,
            seconds=1,
            mode=MODE_ASYNC,
            early_count=0,
            bucket_size=0,
            send_interval=send_interval,
            request_style=request_style_arg,
        )

    ####################################################################
    # test_throttle_async
    ####################################################################
    @pytest.mark.parametrize("reqs_per_sec_arg", (1, 2, 3))
    @pytest.mark.parametrize("seconds_arg", (0.3, 1, 2))
    @pytest.mark.parametrize("send_interval_mult_arg", (0.0, 0.9, 1.0, 1.1))
    def test_throttle_async(
        self,
        reqs_per_sec_arg: int,
        seconds_arg: IntFloat,
        send_interval_mult_arg: float,
    ) -> None:
        """Method to start throttle mode1 tests.

        Args:
            reqs_per_sec_arg: number of requests per interval from fixture
            seconds_arg: interval for number of requests from fixture
            send_interval_mult_arg: interval between each send of a
                                      request
        """
        send_interval = (seconds_arg / reqs_per_sec_arg) * send_interval_mult_arg
        self.throttle_router(
            reqs_per_sec=reqs_per_sec_arg,
            seconds=seconds_arg,
            mode=MODE_ASYNC,
            early_count=0,
            bucket_size=0,
            send_interval=send_interval,
            request_style=2,
        )

    ####################################################################
    # test_throttle_async
    ####################################################################
    @pytest.mark.parametrize("reqs_per_sec_arg", (1, 2, 3))
    @pytest.mark.parametrize("seconds_arg", (0.3, 1, 2))
    def test_throttle_multi_async(
        self,
        reqs_per_sec_arg: int,
        seconds_arg: IntFloat,
    ) -> None:
        """Method to start throttle multi tests.

        Args:
            reqs_per_sec_arg: number of requests per interval from fixture
            seconds_arg: interval for number of requests from fixture

        """
        send_interval = 0.0
        self.throttle_router(
            reqs_per_sec=reqs_per_sec_arg,
            seconds=seconds_arg,
            mode=MODE_ASYNC,
            early_count=0,
            bucket_size=0,
            send_interval=send_interval,
            request_style=1,
            num_threads=8,
        )

    ####################################################################
    # test_throttle_sync_args_style
    ####################################################################
    @pytest.mark.parametrize("request_style_arg", (0, 1, 2, 3, 4, 5, 6))
    def test_throttle_sync_args_style(self, request_style_arg: int) -> None:
        """Method to start throttle sync tests.

        Args:
            request_style_arg: chooses function args mix
        """
        send_interval = 0.2
        self.throttle_router(
            reqs_per_sec=2,
            seconds=1,
            mode=MODE_SYNC,
            early_count=0,
            bucket_size=0,
            send_interval=send_interval,
            request_style=request_style_arg,
        )

    ####################################################################
    # test_throttle_sync
    ####################################################################
    @pytest.mark.parametrize("reqs_per_sec_arg", (1, 2, 3))
    @pytest.mark.parametrize("seconds_arg", (0.3, 1, 2))
    @pytest.mark.parametrize("send_interval_mult_arg", (0.0, 0.9, 1.0, 1.1))
    def test_throttle_sync(
        self,
        reqs_per_sec_arg: int,
        seconds_arg: IntFloat,
        send_interval_mult_arg: float,
    ) -> None:
        """Method to start throttle sync tests.

        Args:
            reqs_per_sec_arg: number of requests per interval from fixture
            seconds_arg: interval for number of requests from fixture
            send_interval_mult_arg: interval between each send of a
                                      request
        """
        send_interval = (seconds_arg / reqs_per_sec_arg) * send_interval_mult_arg
        self.throttle_router(
            reqs_per_sec=reqs_per_sec_arg,
            seconds=seconds_arg,
            mode=MODE_SYNC,
            early_count=0,
            bucket_size=0,
            send_interval=send_interval,
            request_style=3,
        )

    ####################################################################
    # test_throttle_async
    ####################################################################
    @pytest.mark.parametrize("reqs_per_sec_arg", (1, 2, 3))
    @pytest.mark.parametrize("seconds_arg", (0.3, 1, 2))
    def test_throttle_multi_sync(
        self,
        reqs_per_sec_arg: int,
        seconds_arg: IntFloat,
    ) -> None:
        """Method to start throttle multi tests.

        Args:
            reqs_per_sec_arg: number of requests per interval from fixture
            seconds_arg: interval for number of requests from fixture

        """
        send_interval = 0.0
        self.throttle_router(
            reqs_per_sec=reqs_per_sec_arg,
            seconds=seconds_arg,
            mode=MODE_SYNC,
            early_count=0,
            bucket_size=0,
            send_interval=send_interval,
            request_style=1,
            num_threads=8,
        )

    ####################################################################
    # test_throttle_sync_ec
    ####################################################################
    @pytest.mark.parametrize("request_style_arg", (0, 1, 2, 3, 4, 5, 6))
    def test_throttle_sync_ec_args_style(self, request_style_arg: int) -> None:
        """Method to start throttle sync_ec tests.

        Args:
            request_style_arg: chooses function args mix

        """
        send_interval = 0.4
        self.throttle_sync_ec_router(
            reqs_per_sec=3,
            seconds=1,
            mode=MODE_SYNC_EC,
            early_count=1,
            bucket_size=0,
            send_interval=send_interval,
            request_style=request_style_arg,
        )

    ####################################################################
    # test_throttle_sync_ec
    ####################################################################
    @pytest.mark.parametrize("reqs_per_sec_arg", (1, 2, 3))
    @pytest.mark.parametrize("seconds_arg", (0.3, 1, 2))
    @pytest.mark.parametrize("early_count_arg", (1, 2, 3))
    @pytest.mark.parametrize("send_interval_mult_arg", (0.0, 0.9, 1.0, 1.1))
    def test_throttle_sync_ec(
        self,
        reqs_per_sec_arg: int,
        seconds_arg: IntFloat,
        early_count_arg: int,
        send_interval_mult_arg: float,
    ) -> None:
        """Method to start throttle sync_ec tests.

        Args:
            reqs_per_sec_arg: number of requests per interval from fixture
            seconds_arg: interval for number of requests from fixture
            early_count_arg: count used for sync with early count algo
            send_interval_mult_arg: interval between each send of a
                                      request
        """
        send_interval = (seconds_arg / reqs_per_sec_arg) * send_interval_mult_arg
        self.throttle_sync_ec_router(
            reqs_per_sec=reqs_per_sec_arg,
            seconds=seconds_arg,
            mode=MODE_SYNC_EC,
            early_count=early_count_arg,
            bucket_size=0,
            send_interval=send_interval,
            request_style=0,
        )

    ####################################################################
    # test_throttle_async
    ####################################################################
    @pytest.mark.parametrize("reqs_per_sec_arg", (1, 2, 3))
    @pytest.mark.parametrize("seconds_arg", (0.3, 1, 2))
    @pytest.mark.parametrize("early_count_arg", (1, 2, 3))
    def test_throttle_multi_sync_ec(
        self, reqs_per_sec_arg: int, seconds_arg: IntFloat, early_count_arg: int
    ) -> None:
        """Method to start throttle multi tests.

        Args:
            reqs_per_sec_arg: number of requests per interval from fixture
            seconds_arg: interval for number of requests from fixture
            early_count_arg: count used for sync with early count algo

        """
        send_interval = 0.0
        self.throttle_sync_ec_router(
            reqs_per_sec=reqs_per_sec_arg,
            seconds=seconds_arg,
            mode=MODE_SYNC_EC,
            early_count=early_count_arg,
            bucket_size=0,
            send_interval=send_interval,
            request_style=1,
            num_threads=8,
        )

    ####################################################################
    # test_throttle_sync_lb_args_style
    ####################################################################
    @pytest.mark.parametrize("request_style_arg", (0, 1, 2, 3, 4, 5, 6))
    def test_throttle_sync_lb_args_style(self, request_style_arg: int) -> None:
        """Method to start throttle sync_lb tests.

        Args:
            request_style_arg: chooses function args mix
        """
        send_interval = 0.5
        self.throttle_router(
            reqs_per_sec=4,
            seconds=1,
            mode=MODE_SYNC_LB,
            early_count=0,
            bucket_size=1,
            send_interval=send_interval,
            request_style=request_style_arg,
        )

    ####################################################################
    # test_throttle_sync_lb
    ####################################################################
    @pytest.mark.parametrize("reqs_per_sec_arg", (1, 2, 3))
    @pytest.mark.parametrize("seconds_arg", (0.3, 1, 2))
    @pytest.mark.parametrize("bucket_size_arg", (0.5, 1, 1.5, 3))
    @pytest.mark.parametrize("send_interval_mult_arg", (0.0, 0.9, 1.0, 1.1))
    def test_throttle_sync_lb(
        self,
        reqs_per_sec_arg: int,
        seconds_arg: IntFloat,
        bucket_size_arg: IntFloat,
        send_interval_mult_arg: float,
    ) -> None:
        """Method to start throttle sync_lb tests.

        Args:
            reqs_per_sec_arg: number of requests per interval from fixture
            seconds_arg: interval for number of requests from fixture
            bucket_size_arg: threshold used with sync leaky bucket algo
            send_interval_mult_arg: interval between each send of a
                                      request
        """
        send_interval = (seconds_arg / reqs_per_sec_arg) * send_interval_mult_arg
        self.throttle_router(
            reqs_per_sec=reqs_per_sec_arg,
            seconds=seconds_arg,
            mode=MODE_SYNC_LB,
            early_count=0,
            bucket_size=bucket_size_arg,
            send_interval=send_interval,
            request_style=6,
        )

    ####################################################################
    # test_throttle_multi_sync_lb
    ####################################################################
    @pytest.mark.parametrize("reqs_per_sec_arg", (1, 2, 3))
    @pytest.mark.parametrize("seconds_arg", (0.3, 1, 2))
    @pytest.mark.parametrize("bucket_size_arg", (1, 1.5, 3))
    def test_throttle_multi_sync_lb(
        self, reqs_per_sec_arg: int, seconds_arg: IntFloat, bucket_size_arg: int
    ) -> None:
        """Method to start throttle multi tests.

        Args:
            reqs_per_sec_arg: number of requests per interval from fixture
            seconds_arg: interval for number of requests from fixture
            bucket_size_arg: threshold used with sync leaky bucket algo

        """
        send_interval = 0.0
        self.throttle_router(
            reqs_per_sec=reqs_per_sec_arg,
            seconds=seconds_arg,
            mode=MODE_SYNC_LB,
            early_count=0,
            bucket_size=bucket_size_arg,
            send_interval=send_interval,
            request_style=1,
            num_threads=2,
        )

    ####################################################################
    # build_send_intervals
    ####################################################################
    @staticmethod
    def build_send_intervals(send_interval: float) -> tuple[int, list[float]]:
        """Build the list of send intervals.

        Args:
            send_interval: the interval between sends

        Returns:
            a list of send intervals

        """
        random.seed(send_interval)
        num_reqs_to_do = 16
        # if throttle_mode == MODE_SYNC_EC:
        #     num_reqs_to_do = ((((num_reqs_to_do + 1)
        #                         // early_count)
        #                        * early_count)
        #                       + 1)

        send_intervals = [0.0]
        for idx in range(1, num_reqs_to_do):
            if idx < (num_reqs_to_do // 2):
                send_intervals.append(send_interval)
            else:
                if send_interval == 0.0:
                    alt_send_interval = 0.0  # .5 * (random.random() * 2)
                else:
                    alt_send_interval = send_interval * (random.random() * 2)
                # if idx == 4:
                #     alt_send_interval = 0.015
                send_intervals.append(alt_send_interval)

        return num_reqs_to_do, send_intervals

    @staticmethod
    def build_send_intervals2(send_interval: float, num_reqs_to_do: int) -> list[float]:
        """Build the list of send intervals.

        Args:
            send_interval: the interval between sends

        Returns:
            a list of send intervals

        """
        random.seed(send_interval)

        # if throttle_mode == MODE_SYNC_EC:
        #     num_reqs_to_do = ((((num_reqs_to_do + 1)
        #                         // early_count)
        #                        * early_count)
        #                       + 1)

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
        requests: int,
        seconds: IntFloat,
        mode: int,
        early_count: int,
        bucket_size: IntFloat,
        send_interval: float,
        request_style: int,
        num_threads: int = 0,
    ) -> None:
        """Method test_throttle_router.

        Args:
            requests: number of requests per interval
            seconds: interval for number of requests
            mode: async or sync_EC or sync_LB
            early_count: count used for sync with early count algo
            bucket_size: threshold used with sync leaky bucket algo
            send_interval: interval between each send of a request
            request_style: chooses function args mix
            num_threads: number of threads to issue requests

        Raises:
            InvalidModeNum: The Mode must be 1, 2, 3, or 4

        """
        logger.debug(f"throttle_router entered")
        ################################################################
        # get send interval list
        ################################################################
        num_reqs_to_do = 16
        send_intervals = self.build_send_intervals2(send_interval, num_reqs_to_do)
        if num_threads > 1:
            num_reqs_to_do *= num_threads

        ##############################################################
        # Instantiate Throttle
        ##############################################################
        if mode == MODE_ASYNC:
            a_throttle = Throttle(
                reqs_per_sec=requests, seconds=seconds, async_q_size=num_reqs_to_do
            )
        elif mode == MODE_SYNC:
            a_throttle = ThrottleSync(reqs_per_sec=requests, seconds=seconds)
        elif mode == MODE_SYNC_EC:
            a_throttle = ThrottleSyncEc(
                reqs_per_sec=requests, seconds=seconds, early_count=early_count
            )
        elif mode == MODE_SYNC_LB:
            a_throttle = ThrottleSyncLb(
                reqs_per_sec=requests, seconds=seconds, bucket_size=bucket_size
            )
        else:
            raise InvalidModeNum("The Mode must be 1, 2, 3, or 4")

        ################################################################
        # Instantiate Request Validator
        ################################################################
        request_validator = RequestValidator(
            reqs_per_sec=requests,
            seconds=seconds,
            mode=mode,
            early_count=early_count,
            bucket_size=bucket_size,
            total_reqs_per_sec=num_reqs_to_do,
            send_interval=send_interval,
            send_intervals=send_intervals,
            t_throttle=a_throttle,
            num_threads=num_threads,
        )

        if num_threads == 0:
            logger.debug(f"throttle_router making requests")
            self.make_reqs2(request_validator, request_style)
            if mode == MODE_ASYNC:
                logger.debug(f"throttle_router doing throttle shutdown")
                a_throttle.start_shutdown(shutdown_type=Throttle.TYPE_SHUTDOWN_SOFT)
            logger.debug(f"throttle_router validating series")
            request_validator.validate_series2()  # validate for the series
        else:
            logger.debug(f"throttle_router creating threads")
            for t_num in range(num_threads):
                req_thread_item = RequestThreadItem(
                    thread_item_idx=t_num,
                    thread_create_time=perf_counter_ns(),
                    num_reqs=len(send_intervals),
                    send_intervals=send_intervals.copy(),
                )
                thread_item = threading.Thread(
                    target=self.make_multi_reqs2,
                    args=(request_validator, req_thread_item),
                )
                req_thread_item.thread_item = thread_item
                request_validator.thread_items.append(req_thread_item)

            logger.debug(f"throttle_router starting threads")
            for thread_item in request_validator.thread_items:
                thread_item.thread_item.start()

            logger.debug(f"throttle_router joining threads")
            for thread_item in request_validator.thread_items:
                thread_item.thread_item.join()

            if mode == MODE_ASYNC:
                logger.debug(f"throttle_router doing throttle shutdown")
                a_throttle.start_shutdown(shutdown_type=Throttle.TYPE_SHUTDOWN_SOFT)

            logger.debug(f"throttle_router validating series")
            request_validator.validate_series2()

        logger.debug(f"throttle_router exiting")

    ####################################################################
    # throttle_sync_router
    ####################################################################
    def throttle_sync_router(
        self,
        requests: int,
        seconds: IntFloat,
        mode: int,
        early_count: int,
        bucket_size: IntFloat,
        send_interval: float,
        request_style: int,
        num_threads: int = 0,
    ) -> None:
        """Method test_throttle_router.

        Args:
            requests: number of requests per interval
            seconds: interval for number of requests
            mode: async or sync_EC or sync_LB
            early_count: count used for sync with early count algo
            bucket_size: threshold used with sync leaky bucket algo
            send_interval: interval between each send of a request
            request_style: chooses function args mix
            num_threads: number of threads to issue requests

        """
        ################################################################
        # get send interval list
        ################################################################
        num_reqs_to_do, send_intervals = self.build_send_intervals(send_interval)
        if num_threads > 1:
            num_reqs_to_do *= num_threads
        ################################################################
        # Instantiate Throttle
        ################################################################
        a_throttle = ThrottleSync(reqs_per_sec=requests, seconds=seconds)

        ################################################################
        # Instantiate Request Validator
        ################################################################
        request_validator = RequestValidator(
            reqs_per_sec=requests,
            seconds=seconds,
            mode=mode,
            early_count=early_count,
            bucket_size=bucket_size,
            total_reqs_per_sec=num_reqs_to_do,
            send_interval=send_interval,
            send_intervals=send_intervals,
            t_throttle=a_throttle,
            num_threads=num_threads,
        )

        if num_threads == 0:
            self.make_reqs(request_validator, request_style)
            request_validator.validate_series()  # validate for the series
        else:
            mr_threads = []
            start_times_list: list[list[float]] = []
            for t_num in range(num_threads):
                start_times_list.append([])
                mr_threads.append(
                    threading.Thread(
                        target=self.make_multi_reqs,
                        args=(request_validator, start_times_list[t_num]),
                    )
                )
            for mr_thread in mr_threads:
                mr_thread.start()

            for mr_thread in mr_threads:
                mr_thread.join()

            for start_times in start_times_list:
                request_validator.start_times += start_times.copy()

            request_validator.start_times.sort()
            request_validator.validate_series()

    ####################################################################
    # throttle_sync_ec_router
    ####################################################################
    def throttle_sync_ec_router(
        self,
        requests: int,
        seconds: IntFloat,
        mode: int,
        early_count: int,
        bucket_size: IntFloat,
        send_interval: float,
        request_style: int,
        num_threads: int = 0,
    ) -> None:
        """Method test_throttle_router.

        Args:
            requests: number of requests per interval
            seconds: interval for number of requests
            mode: async or sync_EC or sync_LB
            early_count: count used for sync with early count algo
            bucket_size: threshold used with sync leaky bucket algo
            send_interval: interval between each send of a request
            request_style: chooses function args mix
            num_threads: number of threads to issue requests

        """
        ################################################################
        # get send interval list
        ################################################################
        num_reqs_to_do, send_intervals = self.build_send_intervals(send_interval)
        if num_threads > 1:
            num_reqs_to_do *= num_threads
        ################################################################
        # Instantiate Throttle
        ################################################################
        a_throttle = ThrottleSyncEc(
            reqs_per_sec=requests, seconds=seconds, early_count=early_count
        )

        ################################################################
        # Instantiate Request Validator
        ################################################################
        request_validator = RequestValidator(
            reqs_per_sec=requests,
            seconds=seconds,
            mode=mode,
            early_count=early_count,
            bucket_size=bucket_size,
            total_reqs_per_sec=num_reqs_to_do,
            send_interval=send_interval,
            send_intervals=send_intervals,
            t_throttle=a_throttle,
            num_threads=num_threads,
        )

        if num_threads == 0:
            self.make_reqs(request_validator, request_style)
            request_validator.validate_series()  # validate for the series
        else:
            mr_threads = []
            start_times_list: list[list[float]] = []
            for t_num in range(num_threads):
                start_times_list.append([])
                mr_threads.append(
                    threading.Thread(
                        target=self.make_multi_reqs,
                        args=(request_validator, start_times_list[t_num]),
                    )
                )
            for mr_thread in mr_threads:
                mr_thread.start()

            for mr_thread in mr_threads:
                mr_thread.join()

            for start_times in start_times_list:
                request_validator.start_times += start_times.copy()

            request_validator.start_times.sort()
            request_validator.validate_series()

    ####################################################################
    # throttle_sync_lb_router
    ####################################################################
    def throttle_sync_lb_router(
        self,
        requests: int,
        seconds: IntFloat,
        mode: int,
        early_count: int,
        bucket_size: IntFloat,
        send_interval: float,
        request_style: int,
        num_threads: int = 0,
    ) -> None:
        """Method test_throttle_router.

        Args:
            requests: number of requests per interval
            seconds: interval for number of requests
            mode: async or sync_EC or sync_LB
            early_count: count used for sync with early count algo
            bucket_size: threshold used with sync leaky bucket algo
            send_interval: interval between each send of a request
            request_style: chooses function args mix
            num_threads: number of threads to issue requests

        """
        logger.debug(f"throttle_sync_lb_router entered")
        ################################################################
        # get send interval list
        ################################################################
        num_reqs_to_do = 16
        send_intervals = self.build_send_intervals2(send_interval, num_reqs_to_do)
        if num_threads > 1:
            num_reqs_to_do *= num_threads
        ################################################################
        # Instantiate Throttle
        ################################################################
        a_throttle = ThrottleSyncLb(
            reqs_per_sec=requests, seconds=seconds, bucket_size=bucket_size
        )

        ################################################################
        # Instantiate Request Validator
        ################################################################
        request_validator = RequestValidator(
            reqs_per_sec=requests,
            seconds=seconds,
            mode=mode,
            early_count=early_count,
            bucket_size=bucket_size,
            total_reqs_per_sec=num_reqs_to_do,
            send_interval=send_interval,
            send_intervals=send_intervals,
            t_throttle=a_throttle,
            num_threads=num_threads,
        )

        if num_threads == 0:
            self.make_reqs2(request_validator, request_style)
            request_validator.validate_series2()  # validate for the series
        else:
            for t_num in range(num_threads):
                req_thread_item = RequestThreadItem(
                    thread_item_idx=t_num,
                    thread_create_time=perf_counter_ns(),
                    num_reqs=len(send_intervals),
                    send_intervals=send_intervals.copy(),
                )
                thread_item = threading.Thread(
                    target=self.make_multi_reqs2,
                    args=(request_validator, req_thread_item),
                )
                req_thread_item.thread_item = thread_item
                request_validator.thread_items.append(req_thread_item)

            logger.debug(f"throttle_sync_lb_router starting threads")
            for thread_item in request_validator.thread_items:
                thread_item.thread_item.start()

            logger.debug(f"throttle_sync_lb_router joining threads")
            for thread_item in request_validator.thread_items:
                thread_item.thread_item.join()

            logger.debug(f"throttle_sync_lb_router validating series")
            request_validator.validate_series2()
        logger.debug(f"throttle_sync_lb_router exiting")

    ####################################################################
    # throttle_async_router
    ####################################################################
    def throttle_async_router(
        self,
        requests: int,
        seconds: IntFloat,
        mode: int,
        early_count: int,
        bucket_size: IntFloat,
        send_interval: float,
        request_style: int,
        num_threads: int = 0,
    ) -> None:
        """Method test_throttle_router.

        Args:
            requests: number of requests per interval
            seconds: interval for number of requests
            mode: async or sync_EC or sync_LB
            early_count: count used for sync with early count algo
            bucket_size: threshold used with sync leaky bucket algo
            send_interval: interval between each send of a request
            request_style: chooses function args mix
            num_threads: number of threads to issue requests

        """
        ################################################################
        # get send interval list
        ################################################################
        num_reqs_to_do, send_intervals = self.build_send_intervals(send_interval)
        if num_threads > 1:
            num_reqs_to_do *= num_threads
        ################################################################
        # Instantiate Throttle
        ################################################################
        a_throttle = Throttle(
            reqs_per_sec=requests, seconds=seconds, async_q_size=num_reqs_to_do
        )

        ################################################################
        # Instantiate Request Validator
        ################################################################
        request_validator = RequestValidator(
            reqs_per_sec=requests,
            seconds=seconds,
            mode=mode,
            early_count=early_count,
            bucket_size=bucket_size,
            total_reqs_per_sec=num_reqs_to_do,
            send_interval=send_interval,
            send_intervals=send_intervals,
            t_throttle=a_throttle,
            num_threads=num_threads,
        )

        if num_threads == 0:
            self.make_reqs(request_validator, request_style)
            a_throttle.start_shutdown(shutdown_type=Throttle.TYPE_SHUTDOWN_SOFT)
            request_validator.validate_series()  # validate for the series
        else:
            mr_threads = []
            start_times_list: list[list[float]] = []
            for t_num in range(num_threads):
                start_times_list.append([])
                mr_threads.append(
                    threading.Thread(
                        target=self.make_multi_reqs,
                        args=(request_validator, start_times_list[t_num]),
                    )
                )
            for mr_thread in mr_threads:
                mr_thread.start()

            for mr_thread in mr_threads:
                mr_thread.join()

            a_throttle.start_shutdown(shutdown_type=Throttle.TYPE_SHUTDOWN_SOFT)

            for start_times in start_times_list:
                request_validator.start_times += start_times.copy()

            request_validator.start_times.sort()
            request_validator.validate_series()

    ####################################################################
    # make_multi_reqs
    ####################################################################
    @staticmethod
    def make_multi_reqs(
        request_validator: "RequestValidator", start_times: list[float]
    ) -> None:
        """Make the requests.

        Args:
            request_validator: the validator for the reqs
            start_times: list of times needed for validation

        """
        # pauser = Pauser()
        a_throttle = request_validator.t_throttle
        # throttle_mode = request_validator.throttle_mode

        for i, s_interval in enumerate(request_validator.send_intervals):
            # 0
            start_times.append(perf_counter_ns())
            # pauser.pause(s_interval)  # first one is 0.0
            # request_validator.before_req_times.append(perf_counter_ns())
            _ = a_throttle.send_request(request_validator.request0)
            # request_validator.after_req_times.append(perf_counter_ns())

    ####################################################################
    # make_reqs2
    ####################################################################
    @staticmethod
    def make_reqs2(request_validator: "RequestValidator", request_style: int) -> None:
        """Make the requests.

        Args:
            request_validator: the validator for the reqs
            request_style: determine the args to pass

        Raises:
            BadRequestStyleArg: The request style arg must be 0 to 6

        """

        pauser = Pauser()
        a_throttle = request_validator.t_throttle
        mode = request_validator.mode

        call_args: str

        if request_style == 0:
            call_args = "a_throttle.send_request(request_validator.request0b)"
        elif request_style == 1:
            call_args = "a_throttle.send_request(request_validator.request1b, idx)"
        elif request_style == 2:
            call_args = "a_throttle.send_request(request_validator.request2b, idx, request_validator.requests)"
        elif request_style == 3:
            call_args = "a_throttle.send_request(request_validator.request3b, idx=idx)"
        elif request_style == 4:
            call_args = "a_throttle.send_request(request_validator.request4b, idx=idx, seconds=request_validator.seconds)"
        elif request_style == 5:
            call_args = "a_throttle.send_request(request_validator.request5b, idx, interval=request_validator.send_interval,)"
        elif request_style == 6:
            call_args = (
                "a_throttle.send_request(request_validator.request6b, "
                "idx, "
                "request_validator.requests, "
                "seconds=request_validator.seconds, "
                "interval=request_validator.send_interval,)"
            )
        else:
            raise BadRequestStyleArg("The request style arg must be 0 to 6")

        for idx, s_interval in enumerate(request_validator.send_intervals):
            request_item = RequestItem(
                req_id=idx,
                create_time=perf_counter_ns(),
                throttle_mode=mode,
                send_interval=s_interval,
            )

            if s_interval > 0.0:
                pauser.pause(s_interval)
            request_item.send_time_ns = perf_counter_ns()
            request_validator.request_item.append(request_item)
            rc = eval(call_args)
            request_item.return_time = perf_counter_ns()
            exp_rc = idx if mode != MODE_ASYNC else Throttle.RC_OK
            assert rc == exp_rc

    ####################################################################
    # make_multi_reqs2
    ####################################################################
    @staticmethod
    def make_multi_reqs2(
        request_validator: "RequestValidator", request_thread_item: RequestThreadItem
    ) -> None:
        """Make the requests.

        Args:
            request_validator: the validator for the reqs
            request_thread_item: the request thread item

        """
        # logger.debug(
        #     f"making_multi_reqs entered for " f"{request_thread_item.thread_item_idx=}"
        # )
        pauser = Pauser()
        a_throttle = request_validator.t_throttle

        for idx, s_interval in enumerate(request_thread_item.send_intervals):
            request_item = RequestItem(
                req_id=idx,
                create_time=perf_counter_ns(),
                throttle_mode=request_validator.mode,
                send_interval=s_interval,
            )

            if s_interval > 0.0:
                pauser.pause(s_interval)
            request_item.send_time_ns = perf_counter_ns()
            # logger.debug(
            #     f"making_multi_reqs {request_thread_item.thread_item_idx=} "
            #     f"sending request {idx=} to throttle"
            # )
            _ = a_throttle.send_request(
                request_validator.request0c, request_item=request_item
            )
            # logger.debug(f"making_multi_reqs sending request to throttle")
            request_item.return_time = perf_counter_ns()
        # logger.debug(f"making_multi_reqs exiting")

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
        mode = request_validator.mode

        call_args: str

        if request_style == 0:
            call_args = "a_throttle.send_request(request_validator.request0)"
        elif request_style == 1:
            call_args = "a_throttle.send_request(request_validator.request1, i)"
        elif request_style == 2:
            call_args = "a_throttle.send_request(request_validator.request2, i, request_validator.requests)"
        elif request_style == 3:
            call_args = "a_throttle.send_request(request_validator.request3, idx=i)"
        elif request_style == 4:
            call_args = "a_throttle.send_request(request_validator.request4, idx=i, seconds=request_validator.seconds)"
        elif request_style == 5:
            call_args = "a_throttle.send_request(request_validator.request5, i, interval=request_validator.send_interval,)"
        elif request_style == 6:
            call_args = (
                "a_throttle.send_request(request_validator.request6, "
                "i, "
                "request_validator.requests, "
                "seconds=request_validator.seconds, "
                "interval=request_validator.send_interval,)"
            )
        else:
            raise BadRequestStyleArg("The request style arg must be 0 to 6")

        for i, s_interval in enumerate(request_validator.send_intervals):
            # 0
            request_validator.start_times.append(perf_counter_ns())
            pauser.pause(s_interval)  # first one is 0.0
            request_validator.before_req_times.append(perf_counter_ns())
            rc = eval(call_args)
            request_validator.after_req_times.append(perf_counter_ns())
            exp_rc = i if mode != MODE_ASYNC else Throttle.RC_OK
            assert rc == exp_rc

        # if request_style == 0:
        #     for i, s_interval in enumerate(request_validator.send_intervals):
        #         # 0
        #         request_validator.start_times.append(perf_counter_ns())
        #         pauser.pause(s_interval)  # first one is 0.0
        #         request_validator.before_req_times.append(perf_counter_ns())
        #         rc = a_throttle.send_request(request_validator.request0)
        #         # rc = eval(
        #         #     call_list[request_style_arg][0] + call_list[request_style_arg][1]
        #         # )
        #         request_validator.after_req_times.append(perf_counter_ns())
        #         exp_rc = i if throttle_mode != MODE_ASYNC else Throttle.RC_OK
        #         assert rc == exp_rc
        #
        # elif request_style == 1:
        #     for i, s_interval in enumerate(request_validator.send_intervals):
        #         # 1
        #         request_validator.start_times.append(perf_counter_ns())
        #         pauser.pause(s_interval)  # first one is 0.0
        #         request_validator.before_req_times.append(perf_counter_ns())
        #         rc = a_throttle.send_request(request_validator.request1, i)
        #         request_validator.after_req_times.append(perf_counter_ns())
        #         exp_rc = i if throttle_mode != MODE_ASYNC else Throttle.RC_OK
        #         assert rc == exp_rc
        #
        # elif request_style == 2:
        #     for i, s_interval in enumerate(request_validator.send_intervals):
        #         # 2
        #         request_validator.start_times.append(perf_counter_ns())
        #         # time_traces, stops_time = pauser.pause(s_interval)
        #         pauser.pause(s_interval)  # first
        #         # one is 0.0
        #         # request_validator.time_traces.append(time_traces)
        #         # request_validator.stop_times.append(stops_time)
        #         request_validator.before_req_times.append(perf_counter_ns())
        #         rc = a_throttle.send_request(
        #             request_validator.request2, i, request_validator.requests
        #         )
        #         request_validator.after_req_times.append(perf_counter_ns())
        #         exp_rc = i if throttle_mode != MODE_ASYNC else Throttle.RC_OK
        #         assert rc == exp_rc
        #
        # elif request_style == 3:
        #     for i, s_interval in enumerate(request_validator.send_intervals):
        #         # 3
        #         request_validator.start_times.append(perf_counter_ns())
        #         pauser.pause(s_interval)  # first one is 0.0
        #         request_validator.before_req_times.append(perf_counter_ns())
        #         rc = a_throttle.send_request(request_validator.request3, idx=i)
        #         request_validator.after_req_times.append(perf_counter_ns())
        #         exp_rc = i if throttle_mode != MODE_ASYNC else Throttle.RC_OK
        #         assert rc == exp_rc
        #
        # elif request_style == 4:
        #     for i, s_interval in enumerate(request_validator.send_intervals):
        #         # 4
        #         request_validator.start_times.append(perf_counter_ns())
        #         pauser.pause(s_interval)  # first one is 0.0
        #         request_validator.before_req_times.append(perf_counter_ns())
        #         rc = a_throttle.send_request(
        #             request_validator.request4, idx=i, seconds=request_validator.seconds
        #         )
        #         request_validator.after_req_times.append(perf_counter_ns())
        #         exp_rc = i if throttle_mode != MODE_ASYNC else Throttle.RC_OK
        #         assert rc == exp_rc
        #
        # elif request_style == 5:
        #     for i, s_interval in enumerate(request_validator.send_intervals):
        #         # 5
        #         request_validator.start_times.append(perf_counter_ns())
        #         pauser.pause(s_interval)  # first one is 0.0
        #         request_validator.before_req_times.append(perf_counter_ns())
        #         rc = a_throttle.send_request(
        #             request_validator.request5,
        #             i,
        #             interval=request_validator.send_interval,
        #         )
        #         request_validator.after_req_times.append(perf_counter_ns())
        #         exp_rc = i if throttle_mode != MODE_ASYNC else Throttle.RC_OK
        #         assert rc == exp_rc
        #
        # elif request_style == 6:
        #     for i, s_interval in enumerate(request_validator.send_intervals):
        #         # 6
        #         request_validator.start_times.append(perf_counter_ns())
        #         if i == 5:
        #             pauser.pause(s_interval + 0.97)
        #         else:
        #             pauser.pause(s_interval)  # first one is 0.0
        #         request_validator.before_req_times.append(perf_counter_ns())
        #         rc = a_throttle.send_request(
        #             request_validator.request6,
        #             i,
        #             request_validator.requests,
        #             seconds=request_validator.seconds,
        #             interval=request_validator.send_interval,
        #         )
        #         request_validator.after_req_times.append(perf_counter_ns())
        #         exp_rc = i if throttle_mode != MODE_ASYNC else Throttle.RC_OK
        #         assert rc == exp_rc
        # else:
        #     raise BadRequestStyleArg("The request style arg must be 0 to 6")

    ####################################################################
    # test_pie_throttle_async_args_style
    ####################################################################
    @pytest.mark.parametrize("request_style_arg", (0, 1, 2, 3, 4, 5, 6))
    def test_pie_throttle_async_args_style(self, request_style_arg: int) -> None:
        """Method to start throttle mode1 tests.

        Args:
            request_style_arg: chooses which function args to use

        """
        ################################################################
        # Instantiate Request Validator
        ################################################################
        pauser = Pauser()
        reqs_per_sec_arg = 4
        seconds_arg = 1
        send_interval = 0.1

        ################################################################
        # get send interval list
        ################################################################
        num_reqs_to_do, send_intervals = self.build_send_intervals(send_interval)

        ################################################################
        # Decorate functions with throttle
        ################################################################
        call_list: list[tuple[str, str, str]] = []

        ################################################################
        # f0
        ################################################################
        @throttle(reqs_per_sec=reqs_per_sec_arg, throttle_mode=ThrottleMode.ASYNC)
        def f0() -> Any:
            request_validator.callback0()

        call_list.append(("f0", "()", "0"))

        ################################################################
        # f1
        ################################################################
        @throttle(reqs_per_sec=reqs_per_sec_arg, throttle_mode=ThrottleMode.ASYNC)
        def f1(idx: int) -> Any:
            request_validator.callback1(idx)

        call_list.append(("f1", "(i)", "0"))

        ################################################################
        # f2
        ################################################################
        @throttle(reqs_per_sec=reqs_per_sec_arg, throttle_mode=ThrottleMode.ASYNC)
        def f2(idx: int, requests: int) -> Any:
            request_validator.callback2(idx, requests)

        call_list.append(("f2", "(i, reqs_per_sec_arg)", "0"))

        ################################################################
        # f3
        ################################################################
        @throttle(reqs_per_sec=reqs_per_sec_arg, throttle_mode=ThrottleMode.ASYNC)
        def f3(*, idx: int) -> Any:
            request_validator.callback3(idx=idx)

        call_list.append(("f3", "(idx=i)", "0"))

        ################################################################
        # f4
        ################################################################
        @throttle(reqs_per_sec=reqs_per_sec_arg, throttle_mode=ThrottleMode.ASYNC)
        def f4(*, idx: int, seconds: float) -> Any:
            request_validator.callback4(idx=idx, seconds=seconds)

        call_list.append(("f4", "(idx=i, seconds=seconds_arg)", "0"))

        ################################################################
        # f5
        ################################################################
        @throttle(reqs_per_sec=reqs_per_sec_arg, throttle_mode=ThrottleMode.ASYNC)
        def f5(idx: int, *, interval: float) -> Any:
            request_validator.callback5(idx, interval=interval)

        call_list.append(("f5", "(idx=i, interval=send_interval)", "0"))

        ################################################################
        # f6
        ################################################################
        @throttle(reqs_per_sec=reqs_per_sec_arg, throttle_mode=ThrottleMode.ASYNC)
        def f6(idx: int, requests: int, *, seconds: float, interval: float) -> Any:
            request_validator.callback6(
                idx, requests, seconds=seconds, interval=interval
            )

        call_list.append(
            (
                "f6",
                "(i, reqs_per_sec_arg, seconds=seconds_arg, " "interval=send_interval)",
                "0",
            )
        )

        ################################################################
        # Instantiate the validator
        ################################################################
        request_validator = RequestValidator(
            reqs_per_sec=reqs_per_sec_arg,
            seconds=seconds_arg,
            mode=MODE_ASYNC,
            early_count=0,
            bucket_size=0,
            total_reqs_per_sec=num_reqs_to_do,
            send_interval=send_interval,
            send_intervals=send_intervals,
            t_throttle=eval(call_list[request_style_arg][0]).throttle,
        )
        ################################################################
        # Invoke the functions
        ################################################################
        for i, s_interval in enumerate(send_intervals):
            request_validator.start_times.append(perf_counter_ns())
            pauser.pause(s_interval)  # first one is 0.0
            request_validator.before_req_times.append(perf_counter_ns())
            rc = eval(call_list[request_style_arg][0] + call_list[request_style_arg][1])
            request_validator.after_req_times.append(perf_counter_ns())
            assert rc == 0

        # funcs_to_shutdown = [eval(a_func[0]) for a_func in call_list]
        # funcs_to_shutdown = [f0, f1, f2, f3, f4, f5, f6]
        shutdown_throttle_funcs(f0, f1, f2, f3, f4, f5, f6)
        request_validator.validate_series()  # validate for the series

    ####################################################################
    # test_pie_throttle_async
    ####################################################################
    @pytest.mark.parametrize("reqs_per_sec_arg", (1, 2, 3))
    @pytest.mark.parametrize("seconds_arg", (0.3, 1, 2))
    @pytest.mark.parametrize("send_interval_mult_arg", (0.0, 0.9, 1.0, 1.1))
    def test_pie_throttle_async(
        self,
        reqs_per_sec_arg: int,
        seconds_arg: IntFloat,
        send_interval_mult_arg: float,
    ) -> None:
        """Method to start throttle mode1 tests.

        Args:
            reqs_per_sec_arg: number of requests per interval from fixture
            seconds_arg: interval for number of requests from fixture
            send_interval_mult_arg: interval between each send of a
                                      request
        """
        ################################################################
        # Instantiate Request Validator
        ################################################################
        pauser = Pauser()
        send_interval = (seconds_arg / reqs_per_sec_arg) * send_interval_mult_arg

        ################################################################
        # get send interval list
        ################################################################
        num_reqs_to_do, send_intervals = self.build_send_intervals(send_interval)

        ################################################################
        # Decorate functions with throttle
        ################################################################
        @throttle(reqs_per_sec=reqs_per_sec_arg, throttle_mode=ThrottleMode.ASYNC)
        def f0() -> Any:
            request_validator.callback0()

        ################################################################
        # Instantiate the validator
        ################################################################
        request_validator = RequestValidator(
            reqs_per_sec=reqs_per_sec_arg,
            seconds=seconds_arg,
            mode=MODE_ASYNC,
            early_count=0,
            bucket_size=0,
            total_reqs_per_sec=num_reqs_to_do,
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
        for i, s_interval in enumerate(send_intervals):
            request_validator.start_times.append(perf_counter_ns())
            pauser.pause(s_interval)  # first one is 0.0
            request_validator.before_req_times.append(perf_counter_ns())
            rc = f0()
            request_validator.after_req_times.append(perf_counter_ns())
            assert rc == 0

        shutdown_throttle_funcs(f0)
        request_validator.validate_series()  # validate for the series

    ####################################################################
    # test_throttle_sync
    ####################################################################
    @pytest.mark.parametrize("request_style_arg", (0, 1, 2, 3, 4, 5, 6))
    def test_pie_throttle_sync_args_style(self, request_style_arg: int) -> None:
        """Method to start pie throttle sync throttle_mode tests.

        Args:
            request_style_arg: chooses which function args to use

        """
        ################################################################
        # Instantiate Request Validator
        ################################################################
        pauser = Pauser()
        reqs_per_sec_arg = 2
        seconds_arg = 0.5
        send_interval_mult_arg = 1.0
        send_interval = (seconds_arg / reqs_per_sec_arg) * send_interval_mult_arg

        ################################################################
        # get send interval list
        ################################################################
        num_reqs_to_do, send_intervals = self.build_send_intervals(send_interval)

        ################################################################
        # Decorate functions with throttle
        ################################################################
        call_list: list[tuple[str, str, str]] = []

        ################################################################
        # f0
        ################################################################
        @throttle_sync(reqs_per_sec=reqs_per_sec_arg, seconds=seconds_arg)
        def f0() -> int:
            request_validator.callback0()
            return 42

        call_list.append(("f0", "()", "42"))

        ################################################################
        # f1
        ################################################################
        @throttle_sync(reqs_per_sec=reqs_per_sec_arg, seconds=seconds_arg)
        def f1(idx: int) -> int:
            request_validator.callback1(idx)
            return idx + 42 + 1

        call_list.append(("f1", "(i)", "i + 42 + 1"))

        ################################################################
        # f2
        ################################################################
        @throttle_sync(reqs_per_sec=reqs_per_sec_arg, seconds=seconds_arg)
        def f2(idx: int, requests: int) -> int:
            request_validator.callback2(idx, requests)
            return idx + 42 + 2

        call_list.append(("f2", "(i, reqs_per_sec_arg)", "i + 42 + 2"))

        ################################################################
        # f3
        ################################################################
        @throttle_sync(reqs_per_sec=reqs_per_sec_arg, seconds=seconds_arg)
        def f3(*, idx: int) -> int:
            request_validator.callback3(idx=idx)
            return idx + 42 + 3

        call_list.append(("f3", "(idx=i)", "i + 42 + 3"))

        ################################################################
        # f4
        ################################################################
        @throttle_sync(reqs_per_sec=reqs_per_sec_arg, seconds=seconds_arg)
        def f4(*, idx: int, seconds: float) -> int:
            request_validator.callback4(idx=idx, seconds=seconds)
            return idx + 42 + 4

        call_list.append(("f4", "(idx=i, seconds=seconds_arg)", "i + 42 + 4"))

        ################################################################
        # f5
        ################################################################
        @throttle_sync(reqs_per_sec=reqs_per_sec_arg, seconds=seconds_arg)
        def f5(idx: int, *, interval: float) -> int:
            request_validator.callback5(idx, interval=interval)
            return idx + 42 + 5

        call_list.append(
            ("f5", "(idx=i, interval=send_interval_mult_arg)", "i + 42 + 5")
        )

        ################################################################
        # f6
        ################################################################
        @throttle_sync(reqs_per_sec=reqs_per_sec_arg, seconds=seconds_arg)
        def f6(idx: int, requests: int, *, seconds: float, interval: float) -> int:
            request_validator.callback6(
                idx, requests, seconds=seconds, interval=interval
            )
            return idx + 42 + 6

        call_list.append(
            (
                "f6",
                "(i, reqs_per_sec_arg, seconds=seconds_arg,"
                " interval=send_interval_mult_arg)",
                "i + 42 + 6",
            )
        )

        ################################################################
        # Instantiate the validator
        ################################################################
        request_validator = RequestValidator(
            reqs_per_sec=reqs_per_sec_arg,
            seconds=seconds_arg,
            mode=MODE_SYNC,
            early_count=0,
            bucket_size=0,
            total_reqs_per_sec=num_reqs_to_do,
            send_interval=send_interval,
            send_intervals=send_intervals,
            t_throttle=eval(call_list[request_style_arg][0]).throttle,
        )
        ################################################################
        # Invoke the functions
        ################################################################
        for i, s_interval in enumerate(send_intervals):
            request_validator.start_times.append(perf_counter_ns())
            pauser.pause(s_interval)  # first one is 0.0
            request_validator.before_req_times.append(perf_counter_ns())
            rc = eval(call_list[request_style_arg][0] + call_list[request_style_arg][1])
            request_validator.after_req_times.append(perf_counter_ns())
            assert rc == eval(call_list[request_style_arg][2])

        request_validator.validate_series()  # validate for the series

    ####################################################################
    # test_throttle_sync
    ####################################################################
    @pytest.mark.parametrize("reqs_per_sec_arg", (1, 2, 3))
    @pytest.mark.parametrize("seconds_arg", (0.3, 1, 2))
    @pytest.mark.parametrize("send_interval_mult_arg", (0.0, 0.9, 1.0, 1.1))
    def test_pie_throttle_sync(
        self,
        reqs_per_sec_arg: int,
        seconds_arg: IntFloat,
        send_interval_mult_arg: float,
    ) -> None:
        """Method to start throttle sync tests.

        Args:
            reqs_per_sec_arg: number of requests per interval from fixture
            seconds_arg: interval for number of requests from fixture
            send_interval_mult_arg: interval between each send of a
                                      request
        """
        ################################################################
        # Instantiate Request Validator
        ################################################################
        pauser = Pauser()
        send_interval = (seconds_arg / reqs_per_sec_arg) * send_interval_mult_arg

        ################################################################
        # get send interval list
        ################################################################
        num_reqs_to_do, send_intervals = self.build_send_intervals(send_interval)

        ################################################################
        # Decorate functions with throttle
        ################################################################
        @throttle_sync(reqs_per_sec=reqs_per_sec_arg, seconds=seconds_arg)
        def f1(idx: int) -> int:
            request_validator.callback1(idx)
            return idx + 42 + 1

        ################################################################
        # Instantiate the validator
        ################################################################
        request_validator = RequestValidator(
            reqs_per_sec=reqs_per_sec_arg,
            seconds=seconds_arg,
            mode=MODE_SYNC,
            early_count=0,
            bucket_size=0,
            total_reqs_per_sec=num_reqs_to_do,
            send_interval=send_interval,
            send_intervals=send_intervals,
            t_throttle=f1.throttle,
        )
        ################################################################
        # Invoke the functions
        ################################################################
        ################################################################
        # Invoke f1
        ################################################################
        for i, s_interval in enumerate(send_intervals):
            request_validator.start_times.append(perf_counter_ns())
            pauser.pause(s_interval)  # first one is 0.0
            request_validator.before_req_times.append(perf_counter_ns())
            rc = f1(i)
            request_validator.after_req_times.append(perf_counter_ns())
            assert rc == i + 42 + 1

        request_validator.validate_series()  # validate for the series

    ####################################################################
    # test_throttle_sync_ec
    ####################################################################
    @pytest.mark.parametrize("request_style_arg", (0, 1, 2, 3, 4, 5, 6))
    def test_pie_throttle_sync_ec_args_style(self, request_style_arg: int) -> None:
        """Method to start pie throttle sync ec throttle_mode tests.

        Args:
            request_style_arg: chooses which function args to use

        """
        ################################################################
        # Instantiate Request Validator
        ################################################################
        pauser = Pauser()
        reqs_per_sec_arg = 3
        seconds_arg = 0.9
        early_count_arg = 2
        send_interval_mult_arg = 1.0

        send_interval = (seconds_arg / reqs_per_sec_arg) * send_interval_mult_arg

        ################################################################
        # get send interval list
        ################################################################
        num_reqs_to_do, send_intervals = self.build_send_intervals(send_interval)

        ################################################################
        # Decorate functions with throttle
        ################################################################
        call_list: list[tuple[str, str, str]] = []

        ################################################################
        # f0
        ################################################################
        @throttle_sync_ec(
            reqs_per_sec=reqs_per_sec_arg,
            seconds=seconds_arg,
            early_count=early_count_arg,
        )
        def f0() -> int:
            request_validator.callback0()
            return 42

        call_list.append(("f0", "()", "42"))

        ################################################################
        # f1
        ################################################################
        @throttle_sync_ec(
            reqs_per_sec=reqs_per_sec_arg,
            seconds=seconds_arg,
            early_count=early_count_arg,
        )
        def f1(idx: int) -> int:
            request_validator.callback1(idx)
            return idx + 42 + 1

        call_list.append(("f1", "(i)", "i + 42 + 1"))

        ################################################################
        # f2
        ################################################################
        @throttle_sync_ec(
            reqs_per_sec=reqs_per_sec_arg,
            seconds=seconds_arg,
            early_count=early_count_arg,
        )
        def f2(idx: int, requests: int) -> int:
            request_validator.callback2(idx, requests)
            return idx + 42 + 2

        call_list.append(("f2", "(i, reqs_per_sec_arg)", "i + 42 + 2"))

        ################################################################
        # f3
        ################################################################
        @throttle_sync_ec(
            reqs_per_sec=reqs_per_sec_arg,
            seconds=seconds_arg,
            early_count=early_count_arg,
        )
        def f3(*, idx: int) -> int:
            request_validator.callback3(idx=idx)
            return idx + 42 + 3

        call_list.append(("f3", "(idx=i)", "i + 42 + 3"))

        ################################################################
        # f4
        ################################################################
        @throttle_sync_ec(
            reqs_per_sec=reqs_per_sec_arg,
            seconds=seconds_arg,
            early_count=early_count_arg,
        )
        def f4(*, idx: int, seconds: float) -> int:
            request_validator.callback4(idx=idx, seconds=seconds)
            return idx + 42 + 4

        call_list.append(("f4", "(idx=i, seconds=seconds_arg)", "i + 42 + 4"))

        ################################################################
        # f5
        ################################################################
        @throttle_sync_ec(
            reqs_per_sec=reqs_per_sec_arg,
            seconds=seconds_arg,
            early_count=early_count_arg,
        )
        def f5(idx: int, *, interval: float) -> int:
            request_validator.callback5(idx, interval=interval)
            return idx + 42 + 5

        call_list.append(
            ("f5", "(idx=i, interval=send_interval_mult_arg)", "i + 42 + 5")
        )

        ################################################################
        # f6
        ################################################################
        @throttle_sync_ec(
            reqs_per_sec=reqs_per_sec_arg,
            seconds=seconds_arg,
            early_count=early_count_arg,
        )
        def f6(idx: int, requests: int, *, seconds: float, interval: float) -> int:
            request_validator.callback6(
                idx, requests, seconds=seconds, interval=interval
            )
            return idx + 42 + 6

        call_list.append(
            (
                "f6",
                "(i, reqs_per_sec_arg,"
                "seconds=seconds_arg,"
                "interval=send_interval_mult_arg)",
                "i + 42 + 6",
            )
        )

        ################################################################
        # Instantiate the validator
        ################################################################
        request_validator = RequestValidator(
            reqs_per_sec=reqs_per_sec_arg,
            seconds=seconds_arg,
            mode=MODE_SYNC_EC,
            early_count=early_count_arg,
            bucket_size=0,
            total_reqs_per_sec=num_reqs_to_do,
            send_interval=send_interval,
            send_intervals=send_intervals,
            t_throttle=eval(call_list[request_style_arg][0]).throttle,
        )
        ################################################################
        # Invoke the functions
        ################################################################
        for i, s_interval in enumerate(send_intervals):
            request_validator.start_times.append(perf_counter_ns())
            pauser.pause(s_interval)  # first one is 0.0
            request_validator.before_req_times.append(perf_counter_ns())
            rc = eval(call_list[request_style_arg][0] + call_list[request_style_arg][1])
            request_validator.after_req_times.append(perf_counter_ns())
            assert rc == eval(call_list[request_style_arg][2])
        request_validator.validate_series()  # validate for the series

    ####################################################################
    # test_throttle_sync_ec
    ####################################################################
    @pytest.mark.parametrize("reqs_per_sec_arg", (1, 2, 3))
    @pytest.mark.parametrize("seconds_arg", (0.3, 1, 2))
    @pytest.mark.parametrize("early_count_arg", (1, 2, 3))
    @pytest.mark.parametrize("send_interval_mult_arg", (0.0, 0.9, 1.0, 1.1))
    def test_pie_throttle_sync_ec(
        self,
        reqs_per_sec_arg: int,
        seconds_arg: IntFloat,
        early_count_arg: int,
        send_interval_mult_arg: float,
    ) -> None:
        """Method to start throttle sync_ec tests.

        Args:
            reqs_per_sec_arg: number of requests per interval from fixture
            seconds_arg: interval for number of requests from fixture
            early_count_arg: count used for sync with early count algo
            send_interval_mult_arg: interval between each send of a
                                      request
        """
        ################################################################
        # Instantiate Request Validator
        ################################################################
        pauser = Pauser()
        send_interval = (seconds_arg / reqs_per_sec_arg) * send_interval_mult_arg

        ################################################################
        # get send interval list
        ################################################################
        num_reqs_to_do, send_intervals = self.build_send_intervals(send_interval)

        ################################################################
        # Decorate functions with throttle
        ################################################################
        @throttle_sync_ec(
            reqs_per_sec=reqs_per_sec_arg,
            seconds=seconds_arg,
            early_count=early_count_arg,
        )
        def f5(idx: int, *, interval: float) -> int:
            request_validator.callback5(idx, interval=interval)
            return idx + 42 + 5

        ################################################################
        # Instantiate the validator
        ################################################################
        request_validator = RequestValidator(
            reqs_per_sec=reqs_per_sec_arg,
            seconds=seconds_arg,
            mode=MODE_SYNC_EC,
            early_count=early_count_arg,
            bucket_size=0,
            total_reqs_per_sec=num_reqs_to_do,
            send_interval=send_interval,
            send_intervals=send_intervals,
            t_throttle=f5.throttle,
        )
        ################################################################
        # Invoke the functions
        ################################################################
        for i, s_interval in enumerate(send_intervals):
            request_validator.start_times.append(perf_counter_ns())
            pauser.pause(s_interval)  # first one is 0.0
            request_validator.before_req_times.append(perf_counter_ns())
            rc = f5(idx=i, interval=send_interval_mult_arg)
            request_validator.after_req_times.append(perf_counter_ns())
            assert rc == i + 42 + 5
        request_validator.validate_series()  # validate for the series

    ####################################################################
    # test_throttle_sync_lb
    ####################################################################
    @pytest.mark.parametrize("request_style_arg", (0, 1, 2, 3, 4, 5, 6))
    def test_pie_throttle_sync_lb_args_style(self, request_style_arg: int) -> None:
        """Method to start pie throttle sync ec throttle_mode tests.

        Args:
            request_style_arg: chooses which function args to use

        """
        ################################################################
        # Instantiate Request Validator
        ################################################################
        pauser = Pauser()
        reqs_per_sec_arg = 3
        seconds_arg = 0.7
        bucket_size_arg = 4
        send_interval_mult_arg = 0.3

        send_interval = (seconds_arg / reqs_per_sec_arg) * send_interval_mult_arg

        ################################################################
        # get send interval list
        ################################################################
        num_reqs_to_do, send_intervals = self.build_send_intervals(send_interval)

        ################################################################
        # Decorate functions with throttle
        ################################################################
        call_list: list[tuple[str, str, str]] = []

        ################################################################
        # f0
        ################################################################
        @throttle(
            reqs_per_sec=reqs_per_sec_arg,
            bucket_size=bucket_size_arg,
        )
        def f0() -> int:
            request_validator.callback0()
            return 42

        call_list.append(("f0", "()", "42"))

        ################################################################
        # f1
        ################################################################
        @throttle(
            reqs_per_sec=reqs_per_sec_arg,
            bucket_size=bucket_size_arg,
        )
        def f1(idx: int) -> int:
            request_validator.callback1(idx)
            return idx + 42 + 1

        call_list.append(("f1", "(i)", "i + 42 + 1"))

        ################################################################
        # f2
        ################################################################
        @throttle(
            reqs_per_sec=reqs_per_sec_arg,
            bucket_size=bucket_size_arg,
        )
        def f2(idx: int, requests: int) -> int:
            request_validator.callback2(idx, requests)
            return idx + 42 + 2

        call_list.append(("f2", "(i, reqs_per_sec_arg)", "i + 42 + 2"))

        ################################################################
        # f3
        ################################################################
        @throttle(
            reqs_per_sec=reqs_per_sec_arg,
            bucket_size=bucket_size_arg,
        )
        def f3(*, idx: int) -> int:
            request_validator.callback3(idx=idx)
            return idx + 42 + 3

        call_list.append(("f3", "(idx=i)", "i + 42 + 3"))

        ################################################################
        # f4
        ################################################################
        @throttle(
            reqs_per_sec=reqs_per_sec_arg,
            bucket_size=bucket_size_arg,
        )
        def f4(*, idx: int, seconds: float) -> int:
            request_validator.callback4(idx=idx, seconds=seconds)
            return idx + 42 + 4

        call_list.append(("f4", "(idx=i, seconds=seconds_arg)", "i + 42 + 4"))

        ################################################################
        # f5
        ################################################################
        @throttle(
            reqs_per_sec=reqs_per_sec_arg,
            bucket_size=bucket_size_arg,
        )
        def f5(idx: int, *, interval: float) -> int:
            request_validator.callback5(idx, interval=interval)
            return idx + 42 + 5

        call_list.append(
            ("f5", "(idx=i, interval=send_interval_mult_arg)", "i + 42 + 5")
        )

        ################################################################
        # f6
        ################################################################
        @throttle(
            reqs_per_sec=reqs_per_sec_arg,
            bucket_size=bucket_size_arg,
        )
        def f6(idx: int, requests: int, *, seconds: float, interval: float) -> int:
            request_validator.callback6(
                idx, requests, seconds=seconds, interval=interval
            )
            return idx + 42 + 6

        call_list.append(
            (
                "f6",
                "(i, reqs_per_sec_arg,"
                "seconds=seconds_arg,"
                " interval=send_interval_mult_arg)",
                "i + 42 + 6",
            )
        )

        ################################################################
        # Instantiate the validator
        ################################################################
        request_validator = RequestValidator(
            reqs_per_sec=reqs_per_sec_arg,
            seconds=seconds_arg,
            mode=MODE_SYNC_LB,
            early_count=0,
            bucket_size=bucket_size_arg,
            total_reqs_per_sec=num_reqs_to_do,
            send_interval=send_interval,
            send_intervals=send_intervals,
            t_throttle=eval(call_list[request_style_arg][0]).throttle,
        )
        ################################################################
        # Invoke the functions
        ################################################################
        for i, s_interval in enumerate(send_intervals):
            request_validator.start_times.append(perf_counter_ns())
            pauser.pause(s_interval)  # first one is 0.0
            request_validator.before_req_times.append(perf_counter_ns())
            rc = eval(call_list[request_style_arg][0] + call_list[request_style_arg][1])
            request_validator.after_req_times.append(perf_counter_ns())
            assert rc == eval(call_list[request_style_arg][2])
        request_validator.validate_series()  # validate for the series

    ####################################################################
    # test_throttle_sync_lb
    ####################################################################
    @pytest.mark.parametrize("reqs_per_sec_arg", (1, 2, 3))
    @pytest.mark.parametrize("seconds_arg", (0.3, 1, 2))
    @pytest.mark.parametrize("bucket_size_arg", (1, 1.5, 3))
    @pytest.mark.parametrize("send_interval_mult_arg", (0.0, 0.9, 1.0, 1.1))
    def test_pie_throttle_sync_lb(
        self,
        reqs_per_sec_arg: int,
        seconds_arg: IntFloat,
        bucket_size_arg: IntFloat,
        send_interval_mult_arg: float,
    ) -> None:
        """Method to start throttle sync_lb tests.

        Args:
            reqs_per_sec_arg: number of requests per interval from fixture
            seconds_arg: interval for number of requests from fixture
            bucket_size_arg: threshold used with sync leaky bucket algo
            send_interval_mult_arg: interval between each send of a
                                      request
        """
        ################################################################
        # Instantiate Request Validator
        ################################################################
        pauser = Pauser()
        send_interval = (seconds_arg / reqs_per_sec_arg) * send_interval_mult_arg

        ################################################################
        # get send interval list
        ################################################################
        num_reqs_to_do, send_intervals = self.build_send_intervals(send_interval)

        ################################################################
        # Decorate functions with throttle
        ################################################################
        @throttle(
            reqs_per_sec=reqs_per_sec_arg,
            bucket_size=bucket_size_arg,
        )
        def f6(idx: int, requests: int, *, seconds: float, interval: float) -> int:
            request_validator.callback6(
                idx, requests, seconds=seconds, interval=interval
            )
            return idx + 42 + 6

        ################################################################
        # Instantiate the validator
        ################################################################
        request_validator = RequestValidator(
            reqs_per_sec=reqs_per_sec_arg,
            seconds=seconds_arg,
            mode=MODE_SYNC_LB,
            early_count=0,
            bucket_size=bucket_size_arg,
            total_reqs_per_sec=num_reqs_to_do,
            send_interval=send_interval,
            send_intervals=send_intervals,
            t_throttle=f6.throttle,
        )

        ################################################################
        # Invoke function f6
        ################################################################
        for i, s_interval in enumerate(send_intervals):
            request_validator.start_times.append(perf_counter_ns())
            pauser.pause(s_interval)  # first one is 0.0
            request_validator.before_req_times.append(perf_counter_ns())
            rc = f6(
                i,
                reqs_per_sec_arg,
                seconds=seconds_arg,
                interval=send_interval_mult_arg,
            )
            request_validator.after_req_times.append(perf_counter_ns())
            assert rc == i + 42 + 6
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
    @pytest.mark.parametrize("reqs_per_sec_arg", (1, 2, 3))
    @pytest.mark.parametrize("seconds_arg", (0.3, 1, 2))
    def test_get_interval_secs(self, reqs_per_sec_arg: int, seconds_arg: float) -> None:
        """Method to test get interval in seconds.

        Args:
            reqs_per_sec_arg: number of requests specified for the throttle
            seconds_arg: number of seconds specified for the throttle

        """
        ################################################################
        # create a sync throttle_mode throttle
        ################################################################
        a_throttle1 = ThrottleSync(reqs_per_sec=reqs_per_sec_arg, seconds=seconds_arg)

        interval = seconds_arg / reqs_per_sec_arg
        assert interval == a_throttle1.get_interval_secs()

    ####################################################################
    # test_get_interval_ns
    ####################################################################
    @pytest.mark.parametrize("reqs_per_sec_arg", (1, 2, 3))
    @pytest.mark.parametrize("seconds_arg", (0.3, 1, 2))
    def test_get_interval_ns(self, reqs_per_sec_arg: int, seconds_arg: float) -> None:
        """Method to test get interval in nanoseconds.

        Args:
            reqs_per_sec_arg: number of requests specified for the throttle
            seconds_arg: number of seconds specified for the throttle

        """
        ################################################################
        # create a sync throttle_mode throttle
        ################################################################
        a_throttle1 = ThrottleSync(reqs_per_sec=reqs_per_sec_arg, seconds=seconds_arg)

        interval = (seconds_arg / reqs_per_sec_arg) * 1000000000
        assert interval == a_throttle1.get_interval_ns()

    ####################################################################
    # test_get_completion_time_secs
    ####################################################################
    @pytest.mark.parametrize("reqs_per_sec_arg", (1, 2, 3))
    @pytest.mark.parametrize("seconds_arg", (0.3, 1, 2))
    def test_get_completion_time_secs(
        self, reqs_per_sec_arg: int, seconds_arg: float
    ) -> None:
        """Method to test get completion time in seconds.

        Args:
            reqs_per_sec_arg: number of requests specified for the throttle
            seconds_arg: number of seconds specified for the throttle

        """
        ################################################################
        # create a sync throttle_mode throttle
        ################################################################
        a_throttle1 = ThrottleSync(reqs_per_sec=reqs_per_sec_arg, seconds=seconds_arg)

        interval = seconds_arg / reqs_per_sec_arg
        for num_reqs in range(1, 10):
            exp_completion_time = (num_reqs - 1) * interval
            actual_completion_time = a_throttle1.get_completion_time_secs(
                reqs_per_sec=num_reqs, from_start=True
            )
            assert actual_completion_time == exp_completion_time

        for num_reqs in range(1, 10):
            exp_completion_time = num_reqs * interval
            actual_completion_time = a_throttle1.get_completion_time_secs(
                reqs_per_sec=num_reqs, from_start=False
            )
            assert actual_completion_time == exp_completion_time

    ####################################################################
    # test_get_completion_time_ns
    ####################################################################
    @pytest.mark.parametrize("reqs_per_sec_arg", (1, 2, 3))
    @pytest.mark.parametrize("seconds_arg", (0.3, 1, 2))
    def test_get_completion_time_ns(
        self, reqs_per_sec_arg: int, seconds_arg: float
    ) -> None:
        """Method to test get completion time in nanoseconds.

        Args:
            reqs_per_sec_arg: number of requests specified for the throttle
            seconds_arg: number of seconds specified for the throttle

        """
        ################################################################
        # create a sync throttle_mode throttle
        ################################################################
        a_throttle1 = ThrottleSync(reqs_per_sec=reqs_per_sec_arg, seconds=seconds_arg)

        interval = (seconds_arg / reqs_per_sec_arg) * 1000000000
        for num_reqs in range(1, 10):
            exp_completion_time = (num_reqs - 1) * interval
            actual_completion_time = a_throttle1.get_completion_time_ns(
                reqs_per_sec=num_reqs, from_start=True
            )
            assert actual_completion_time == exp_completion_time

        for num_reqs in range(1, 10):
            exp_completion_time = num_reqs * interval
            actual_completion_time = a_throttle1.get_completion_time_ns(
                reqs_per_sec=num_reqs, from_start=False
            )
            assert actual_completion_time == exp_completion_time


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
            "test_throttle.py::TestThrottleShutdown" ".test_incorrect_shutdown_type"
        )
        log_ver.add_call_seq(name="alpha", seq=alpha_call_seq)

        ################################################################
        # create a sync throttle_mode throttle
        ################################################################
        reqs_per_sec_arg = 4
        seconds_arg = 1
        a_throttle1 = ThrottleSync(reqs_per_sec=reqs_per_sec_arg, seconds=seconds_arg)

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
        # Note: this test is not really needed since the sync throttle
        # does not have a shutdown method to call. We are essentially
        # and unnecessarily testing Python's ability to detect an
        # attribute error. It is, however, nice to know that we get the
        # expected error and are able to continue the use of the
        # throttle.
        ################################################################
        with pytest.raises(AttributeError):
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
    # test_attempt_sync_throttle_shutdown
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
            "test_throttle.py::TestThrottleShutdown" ".test_incorrect_shutdown_type"
        )
        log_ver.add_call_seq(name="alpha", seq=alpha_call_seq)
        ################################################################
        # create an async throttle_mode throttle
        ################################################################
        reqs_per_sec_arg = 6
        seconds_arg = 2
        a_throttle1 = Throttle(
            reqs_per_sec=reqs_per_sec_arg, seconds=seconds_arg, name="test1"
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
        with pytest.raises(IncorrectShutdownTypeSpecified):
            a_throttle1.start_shutdown(shutdown_type=100)

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
            level=logging.DEBUG,
            pattern=log_msg,
        )

        ################################################################
        # verify the log messages
        ################################################################
        match_results = log_ver.get_match_results(caplog=caplog)
        log_ver.print_match_results(match_results)
        log_ver.verify_log_results(match_results)


########################################################################
# TestThrottleShutdown
########################################################################
# F = TypeVar("F", bound=Callable[..., Any])
#
#
# def clear_log_ver(
#     wrapped: Optional[F] = None,
# ) -> F:
#     @wrapt.decorator(enabled=True)  # type: ignore
#     def trace_wrapper(
#         wrapped: F,
#         instance: Optional[Any],
#         args: tuple[Any, ...],
#         kwargs: dict[str, Any],
#     ) -> Any:
#         instance.log_ver.patterns = []
#         return_value = wrapped(*args, **kwargs)
#         return return_value
#
#     return cast(F, trace_wrapper(wrapped))


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
    requests: int, seconds: float, async_q_size: int, name: Optional[str] = None
) -> tuple[Throttle, float]:
    """Obtain an async throttle and return it.

    Args:
        requests: number of requests per *seconds&
        seconds: number of seconds the the number of *requests*
        name: throttle name used in log messages
        async_q_size: max number of requests that will be queued

    """
    a_throttle = Throttle(
        reqs_per_sec=requests, seconds=seconds, name=name, async_q_size=async_q_size
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
    """Queue the request to the asyn throttle.

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
            shutdown_type=Throttle.TYPE_SHUTDOWN_HARD, timeout=60
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
        level=logging.DEBUG,
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
            reqs_per_sec_arg: how many requests per seconds
            short_long_timeout_arg: whether to do short or long timeout
            caplog: pytest fixture to capture log output


        """
        seconds_arg = 0.3
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
            seconds=seconds_arg,
            name="hard",
            async_q_size=num_reqs_to_make,
        )
        log_ver.test_msg(
            f"{seconds_arg=}, {num_reqs_to_make=}, {sleep_delay_arg=}, {interval=}"
        )

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
                # since it is based of start_time, but no reqs should
                # be processed once the shutdown is started
                if num_reqs_done_before_shutdown == 0:
                    num_reqs_done_before_shutdown = a_req_time.num_reqs

                ret_code = a_throttle.start_shutdown(
                    shutdown_type=Throttle.TYPE_SHUTDOWN_HARD, timeout=timeout
                )

                async_q_empty, num_reqs = issue_remaining_requests_log_entry(
                    throttle=a_throttle, log_ver=log_ver
                )

                # verify that the throttle did not process any reqs
                # after the shutdown was started
                assert num_reqs_done_before_shutdown == a_req_time.num_reqs

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
            a_throttle.start_shutdown(Throttle.TYPE_SHUTDOWN_HARD)

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
            reqs_per_sec_arg: how many requests per seconds
            sleep_delay_arg: how many requests as a ratio to total
                               requests to schedule before starting
                               shutdown
            timeout3_arg: timeout value to use
            caplog: pytest fixture to capture log output


        """
        seconds_arg = 0.3
        num_reqs_to_make = 100

        log_ver = self.log_ver
        alpha_call_seq = (
            "test_throttle.py::TestThrottleShutdown"
            ".test_throttle_soft_shutdown_timeout"
        )
        log_ver.add_call_seq(name="alpha", seq=alpha_call_seq)

        a_throttle, interval = get_async_throttle(
            reqs_per_sec=reqs_per_sec_arg,
            seconds=seconds_arg,
            name="soft_timeout",
            async_q_size=num_reqs_to_make,
        )
        log_ver.test_msg(
            f"{seconds_arg=}, {num_reqs_to_make=}, {sleep_delay_arg=}, {interval=}"
        )

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
                    shutdown_type=Throttle.TYPE_SHUTDOWN_SOFT, timeout=timeout
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
                            shutdown_type=Throttle.TYPE_SHUTDOWN_SOFT,
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
            a_throttle.start_shutdown(Throttle.TYPE_SHUTDOWN_HARD)

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
            reqs_per_sec_arg: how many requests per seconds
            multi_timeout_arg: timeout time factors
            caplog: pytest fixture to capture log output


        """
        seconds_arg = 0.3
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
            seconds=seconds_arg,
            name="multi soft",
            async_q_size=num_reqs_to_make,
        )
        log_ver.test_msg(
            f"{seconds_arg=}, {num_reqs_to_make=}, {sleep_delay_arg=}, {interval=}"
        )

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
                shutdown_type=Throttle.TYPE_SHUTDOWN_SOFT, timeout=ss_timeout
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
            a_throttle.start_shutdown(Throttle.TYPE_SHUTDOWN_HARD)

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
            reqs_per_sec_arg: how many requests per seconds
            short_long_timeout_arg: whether to do short or long timeout
            hard_soft_combo_arg: whether to do hard of soft
            caplog: pytest fixture to capture log output


        """
        seconds_arg = 0.3
        num_reqs_to_make = 1_000_000
        sleep_reqs_to_do = 10

        # The following code will limit the number of requests to a
        # smaller number if we will be doing a soft shutdown to
        # completion without and intervening hard shutdown. We do not
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
            seconds=seconds_arg,
            name="shutdown combos",
            async_q_size=num_reqs_to_make,
        )
        log_ver.test_msg(
            f"{seconds_arg=}, {num_reqs_to_make=}, {interval=}, {sleep_reqs_to_do=}"
        )

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
                    shutdown_type = Throttle.TYPE_SHUTDOWN_SOFT
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
                    shutdown_type = Throttle.TYPE_SHUTDOWN_HARD
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
                    assert last_num_reqs_done == a_req_time.num_reqs

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
            a_throttle.start_shutdown(Throttle.TYPE_SHUTDOWN_HARD)

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
            reqs_per_sec_arg: how many requests per seconds
            timeout1_arg: whether to issue timeout
            caplog: pytest fixture to capture log output

        """
        seconds_arg = 0.3
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
            seconds=seconds_arg,
            name="soft hard",
            async_q_size=num_reqs_to_make,
        )
        log_ver.test_msg(
            f"{seconds_arg=}, {num_reqs_to_make=}, {sleep_reqs_to_do=}, {interval=}"
        )

        def soft_shutdown(timeout_tf: bool) -> None:
            """Do soft shutdown.

            Args:
                timeout_tf: whether to issue timeout
            """
            if timeout_tf:
                rc = a_throttle.start_shutdown(
                    shutdown_type=Throttle.TYPE_SHUTDOWN_SOFT,
                    timeout=max_timeout_seconds,
                )
            else:
                rc = a_throttle.start_shutdown(
                    shutdown_type=Throttle.TYPE_SHUTDOWN_SOFT
                )

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
                shutdown_type=Throttle.TYPE_SHUTDOWN_HARD
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
            a_throttle.start_shutdown(Throttle.TYPE_SHUTDOWN_HARD)

    ####################################################################
    # test_shutdown_throttle_funcs
    ####################################################################
    # @pytest.mark.parametrize("sleep2_delay_arg", (1.1,))
    # @pytest.mark.parametrize("num_shutdown1_funcs_arg", (3,))
    # @pytest.mark.parametrize("f1_num_reqs_arg", (32,))
    # @pytest.mark.parametrize("f2_num_reqs_arg", (32,))
    # @pytest.mark.parametrize("f3_num_reqs_arg", (0,))
    # @pytest.mark.parametrize("f4_num_reqs_arg", (0,))
    # @etrace(omit_parms="caplog", omit_caller=True, log_ver=True)
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
            "test_throttle.py::TestThrottleShutdown"
            ".test_throttle_hard_shutdown_timeout"
        )
        log_ver.add_call_seq(name="alpha", seq=alpha_call_seq)

        ################################################################
        # f1
        ################################################################
        seconds_arg = 0.1
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

        interval = seconds_arg / stats.mean([1, 2, 3, 4, 5])

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
            shutdown1_type_arg = Throttle.TYPE_SHUTDOWN_SOFT
        else:
            shutdown1_type_arg = Throttle.TYPE_SHUTDOWN_HARD

        log_ver.test_msg(f"{mean_reqs_to_make=}, {shutdown1_type_arg=}")

        f1_interval = seconds_arg / f1_reqs
        f2_interval = seconds_arg / f2_reqs
        f3_interval = seconds_arg / f3_reqs

        f1_exp_elapsed_seconds = f1_interval * f1_num_reqs_arg
        f2_exp_elapsed_seconds = f2_interval * f2_num_reqs_arg
        f3_exp_elapsed_seconds = f3_interval * f3_num_reqs_arg

        timeout_arg = None
        if (
            (shutdown1_type_arg != Throttle.TYPE_SHUTDOWN_HARD)
            and (num_shutdown1_funcs_arg == 2)
            and (f1_num_reqs_arg > 0)
            and (f2_num_reqs_arg > 0)
        ):
            timeout_arg = min(f1_exp_elapsed_seconds, f2_exp_elapsed_seconds) / 2
        elif (
            (shutdown1_type_arg != Throttle.TYPE_SHUTDOWN_HARD)
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
            else:
                funcs_shutdown_complete_msg_added.append(func)
                log_msg = (
                    f"throttle {func.throttle.t_name} start_shutdown request "
                    "successfully completed in "
                    f"{func.throttle.shutdown_elapsed_time:.4f} seconds"
                )

            log_ver.add_pattern(
                log_name="scottbrian_throttle.throttle",
                level=logging.DEBUG,
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
                    level=logging.DEBUG,
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
# ThrottleVerifier used to track async throttle
########################################################################
@dataclass
class ThrottleVerifier:
    """ThrottleVerifier class to track async throttle."""

    ####################################################################
    # __init__
    ####################################################################
    def __init__(self, requests: int, seconds: float, bucket_size: float = 0.0) -> None:
        """Initialize the ThrottleVerifier object.

        Args:
            requests: number of requests per second
            seconds: number of seconds for number of requests
            bucket_size: the leaky bucket threshold
        """

        self.requests = requests
        self.seconds = seconds
        self.bucket_size = bucket_size
        self.bucket_threshold_size_ns = 0.0
        self.amount_in_bucket_ns = 0.0
        self.previous_throttle_send_time: float = 0.0
        self.previous_send_time: float = 0.0
        self.current_send_time: float = 0.0
        self.previous_arrival_time: float = 0.0
        self.current_arrival_time: float = 0.0

        self.request_interval_secs = self.seconds / self.requests

        self.request_interval_ns = self.request_interval_secs * SECS_2_NS

        self.delay_tolerance_ns = max(self.request_interval_ns * 0.1, 0.15 * SECS_2_NS)
        self.num_excessive_request_delays: int = 0

        self.cumulative_expected_delay_ns: float = 0.0

        self.cumulative_throttle_wait_time_ns: float = 0.0

        self.cumulative_actual_delay_ns: float = 0.0

        self.bucket_threshold_size_ns = self.request_interval_ns * self.bucket_size

    ####################################################################
    # verify_request
    ####################################################################
    def verify_request(self, request_item: RequestItem):
        """Handle a request at the given arrival time.

        Args:
            request_item: contains the arrival and sent times

        """
        # Calculate the interval between request send and exit receive
        # as observed by the requestor.
        # Note that previous_throttle_send_time will be zero on the
        # first request which will result in a huge interval, and this
        # is handled below using the max function
        interval = request_item.actual_func_arrival_time_ns - self.previous_send_time

        # calculate the delay this request had - will be zero if bucket
        # had enough room
        request_item.actual_delay_ns = (
            request_item.actual_func_arrival_time_ns - request_item.send_time_ns
        )
        self.cumulative_actual_delay_ns += request_item.actual_delay_ns

        request_item.expected_delay_ns = 0.0
        if request_item.throttle_mode == MODE_ASYNC:
            request_item.expected_delay_ns = max(
                0,
                (self.previous_throttle_send_time + self.request_interval_ns)
                - request_item.send_time_ns,
            )
            request_item.expected_func_arrival_time_ns = (
                request_item.send_time_ns + request_item.expected_delay_ns
            )
            self.previous_throttle_send_time = (
                request_item.send_time_ns + request_item.expected_delay_ns
            )

        elif request_item.throttle_mode == MODE_SYNC_LB:
            # Remove the amount from the bucket that will have leaked out
            # since the last request was processed. Note that we will
            # have overfilled the bucket if the previous request needed to
            # be delayed, but the elapsed time between arrivals will reflect
            # that delay to ensure the bucket is not filled beyond the
            # threshold line. We use the max function to ensure we do not
            # set the bucket amount negative for the case where the elapsed
            # time is greater than what was in the bucket.
            self.amount_in_bucket_ns = max(0.0, self.amount_in_bucket_ns - interval)

            available_amount_ns = (
                self.bucket_threshold_size_ns - self.amount_in_bucket_ns
            )

            self.amount_in_bucket_ns += self.request_interval_ns

            request_item.expected_delay_ns = max(
                0, self.request_interval_ns - available_amount_ns
            )

        assert request_item.expected_delay_ns <= request_item.actual_delay_ns

        self.cumulative_expected_delay_ns += request_item.expected_delay_ns

        self.cumulative_throttle_wait_time_ns += request_item.throttle_wait_time_ns

        if (
            request_item.expected_delay_ns + self.delay_tolerance_ns
            < request_item.actual_delay_ns
        ):
            self.num_excessive_request_delays += 1

        self.previous_arrival_time = request_item.throttle_arrival_time

    # def verify_request(self, request_item: RequestItem):
    #     """Handle a request at the given arrival time.
    #
    #     Args:
    #         request_item: contains the arrival and sent times
    #
    #     """
    #     # Calculate the interval between requests as observed by the
    #     # throttle. Note that previous_arrivel_time will be zero on the
    #     # first request which will result in a huge interval, and this
    #     # is handled below using the max function
    #     interval = request_item.throttle_arrival_time - self.previous_arrival_time
    #
    #     # calculate the delay this request had - will be zero if bucket
    #     # had enough room
    #     actual_delay_ns = (
    #         request_item.actual_func_arrival_time_ns - request_item.throttle_arrival_time
    #     )
    #     self.cumulative_actual_delay_ns += actual_delay_ns
    #
    #     expected_delay_ns = 0.0
    #     if request_item.throttle_mode == MODE_ASYNC:
    #         expected_delay_ns = max(0, self.request_interval_ns - interval)
    #     elif request_item.throttle_mode == MODE_SYNC_LB:
    #         # Remove the amount from the bucket that will have leaked out
    #         # since the last request was processed. Note that we will
    #         # have overfilled the bucket if the previous request needed to
    #         # be delayed, but the elapsed time between arrivals will reflect
    #         # that delay to ensure the bucket is not filled beyond the
    #         # threshold line. We use the max function to ensure we do not
    #         # set the bucket amount negative for the case where the elapsed
    #         # time is greater than what was in the bucket.
    #         self.amount_in_bucket_ns = max(0.0, self.amount_in_bucket_ns - interval)
    #
    #         available_amount_ns = (
    #             self.bucket_threshold_size_ns - self.amount_in_bucket_ns
    #         )
    #
    #         self.amount_in_bucket_ns += self.request_interval_ns
    #
    #         expected_delay_ns = max(0, self.request_interval_ns - available_amount_ns)
    #
    #     assert expected_delay_ns <= actual_delay_ns
    #
    #     self.cumulative_expected_delay_ns += expected_delay_ns
    #
    #     self.cumulative_throttle_wait_time_ns += request_item.throttle_wait_time_ns
    #
    #     if expected_delay_ns + self.delay_tolerance_ns < actual_delay_ns:
    #         self.num_excessive_request_delays += 1
    #
    #     self.previous_arrival_time = request_item.throttle_arrival_time


########################################################################
# LeakyBucketVerifier used to track leaky bucket throttle
########################################################################
@dataclass
class LeakyBucketVerifier:
    """LeakyBucketVerifier class to track leaky bucket throttle."""

    ####################################################################
    # __init__
    ####################################################################
    def __init__(self, requests: int, seconds: float, bucket_size: float) -> None:
        """Initialize the LeakyBucketVerifier object.

        Args:
            requests: number of requests per second
            seconds: number of seconds for number of requests
            bucket_size: the leaky bucket threshold
        """

        self.requests = requests
        self.seconds = seconds
        self.bucket_size = bucket_size
        self.bucket_threshold_size_ns = 0.0
        self.amount_in_bucket_ns = 0.0
        self.previous_arrival_time: float = 0.0
        self.previous_send_time: float = 0.0
        self.current_arrival_time: float = 0.0

        self.request_interval_secs = self.seconds / self.requests

        self.request_interval_ns = self.request_interval_secs * SECS_2_NS

        self.delay_tolerance_ns = max(self.request_interval_ns * 0.1, 0.15 * SECS_2_NS)
        self.num_excessive_request_delays: int = 0

        self.cumulative_expected_delay_ns: float = 0.0

        self.cumulative_throttle_wait_time_ns: float = 0.0

        self.cumulative_actual_delay_ns: float = 0.0

        self.bucket_threshold_size_ns = self.request_interval_ns * self.bucket_size

    ####################################################################
    # verify_request
    ####################################################################
    def verify_request(self, request_item: RequestItem):
        """Handle a request at the given arrival time.

        Args:
            request_item: contains the arrival and sent times

        """
        # calculate the interval between requests as observed by the
        # throttle
        interval = request_item.throttle_arrival_time - self.previous_arrival_time

        # Remove the amount from the bucket that will have leaked out
        # since the last request was processed. Note that we will
        # have overfill the bucket if the previous request needed to be
        # delayed, but the elapsed time between arrivals will reflect
        # that delay to ensure the bucket is not filled beyond the
        # threshold line. We use the max function to ensure we do not
        # set the bucket amount negativee for the case where the elapsed
        # time is greater than what was in the bucket.
        self.amount_in_bucket_ns = max(0.0, self.amount_in_bucket_ns - interval)

        # calculate the delay this request had - will be zero if bucket
        # had enough room
        actual_delay_ns = (
            request_item.actual_func_arrival_time_ns
            - request_item.throttle_arrival_time
        )
        self.cumulative_actual_delay_ns += actual_delay_ns

        available_amount_ns = self.bucket_threshold_size_ns - self.amount_in_bucket_ns

        expected_delay_ns = max(0, self.request_interval_ns - available_amount_ns)
        self.cumulative_expected_delay_ns += expected_delay_ns

        self.cumulative_throttle_wait_time_ns += request_item.throttle_wait_time_ns

        assert expected_delay_ns <= actual_delay_ns

        if expected_delay_ns + self.delay_tolerance_ns < actual_delay_ns:
            self.num_excessive_request_delays += 1

        self.amount_in_bucket_ns += self.request_interval_ns
        self.previous_arrival_time = request_item.throttle_arrival_time


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
        requests: int,
        seconds: float,
        mode: int,
        early_count: int,
        bucket_size: float,
        total_requests: int,
        send_interval: float,
        send_intervals: list[float],
        t_throttle: Throttle,
        num_threads: int = 0,
    ) -> None:
        """Initialize the RequestValidator object.

        Args:
            requests: number of requests per second
            seconds: number of seconds for number of requests
            mode: specifies whether async, sync, sync_ec, or sync_lb
            early_count: the early count for the throttle
            bucket_size: the leaky bucket threshold
            total_requests: specifies how many requests to make for the
                              test
            send_interval: the interval between sends
            send_intervals: the list of send intervals
            t_throttle: the throttle being used for this test
            num_threads: number of threads issuing requests

        """
        self.t_throttle = t_throttle
        self.requests = requests
        self.seconds = seconds
        self.mode = mode
        self.num_threads = num_threads
        self.early_count: int = early_count
        self.bucket_size = bucket_size
        self.send_interval = send_interval
        self.send_intervals = send_intervals
        self.send_times: list[float] = []
        self.num_async_overs: int = 0

        self.thread_items: list[RequestThreadItem] = []

        # Single request item passed to exit. We need this
        # to be able to test an exit without args (i.e., request0)
        self.request_item: list[RequestItem] = []

        # list of request items from each thread
        self.request_items: list[RequestItem] = []

        # self.obtained_nowaits: list[bool] = []

        # self.time_traces = []
        # self.stop_times = []

        # self.norm_time_traces_times = []
        # self.norm_time_traces_intervals = []

        self.norm_stop_times_times: list[float] = []
        self.norm_stop_times_intervals: list[float] = []

        # self.check_async_q_times: list[float] = []
        # self.check_async_q_times2: list[float] = []
        # self.norm_check_async_q_times: list[float] = []
        # self.norm_check_async_q_intervals: list[float] = []

        # self.norm_check_async_q_times2: list[float] = []
        # self.norm_check_async_q_intervals2: list[float] = []

        self.send_interval_sums: list[float] = []
        self.exp_interval_sums: list[float] = []

        self.throttles: list[Throttle] = []
        self.before_next_target_times: list[float] = []

        self.t_entry_bucket_amt: list[float] = []
        self.t_exit_bucket_amt: list[float] = []
        self.next_target_times: list[float] = []
        self.idx = -1

        self.target_times: list[float] = []
        self.target_intervals: list[float] = []

        self.expected_times: list[float] = []
        self.expected_intervals: list[float] = []

        self.previous_delay: list[float] = []
        self.current_delay: list[float] = []

        self.enter_bucket_amt: list[float] = []
        self.exit_bucket_amt: list[float] = []
        self.avail_bucket_amt: list[float] = []

        self.diff_req_intervals: list[float] = []
        self.diff_req_ratio: list[float] = []

        self.before_req_times: list[float] = []
        self.arrival_times: list[float] = []

        self.wait_times: list[float] = []

        self.req_times: list[tuple[int, float]] = []
        self.after_req_times: list[float] = []
        self.start_times: list[float] = []

        self.norm_before_req_times: list[float] = []
        self.norm_arrival_times: list[float] = []
        self.norm_req_times: list[float] = []
        self.norm_after_req_times: list[float] = []
        self.norm_start_times: list[float] = []

        self.norm_before_req_intervals: list[float] = []
        self.norm_arrival_intervals: list[float] = []
        self.norm_req_intervals: list[float] = []
        self.norm_after_req_intervals: list[float] = []
        self.norm_start_intervals: list[float] = []

        self.norm_before_next_target_intervals: list[float] = []
        self.norm_next_target_intervals: list[float] = []

        self.mean_before_req_interval = 0.0
        self.mean_arrival_interval = 0.0
        self.mean_req_interval = 0.0
        self.mean_after_req_interval = 0.0
        self.mean_start_interval = 0.0

        self.norm_before_next_target_times: list[float] = []
        self.norm_next_target_times: list[float] = []

        self.mean_next_target_interval = 0.0

        self.path_times: list[list[float]] = []
        self.path_intervals: list[list[float]] = []

        self.path_async_times: list[list[float]] = []
        self.path_async_intervals: list[list[float]] = []

        # calculate parms

        self.total_requests: int = total_requests
        # if throttle_mode == MODE_SYNC_EC:
        #     self.total_requests = ((((self.total_requests + 1)
        #                            // early_count)
        #                            * early_count)
        #                            + 1)

        self.target_interval = seconds / requests

        self.request_interval_ns = self.target_interval * SECS_2_NS

        self.max_interval = max(self.target_interval, self.send_interval)

        self.min_interval = min(self.target_interval, self.send_interval)

        self.exp_total_time = self.max_interval * (self.total_requests - 1)

        self.target_interval_1pct = self.target_interval * 0.01
        self.target_interval_5pct = self.target_interval * 0.05
        self.target_interval_10pct = self.target_interval * 0.10
        self.target_interval_15pct = self.target_interval * 0.15

        self.max_interval_1pct = self.max_interval * 0.01
        self.max_interval_5pct = self.max_interval * 0.05
        self.max_interval_10pct = self.max_interval * 0.10
        self.max_interval_15pct = self.max_interval * 0.15

        self.min_interval_1pct = self.min_interval * 0.01
        self.min_interval_5pct = self.min_interval * 0.05
        self.min_interval_10pct = self.min_interval * 0.10
        self.min_interval_15pct = self.min_interval * 0.15

        self.cumulative_expected_delay_ns: float = 0.0
        self.cumulative_actual_delay_ns: float = 0.0

        self.cumulative_throttle_wait_time_ns: float = 0.0

        self.reset()

        self.print_vars()

    ####################################################################
    # reset
    ####################################################################
    def reset(self) -> None:
        """Reset the variables to starting values."""
        self.idx = -1

        self.send_interval_sums = []
        self.exp_interval_sums = []

        # self.check_async_q_times = []
        # self.check_async_q_times2 = []
        # self.norm_check_async_q_times = []
        # self.norm_check_async_q_intervals = []
        #
        # self.norm_check_async_q_times2 = []
        # self.norm_check_async_q_intervals2 = []

        # self.obtained_nowaits = []
        # self.time_traces = []
        # self.stop_times = []

        self.before_req_times = []
        self.arrival_times = []

        self.wait_times = []

        self.req_times = []
        self.after_req_times = []

        self.send_times = []
        self.target_times = []
        self.target_intervals = []

        self.expected_times = []
        self.expected_intervals = []

        self.previous_delay = []
        self.current_delay = []

        self.enter_bucket_amt = []
        self.exit_bucket_amt = []
        self.avail_bucket_amt = []

        self.diff_req_intervals = []
        self.diff_req_ratio = []

        self.before_req_times = []
        self.arrival_times = []
        self.wait_times = []
        self.req_times = []
        self.after_req_times = []
        self.start_times = []

        self.norm_before_req_times = []
        self.norm_arrival_times = []
        self.norm_req_times = []
        self.norm_after_req_times = []
        self.norm_start_times = []

        self.norm_before_req_intervals = []
        self.norm_arrival_intervals = []
        self.norm_req_intervals = []
        self.norm_after_req_intervals = []
        self.norm_start_intervals = []

        self.norm_before_next_target_intervals = []
        self.norm_next_target_intervals = []

        self.mean_before_req_interval = 0.0
        self.mean_arrival_interval = 0.0
        self.mean_req_interval = 0.0
        self.mean_after_req_interval = 0.0

        self.before_next_target_times = []
        self.norm_before_next_target_times = []
        self.next_target_times = []
        self.norm_next_target_times = []

        self.t_entry_bucket_amt = []
        self.t_exit_bucket_amt = []

        self.mean_next_target_interval = 0.0

        self.path_times = []
        self.path_intervals = []

        self.path_async_times = []
        self.path_async_intervals = []

        # self.norm_time_traces_times = []
        # self.norm_time_traces_intervals = []

        self.norm_stop_times_times = []
        self.norm_stop_times_intervals = []

    ####################################################################
    # print_vars
    ####################################################################
    def print_vars(self) -> None:
        """Print the vars for the test case."""
        print(f"\n{self.reqs_per_sec=}")
        print(f"{self.seconds=}")
        print(f"{self.mode=}")
        print(f"{self.early_count=}")
        print(f"{self.bucket_size=}")
        print(f"{self.send_interval=}")
        print(f"{self.total_reqs_per_sec=}")
        print(f"{self.target_interval=}")
        print(f"{self.send_interval=}")
        print(f"{self.min_interval=}")
        print(f"{self.max_interval=}")
        print(f"{self.exp_total_time=}")

        # print(f"{self.t_throttle.lb_adjustment=}")
        # print(f"{self.t_throttle.lb_adjustment_ns=}")
        print(f"{self.t_throttle._next_target_time=}")
        print(f"{self.t_throttle._target_interval=}")

    ####################################################################
    # add_func_throttles
    ####################################################################
    def add_func_throttles(
        self, *args: FuncWithThrottleAttr[Callable[..., Any]]
    ) -> None:
        """Add the throttles for decorated functions to the validator.

        Args:
            args: the functions that have the throttles attached as
                    attributes

        """
        self.throttles = []
        for func in args:
            self.throttles.append(func.throttle)

    ####################################################################
    # build_async_exp_list
    ####################################################################
    def build_async_exp_list(self) -> None:
        """Build lists of async and sync expected intervals."""
        self.expected_intervals = [0.0]
        self.num_async_overs = 0
        send_interval_sum = 0.0
        exp_interval_sum = 0.0
        self.send_interval_sums = [0.0]
        self.exp_interval_sums = [0.0]
        for idx, send_interval in enumerate(self.send_intervals[1:], 1):
            # send_interval_sum = self.norm_arrival_times[idx]
            # send_interval_sum += send_interval
            send_interval_sum = self.norm_start_times[idx] + send_interval
            self.send_interval_sums.append(send_interval_sum)

            # exp_interval_sum += self._target_interval
            exp_interval_sum = self.norm_req_times[idx - 1] + self.target_interval
            self.exp_interval_sums.append(exp_interval_sum)

            if send_interval_sum <= exp_interval_sum:
                self.expected_intervals.append(self.target_interval)
            else:
                self.expected_intervals.append(
                    self.target_interval + (send_interval_sum - exp_interval_sum)
                )
                send_interval_sum = 0.0
                exp_interval_sum = 0.0
                self.num_async_overs += 1

    ####################################################################
    # build_sync_exp_list
    ####################################################################
    def build_sync_exp_list(self) -> None:
        """Build lists of async and sync expected intervals."""
        self.expected_intervals = [0.0]
        for send_interval in self.send_intervals[1:]:
            self.expected_intervals.append(max(self.target_interval, send_interval))

    ####################################################################
    # build_sync_ec_exp_list
    ####################################################################
    def build_sync_ec_exp_list(self) -> None:
        """Build list of sync ec expected intervals."""
        self.expected_intervals = [0.0]
        current_interval_sum = 0.0
        # the very first request is counted as early, and each
        # first request of each new target interval is counted as
        # early
        current_early_count = 0
        current_target_interval = 0.0
        for send_interval in self.send_intervals[1:]:
            current_target_interval += self.target_interval
            current_interval_sum += send_interval
            interval_remaining = current_target_interval - current_interval_sum
            # if this send is at or beyond the target interval
            if current_target_interval <= current_interval_sum:
                current_early_count = 0  # start a new series
                current_interval_sum = 0.0
                current_target_interval = 0.0
                self.expected_intervals.append(send_interval)
            else:  # this send is early
                if self.early_count <= current_early_count:
                    # we have exhausted our early count - must pause
                    current_early_count = 0  # start a new series
                    current_interval_sum = 0.0
                    current_target_interval = 0.0
                    self.expected_intervals.append(send_interval + interval_remaining)
                else:
                    current_early_count += 1
                    self.expected_intervals.append(send_interval)

    ####################################################################
    # build_sync_lb_exp_list
    ####################################################################
    def build_sync_lb_exp_list(self) -> None:
        """Build list of sync lb expected intervals."""
        self.expected_intervals = [0.0]
        self.previous_delay = [0.0]
        self.current_delay = [0.0]

        bucket_capacity = self.bucket_size * self.target_interval
        current_bucket_amt = self.target_interval  # first send
        self.enter_bucket_amt = [0.0]
        self.exit_bucket_amt = [current_bucket_amt]
        self.avail_bucket_amt = [bucket_capacity - current_bucket_amt]
        if self.norm_arrival_intervals:
            intervals_to_use = self.norm_arrival_intervals
        else:
            intervals_to_use = self.send_intervals
        current_delay = 0.0
        for send_interval in intervals_to_use[1:]:
            previous_delay = current_delay
            current_delay = 0.0
            # remove the amount that leaked since the last send
            current_bucket_amt = max(
                0.0, current_bucket_amt - (send_interval - previous_delay)
            )
            self.enter_bucket_amt.append(current_bucket_amt)
            available_bucket_amt = bucket_capacity - current_bucket_amt
            self.avail_bucket_amt.append(available_bucket_amt)
            # add target interval amount

            self.previous_delay.append(previous_delay)

            if self.target_interval <= available_bucket_amt:
                current_bucket_amt += self.target_interval
                self.expected_intervals.append(
                    send_interval - previous_delay + current_delay
                )
            else:
                current_delay = self.target_interval - available_bucket_amt
                self.expected_intervals.append(
                    send_interval - previous_delay + current_delay
                )
                current_bucket_amt += self.target_interval - current_delay

            self.current_delay.append(current_delay)
            self.exit_bucket_amt.append(current_bucket_amt)

    ####################################################################
    # build time lists
    ####################################################################
    def build_times(self) -> None:
        """Build lists of times and intervals."""
        ################################################################
        # create list of target times and intervals
        ################################################################
        self.target_intervals = [0.0] + [
            self.target_interval for _ in range(len(self.req_times) - 1)
        ]
        self.target_times = list(it.accumulate(self.target_intervals))
        base_time: float = -1.0
        ################################################################
        # create list of start times and intervals
        ################################################################
        if self.start_times:
            assert len(self.start_times) == self.total_requests
            base_time = self.start_times[0]
            self.norm_start_times = [
                (item - base_time) * Pauser.NS_2_SECS for item in self.start_times
            ]
            self.norm_start_intervals = list(
                map(
                    lambda t1, t2: t1 - t2,
                    self.norm_start_times,
                    [0.0] + self.norm_start_times[:-1],
                )
            )

            self.mean_start_interval = self.norm_start_times[-1] / (
                self.total_requests - 1
            )

        ################################################################
        # create list of before request times and intervals
        ################################################################
        if self.before_req_times:
            assert len(self.before_req_times) == self.total_requests
            self.norm_before_req_times = [
                (item - base_time) * Pauser.NS_2_SECS for item in self.before_req_times
            ]
            self.norm_before_req_intervals = list(
                map(
                    lambda t1, t2: t1 - t2,
                    self.norm_before_req_times,
                    [0.0] + self.norm_before_req_times[:-1],
                )
            )

            self.mean_before_req_interval = self.norm_before_req_times[-1] / (
                self.total_requests - 1
            )

        ################################################################
        # create list of arrival times and intervals
        ################################################################
        if self.arrival_times:
            assert len(self.arrival_times) == self.total_requests
            # base_time2 = self.arrival_times[0]
            # self.norm_arrival_times = [
            # (item - base_time2) * Pauser.NS_2_SECS
            #                            for item in self.arrival_times]
            if base_time == -1.0:
                base_time = self.arrival_times[0]
            self.norm_arrival_times = [
                (item - base_time) * Pauser.NS_2_SECS for item in self.arrival_times
            ]
            self.norm_arrival_intervals = list(
                map(
                    lambda t1, t2: t1 - t2,
                    self.norm_arrival_times,
                    [0.0] + self.norm_arrival_times[:-1],
                )
            )

            self.mean_arrival_interval = self.norm_arrival_times[-1] / (
                self.total_requests - 1
            )

        ################################################################
        # create list of check async q times and intervals
        ################################################################
        # self.norm_check_async_q_times = [
        #     (item - base_time) * Pauser.NS_2_SECS
        #     for item in self.check_async_q_times]
        # self.norm_check_async_q_intervals = list(
        #     map(lambda t1, t2: t1 - t2,
        #         self.norm_check_async_q_times,
        #         [0.0] + self.norm_check_async_q_times[:-1]))

        ################################################################
        # create list of check async q times and intervals
        ################################################################
        # self.norm_check_async_q_times2 = [
        #     (item - base_time) * Pauser.NS_2_SECS
        #     for item in self.check_async_q_times2]
        # self.norm_check_async_q_intervals2 = list(
        #     map(lambda t1, t2: t1 - t2,
        #         self.norm_check_async_q_times2,
        #         [0.0] + self.norm_check_async_q_times2[:-1]))
        # self.mean_req_interval = (self.norm_req_times[-1]
        #                           / (len(self.norm_req_times) - 1))

        ################################################################
        # create list of request times and intervals
        ################################################################
        self.norm_req_times = [
            (item[1] - base_time) * Pauser.NS_2_SECS for item in self.req_times
        ]
        self.norm_req_intervals = list(
            map(
                lambda t1, t2: t1 - t2,
                self.norm_req_times,
                [0.0] + self.norm_req_times[:-1],
            )
        )
        self.mean_req_interval = self.norm_req_times[-1] / (
            len(self.norm_req_times) - 1
        )

        ################################################################
        # create list of after request times and intervals
        ################################################################
        if self.after_req_times:
            assert len(self.after_req_times) == self.total_requests
            self.norm_after_req_times = [
                (item - base_time) * Pauser.NS_2_SECS for item in self.after_req_times
            ]
            self.norm_after_req_intervals = list(
                map(
                    lambda t1, t2: t1 - t2,
                    self.norm_after_req_times,
                    [0.0] + self.norm_after_req_times[:-1],
                )
            )

            self.mean_after_req_interval = self.norm_after_req_times[-1] / (
                self.total_requests - 1
            )

        ################################################################
        # Build the expected intervals list
        ################################################################
        if self.num_threads > 1:
            self.send_intervals *= self.num_threads
        if self.mode == MODE_ASYNC:
            self.build_async_exp_list()
        elif self.mode == MODE_SYNC:
            self.build_sync_exp_list()
        elif self.mode == MODE_SYNC_EC:
            self.build_sync_ec_exp_list()
        elif self.mode == MODE_SYNC_LB:
            self.build_sync_lb_exp_list()

        self.expected_times = list(it.accumulate(self.expected_intervals))
        self.send_times = list(it.accumulate(self.send_intervals))

        ################################################################
        # create list of diff and diff pct on req_intervals/exp_req_int
        ################################################################
        self.diff_req_intervals = list(
            map(
                lambda t1, t2: t1 - t2, self.norm_req_intervals, self.expected_intervals
            )
        )

        self.diff_req_ratio = [
            item / self.target_interval for item in self.diff_req_intervals
        ]

        ################################################################
        # create list of before next target times and intervals
        ################################################################
        if self.before_next_target_times:
            assert len(self.before_next_target_times) == self.total_requests
            # base_time = self.before_next_target_times[0]
            self.norm_before_next_target_times = [
                (item - base_time) * Pauser.NS_2_SECS
                for item in self.before_next_target_times
            ]
            self.norm_before_next_target_intervals = list(
                map(
                    lambda t1, t2: t1 - t2,
                    self.norm_before_next_target_times,
                    [0.0] + self.norm_before_next_target_times[:-1],
                )
            )

        ################################################################
        # create list of next target times and intervals
        ################################################################
        if self.next_target_times:
            assert len(self.next_target_times) == self.total_requests
            # base_time = self.next_target_times[0]
            self.norm_next_target_times = [
                (item - base_time) * Pauser.NS_2_SECS for item in self.next_target_times
            ]
            self.norm_next_target_intervals = list(
                map(
                    lambda t1, t2: t1 - t2,
                    self.norm_next_target_times,
                    [0.0] + self.norm_next_target_times[:-1],
                )
            )

            self.mean_next_target_interval = self.norm_next_target_times[-1] / (
                self.total_requests - 1
            )

        ################################################################
        # create list of time traces from pauser
        ################################################################
        # for time_trace in self.time_traces:
        #     norm_time_traces_times = [(item - base_time)
        #                                    * Pauser.NS_2_SECS
        #                                    for item in time_trace]
        #     norm_time_traces_intervals = list(
        #         map(lambda t1, t2: t1 - t2,
        #             norm_time_traces_times,
        #             [0.0] + norm_time_traces_times[:-1]))
        #     self.norm_time_traces_times.append(norm_time_traces_times)
        #     self.norm_time_traces_intervals.append(norm_time_traces_intervals)
        #
        # self.norm_stop_times_times = [
        # (item - base_time) * Pauser.NS_2_SECS
        #                               for item in self.stop_times]
        # self.norm_stop_times_intervals = list(
        #     map(lambda t1, t2: t1 - t2,
        #         self.norm_stop_times_times,
        #         [0.0] + self.norm_stop_times_times[:-1]))

        ################################################################
        # create list of path times and intervals
        ################################################################
        if self.num_threads < 2:
            for idx in range(self.total_requests):
                self.path_times.append(
                    [
                        self.norm_start_times[idx],
                        self.norm_before_req_times[idx],
                        self.norm_arrival_times[idx],
                        self.norm_req_times[idx],
                        self.norm_after_req_times[idx],
                    ]
                )

            for item in self.path_times:
                self.path_intervals.append(
                    [
                        item[1] - item[0],
                        item[2] - item[1],
                        item[3] - item[2],
                        item[4] - item[3],
                    ]
                )

        ################################################################
        # create list of async path times and intervals
        ################################################################
        # for idx in range(self.total_requests):
        #     self.path_async_times.append([self.norm_check_async_q_times[idx],
        #                                   self.norm_check_async_q_times2[idx],
        #                                   (self.norm_next_target_times[idx]
        #                                    - self._target_interval),
        #                                   self.norm_req_times[idx],
        #                                   self.norm_next_target_times[idx]
        #                                   ])
        #
        # for item in self.path_async_times:
        #     self.path_async_intervals.append(
        #         [item[1] - item[0],
        #          item[2] - item[1],
        #          item[3] - item[2],
        #          item[4] - item[3]]
        #     )

    ####################################################################
    # print_intervals
    ####################################################################
    def print_intervals(self) -> None:
        """Build the expected intervals arrays."""
        print(f"{self.norm_req_times[-1]=}")
        print(f"{self.mean_req_interval=}")
        print(f"{self.mean_before_req_interval=}")
        print(f"{self.mean_arrival_interval=}")
        print(f"{self.norm_arrival_times[-1]=}")
        print(f"{self.mean_after_req_interval=}")
        print(f"{self.mean_start_interval=}")
        print(f"{self.num_async_overs=}")

        ################################################################
        # build printable times
        ################################################################
        idx_list = list(range(self.total_requests))

        p_idx_list = list(map(lambda num: f"{num: 7}", idx_list))
        # p_obtained_nowaits = list(map(lambda tf: f'{tf: 7}',
        #                               self.obtained_nowaits))
        p_send_times = list(map(lambda num: f"{num: 7.3f}", self.send_times))
        p_send_interval_sums = list(
            map(lambda num: f"{num: 7.3f}", self.send_interval_sums)
        )
        p_exp_interval_sums = list(
            map(lambda num: f"{num: 7.3f}", self.exp_interval_sums)
        )
        p_target_times = list(map(lambda num: f"{num: 7.3f}", self.target_times))

        if self.wait_times:
            p_wait_times = list(map(lambda num: f"{num: 7.3f}", self.wait_times))
        else:
            p_wait_times = []

        p_expected_times = list(map(lambda num: f"{num: 7.3f}", self.expected_times))

        # p_check_q_times = list(map(lambda num: f'{num: 7.3f}',
        #                        self.norm_check_async_q_times))

        p_before_req_times = list(
            map(lambda num: f"{num: 7.3f}", self.norm_before_req_times)
        )
        p_arrival_times = list(map(lambda num: f"{num: 7.3f}", self.norm_arrival_times))
        p_norm_req_times = list(map(lambda num: f"{num: 7.3f}", self.norm_req_times))
        p_after_req_times = list(
            map(lambda num: f"{num: 7.3f}", self.norm_after_req_times)
        )
        p_start_times = list(map(lambda num: f"{num: 7.3f}", self.norm_start_times))

        # p_time_traces_times = []
        # for time_trace in self.norm_time_traces_times:
        #     p_time_traces_time = list(map(lambda num: f'{num: 7.3f}',
        #                               time_trace))
        #     p_time_traces_times.append(p_time_traces_time)
        # p_stop_times_times = list(map(lambda num: f'{num: 7.3f}',
        #                               self.norm_stop_times_times))

        ################################################################
        # build printable intervals
        ################################################################
        p_send_intervals = list(map(lambda num: f"{num: 7.3f}", self.send_intervals))
        p_target_intervals = list(
            map(lambda num: f"{num: 7.3f}", self.target_intervals)
        )

        p_expected_intervals = list(
            map(lambda num: f"{num: 7.3f}", self.expected_intervals)
        )

        # p_check_q_intervals = list(map(lambda num: f'{num: 7.3f}',
        #                            self.norm_check_async_q_intervals))

        p_before_req_intervals = list(
            map(lambda num: f"{num: 7.3f}", self.norm_before_req_intervals)
        )
        p_arrival_intervals = list(
            map(lambda num: f"{num: 7.3f}", self.norm_arrival_intervals)
        )
        p_req_intervals = list(map(lambda num: f"{num: 7.3f}", self.norm_req_intervals))
        p_after_req_intervals = list(
            map(lambda num: f"{num: 7.3f}", self.norm_after_req_intervals)
        )
        p_send = list(map(lambda num: f"{num: 7.3f}", self.norm_start_intervals))

        p_diff_intervals = list(
            map(lambda num: f"{num: 7.3f}", self.diff_req_intervals)
        )
        p_diff_ratio = list(map(lambda num: f"{num: 7.3f}", self.diff_req_ratio))

        if self.previous_delay:
            p_previous_delay = list(
                map(lambda num: f"{num: 7.3f}", self.previous_delay)
            )
            p_current_delay = list(map(lambda num: f"{num: 7.3f}", self.current_delay))
            p_current_delay = list(map(lambda num: f"{num: 7.3f}", self.current_delay))
            p_current_delay = list(map(lambda num: f"{num: 7.3f}", self.current_delay))
            p_enter_bucket_amt = list(
                map(lambda num: f"{num: 7.3f}", self.enter_bucket_amt)
            )
            p_exit_bucket_amt = list(
                map(lambda num: f"{num: 7.3f}", self.exit_bucket_amt)
            )
            p_avail_bucket_amt = list(
                map(lambda num: f"{num: 7.3f}", self.avail_bucket_amt)
            )
        else:
            p_previous_delay = []
            p_current_delay = []
            p_enter_bucket_amt = []
            p_exit_bucket_amt = []
            p_avail_bucket_amt = []

        if self.norm_before_next_target_times:
            p_b4_next_t_times = list(
                map(lambda num: f"{num: 7.3f}", self.norm_before_next_target_times)
            )
            p_b4_next_t_intervals = list(
                map(lambda num: f"{num: 7.3f}", self.norm_before_next_target_intervals)
            )
        else:
            p_b4_next_t_times = []
            p_b4_next_t_intervals = []

        if self.norm_next_target_times:
            p_next_t_times = list(
                map(lambda num: f"{num: 7.3f}", self.norm_next_target_times)
            )
            p_next_t_intervals = list(
                map(lambda num: f"{num: 7.3f}", self.norm_next_target_intervals)
            )
        else:
            p_next_t_times = []
            p_next_t_intervals = []

        if self.t_entry_bucket_amt:
            p_t_entry_bucket_amt = list(
                map(lambda num: f"{num: 7.3f}", self.t_entry_bucket_amt)
            )
        else:
            p_t_entry_bucket_amt = []

        if self.t_exit_bucket_amt:
            p_t_exit_bucket_amt = list(
                map(lambda num: f"{num: 7.3f}", self.t_exit_bucket_amt)
            )
        else:
            p_t_exit_bucket_amt = []

        # p_time_traces_intervals = []
        # for time_trace in self.norm_time_traces_intervals:
        #     p_time_traces_interval = list(
        #     map(lambda num: f'{num: 7.3f}',
        #         time_trace))
        #     p_time_traces_intervals.append(p_time_traces_interval)
        #
        # p_stop_times_intervals = list(map(lambda num: f'{num: 7.3f}',
        #                               self.norm_stop_times_intervals))

        print(f"\n{p_idx_list            =}")  # noqa E221 E251
        # print(f'{p_obtained_nowaits    =}')
        print(f"{p_send_times          =}")  # noqa E221 E251
        print(f"{p_target_times        =}")  # noqa E221 E251
        print(f"{p_expected_times      =}")  # noqa E221 E251

        print(f"\n{p_start_times         =}")  # noqa E221 E251
        print(f"{p_before_req_times    =}")  # noqa E221 E251
        print(f"{p_arrival_times       =}")  # noqa E221 E251
        # print(f'{p_check_q_times       =}')
        print(f"{p_norm_req_times      =}")  # noqa E221 E251
        print(f"{p_after_req_times     =}")  # noqa E221 E251

        print(f"\n{p_send_intervals      =}")  # noqa E221 E251
        print(f"{p_send_interval_sums  =}")  # noqa E221 E251
        print(f"{p_exp_interval_sums   =}")  # noqa E221 E251
        print(f"{p_target_intervals    =}")  # noqa E221 E251
        print(f"{p_expected_intervals  =}")  # noqa E221 E251

        # print(f"\n{p_start_intervals     =}")  # noqa E221 E251
        print(f"{p_before_req_intervals=}")
        print(f"{p_arrival_intervals   =}")  # noqa E221 E251
        # print(f'{p_check_q_intervals   =}')
        print(f"{p_req_intervals       =}")  # noqa E221 E251
        print(f"{p_after_req_intervals =}")  # noqa E221 E251

        print(f"\n{p_diff_intervals      =}")  # noqa E221 E251
        print(f"{p_diff_ratio          =}")  # noqa E221 E251

        print(f"\n{p_previous_delay      =}")  # noqa E221 E251

        print(f"\n{p_arrival_times       =}")  # noqa E221 E251
        print(f"{p_b4_next_t_times     =}")  # noqa E221 E251
        print(f"{p_next_t_times        =}")  # noqa E221 E251

        print(f"\n{p_b4_next_t_intervals =}")  # noqa E221 E251
        print(f"{p_next_t_intervals    =}")  # noqa E221 E251

        print(f"\n{p_enter_bucket_amt    =}")  # noqa E221 E251
        print(f"{p_t_entry_bucket_amt  =}")  # noqa E221 E251

        print(f"\n{p_current_delay       =}")  # noqa E221 E251
        print(f"{p_wait_times          =}")  # noqa E221 E251

        print(f"\n{p_exit_bucket_amt     =}")  # noqa E221 E251
        print(f"{p_t_exit_bucket_amt   =}")  # noqa E221 E251

        print(f"\n{p_avail_bucket_amt    =}")  # noqa E221 E251

        # if self.throttle_mode == MODE_ASYNC:
        #     flowers(['path times:',
        #              'start before_req req after_req'])
        #     for idx, item in enumerate(self.path_times):
        #         line = (f'{item[0]: .3f} '
        #                 f'{item[1]: .3f} '
        #                 f'{item[3]: .3f} '
        #                 f'{item[4]: .3f} ')
        #         print(f'{idx:>3}: {line}')
        #
        #     flowers(['path intervals',
        #             'before_req req after_req wait'])
        #     for idx, item in enumerate(self.path_intervals):
        #         line = (f'{item[0]: .3f} '
        #                 f'{item[2]: .3f} '
        #                 f'{item[3]: .3f} ')
        #         print(f'{idx:>3}: {line}')
        # else:

        # for p_time_trace in p_time_traces_times:
        #     print(f'{p_time_trace[0]=}  {p_time_trace[-1]=}')
        # for p_time_interval in p_time_traces_intervals:
        #     print(f'{p_time_interval[0]=}  {p_time_interval[-1]=}')
        # print(f'{p_time_traces_times[3][0] =}')
        # print(f'{p_stop_times_times     =}')
        # print(f'{p_stop_times_intervals =}')

        flowers(
            [
                "path times:",
                "idx  start   b4_req arrival   req    af_req    check "
                "  pre-req pre-req2 "
                "  req "
                "  nxt-trg",
            ]
        )
        for idx, item in enumerate(self.path_times):
            line = (
                f"{item[0]: 7.3f} "
                f"{item[1]: 7.3f} "
                f"{item[2]: 7.3f} "
                f"{item[3]: 7.3f} "
                f"{item[4]: 7.3f} "
            )
            # line2 = (f'{self.path_async_times[idx][0]: 7.3f} '
            #          f'{self.path_async_times[idx][1]: 7.3f} '
            #          f'{self.path_async_times[idx][2]: 7.3f} '
            #          f'{self.path_async_times[idx][3]: 7.3f} '
            #          f'{self.path_async_times[idx][4]: 7.3f} ')
            # print(f'{idx:>3}: {line}   {line2}')
            print(f"{idx:>3}: {line}")

        flowers(
            [
                "path intervals",
                "idx  b4_req arrival   req    af_req    pre-req   "
                "pre-req2 req "
                "  nxt-trg",
            ]
        )
        for idx, item in enumerate(self.path_intervals):
            line = (
                f"{item[0]: 7.3f} "
                f"{item[1]: 7.3f} "
                f"{item[2]: 7.3f} "
                f"{item[3]: 7.3f} "
            )

            # line2 = (f'{self.path_async_intervals[idx][0]: 7.3f} '
            #          f'{self.path_async_intervals[idx][1]: 7.3f} '
            #          f'{self.path_async_intervals[idx][2]: 7.3f} '
            #          f'{self.path_async_intervals[idx][3]: 7.3f} ')
            # print(f'{idx:>3}: {line}   {line2}')
            print(f"{idx:>3}: {line}")

        flowers("stats")
        diff_mean = stats.mean(self.diff_req_intervals[1:])
        print(f"{diff_mean=:.3f}")

        diff_median = stats.median(self.diff_req_intervals[1:])
        print(f"{diff_median=:.3f}")

        diff_pvariance = stats.pvariance(self.diff_req_intervals[1:])
        print(f"{diff_pvariance=:.5f}")

        diff_pstdev = stats.pstdev(self.diff_req_intervals[1:])
        print(f"{diff_pstdev=:.3f}")

        diff_variance = stats.variance(self.diff_req_intervals[1:])
        print(f"{diff_variance=:.5f}")

        diff_stdev = stats.stdev(self.diff_req_intervals[1:])
        print(f"{diff_stdev=:.3f}")

        # plt.style.use('_mpl-gallery')

        # make data
        # np.random.seed(1)
        # x = 4 + np.random.normal(0, 1.5, 200)

        # plot:
        # fig, ax = plt.subplots()
        #
        # ax.hist(self.diff_req_intervals,
        #         bins=16,
        #         linewidth=0.5,
        #         edgecolor="white")

        # ax.set(xlim=(0, 8), xticks=np.arange(1, 8),
        #        ylim=(0, 56), yticks=np.linspace(0, 56, 9))

        # plt.show()

    ####################################################################
    # validate_series
    ####################################################################
    def validate_series(self) -> None:
        """Validate the requests.

        Raises:
            InvalidModeNum: Mode must be 1, 2, 3, or 4

        """
        assert 0 < self.total_requests
        assert len(self.req_times) == self.total_requests

        for idx, req_item in enumerate(self.req_times):
            assert idx == req_item[0]

        ################################################################
        # create list of target, actual, expected times and intervals
        ################################################################
        self.build_times()

        if (self.mode == MODE_ASYNC) or (self.mode == MODE_SYNC):
            self.validate_async_sync()
        elif self.mode == MODE_SYNC_EC:
            self.validate_sync_ec()
        elif self.mode == MODE_SYNC_LB:
            self.validate_sync_lb()
        else:
            raise InvalidModeNum("Mode must be 1, 2, 3, or 4")

        self.reset()

    ####################################################################
    # validate_series2
    ####################################################################
    def validate_series2(self) -> None:
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
        # create list of target, actual, expected times and intervals
        ################################################################
        # self.build_times()

        if (self.mode == MODE_ASYNC) or (self.mode == MODE_SYNC):
            self.validate_async_sync()
        elif self.mode == MODE_SYNC_EC:
            self.validate_sync_ec()
        elif self.mode == MODE_SYNC_LB:
            self.validate_sync_lb2()
        else:
            raise InvalidModeNum("Mode must be 1, 2, 3, or 4")

        self.reset()

    ####################################################################
    # process_request_items
    ####################################################################
    def process_request_items(self) -> None:
        """Validate the results for sync leaky bucket."""
        # Calculate the interval between request send and exit receive
        # as observed by the requestor.

        self.request_items[0].expected_delay_ns = 0

        self.request_items[0].expected_func_arrival_time_ns = self.request_items[
            0
        ].send_time_ns

        self.request_items[0].actual_delay_ns = (
            self.request_items[0].actual_func_arrival_time_ns
            - self.request_items[0].send_time_ns
        )
        for idx in range(1, len(self.request_items)):
            # if request_item.throttle_mode == MODE_ASYNC:
            self.request_items[idx].expected_delay_ns = max(
                0,
                self.request_items[idx - 1].throttle_next_target_time
                - self.request_items[idx].send_time_ns,
            )
            self.request_items[idx].expected_func_arrival_time_ns = (
                self.request_items[idx].send_time_ns
                + self.request_items[idx].expected_delay_ns
            )
            self.request_items[idx].actual_delay_ns = (
                self.request_items[idx].actual_func_arrival_time_ns
                - self.request_items[idx].send_time_ns
            )
            assert (
                self.request_items[idx].expected_delay_ns
                <= self.request_items[idx].actual_delay_ns
            )

            self.cumulative_expected_delay_ns += self.request_items[
                idx
            ].expected_delay_ns
            self.cumulative_actual_delay_ns += self.request_items[idx].actual_delay_ns

            self.cumulative_throttle_wait_time_ns += self.request_items[
                idx
            ].throttle_wait_time_ns

    ####################################################################
    # validate_async_sync
    ####################################################################
    def validate_async_sync(self) -> None:
        """Validate the results for sync leaky bucket."""

        self.process_request_items()
        print(
            "\ninterval times: arrival idx| send | throttle arrival | expected arrival | "
            "actual arrival | expected delay | actual delay | diff ratio"
        )

        first_send_time = self.request_items[0].send_time_ns
        for req_item in self.request_items:
            extra_time = 0.0
            if req_item.expected_delay_ns == 0.0:
                extra_time = self.request_interval_ns
            expected_actual_diff_ratio = (
                req_item.actual_delay_ns - req_item.expected_delay_ns
            ) / (req_item.expected_delay_ns + extra_time)
            print(
                f"req_id: {req_item.req_id:2} "
                f"| {req_item.arrival_idx:2} "
                f"| {(req_item.send_time_ns - first_send_time) * NS_2_SECS:.4f} "
                f"| {(req_item.throttle_arrival_time - first_send_time) * NS_2_SECS:.4f}"
                f"| {(req_item.expected_func_arrival_time_ns - first_send_time) * NS_2_SECS:.4f}"
                f"| {(req_item.actual_func_arrival_time_ns - first_send_time) * NS_2_SECS:.4f}"
                f"| {req_item.expected_delay_ns * NS_2_SECS:.4f} "
                f"| {req_item.actual_delay_ns * NS_2_SECS:.4f} "
                f"| {expected_actual_diff_ratio * NS_2_SECS:.4f} "
            )

        # print(f"{throttle_verifier.num_excessive_request_delays=}")
        print(f"{self.cumulative_expected_delay_ns=}")
        print(f"{self.cumulative_actual_delay_ns=}")
        # print(f"{throttle_verifier.cumulative_throttle_wait_time_ns=}")
        extra_time = 0.0
        if self.cumulative_expected_delay_ns == 0.0:
            extra_time = 0.0001
        ratio_delay_time = (
            self.cumulative_actual_delay_ns - self.cumulative_expected_delay_ns
        ) / (self.cumulative_expected_delay_ns + extra_time)
        print(f"ratio diff expected/actual: {ratio_delay_time:.4f}")

        # assert throttle_verifier.num_excessive_request_delays < 4
        assert ratio_delay_time <= 0.15

    ####################################################################
    # validate_sync_ec
    ####################################################################
    def validate_sync_ec(self) -> None:
        """Validate results for sync early count."""
        self.print_intervals()
        num_early = 0
        num_early_1pct = 0
        num_early_5pct = 0
        num_early_10pct = 0
        num_early_15pct = 0

        num_late = 0
        num_late_1pct = 0
        num_late_5pct = 0
        num_late_10pct = 0
        num_late_15pct = 0

        for ratio in self.diff_req_ratio[1:]:
            if ratio < 0:  # if negative
                num_early += 1
                if ratio <= -0.01:
                    num_early_1pct += 1
                if ratio <= -0.05:
                    num_early_5pct += 1
                if ratio <= -0.10:
                    num_early_10pct += 1
                if ratio <= -0.15:
                    num_early_15pct += 1
            else:
                num_late += 1
                if 0.01 <= ratio:
                    num_late_1pct += 1
                if 0.05 <= ratio:
                    num_late_5pct += 1
                if 0.10 <= ratio:
                    num_late_10pct += 1
                if 0.15 <= ratio:
                    num_late_15pct += 1

        print(f"{num_early=}")
        print(f"{num_early_1pct=}")
        print(f"{num_early_5pct=}")
        print(f"{num_early_10pct=}")
        print(f"{num_early_15pct=}")

        print(f"{num_late=}")
        print(f"{num_late_1pct=}")
        print(f"{num_late_5pct=}")
        print(f"{num_late_10pct=}")
        print(f"{num_late_15pct=}")

        assert num_early_10pct == 0
        assert num_early_5pct == 0
        # assert num_long_early_1pct == 0

        assert num_late_15pct < 3
        assert num_late_10pct < 4
        assert num_late_5pct < 5
        # assert num_long_late_1pct == 0

        assert self.expected_times[-1] <= self.norm_req_times[-1]

        worst_case_mean_interval = (
            self.target_interval * (self.total_requests - self.early_count - 1)
        ) / (self.total_requests - 1)
        assert worst_case_mean_interval <= self.mean_req_interval

    ####################################################################
    # validate_sync_lb
    ####################################################################
    def validate_sync_lb(self) -> None:
        """Validate the results for sync leaky bucket."""
        self.print_intervals()
        num_early = 0
        num_early_1pct = 0
        num_early_5pct = 0
        num_early_10pct = 0
        num_early_15pct = 0

        num_late = 0
        num_late_1pct = 0
        num_late_5pct = 0
        num_late_10pct = 0
        num_late_15pct = 0

        for ratio in self.diff_req_ratio[1:]:
            if ratio < 0:  # if negative
                num_early += 1
                if ratio <= -0.01:
                    num_early_1pct += 1
                if ratio <= -0.05:
                    num_early_5pct += 1
                if ratio <= -0.10:
                    num_early_10pct += 1
                if ratio <= -0.15:
                    num_early_15pct += 1
            else:
                num_late += 1
                if 0.01 <= ratio:
                    num_late_1pct += 1
                if 0.05 <= ratio:
                    num_late_5pct += 1
                if 0.10 <= ratio:
                    num_late_10pct += 1
                if 0.15 <= ratio:
                    num_late_15pct += 1

        print(f"{num_early=}")
        print(f"{num_early_1pct=}")
        print(f"{num_early_5pct=}")
        print(f"{num_early_10pct=}")
        print(f"{num_early_15pct=}")

        print(f"{num_late=}")
        print(f"{num_late_1pct=}")
        print(f"{num_late_5pct=}")
        print(f"{num_late_10pct=}")
        print(f"{num_late_15pct=}")

        assert num_early_10pct == 0
        assert num_early_5pct == 0
        # assert num_long_early_1pct == 0

        assert num_late_15pct < 3
        assert num_late_10pct < 4
        assert num_late_5pct < 5
        # assert num_long_late_1pct == 0

        assert self.expected_times[-1] <= self.norm_req_times[-1]

        worst_case_mean_interval = (
            self.target_interval * (self.total_requests - self.bucket_size)
        ) / self.total_requests
        assert worst_case_mean_interval <= self.mean_req_interval

    ####################################################################
    # validate_sync_lb2
    ####################################################################
    def validate_sync_lb2(self) -> None:
        """Validate the results for sync leaky bucket."""

        throttle_verifier = ThrottleVerifier(
            reqs_per_sec=self.requests,
            seconds=self.seconds,
            bucket_size=self.bucket_size,
        )
        print(
            "\ninterval times: idx| throttle arrival interval sec | throttle wait_time sec | func arrival interval sec"
        )
        prev_arrival_time = self.request_items[0].throttle_arrival_time
        for req_item in self.request_items:
            print(
                f"idx: {req_item.arrival_idx} "
                f"| {(req_item.throttle_arrival_time - prev_arrival_time) * NS_2_SECS:.2f} "
                f"| {req_item.throttle_wait_time_ns * NS_2_SECS:.2f} "
                f"| {(req_item.actual_func_arrival_time_ns - req_item.throttle_arrival_time) * NS_2_SECS:.2f}"
            )
            prev_arrival_time = req_item.throttle_arrival_time

        for req_item in self.request_items:
            throttle_verifier.verify_request(request_item=req_item)

        print(f"{throttle_verifier.num_excessive_request_delays=}")
        print(f"{throttle_verifier.cumulative_expected_delay_ns=}")
        print(f"{throttle_verifier.cumulative_actual_delay_ns=}")
        print(f"{throttle_verifier.cumulative_throttle_wait_time_ns=}")
        ratio_expected_to_actual_wait_time = (
            throttle_verifier.cumulative_throttle_wait_time_ns + 1000
        ) / (throttle_verifier.cumulative_expected_delay_ns + 1000)
        print(f"ratio expected/actual: {ratio_expected_to_actual_wait_time:.2f}")

        assert throttle_verifier.num_excessive_request_delays < 4
        assert ratio_expected_to_actual_wait_time >= 0.95

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
        request_item.throttle_arrival_time = self.t_throttle._arrival_time
        request_item.throttle_next_target_time = self.t_throttle._next_target_time
        request_item.throttle_wait_time_ns = self.t_throttle._wait_time_ns
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
        request_item = self.request_item[self.idx]
        assert request_item.req_id == self.idx
        request_item.arrival_idx = self.idx  # first is zero
        request_item.actual_func_arrival_time_ns = perf_counter_ns()
        request_item.throttle_arrival_time = self.t_throttle._arrival_time
        request_item.throttle_next_target_time = self.t_throttle._next_target_time
        request_item.throttle_wait_time_ns = self.t_throttle._wait_time_ns
        self.request_items.append(request_item)

        # logger.debug("request0b exiting")
        return request_item.req_id

    ####################################################################
    # request1b
    ####################################################################
    def request1b(self, idx: int) -> int:
        """Request1 target.

        Args:
            idx: the index of the call

        Returns:
            the index reflected back
        """
        self.idx += 1
        request_item = self.request_item[self.idx]
        request_item.arrival_idx = self.idx  # first is zero
        request_item.actual_func_arrival_time_ns = perf_counter_ns()
        request_item.throttle_arrival_time = self.t_throttle._arrival_time
        request_item.throttle_next_target_time = self.t_throttle._next_target_time
        request_item.throttle_wait_time_ns = self.t_throttle._wait_time_ns
        self.request_items.append(request_item)

        return request_item.req_id

    ####################################################################
    # request2b
    ####################################################################
    # def request2b(self, idx: int, requests: int,
    # obtained_nowait: bool) -> int:
    def request2b(self, idx: int, requests: int) -> int:
        """Request2 target.

        Args:
            idx: the index of the call
            requests: number of requests for the throttle

        Returns:
            the index reflected back
        """
        self.idx += 1
        request_item = self.request_item[self.idx]
        request_item.arrival_idx = self.idx  # first is zero
        request_item.actual_func_arrival_time_ns = perf_counter_ns()
        request_item.throttle_arrival_time = self.t_throttle._arrival_time
        request_item.throttle_next_target_time = self.t_throttle._next_target_time
        request_item.throttle_wait_time_ns = self.t_throttle._wait_time_ns
        self.request_items.append(request_item)

        assert idx == request_item.req_id
        assert requests == self.requests
        return request_item.req_id

    ####################################################################
    # request3b
    ####################################################################
    def request3b(self, *, idx: int) -> int:
        """Request3 target.

        Args:
            idx: the index of the call

        Returns:
            the index reflected back
        """
        self.idx += 1
        request_item = self.request_item[self.idx]
        request_item.arrival_idx = self.idx  # first is zero
        request_item.actual_func_arrival_time_ns = perf_counter_ns()
        request_item.throttle_arrival_time = self.t_throttle._arrival_time
        request_item.throttle_next_target_time = self.t_throttle._next_target_time
        request_item.throttle_wait_time_ns = self.t_throttle._wait_time_ns
        self.request_items.append(request_item)

        assert idx == request_item.req_id

        return request_item.req_id

    ####################################################################
    # request4b
    ####################################################################
    def request4b(self, *, idx: int, seconds: int) -> int:
        """Request4 target.

        Args:
            idx: the index of the call
            seconds: number of seconds for the throttle

        Returns:
            the index reflected back
        """
        self.idx += 1
        request_item = self.request_item[self.idx]
        request_item.arrival_idx = self.idx  # first is zero
        request_item.actual_func_arrival_time_ns = perf_counter_ns()
        request_item.throttle_arrival_time = self.t_throttle._arrival_time
        request_item.throttle_next_target_time = self.t_throttle._next_target_time
        request_item.throttle_wait_time_ns = self.t_throttle._wait_time_ns
        self.request_items.append(request_item)

        assert idx == request_item.req_id
        assert seconds == self.seconds
        return request_item.req_id

    ####################################################################
    # request5b
    ####################################################################
    def request5b(self, idx: int, *, interval: float) -> int:
        """Request5 target.

        Args:
            idx: the index of the call
            interval: the interval used between requests

        Returns:
            the index reflected back
        """
        self.idx += 1
        request_item = self.request_item[self.idx]
        request_item.arrival_idx = self.idx  # first is zero
        request_item.actual_func_arrival_time_ns = perf_counter_ns()
        request_item.throttle_arrival_time = self.t_throttle._arrival_time
        request_item.throttle_next_target_time = self.t_throttle._next_target_time
        request_item.throttle_wait_time_ns = self.t_throttle._wait_time_ns
        self.request_items.append(request_item)

        assert idx == request_item.req_id
        assert interval == self.send_interval
        return request_item.req_id

    ####################################################################
    # request6b
    ####################################################################
    def request6b(
        self, idx: int, requests: int, *, seconds: int, interval: float
    ) -> int:
        """Request5 target.

         Args:
            idx: the index of the call
            requests: number of requests for the throttle
            seconds: number of seconds for the throttle
            interval: the interval used between requests

        Returns:
            the index reflected back
        """
        self.idx += 1
        request_item = self.request_item[self.idx]
        request_item.arrival_idx = self.idx  # first is zero
        request_item.actual_func_arrival_time_ns = perf_counter_ns()
        request_item.throttle_arrival_time = self.t_throttle._arrival_time
        request_item.throttle_next_target_time = self.t_throttle._next_target_time
        request_item.throttle_wait_time_ns = self.t_throttle._wait_time_ns
        self.request_items.append(request_item)

        assert idx == request_item.req_id
        assert requests == self.requests
        assert seconds == self.seconds
        assert interval == self.send_interval
        return request_item.req_id

    ####################################################################
    # request0
    ####################################################################
    def request0(self) -> int:
        """Request0 target.

        Returns:
            the index reflected back
        """
        self.idx += 1
        self.req_times.append((self.idx, perf_counter_ns()))
        self.arrival_times.append(self.t_throttle._arrival_time)
        self.next_target_times.append(self.t_throttle._next_target_time)
        self.wait_times.append(self.t_throttle._wait_time_ns)
        # self.check_async_q_times.append(self.t_throttle._check_async_q_time)
        return self.idx

    ####################################################################
    # request1
    ####################################################################
    def request1(self, idx: int) -> int:
        """Request1 target.

        Args:
            idx: the index of the call

        Returns:
            the index reflected back
        """
        self.req_times.append((idx, perf_counter_ns()))
        self.arrival_times.append(self.t_throttle._arrival_time)
        self.next_target_times.append(self.t_throttle._next_target_time)
        self.wait_times.append(self.t_throttle._wait_time_ns)
        # self.check_async_q_times.append(self.t_throttle._check_async_q_time)
        assert idx == self.idx + 1
        self.idx = idx
        return idx

    ####################################################################
    # request2
    ####################################################################
    # def request2(self, idx: int, requests: int,
    # obtained_nowait: bool) -> int:
    def request2(self, idx: int, requests: int) -> int:
        """Request2 target.

        Args:
            idx: the index of the call
            requests: number of requests for the throttle

        Returns:
            the index reflected back
        """
        self.req_times.append((idx, perf_counter_ns()))
        self.arrival_times.append(self.t_throttle._arrival_time)
        self.next_target_times.append(self.t_throttle._next_target_time)
        self.wait_times.append(self.t_throttle._wait_time_ns)
        # self.check_async_q_times.append(self.t_throttle._check_async_q_time)
        # self.check_async_q_times2.append(self.t_throttle._check_async_q_time2)
        # self.obtained_nowaits.append(obtained_nowait)
        assert idx == self.idx + 1
        assert requests == self.requests
        self.idx = idx
        return idx

    ####################################################################
    # request3
    ####################################################################
    def request3(self, *, idx: int) -> int:
        """Request3 target.

        Args:
            idx: the index of the call

        Returns:
            the index reflected back
        """
        self.req_times.append((idx, perf_counter_ns()))
        self.arrival_times.append(self.t_throttle._arrival_time)
        self.next_target_times.append(self.t_throttle._next_target_time)
        self.wait_times.append(self.t_throttle._wait_time_ns)
        # self.check_async_q_times.append(self.t_throttle._check_async_q_time)
        assert idx == self.idx + 1
        self.idx = idx
        return idx

    ####################################################################
    # request4
    ####################################################################
    def request4(self, *, idx: int, seconds: int) -> int:
        """Request4 target.

        Args:
            idx: the index of the call
            seconds: number of seconds for the throttle

        Returns:
            the index reflected back
        """
        self.req_times.append((idx, perf_counter_ns()))
        self.arrival_times.append(self.t_throttle._arrival_time)
        self.next_target_times.append(self.t_throttle._next_target_time)
        self.wait_times.append(self.t_throttle._wait_time_ns)
        # self.check_async_q_times.append(self.t_throttle._check_async_q_time)
        assert idx == self.idx + 1
        assert seconds == self.seconds
        self.idx = idx
        return idx

    ####################################################################
    # request5
    ####################################################################
    def request5(self, idx: int, *, interval: float) -> int:
        """Request5 target.

        Args:
            idx: the index of the call
            interval: the interval used between requests

        Returns:
            the index reflected back
        """
        self.req_times.append((idx, perf_counter_ns()))
        self.arrival_times.append(self.t_throttle._arrival_time)
        self.next_target_times.append(self.t_throttle._next_target_time)
        self.wait_times.append(self.t_throttle._wait_time_ns)
        # self.check_async_q_times.append(self.t_throttle._check_async_q_time)
        assert idx == self.idx + 1
        assert interval == self.send_interval
        self.idx = idx
        return idx

    ####################################################################
    # request6
    ####################################################################
    def request6(
        self, idx: int, requests: int, *, seconds: int, interval: float
    ) -> int:
        """Request5 target.

         Args:
            idx: the index of the call
            requests: number of requests for the throttle
            seconds: number of seconds for the throttle
            interval: the interval used between requests

        Returns:
            the index reflected back
        """
        self.req_times.append((idx, perf_counter_ns()))
        self.arrival_times.append(self.t_throttle._arrival_time)
        self.next_target_times.append(self.t_throttle._next_target_time)
        self.wait_times.append(self.t_throttle._wait_time_ns)
        # self.t_entry_bucket_amt.append(self.t_throttle._entry_bucket_amt)
        # self.t_exit_bucket_amt.append(self.t_throttle._exit_bucket_amt)
        # self.check_async_q_times.append(self.t_throttle._check_async_q_time)
        assert idx == self.idx + 1
        assert requests == self.requests
        assert seconds == self.seconds
        assert interval == self.send_interval
        self.idx = idx
        return idx

    ####################################################################
    # Queue callback targets
    ####################################################################
    ####################################################################
    # callback0
    ####################################################################
    def callback0(self) -> None:
        """Queue the callback for request0."""
        self.idx += 1
        self.req_times.append((self.idx, perf_counter_ns()))
        self.arrival_times.append(self.t_throttle._arrival_time)
        self.next_target_times.append(self.t_throttle._next_target_time)
        # self.check_async_q_times.append(self.t_throttle._check_async_q_time)

    ####################################################################
    # callback1
    ####################################################################
    def callback1(self, idx: int) -> None:
        """Queue the callback for request0.

        Args:
            idx: index of the request call
        """
        self.req_times.append((idx, perf_counter_ns()))
        self.arrival_times.append(self.t_throttle._arrival_time)
        self.next_target_times.append(self.t_throttle._next_target_time)
        # self.check_async_q_times.append(self.t_throttle._check_async_q_time)
        assert idx == self.idx + 1
        self.idx = idx

    ####################################################################
    # callback2
    ####################################################################
    def callback2(self, idx: int, requests: int) -> None:
        """Queue the callback for request0.

        Args:
            idx: index of the request call
            requests: number of requests for the throttle
        """
        self.req_times.append((idx, perf_counter_ns()))
        self.arrival_times.append(self.t_throttle._arrival_time)
        self.next_target_times.append(self.t_throttle._next_target_time)
        # self.check_async_q_times.append(self.t_throttle._check_async_q_time)
        assert idx == self.idx + 1
        assert requests == self.requests
        self.idx = idx

    ####################################################################
    # callback3
    ####################################################################
    def callback3(self, *, idx: int) -> None:
        """Queue the callback for request0.

        Args:
            idx: index of the request call
        """
        self.req_times.append((idx, perf_counter_ns()))
        self.arrival_times.append(self.t_throttle._arrival_time)
        self.next_target_times.append(self.t_throttle._next_target_time)
        # self.check_async_q_times.append(self.t_throttle._check_async_q_time)
        assert idx == self.idx + 1
        self.idx = idx

    ####################################################################
    # callback4
    ####################################################################
    def callback4(self, *, idx: int, seconds: float) -> None:
        """Queue the callback for request0.

        Args:
            idx: index of the request call
            seconds: number of seconds for the throttle
        """
        self.req_times.append((idx, perf_counter_ns()))
        self.arrival_times.append(self.t_throttle._arrival_time)
        self.next_target_times.append(self.t_throttle._next_target_time)
        # self.check_async_q_times.append(self.t_throttle._check_async_q_time)
        assert idx == self.idx + 1
        assert seconds == self.seconds
        self.idx = idx

    ####################################################################
    # callback5
    ####################################################################
    def callback5(self, idx: int, *, interval: float) -> None:
        """Queue the callback for request0.

        Args:
            idx: index of the request call
            interval: interval between requests
        """
        self.req_times.append((idx, perf_counter_ns()))
        self.arrival_times.append(self.t_throttle._arrival_time)
        self.next_target_times.append(self.t_throttle._next_target_time)
        # self.check_async_q_times.append(self.t_throttle._check_async_q_time)
        assert idx == self.idx + 1
        assert 0.0 <= interval
        self.idx = idx

    ####################################################################
    # callback6
    ####################################################################
    def callback6(
        self, idx: int, requests: int, *, seconds: float, interval: float
    ) -> None:
        """Queue the callback for request0.

        Args:
            idx: index of the request call
            requests: number of requests for the throttle
            seconds: number of seconds for the throttle
            interval: interval between requests
        """
        self.req_times.append((idx, perf_counter_ns()))
        self.arrival_times.append(self.t_throttle._arrival_time)
        self.next_target_times.append(self.t_throttle._next_target_time)
        # self.check_async_q_times.append(self.t_throttle._check_async_q_time)
        assert idx == self.idx + 1
        assert requests == self.requests
        assert seconds == self.seconds
        assert 0.0 <= interval
        self.idx = idx


########################################################################
# TestThrottleDocstrings class
########################################################################
class TestThrottleDocstrings:
    """Class TestThrottleDocstrings."""

    ####################################################################
    # test_throttle_example_1
    ####################################################################
    def test_throttle_example_1(self) -> None:
        """Method test_throttle_example_1."""
        flowers("Example for README:")

        import time
        from scottbrian_throttle.throttle import throttle_sync

        @throttle_sync(reqs_per_sec=3)
        def make_request(idx: int, previous_arrival_time: float) -> float:
            arrival_time = time.time()
            if idx == 0:
                previous_arrival_time = arrival_time
            interval = arrival_time - previous_arrival_time
            print(f"request {idx} interval from previous: {interval:0.2f} " f"seconds")
            return arrival_time

        previous_time = 0.0
        for i in range(10):
            previous_time = make_request(i, previous_time)

    ####################################################################
    # test_throttle_example_2
    ####################################################################
    def test_throttle_example_2(self, capsys: Any) -> None:
        """Method test_throttle_example_2.

        Args:
            capsys: pytest fixture to capture print output

        """
        from scottbrian_throttle.throttle import throttle_sync
        import time

        @throttle_sync(reqs_per_sec=1)
        def make_request() -> None:
            time.sleep(0.1)  # simulate request that takes 1/10 second

        start_time = time.time()
        for i in range(10):
            make_request()
        elapsed_time = time.time() - start_time
        print(f"total time for 10 requests: {elapsed_time:0.1f} seconds")

        expected_result = "total time for 10 requests: 9.1 seconds\n"

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
        from scottbrian_throttle.throttle import ThrottleSync
        import time

        a_throttle = ThrottleSync(reqs_per_sec=1)

        def make_request() -> None:
            time.sleep(0.1)  # simulate request that takes 1/10 second

        start_time = time.time()
        for i in range(10):
            a_throttle.send_request(make_request)
        elapsed_time = time.time() - start_time
        print(f"total time for 10 requests: {elapsed_time:0.1f} seconds")

        expected_result = "total time for 10 requests: 9.1 seconds\n"

        captured = capsys.readouterr().out

        assert captured == expected_result

    # def test_throttle_with_example_4(self) -> None:
    #     """Method test_throttle_with_example_4."""
    #     print()
    #     print('#' * 50)
    #     print('Example of statically wrapping function with
    #            throttle:')
    #     print()
    #
    #     _tbe = False
    #
    #     @throttle(throttle_enabled=_tbe, file=sys.stdout)
    #     def func4a() -> None:
    #         print('this is sample text for _tbe = False static
    #                example')
    #
    #     func4a()  # func4a is not wrapped by time box
    #
    #     _tbe = True
    #
    #     @throttle(throttle_enabled=_tbe, file=sys.stdout)
    #     def func4b() -> None:
    #         print('this is sample text for _tbe = True static
    #                                                      example')
    #
    #     func4b()  # func4b is wrapped by time box
    #
    # def test_throttle_with_example_5(self) -> None:
    #     """Method test_throttle_with_example_5."""
    #     print()
    #     print('#' * 50)
    #     print('Example of dynamically wrapping function with
    #            throttle:')
    #     print()
    #
    #     _tbe = True
    #     def tbe() -> bool: return _tbe
    #
    #     @throttle(throttle_enabled=tbe, file=sys.stdout)
    #     def func5() -> None:
    #         print('this is sample text for the tbe dynamic example')
    #
    #     func5()  # func5 is wrapped by time box
    #
    #     _tbe = False
    #     func5()  # func5 is not wrapped by throttle
    #
    # def test_throttle_with_example_6(self) -> None:
    #     """Method test_throttle_with_example_6."""
    #     print()
    #     print('#' * 50)
    #     print('Example of using different datetime format:')
    #     print()
    #
    #     a_datetime_format: DT_Format = cast(DT_Format,
    #                                         '%m/%d/%y %H:%M:%S')
    #
    #     @throttle(dt_format=a_datetime_format)
    #     def func6() -> None:
    #         print('this is sample text for the datetime forma
    #                example')
    #
    #     func6()
