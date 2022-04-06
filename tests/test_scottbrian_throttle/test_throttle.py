"""test_throttle.py module."""

########################################################################
# Standard Library
########################################################################
import copy
from dataclasses import dataclass
from enum import auto, Flag
from itertools import accumulate
import logging
import math
import random
import statistics as stats
import threading
import time
from time import perf_counter_ns
from typing import Any, Callable, cast, Optional, Union
from typing_extensions import TypeAlias

########################################################################
# Third Party
########################################################################
import pytest
from scottbrian_utils.flower_box import print_flower_box_msg as flowers
from scottbrian_utils.pauser import Pauser
########################################################################
# Local
########################################################################
from scottbrian_throttle.throttle import (
    Throttle,
    throttle,
    FuncWithThrottleAttr,
    shutdown_throttle_funcs,
    IncorrectInputSpecified,
    IncorrectRequestsSpecified,
    IncorrectSecondsSpecified,
    IncorrectModeSpecified,
    IncorrectAsyncQSizeSpecified,
    AsyncQSizeNotAllowed,
    IncorrectEarlyCountSpecified,
    MissingEarlyCountSpecification,
    EarlyCountNotAllowed,
    IncorrectLbThresholdSpecified,
    MissingLbThresholdSpecification,
    LbThresholdNotAllowed,
    AttemptedShutdownForSyncThrottle,
    IncorrectShutdownTypeSpecified)


########################################################################
# type aliases
########################################################################
IntFloat: TypeAlias = Union[int, float]
OptIntFloat: TypeAlias = Optional[IntFloat]

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


single_requests_arg: Optional[int] = None
single_seconds_arg: Optional[float] = None
single_early_count_arg: Optional[int] = None
single_send_interval_mult_arg: Optional[float] = None

single_lb_threshold_arg: OptIntFloat = None


########################################################################
# requests_arg fixture
########################################################################
requests_arg_list = [1, 2, 3]
if single_requests_arg is not None:
    requests_arg_list = [single_requests_arg]


@pytest.fixture(params=requests_arg_list)  # type: ignore
def requests_arg(request: Any) -> int:
    """Using different requests.

    Args:
        request: special fixture that returns the fixture params

    Returns:
        The params values are returned one at a time
    """
    return cast(int, request.param)


########################################################################
# seconds_arg fixture
########################################################################
seconds_arg_list = [0.3, 1, 2]
if single_seconds_arg is not None:
    seconds_arg_list = [single_seconds_arg]


@pytest.fixture(params=seconds_arg_list)  # type: ignore
def seconds_arg(request: Any) -> IntFloat:
    """Using different seconds.

    Args:
        request: special fixture that returns the fixture params

    Returns:
        The params values are returned one at a time
    """
    return cast(IntFloat, request.param)


########################################################################
# shutdown_requests_arg fixture
########################################################################
shutdown_requests_arg_list = [1, 3]


@pytest.fixture(params=shutdown_requests_arg_list)  # type: ignore
def shutdown_requests_arg(request: Any) -> int:
    """Using different requests.

    Args:
        request: special fixture that returns the fixture params

    Returns:
        The params values are returned one at a time
    """
    return cast(int, request.param)


########################################################################
# f_num_reqs_arg fixture
########################################################################
f_num_reqs_arg_list = [0, 16, 32]


@pytest.fixture(params=f_num_reqs_arg_list)  # type: ignore
def f1_num_reqs_arg(request: Any) -> int:
    """Number of requests to make for f1.

    Args:
        request: special fixture that returns the fixture params

    Returns:
        The params values are returned one at a time
    """
    return cast(int, request.param)


@pytest.fixture(params=f_num_reqs_arg_list)  # type: ignore
def f2_num_reqs_arg(request: Any) -> int:
    """Number of requests to make for f2.

    Args:
        request: special fixture that returns the fixture params

    Returns:
        The params values are returned one at a time
    """
    return cast(int, request.param)


@pytest.fixture(params=f_num_reqs_arg_list)  # type: ignore
def f3_num_reqs_arg(request: Any) -> int:
    """Number of requests to make for f3.

    Args:
        request: special fixture that returns the fixture params

    Returns:
        The params values are returned one at a time
    """
    return cast(int, request.param)


@pytest.fixture(params=f_num_reqs_arg_list)  # type: ignore
def f4_num_reqs_arg(request: Any) -> int:
    """Number of requests to make for f4.

    Args:
        request: special fixture that returns the fixture params

    Returns:
        The params values are returned one at a time
    """
    return cast(int, request.param)


@pytest.fixture(params=f_num_reqs_arg_list)  # type: ignore
def f5_num_reqs_arg(request: Any) -> int:
    """Number of requests to make for f5.

    Args:
        request: special fixture that returns the fixture params

    Returns:
        The params values are returned one at a time
    """
    return cast(int, request.param)


########################################################################
# num_shutdown1_funcs_arg fixture
########################################################################
num_shutdown1_funcs_arg_list = [0, 1, 2, 3, 4]


@pytest.fixture(params=num_shutdown1_funcs_arg_list)  # type: ignore
def num_shutdown1_funcs_arg(request: Any) -> int:
    """Number of requests to shutdown in first shutdown.

    Args:
        request: special fixture that returns the fixture params

    Returns:
        The params values are returned one at a time
    """
    return cast(int, request.param)


########################################################################
# shutdown_seconds_arg fixture
########################################################################
shutdown_seconds_arg_list = [0.3, 1, 2]


@pytest.fixture(params=shutdown_seconds_arg_list)  # type: ignore
def shutdown_seconds_arg(request: Any) -> IntFloat:
    """Using different seconds.

    Args:
        request: special fixture that returns the fixture params

    Returns:
        The params values are returned one at a time
    """
    return cast(IntFloat, request.param)


########################################################################
# shutdown_type_arg fixture
########################################################################
shutdown1_type_arg_list = [None,
                           Throttle.TYPE_SHUTDOWN_SOFT,
                           Throttle.TYPE_SHUTDOWN_HARD]


@pytest.fixture(params=shutdown1_type_arg_list)  # type: ignore
def shutdown1_type_arg(request: Any) -> int:
    """Using different shutdown types.

    Args:
        request: special fixture that returns the fixture params

    Returns:
        The params values are returned one at a time
    """
    return cast(int, request.param)


shutdown2_type_arg_list = [Throttle.TYPE_SHUTDOWN_SOFT,
                           Throttle.TYPE_SHUTDOWN_HARD]


@pytest.fixture(params=shutdown2_type_arg_list)  # type: ignore
def shutdown2_type_arg(request: Any) -> int:
    """Using different shutdown types.

    Args:
        request: special fixture that returns the fixture params

    Returns:
        The params values are returned one at a time
    """
    return cast(int, request.param)


########################################################################
# timeout_arg fixture
########################################################################
timeout_arg_list = [True, False]


@pytest.fixture(params=timeout_arg_list)  # type: ignore
def timeout1_arg(request: Any) -> bool:
    """Whether to use timeout.

    Args:
        request: special fixture that returns the fixture params

    Returns:
        The params values are returned one at a time

    """
    return cast(bool, request.param)


@pytest.fixture(params=timeout_arg_list)  # type: ignore
def timeout2_arg(request: Any) -> bool:
    """Whether to use timeout.

    Args:
        request: special fixture that returns the fixture params

    Returns:
        The params values are returned one at a time

    """
    return cast(bool, request.param)


########################################################################
# timeout_arg fixture
########################################################################
timeout3_arg_list = [0.10, 0.75, 1.25]


@pytest.fixture(params=timeout3_arg_list)  # type: ignore
def timeout3_arg(request: Any) -> float:
    """Whether to use timeout.

    Args:
        request: special fixture that returns the fixture params

    Returns:
        The params values are returned one at a time

    """
    return cast(float, request.param)


########################################################################
# sleep_delay_arg fixture
########################################################################
sleep_delay_arg_list = [0.10, 0.30, 1.25]


@pytest.fixture(params=sleep_delay_arg_list)  # type: ignore
def sleep_delay_arg(request: Any) -> float:
    """Whether to use timeout.

    Args:
        request: special fixture that returns the fixture params

    Returns:
        The params values are returned one at a time

    """
    return cast(float, request.param)


########################################################################
# sleep2_delay_arg fixture
########################################################################
sleep2_delay_arg_list = [0.3, 1.1]


@pytest.fixture(params=sleep2_delay_arg_list)  # type: ignore
def sleep2_delay_arg(request: Any) -> float:
    """Whether to use timeout.

    Args:
        request: special fixture that returns the fixture params

    Returns:
        The params values are returned one at a time

    """
    return cast(float, request.param)


########################################################################
# which_throttle_arg fixture
########################################################################
class WT(Flag):
    """Which Throttle arg."""
    PieThrottleDirectShutdown = auto()
    PieThrottleShutdownFuncs = auto()
    NonPieThrottle = auto()


which_throttle_arg_list = [WT.PieThrottleDirectShutdown,
                           WT.PieThrottleShutdownFuncs,
                           WT.NonPieThrottle]


@pytest.fixture(params=which_throttle_arg_list)  # type: ignore
def which_throttle_arg(request: Any) -> WT:
    """Using different requests.

    Args:
        request: special fixture that returns the fixture params

    Returns:
        The params values are returned one at a time
    """
    return cast(WT, request.param)


########################################################################
# mode_arg fixture
########################################################################
mode_arg_list = [Throttle.MODE_ASYNC,
                 Throttle.MODE_SYNC,
                 Throttle.MODE_SYNC_LB,
                 Throttle.MODE_SYNC_EC]


@pytest.fixture(params=mode_arg_list)  # type: ignore
def mode_arg(request: Any) -> int:
    """Using different modes.

    Args:
        request: special fixture that returns the fixture params

    Returns:
        The params values are returned one at a time
    """
    return cast(int, request.param)


########################################################################
# mode_arg fixture
########################################################################
lb_threshold_arg_list = [1, 1.5, 3]
if single_lb_threshold_arg is not None:
    lb_threshold_arg_list = [single_lb_threshold_arg]


@pytest.fixture(params=lb_threshold_arg_list)  # type: ignore
def lb_threshold_arg(request: Any) -> IntFloat:
    """Using different lb_threshold values.

    Args:
        request: special fixture that returns the fixture params

    Returns:
        The params values are returned one at a time
    """
    return cast(IntFloat, request.param)


########################################################################
# early_count_arg fixture
########################################################################
early_count_arg_list = [1, 2, 3]
if single_early_count_arg is not None:
    early_count_arg_list = [single_early_count_arg]


@pytest.fixture(params=early_count_arg_list)  # type: ignore
def early_count_arg(request: Any) -> int:
    """Using different early_count values.

    Args:
        request: special fixture that returns the fixture params

    Returns:
        The params values are returned one at a time
    """
    return cast(int, request.param)


########################################################################
# send_interval_mult_arg fixture
########################################################################
send_interval_mult_arg_list = [0.0, 0.9, 1.0, 1.1]
if single_send_interval_mult_arg is not None:
    send_interval_mult_arg_list = [single_send_interval_mult_arg]


@pytest.fixture(params=send_interval_mult_arg_list)  # type: ignore
def send_interval_mult_arg(request: Any) -> float:
    """Using different send rates.

    Args:
        request: special fixture that returns the fixture params

    Returns:
        The params values are returned one at a time
    """
    return cast(float, request.param)


########################################################################
# request_style_arg fixture
########################################################################
request_style_arg_list = [0, 1, 2, 3, 4, 5, 6]


@pytest.fixture(params=request_style_arg_list)  # type: ignore
def request_style_arg(request: Any) -> int:
    """Using different early_count values.

    Args:
        request: special fixture that returns the fixture params

    Returns:
        The params values are returned one at a time
    """
    return cast(int, request.param)


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
        with pytest.raises(IncorrectRequestsSpecified):
            _ = Throttle(requests=0,
                         seconds=1,
                         mode=Throttle.MODE_ASYNC)
        with pytest.raises(IncorrectRequestsSpecified):
            _ = Throttle(requests=-1,
                         seconds=1,
                         mode=Throttle.MODE_ASYNC)
        with pytest.raises(IncorrectRequestsSpecified):
            _ = Throttle(requests='1',  # type: ignore
                         seconds=1,
                         mode=Throttle.MODE_ASYNC)

        ################################################################
        # bad seconds
        ################################################################
        with pytest.raises(IncorrectSecondsSpecified):
            _ = Throttle(requests=1,
                         seconds=0,
                         mode=Throttle.MODE_ASYNC)
        with pytest.raises(IncorrectSecondsSpecified):
            _ = Throttle(requests=1,
                         seconds=-1,
                         mode=Throttle.MODE_ASYNC)
        with pytest.raises(IncorrectSecondsSpecified):
            _ = Throttle(requests=1,
                         seconds='1',  # type: ignore
                         mode=Throttle.MODE_ASYNC)

        ################################################################
        # bad mode
        ################################################################
        with pytest.raises(IncorrectModeSpecified):
            _ = Throttle(requests=1,
                         seconds=1,
                         mode=-1)
        with pytest.raises(IncorrectModeSpecified):
            _ = Throttle(requests=1,
                         seconds=1,
                         mode=0)
        with pytest.raises(IncorrectModeSpecified):
            _ = Throttle(requests=1,
                         seconds=1,
                         mode=Throttle.MODE_MAX+1)
        with pytest.raises(IncorrectModeSpecified):
            _ = Throttle(requests=1,
                         seconds=1,
                         mode='1')  # type: ignore

        ################################################################
        # bad async_q_size
        ################################################################
        with pytest.raises(IncorrectAsyncQSizeSpecified):
            _ = Throttle(requests=1,
                         seconds=1,
                         mode=Throttle.MODE_ASYNC,
                         async_q_size=-1)
        with pytest.raises(IncorrectAsyncQSizeSpecified):
            _ = Throttle(requests=1,
                         seconds=1,
                         mode=Throttle.MODE_ASYNC,
                         async_q_size=0)
        with pytest.raises(IncorrectAsyncQSizeSpecified):
            _ = Throttle(requests=1,
                         seconds=1,
                         mode=Throttle.MODE_ASYNC,
                         async_q_size='1')  # type: ignore
        with pytest.raises(AsyncQSizeNotAllowed):
            _ = Throttle(requests=1,
                         seconds=1,
                         mode=Throttle.MODE_SYNC,
                         async_q_size=256)
        with pytest.raises(AsyncQSizeNotAllowed):
            _ = Throttle(requests=1,
                         seconds=1,
                         mode=Throttle.MODE_SYNC_EC,
                         async_q_size=256,
                         early_count=3)
        with pytest.raises(AsyncQSizeNotAllowed):
            _ = Throttle(requests=1,
                         seconds=1,
                         mode=Throttle.MODE_SYNC_LB,
                         async_q_size=256,
                         lb_threshold=3)
        ################################################################
        # bad early_count
        ################################################################
        with pytest.raises(EarlyCountNotAllowed):
            _ = Throttle(requests=1,
                         seconds=1,
                         mode=Throttle.MODE_ASYNC,
                         early_count=0)
        with pytest.raises(EarlyCountNotAllowed):
            _ = Throttle(requests=1,
                         seconds=1,
                         mode=Throttle.MODE_SYNC,
                         early_count=1)
        with pytest.raises(MissingEarlyCountSpecification):
            _ = Throttle(requests=1,
                         seconds=1,
                         mode=Throttle.MODE_SYNC_EC)
        with pytest.raises(EarlyCountNotAllowed):
            _ = Throttle(requests=1,
                         seconds=1,
                         mode=Throttle.MODE_SYNC_LB,
                         early_count=1)
        with pytest.raises(IncorrectEarlyCountSpecified):
            _ = Throttle(requests=1,
                         seconds=1,
                         mode=Throttle.MODE_SYNC_EC,
                         early_count=-1)
        with pytest.raises(IncorrectEarlyCountSpecified):
            _ = Throttle(requests=1,
                         seconds=1,
                         mode=Throttle.MODE_SYNC_EC,
                         early_count='1')  # type: ignore
        ################################################################
        # bad lb_threshold
        ################################################################
        with pytest.raises(LbThresholdNotAllowed):
            _ = Throttle(requests=1,
                         seconds=1,
                         mode=Throttle.MODE_ASYNC,
                         lb_threshold=1)
        with pytest.raises(LbThresholdNotAllowed):
            _ = Throttle(requests=1,
                         seconds=1,
                         mode=Throttle.MODE_SYNC,
                         lb_threshold=0)
        with pytest.raises(LbThresholdNotAllowed):
            _ = Throttle(requests=1,
                         seconds=1,
                         mode=Throttle.MODE_SYNC_EC,
                         early_count=3,
                         lb_threshold=0)
        with pytest.raises(MissingLbThresholdSpecification):
            _ = Throttle(requests=1,
                         seconds=1,
                         mode=Throttle.MODE_SYNC_LB)
        with pytest.raises(IncorrectLbThresholdSpecified):
            _ = Throttle(requests=1,
                         seconds=1,
                         mode=Throttle.MODE_SYNC_LB,
                         lb_threshold=-1)
        with pytest.raises(IncorrectLbThresholdSpecified):
            _ = Throttle(requests=1,
                         seconds=1,
                         mode=Throttle.MODE_SYNC_LB,
                         lb_threshold='1')  # type: ignore


########################################################################
# TestThrottleBasic class to test Throttle methods
########################################################################
class TestThrottleBasic:
    """Test basic functions of Throttle."""

    ####################################################################
    # len checks
    ####################################################################
    def test_throttle_len_async(self,
                                requests_arg: int,
                                mode_arg: int
                                ) -> None:
        """Test the len of async throttle.

        Args:
            requests_arg: fixture that provides args
            mode_arg: throttle mode to use

        Raises:
            InvalidModeNum: Mode invalid
        """
        # create a throttle with a long enough interval to ensure that
        # we can populate the async_q and get the length before we start
        # removing requests from it
        print('mode_arg:', mode_arg)
        if mode_arg == Throttle.MODE_ASYNC:
            a_throttle = Throttle(requests=requests_arg,
                                  seconds=requests_arg * 3,  # 3 sec interval
                                  mode=Throttle.MODE_ASYNC)
        elif mode_arg == Throttle.MODE_SYNC:
            a_throttle = Throttle(requests=requests_arg,
                                  seconds=1,
                                  mode=Throttle.MODE_SYNC)
        elif mode_arg == Throttle.MODE_SYNC_EC:
            a_throttle = Throttle(requests=requests_arg,
                                  seconds=1,
                                  mode=Throttle.MODE_SYNC_EC,
                                  early_count=3)
        elif mode_arg == Throttle.MODE_SYNC_LB:
            a_throttle = Throttle(requests=requests_arg,
                                  seconds=1,
                                  mode=Throttle.MODE_SYNC_LB,
                                  lb_threshold=2)
        else:
            raise InvalidModeNum('Mode invalid')

        def dummy_func(an_event: threading.Event) -> None:
            an_event.set()

        event = threading.Event()

        for i in range(requests_arg):
            a_throttle.send_request(dummy_func, event)

        event.wait()
        # assert is for 1 less than queued because the first request
        # will be scheduled immediately
        if mode_arg == Throttle.MODE_ASYNC:
            assert len(a_throttle) == requests_arg - 1
            # start_shutdown returns when request_q cleanup completes
            a_throttle.start_shutdown()
            assert len(a_throttle) == 0
        else:
            assert len(a_throttle) == 0

    def test_throttle_len_sync(self,
                               requests_arg: int
                               ) -> None:
        """Test the len of sync throttle.

        Args:
            requests_arg: fixture that provides args

        """
        # create a sync throttle
        a_throttle = Throttle(requests=requests_arg,
                              seconds=requests_arg * 3,  # 3 second interval
                              mode=Throttle.MODE_SYNC)

        def dummy_func() -> None:
            pass

        for i in range(requests_arg):
            a_throttle.send_request(dummy_func)

        # assert is for 0 since sync mode does not have an async_q

        assert len(a_throttle) == 0

    ####################################################################
    # task done check
    ####################################################################
    # def test_throttle_task_done(self,
    #                             requests_arg: int
    #                             ) -> None:
    #     """Test task done for throttle throttle.
    #
    #     Args:
    #         requests_arg: fixture that provides args
    #
    #     """
    #     # create a throttle with a short interval
    #     a_throttle = Throttle(requests=requests_arg,
    #                           # 1/4 interval
    #                           seconds=requests_arg * 0.25,
    #                           mode=Throttle.MODE_ASYNC)
    #
    #     class Counts:
    #         def __init__(self):
    #             self.count = 0
    #
    #     a_counts = Counts()
    #
    #     def dummy_func(counts) -> None:
    #         counts.count += 1
    #
    #     for i in range(requests_arg):
    #          a_throttle.send_request(dummy_func, a_counts)
    #
    #     a_throttle.async_q.join()
    #     assert len(a_throttle) == 0
    #     assert a_counts.count == requests_arg
    #     # start_shutdown to end the scheduler thread
    #     a_throttle.start_shutdown()
    #     assert len(a_throttle) == 0

    ####################################################################
    # repr with mode async
    ####################################################################
    def test_throttle_repr_async(self,
                                 requests_arg: int,
                                 seconds_arg: IntFloat
                                 ) -> None:
        """test_throttle repr mode 1 with various requests and seconds.

        Args:
            requests_arg: fixture that provides args
            seconds_arg: fixture that provides args

        """
        ################################################################
        # throttle with async_q_size specified
        ################################################################
        a_throttle = Throttle(requests=requests_arg,
                              seconds=seconds_arg,
                              mode=Throttle.MODE_ASYNC)

        expected_repr_str = (
            f'Throttle('
            f'requests={requests_arg}, '
            f'seconds={float(seconds_arg)}, '
            f'mode=Throttle.MODE_ASYNC, '
            f'async_q_size={Throttle.DEFAULT_ASYNC_Q_SIZE})')

        assert repr(a_throttle) == expected_repr_str

        a_throttle.start_shutdown()

        ################################################################
        # throttle with async_q_size specified
        ################################################################
        q_size = requests_arg * 3
        a_throttle = Throttle(requests=requests_arg,
                              seconds=seconds_arg,
                              mode=Throttle.MODE_ASYNC,
                              async_q_size=q_size)

        expected_repr_str = (
            f'Throttle('
            f'requests={requests_arg}, '
            f'seconds={float(seconds_arg)}, '
            f'mode=Throttle.MODE_ASYNC, '
            f'async_q_size={q_size})')

        assert repr(a_throttle) == expected_repr_str

        a_throttle.start_shutdown()

    ####################################################################
    # repr with mode sync
    ####################################################################
    def test_throttle_repr_sync(self,
                                requests_arg: int,
                                seconds_arg: IntFloat,
                                ) -> None:
        """test_throttle repr mode 2 with various requests and seconds.

        Args:
            requests_arg: fixture that provides args
            seconds_arg: fixture that provides args
        """
        a_throttle = Throttle(requests=requests_arg,
                              seconds=seconds_arg,
                              mode=Throttle.MODE_SYNC)

        expected_repr_str = (
            f'Throttle('
            f'requests={requests_arg}, '
            f'seconds={float(seconds_arg)}, '
            f'mode=Throttle.MODE_SYNC)')

        assert repr(a_throttle) == expected_repr_str

    ####################################################################
    # repr with mode sync early count
    ####################################################################
    def test_throttle_repr_sync_ec(self,
                                   requests_arg: int,
                                   seconds_arg: IntFloat,
                                   early_count_arg: int,
                                   ) -> None:
        """test_throttle repr mode 2 with various requests and seconds.

        Args:
            requests_arg: fixture that provides args
            seconds_arg: fixture that provides args
            early_count_arg: fixture that provides args
        """
        a_throttle = Throttle(requests=requests_arg,
                              seconds=seconds_arg,
                              mode=Throttle.MODE_SYNC_EC,
                              early_count=early_count_arg)

        expected_repr_str = (
            f'Throttle('
            f'requests={requests_arg}, '
            f'seconds={float(seconds_arg)}, '
            f'mode=Throttle.MODE_SYNC_EC, '
            f'early_count={early_count_arg})')

        assert repr(a_throttle) == expected_repr_str

    ####################################################################
    # repr with mode sync leaky bucket
    ####################################################################
    def test_throttle_repr_sync_lb(self,
                                   requests_arg: int,
                                   seconds_arg: IntFloat,
                                   lb_threshold_arg: IntFloat,
                                   ) -> None:
        """test_throttle repr with various requests and seconds.

        Args:
            requests_arg: fixture that provides args
            seconds_arg: fixture that provides args
            lb_threshold_arg: fixture that provides args
        """
        a_throttle = Throttle(requests=requests_arg,
                              seconds=seconds_arg,
                              mode=Throttle.MODE_SYNC_LB,
                              lb_threshold=lb_threshold_arg)

        expected_repr_str = (
            f'Throttle('
            f'requests={requests_arg}, '
            f'seconds={float(seconds_arg)}, '
            f'mode=Throttle.MODE_SYNC_LB, '
            f'lb_threshold={float(lb_threshold_arg)})')

        assert repr(a_throttle) == expected_repr_str


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
        with pytest.raises(IncorrectRequestsSpecified):
            @throttle(requests=0, seconds=1, mode=Throttle.MODE_ASYNC)
            def f1() -> None:
                print('42')
            f1()

        with pytest.raises(IncorrectRequestsSpecified):
            @throttle(requests=-1, seconds=1, mode=Throttle.MODE_ASYNC)
            def f1() -> None:
                print('42')
            f1()

        with pytest.raises(IncorrectRequestsSpecified):
            @throttle(requests='1', seconds=1,  # type: ignore
                      mode=Throttle.MODE_ASYNC)
            def f1() -> None:
                print('42')
            f1()
        ################################################################
        # bad seconds
        ################################################################
        with pytest.raises(IncorrectSecondsSpecified):
            @throttle(requests=1, seconds=0, mode=Throttle.MODE_ASYNC)
            def f1() -> None:
                print('42')
            f1()

        with pytest.raises(IncorrectSecondsSpecified):
            @throttle(requests=1, seconds=-1, mode=Throttle.MODE_ASYNC)
            def f1() -> None:
                print('42')
            f1()
        with pytest.raises(IncorrectSecondsSpecified):
            @throttle(requests=1, seconds='1',  # type: ignore
                      mode=Throttle.MODE_ASYNC)
            def f1() -> None:
                print('42')
            f1()

        ################################################################
        # bad mode
        ################################################################
        with pytest.raises(IncorrectModeSpecified):
            @throttle(requests=1,
                      seconds=1,
                      mode=-1)
            def f1() -> None:
                print('42')
            f1()
        with pytest.raises(IncorrectModeSpecified):
            @throttle(requests=1,
                      seconds=1,
                      mode=0)
            def f1() -> None:
                print('42')
            f1()
        with pytest.raises(IncorrectModeSpecified):
            @throttle(requests=1,
                      seconds=1,
                      mode=Throttle.MODE_MAX+1)
            def f1() -> None:
                print('42')
            f1()
        with pytest.raises(IncorrectModeSpecified):
            @throttle(requests=1,
                      seconds=1,
                      mode='1')  # type: ignore
            def f1() -> None:
                print('42')
            f1()

        ################################################################
        # bad async_q_size
        ################################################################
        with pytest.raises(IncorrectAsyncQSizeSpecified):
            @throttle(requests=1,
                      seconds=1,
                      mode=Throttle.MODE_ASYNC,
                      async_q_size=-1)
            def f1() -> None:
                print('42')
            f1()
        with pytest.raises(IncorrectAsyncQSizeSpecified):
            @throttle(requests=1,
                      seconds=1,
                      mode=Throttle.MODE_ASYNC,
                      async_q_size=0)
            def f1() -> None:
                print('42')
            f1()
        with pytest.raises(IncorrectAsyncQSizeSpecified):
            @throttle(requests=1,
                      seconds=1,
                      mode=Throttle.MODE_ASYNC,
                      async_q_size='1')  # type: ignore
            def f1() -> None:
                print('42')
            f1()
        with pytest.raises(AsyncQSizeNotAllowed):
            @throttle(requests=1,
                      seconds=1,
                      mode=Throttle.MODE_SYNC,
                      async_q_size=256)
            def f1() -> None:
                print('42')
            f1()
        with pytest.raises(AsyncQSizeNotAllowed):
            @throttle(requests=1,
                      seconds=1,
                      mode=Throttle.MODE_SYNC_EC,
                      async_q_size=256,
                      early_count=3)
            def f1() -> None:
                print('42')
            f1()
        with pytest.raises(AsyncQSizeNotAllowed):
            @throttle(requests=1,
                      seconds=1,
                      mode=Throttle.MODE_SYNC_LB,
                      async_q_size=256,
                      lb_threshold=3)
            def f1() -> None:
                print('42')
            f1()

        ################################################################
        # bad early_count
        ################################################################
        with pytest.raises(EarlyCountNotAllowed):
            @throttle(requests=1,
                      seconds=1,
                      mode=Throttle.MODE_ASYNC,
                      early_count=1)
            def f1() -> None:
                print('42')
            f1()
        with pytest.raises(EarlyCountNotAllowed):
            @throttle(requests=1,
                      seconds=1,
                      mode=Throttle.MODE_SYNC,
                      early_count=1)
            def f1() -> None:
                print('42')
            f1()
        with pytest.raises(MissingEarlyCountSpecification):
            @throttle(requests=1,
                      seconds=1,
                      mode=Throttle.MODE_SYNC_EC)
            def f1() -> None:
                print('42')
            f1()
        with pytest.raises(EarlyCountNotAllowed):
            @throttle(requests=1,
                      seconds=1,
                      mode=Throttle.MODE_SYNC_LB,
                      early_count=1)
            def f1() -> None:
                print('42')
            f1()
        with pytest.raises(IncorrectEarlyCountSpecified):
            @throttle(requests=1,
                      seconds=1,
                      mode=Throttle.MODE_SYNC_EC,
                      early_count=-1)
            def f1() -> None:
                print('42')
            f1()
        with pytest.raises(IncorrectEarlyCountSpecified):
            @throttle(requests=1,
                      seconds=1,
                      mode=Throttle.MODE_SYNC_EC,
                      early_count='1')  # type: ignore
            def f1() -> None:
                print('42')
            f1()
        ################################################################
        # bad lb_threshold
        ################################################################
        with pytest.raises(LbThresholdNotAllowed):
            @throttle(requests=1,
                      seconds=1,
                      mode=Throttle.MODE_ASYNC,
                      lb_threshold=1)
            def f1() -> None:
                print('42')
            f1()
        with pytest.raises(LbThresholdNotAllowed):
            @throttle(requests=1,
                      seconds=1,
                      mode=Throttle.MODE_SYNC,
                      lb_threshold=1)
            def f1() -> None:
                print('42')
            f1()
        with pytest.raises(LbThresholdNotAllowed):
            @throttle(requests=1,
                      seconds=1,
                      mode=Throttle.MODE_SYNC_EC,
                      early_count=5,
                      lb_threshold=0)
            def f1() -> None:
                print('42')
            f1()
        with pytest.raises(MissingLbThresholdSpecification):
            @throttle(requests=1,
                      seconds=1,
                      mode=Throttle.MODE_SYNC_LB)
            def f1() -> None:
                print('42')
            f1()
        with pytest.raises(IncorrectLbThresholdSpecified):
            @throttle(requests=1,
                      seconds=1,
                      mode=Throttle.MODE_SYNC_LB,
                      lb_threshold=-1)
            def f1() -> None:
                print('42')
            f1()
        with pytest.raises(IncorrectLbThresholdSpecified):
            @throttle(requests=1,
                      seconds=1,
                      mode=Throttle.MODE_SYNC_LB,
                      lb_threshold='1')  # type: ignore
            def f1() -> None:
                print('42')
            f1()


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
    def test_throttle_async_args_style(self,
                                       request_style_arg: int
                                       ) -> None:
        """Method to start throttle mode1 tests.

        Args:
            request_style_arg: chooses function args mix
        """
        send_interval = 0.0
        self.throttle_router(requests=1,
                             seconds=1,
                             mode=Throttle.MODE_ASYNC,
                             early_count=0,
                             lb_threshold=0,
                             send_interval=send_interval,
                             request_style=request_style_arg)

    ####################################################################
    # test_throttle_async
    ####################################################################
    def test_throttle_async(self,
                            requests_arg: int,
                            seconds_arg: IntFloat,
                            send_interval_mult_arg: float
                            ) -> None:
        """Method to start throttle mode1 tests.

        Args:
            requests_arg: number of requests per interval from fixture
            seconds_arg: interval for number of requests from fixture
            send_interval_mult_arg: interval between each send of a
                                      request
        """
        send_interval = (seconds_arg / requests_arg) * send_interval_mult_arg
        self.throttle_router(requests=requests_arg,
                             seconds=seconds_arg,
                             mode=Throttle.MODE_ASYNC,
                             early_count=0,
                             lb_threshold=0,
                             send_interval=send_interval,
                             request_style=2)

    ####################################################################
    # test_throttle_sync_args_style
    ####################################################################
    def test_throttle_sync_args_style(self,
                                      request_style_arg: int
                                      ) -> None:
        """Method to start throttle sync tests.

        Args:
            request_style_arg: chooses function args mix
        """
        send_interval = 0.2
        self.throttle_router(requests=2,
                             seconds=1,
                             mode=Throttle.MODE_SYNC,
                             early_count=0,
                             lb_threshold=0,
                             send_interval=send_interval,
                             request_style=request_style_arg)

    ####################################################################
    # test_throttle_sync
    ####################################################################
    def test_throttle_sync(self,
                           requests_arg: int,
                           seconds_arg: IntFloat,
                           send_interval_mult_arg: float
                           ) -> None:
        """Method to start throttle sync tests.

        Args:
            requests_arg: number of requests per interval from fixture
            seconds_arg: interval for number of requests from fixture
            send_interval_mult_arg: interval between each send of a
                                      request
        """
        send_interval = (seconds_arg / requests_arg) * send_interval_mult_arg
        self.throttle_router(requests=requests_arg,
                             seconds=seconds_arg,
                             mode=Throttle.MODE_SYNC,
                             early_count=0,
                             lb_threshold=0,
                             send_interval=send_interval,
                             request_style=3)

    ####################################################################
    # test_throttle_sync_ec
    ####################################################################
    def test_throttle_sync_ec_args_style(self,
                                         request_style_arg: int
                                         ) -> None:
        """Method to start throttle sync_ec tests.

        Args:
            request_style_arg: chooses function args mix

        """
        send_interval = 0.4
        self.throttle_router(requests=3,
                             seconds=1,
                             mode=Throttle.MODE_SYNC_EC,
                             early_count=1,
                             lb_threshold=0,
                             send_interval=send_interval,
                             request_style=request_style_arg)

    ####################################################################
    # test_throttle_sync_ec
    ####################################################################
    def test_throttle_sync_ec(self,
                              requests_arg: int,
                              seconds_arg: IntFloat,
                              early_count_arg: int,
                              send_interval_mult_arg: float
                              ) -> None:
        """Method to start throttle sync_ec tests.

        Args:
            requests_arg: number of requests per interval from fixture
            seconds_arg: interval for number of requests from fixture
            early_count_arg: count used for sync with early count algo
            send_interval_mult_arg: interval between each send of a
                                      request
        """
        send_interval = (seconds_arg / requests_arg) * send_interval_mult_arg
        self.throttle_router(requests=requests_arg,
                             seconds=seconds_arg,
                             mode=Throttle.MODE_SYNC_EC,
                             early_count=early_count_arg,
                             lb_threshold=0,
                             send_interval=send_interval,
                             request_style=0)

    ####################################################################
    # test_throttle_sync_lb
    ####################################################################
    def test_throttle_sync_lb_args_style(self,
                                         request_style_arg: int
                                         ) -> None:
        """Method to start throttle sync_lb tests.

        Args:
            request_style_arg: chooses function args mix
        """
        send_interval = 0.5
        self.throttle_router(requests=4,
                             seconds=1,
                             mode=Throttle.MODE_SYNC_LB,
                             early_count=0,
                             lb_threshold=1,
                             send_interval=send_interval,
                             request_style=request_style_arg)

    ####################################################################
    # test_throttle_sync_lb
    ####################################################################
    def test_throttle_sync_lb(self,
                              requests_arg: int,
                              seconds_arg: IntFloat,
                              lb_threshold_arg: IntFloat,
                              send_interval_mult_arg: float
                              ) -> None:
        """Method to start throttle sync_lb tests.

        Args:
            requests_arg: number of requests per interval from fixture
            seconds_arg: interval for number of requests from fixture
            lb_threshold_arg: threshold used with sync leaky bucket algo
            send_interval_mult_arg: interval between each send of a
                                      request
        """
        send_interval = (seconds_arg / requests_arg) * send_interval_mult_arg
        self.throttle_router(requests=requests_arg,
                             seconds=seconds_arg,
                             mode=Throttle.MODE_SYNC_LB,
                             early_count=0,
                             lb_threshold=lb_threshold_arg,
                             send_interval=send_interval,
                             request_style=6)

    ####################################################################
    # build_send_intervals
    ####################################################################
    def build_send_intervals(self,
                             send_interval: float
                             ) -> tuple[int, list[float]]:
        """Build the list of send intervals.

        Args:
            send_interval: the interval between sends

        Returns:
            a list of send intervals

        """
        random.seed(send_interval)
        num_reqs_to_do = 16
        # if mode == Throttle.MODE_SYNC_EC:
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
                    alt_send_interval = .5 * (random.random() * 2)
                else:
                    alt_send_interval = send_interval * (random.random() * 2)
                # if idx == 4:
                #     alt_send_interval = 0.015
                send_intervals.append(alt_send_interval)

        return num_reqs_to_do, send_intervals

    ####################################################################
    # throttle_router
    ####################################################################
    def throttle_router(self,
                        requests: int,
                        seconds: IntFloat,
                        mode: int,
                        early_count: int,
                        lb_threshold: IntFloat,
                        send_interval: float,
                        request_style: int
                        ) -> None:
        """Method test_throttle_router.

        Args:
            requests: number of requests per interval
            seconds: interval for number of requests
            mode: async or sync_EC or sync_LB
            early_count: count used for sync with early count algo
            lb_threshold: threshold used with sync leaky bucket algo
            send_interval: interval between each send of a request
            request_style: chooses function args mix

        Raises:
            BadRequestStyleArg: The request style arg must be 0 to 6
            InvalidModeNum: The Mode must be 1, 2, 3, or 4
        """
        pauser = Pauser()

        ################################################################
        # get send interval list
        ################################################################
        num_reqs_to_do, send_intervals = self.build_send_intervals(
            send_interval)
        ################################################################
        # Instantiate Throttle
        ################################################################
        if mode == Throttle.MODE_ASYNC:
            a_throttle = Throttle(requests=requests,
                                  seconds=seconds,
                                  mode=Throttle.MODE_ASYNC,
                                  async_q_size=num_reqs_to_do
                                  )
        elif mode == Throttle.MODE_SYNC:
            a_throttle = Throttle(requests=requests,
                                  seconds=seconds,
                                  mode=Throttle.MODE_SYNC
                                  )
        elif mode == Throttle.MODE_SYNC_EC:
            a_throttle = Throttle(requests=requests,
                                  seconds=seconds,
                                  mode=Throttle.MODE_SYNC_EC,
                                  early_count=early_count
                                  )
        elif mode == Throttle.MODE_SYNC_LB:
            a_throttle = Throttle(requests=requests,
                                  seconds=seconds,
                                  mode=Throttle.MODE_SYNC_LB,
                                  lb_threshold=lb_threshold
                                  )
        else:
            raise InvalidModeNum('The Mode must be 1, 2, 3, or 4')

        ################################################################
        # Instantiate Request Validator
        ################################################################
        request_validator = RequestValidator(requests=requests,
                                             seconds=seconds,
                                             mode=mode,
                                             early_count=early_count,
                                             lb_threshold=lb_threshold,
                                             total_requests=num_reqs_to_do,
                                             send_interval=send_interval,
                                             send_intervals=send_intervals,
                                             t_throttle=a_throttle)

        ################################################################
        # Make requests and validate
        ################################################################
        if request_style == 0:
            for i, s_interval in enumerate(send_intervals):
                # 0
                request_validator.start_times.append(perf_counter_ns())
                pauser.pause(s_interval)  # first one is 0.0
                request_validator.before_req_times.append(perf_counter_ns())
                rc = a_throttle.send_request(request_validator.request0)
                request_validator.after_req_times.append(perf_counter_ns())
                exp_rc = i if mode != Throttle.MODE_ASYNC else Throttle.RC_OK
                assert rc == exp_rc

            if mode == Throttle.MODE_ASYNC:
                a_throttle.start_shutdown(
                    shutdown_type=Throttle.TYPE_SHUTDOWN_SOFT)

            request_validator.validate_series()

        elif request_style == 1:
            for i, s_interval in enumerate(send_intervals):
                # 1
                request_validator.start_times.append(perf_counter_ns())
                pauser.pause(s_interval)  # first one is 0.0
                request_validator.before_req_times.append(perf_counter_ns())
                rc = a_throttle.send_request(request_validator.request1, i)
                request_validator.after_req_times.append(perf_counter_ns())
                exp_rc = i if mode != Throttle.MODE_ASYNC else Throttle.RC_OK
                assert rc == exp_rc

            if mode == Throttle.MODE_ASYNC:
                a_throttle.start_shutdown(
                    shutdown_type=Throttle.TYPE_SHUTDOWN_SOFT)
            request_validator.validate_series()  # validate for the series

        elif request_style == 2:
            for i, s_interval in enumerate(send_intervals):
                # 2
                request_validator.start_times.append(perf_counter_ns())
                # time_traces, stops_time = pauser.pause(s_interval)
                pauser.pause(s_interval)  # first
                # one is 0.0
                # request_validator.time_traces.append(time_traces)
                # request_validator.stop_times.append(stops_time)
                request_validator.before_req_times.append(perf_counter_ns())
                rc = a_throttle.send_request(request_validator.request2,
                                             i,
                                             requests)
                request_validator.after_req_times.append(perf_counter_ns())
                exp_rc = i if mode != Throttle.MODE_ASYNC else Throttle.RC_OK
                assert rc == exp_rc

            if mode == Throttle.MODE_ASYNC:
                a_throttle.start_shutdown(
                    shutdown_type=Throttle.TYPE_SHUTDOWN_SOFT)
            request_validator.validate_series()  # validate for the series

        elif request_style == 3:
            for i, s_interval in enumerate(send_intervals):
                # 3
                request_validator.start_times.append(perf_counter_ns())
                pauser.pause(s_interval)  # first one is 0.0
                request_validator.before_req_times.append(perf_counter_ns())
                rc = a_throttle.send_request(request_validator.request3, idx=i)
                request_validator.after_req_times.append(perf_counter_ns())
                exp_rc = i if mode != Throttle.MODE_ASYNC else Throttle.RC_OK
                assert rc == exp_rc

            if mode == Throttle.MODE_ASYNC:
                a_throttle.start_shutdown(
                    shutdown_type=Throttle.TYPE_SHUTDOWN_SOFT)
            request_validator.validate_series()  # validate for the series

        elif request_style == 4:
            for i, s_interval in enumerate(send_intervals):
                # 4
                request_validator.start_times.append(perf_counter_ns())
                pauser.pause(s_interval)  # first one is 0.0
                request_validator.before_req_times.append(perf_counter_ns())
                rc = a_throttle.send_request(request_validator.request4,
                                             idx=i,
                                             seconds=seconds)
                request_validator.after_req_times.append(perf_counter_ns())
                exp_rc = i if mode != Throttle.MODE_ASYNC else Throttle.RC_OK
                assert rc == exp_rc

            if mode == Throttle.MODE_ASYNC:
                a_throttle.start_shutdown(
                    shutdown_type=Throttle.TYPE_SHUTDOWN_SOFT)
            request_validator.validate_series()  # validate for the series

        elif request_style == 5:
            for i, s_interval in enumerate(send_intervals):
                # 5
                request_validator.start_times.append(perf_counter_ns())
                pauser.pause(s_interval)  # first one is 0.0
                request_validator.before_req_times.append(perf_counter_ns())
                rc = a_throttle.send_request(request_validator.request5,
                                             i,
                                             interval=send_interval)
                request_validator.after_req_times.append(perf_counter_ns())
                exp_rc = i if mode != Throttle.MODE_ASYNC else Throttle.RC_OK
                assert rc == exp_rc

            if mode == Throttle.MODE_ASYNC:
                a_throttle.start_shutdown(
                    shutdown_type=Throttle.TYPE_SHUTDOWN_SOFT)
            request_validator.validate_series()  # validate for the series

        elif request_style == 6:
            for i, s_interval in enumerate(send_intervals):
                # 6
                request_validator.start_times.append(perf_counter_ns())
                pauser.pause(s_interval)  # first one is 0.0
                request_validator.before_req_times.append(perf_counter_ns())
                rc = a_throttle.send_request(request_validator.request6,
                                             i,
                                             requests,
                                             seconds=seconds,
                                             interval=send_interval)
                request_validator.after_req_times.append(perf_counter_ns())
                exp_rc = i if mode != Throttle.MODE_ASYNC else Throttle.RC_OK
                assert rc == exp_rc

            if mode == Throttle.MODE_ASYNC:
                a_throttle.start_shutdown(
                    shutdown_type=Throttle.TYPE_SHUTDOWN_SOFT)
            request_validator.validate_series()  # validate for the series

        else:
            raise BadRequestStyleArg('The request style arg must be 0 to 6')

    ####################################################################
    # test_pie_throttle_async_args_style
    ####################################################################
    def test_pie_throttle_async_args_style(self,
                                           request_style_arg: int
                                           ) -> None:
        """Method to start throttle mode1 tests.

        Args:
            request_style_arg: chooses which function args to use

        """
        ################################################################
        # Instantiate Request Validator
        ################################################################
        pauser = Pauser()
        requests_arg = 4
        seconds_arg = 1
        send_interval = 0.1

        ################################################################
        # get send interval list
        ################################################################
        num_reqs_to_do, send_intervals = self.build_send_intervals(
            send_interval)

        ################################################################
        # Decorate functions with throttle
        ################################################################
        call_list: list[tuple[str, str, str]] = []

        ################################################################
        # f0
        ################################################################
        @throttle(requests=requests_arg,
                  seconds=seconds_arg,
                  mode=Throttle.MODE_ASYNC)
        def f0() -> Any:
            request_validator.callback0()

        call_list.append(('f0', '()', '0'))

        ################################################################
        # f1
        ################################################################
        @throttle(requests=requests_arg,
                  seconds=seconds_arg,
                  mode=Throttle.MODE_ASYNC)
        def f1(idx: int) -> Any:
            request_validator.callback1(idx)

        call_list.append(('f1', '(i)', '0'))

        ################################################################
        # f2
        ################################################################
        @throttle(requests=requests_arg,
                  seconds=seconds_arg,
                  mode=Throttle.MODE_ASYNC)
        def f2(idx: int, requests: int) -> Any:
            request_validator.callback2(idx, requests)

        call_list.append(('f2', '(i, requests_arg)', '0'))

        ################################################################
        # f3
        ################################################################
        @throttle(requests=requests_arg,
                  seconds=seconds_arg,
                  mode=Throttle.MODE_ASYNC)
        def f3(*, idx: int) -> Any:
            request_validator.callback3(idx=idx)

        call_list.append(('f3', '(idx=i)', '0'))

        ################################################################
        # f4
        ################################################################
        @throttle(requests=requests_arg,
                  seconds=seconds_arg,
                  mode=Throttle.MODE_ASYNC)
        def f4(*, idx: int, seconds: float) -> Any:
            request_validator.callback4(idx=idx, seconds=seconds)

        call_list.append(('f4', '(idx=i, seconds=seconds_arg)', '0'))

        ################################################################
        # f5
        ################################################################
        @throttle(requests=requests_arg,
                  seconds=seconds_arg,
                  mode=Throttle.MODE_ASYNC)
        def f5(idx: int, *, interval: float) -> Any:
            request_validator.callback5(idx,
                                        interval=interval)

        call_list.append(('f5', '(idx=i, interval=send_interval)', '0'))

        ################################################################
        # f6
        ################################################################
        @throttle(requests=requests_arg,
                  seconds=seconds_arg,
                  mode=Throttle.MODE_ASYNC)
        def f6(idx: int, requests: int, *, seconds: float, interval: float
               ) -> Any:
            request_validator.callback6(idx,
                                        requests,
                                        seconds=seconds,
                                        interval=interval)

        call_list.append(('f6',
                          '(i, requests_arg, seconds=seconds_arg, '
                          'interval=send_interval)',
                          '0'))

        ################################################################
        # Instantiate the validator
        ################################################################
        request_validator = RequestValidator(
            requests=requests_arg,
            seconds=seconds_arg,
            mode=Throttle.MODE_ASYNC,
            early_count=0,
            lb_threshold=0,
            total_requests=num_reqs_to_do,
            send_interval=send_interval,
            send_intervals=send_intervals,
            t_throttle=eval(call_list[request_style_arg][0]).throttle)
        ################################################################
        # Invoke the functions
        ################################################################
        for i, s_interval in enumerate(send_intervals):
            request_validator.start_times.append(perf_counter_ns())
            pauser.pause(s_interval)  # first one is 0.0
            request_validator.before_req_times.append(perf_counter_ns())
            rc = eval(call_list[request_style_arg][0]
                      + call_list[request_style_arg][1])
            request_validator.after_req_times.append(perf_counter_ns())
            assert rc == 0

        shutdown_throttle_funcs(eval(call_list[request_style_arg][0]))
        request_validator.validate_series()  # validate for the series

    ####################################################################
    # test_pie_throttle_async
    ####################################################################
    def test_pie_throttle_async(self,
                                requests_arg: int,
                                seconds_arg: IntFloat,
                                send_interval_mult_arg: float
                                ) -> None:
        """Method to start throttle mode1 tests.

        Args:
            requests_arg: number of requests per interval from fixture
            seconds_arg: interval for number of requests from fixture
            send_interval_mult_arg: interval between each send of a
                                      request
        """
        ################################################################
        # Instantiate Request Validator
        ################################################################
        pauser = Pauser()
        send_interval = (seconds_arg/requests_arg) * send_interval_mult_arg

        ################################################################
        # get send interval list
        ################################################################
        num_reqs_to_do, send_intervals = self.build_send_intervals(
            send_interval)

        ################################################################
        # Decorate functions with throttle
        ################################################################
        @throttle(requests=requests_arg,
                  seconds=seconds_arg,
                  mode=Throttle.MODE_ASYNC)
        def f0() -> Any:
            request_validator.callback0()

        ################################################################
        # Instantiate the validator
        ################################################################
        request_validator = RequestValidator(requests=requests_arg,
                                             seconds=seconds_arg,
                                             mode=Throttle.MODE_ASYNC,
                                             early_count=0,
                                             lb_threshold=0,
                                             total_requests=num_reqs_to_do,
                                             send_interval=send_interval,
                                             send_intervals=send_intervals,
                                             t_throttle=f0.throttle)
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
    def test_pie_throttle_sync_args_style(self,
                                          request_style_arg: int
                                          ) -> None:
        """Method to start pie throttle sync mode tests.

        Args:
            request_style_arg: chooses which function args to use

        """
        ################################################################
        # Instantiate Request Validator
        ################################################################
        pauser = Pauser()
        requests_arg = 2
        seconds_arg = 0.5
        send_interval_mult_arg = 1.0
        send_interval = (seconds_arg / requests_arg) * send_interval_mult_arg

        ################################################################
        # get send interval list
        ################################################################
        num_reqs_to_do, send_intervals = self.build_send_intervals(
            send_interval)

        ################################################################
        # Decorate functions with throttle
        ################################################################
        call_list: list[tuple[str, str, str]] = []

        ################################################################
        # f0
        ################################################################
        @throttle(requests=requests_arg,
                  seconds=seconds_arg,
                  mode=Throttle.MODE_SYNC)
        def f0() -> int:
            request_validator.callback0()
            return 42

        call_list.append(('f0', '()', '42'))

        ################################################################
        # f1
        ################################################################
        @throttle(requests=requests_arg,
                  seconds=seconds_arg,
                  mode=Throttle.MODE_SYNC)
        def f1(idx: int) -> int:
            request_validator.callback1(idx)
            return idx + 42 + 1

        call_list.append(('f1', '(i)', 'i + 42 + 1'))

        ################################################################
        # f2
        ################################################################
        @throttle(requests=requests_arg,
                  seconds=seconds_arg,
                  mode=Throttle.MODE_SYNC)
        def f2(idx: int, requests: int) -> int:
            request_validator.callback2(idx, requests)
            return idx + 42 + 2

        call_list.append(('f2', '(i, requests_arg)', 'i + 42 + 2'))

        ################################################################
        # f3
        ################################################################
        @throttle(requests=requests_arg,
                  seconds=seconds_arg,
                  mode=Throttle.MODE_SYNC)
        def f3(*, idx: int) -> int:
            request_validator.callback3(idx=idx)
            return idx + 42 + 3

        call_list.append(('f3', '(idx=i)', 'i + 42 + 3'))

        ################################################################
        # f4
        ################################################################
        @throttle(requests=requests_arg,
                  seconds=seconds_arg,
                  mode=Throttle.MODE_SYNC)
        def f4(*, idx: int, seconds: float) -> int:
            request_validator.callback4(idx=idx, seconds=seconds)
            return idx + 42 + 4
        call_list.append(('f4', '(idx=i, seconds=seconds_arg)', 'i + 42 + 4'))

        ################################################################
        # f5
        ################################################################
        @throttle(requests=requests_arg,
                  seconds=seconds_arg,
                  mode=Throttle.MODE_SYNC)
        def f5(idx: int, *, interval: float) -> int:
            request_validator.callback5(idx,
                                        interval=interval)
            return idx + 42 + 5

        call_list.append(('f5', '(idx=i, interval=send_interval_mult_arg)',
                          'i + 42 + 5'))

        ################################################################
        # f6
        ################################################################
        @throttle(requests=requests_arg,
                  seconds=seconds_arg,
                  mode=Throttle.MODE_SYNC)
        def f6(idx: int, requests: int, *, seconds: float, interval: float
               ) -> int:
            request_validator.callback6(idx,
                                        requests,
                                        seconds=seconds,
                                        interval=interval)
            return idx + 42 + 6

        call_list.append(('f6', '(i, requests_arg, seconds=seconds_arg,'
                          ' interval=send_interval_mult_arg)',
                          'i + 42 + 6'))

        ################################################################
        # Instantiate the validator
        ################################################################
        request_validator = RequestValidator(
            requests=requests_arg,
            seconds=seconds_arg,
            mode=Throttle.MODE_SYNC,
            early_count=0,
            lb_threshold=0,
            total_requests=num_reqs_to_do,
            send_interval=send_interval,
            send_intervals=send_intervals,
            t_throttle=eval(call_list[request_style_arg][0]).throttle)
        ################################################################
        # Invoke the functions
        ################################################################
        for i, s_interval in enumerate(send_intervals):
            request_validator.start_times.append(perf_counter_ns())
            pauser.pause(s_interval)  # first one is 0.0
            request_validator.before_req_times.append(perf_counter_ns())
            rc = eval(call_list[request_style_arg][0]
                      + call_list[request_style_arg][1])
            request_validator.after_req_times.append(perf_counter_ns())
            assert rc == eval(call_list[request_style_arg][2])

        request_validator.validate_series()  # validate for the series

    ####################################################################
    # test_throttle_sync
    ####################################################################
    def test_pie_throttle_sync(self,
                               requests_arg: int,
                               seconds_arg: IntFloat,
                               send_interval_mult_arg: float
                               ) -> None:
        """Method to start throttle sync tests.

        Args:
            requests_arg: number of requests per interval from fixture
            seconds_arg: interval for number of requests from fixture
            send_interval_mult_arg: interval between each send of a
                                      request
        """
        ################################################################
        # Instantiate Request Validator
        ################################################################
        pauser = Pauser()
        send_interval = (seconds_arg / requests_arg) * send_interval_mult_arg

        ################################################################
        # get send interval list
        ################################################################
        num_reqs_to_do, send_intervals = self.build_send_intervals(
            send_interval)

        ################################################################
        # Decorate functions with throttle
        ################################################################
        @throttle(requests=requests_arg,
                  seconds=seconds_arg,
                  mode=Throttle.MODE_SYNC)
        def f1(idx: int) -> int:
            request_validator.callback1(idx)
            return idx + 42 + 1

        ################################################################
        # Instantiate the validator
        ################################################################
        request_validator = RequestValidator(requests=requests_arg,
                                             seconds=seconds_arg,
                                             mode=Throttle.MODE_SYNC,
                                             early_count=0,
                                             lb_threshold=0,
                                             total_requests=num_reqs_to_do,
                                             send_interval=send_interval,
                                             send_intervals=send_intervals,
                                             t_throttle=f1.throttle)
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
    def test_pie_throttle_sync_ec_args_style(self,
                                             request_style_arg: int
                                             ) -> None:
        """Method to start pie throttle sync ec mode tests.

        Args:
            request_style_arg: chooses which function args to use

        """
        ################################################################
        # Instantiate Request Validator
        ################################################################
        pauser = Pauser()
        requests_arg = 3
        seconds_arg = 0.9
        early_count_arg = 2
        send_interval_mult_arg = 1.0

        send_interval = (seconds_arg / requests_arg) * send_interval_mult_arg

        ################################################################
        # get send interval list
        ################################################################
        num_reqs_to_do, send_intervals = self.build_send_intervals(
            send_interval)

        ################################################################
        # Decorate functions with throttle
        ################################################################
        call_list: list[tuple[str, str, str]] = []

        ################################################################
        # f0
        ################################################################
        @throttle(requests=requests_arg,
                  seconds=seconds_arg,
                  mode=Throttle.MODE_SYNC_EC,
                  early_count=early_count_arg)
        def f0() -> int:
            request_validator.callback0()
            return 42

        call_list.append(('f0', '()', '42'))

        ################################################################
        # f1
        ################################################################
        @throttle(requests=requests_arg,
                  seconds=seconds_arg,
                  mode=Throttle.MODE_SYNC_EC,
                  early_count=early_count_arg)
        def f1(idx: int) -> int:
            request_validator.callback1(idx)
            return idx + 42 + 1

        call_list.append(('f1', '(i)', 'i + 42 + 1'))

        ################################################################
        # f2
        ################################################################
        @throttle(requests=requests_arg,
                  seconds=seconds_arg,
                  mode=Throttle.MODE_SYNC_EC,
                  early_count=early_count_arg)
        def f2(idx: int, requests: int) -> int:
            request_validator.callback2(idx, requests)
            return idx + 42 + 2

        call_list.append(('f2', '(i, requests_arg)', 'i + 42 + 2'))

        ################################################################
        # f3
        ################################################################
        @throttle(requests=requests_arg,
                  seconds=seconds_arg,
                  mode=Throttle.MODE_SYNC_EC,
                  early_count=early_count_arg)
        def f3(*, idx: int) -> int:
            request_validator.callback3(idx=idx)
            return idx + 42 + 3

        call_list.append(('f3', '(idx=i)', 'i + 42 + 3'))

        ################################################################
        # f4
        ################################################################
        @throttle(requests=requests_arg,
                  seconds=seconds_arg,
                  mode=Throttle.MODE_SYNC_EC,
                  early_count=early_count_arg)
        def f4(*, idx: int, seconds: float) -> int:
            request_validator.callback4(idx=idx, seconds=seconds)
            return idx + 42 + 4

        call_list.append(('f4', '(idx=i, seconds=seconds_arg)', 'i + 42 + 4'))

        ################################################################
        # f5
        ################################################################
        @throttle(requests=requests_arg,
                  seconds=seconds_arg,
                  mode=Throttle.MODE_SYNC_EC,
                  early_count=early_count_arg)
        def f5(idx: int, *, interval: float) -> int:
            request_validator.callback5(idx,
                                        interval=interval)
            return idx + 42 + 5

        call_list.append(('f5',
                          '(idx=i, interval=send_interval_mult_arg)',
                          'i + 42 + 5'))

        ################################################################
        # f6
        ################################################################
        @throttle(requests=requests_arg,
                  seconds=seconds_arg,
                  mode=Throttle.MODE_SYNC_EC,
                  early_count=early_count_arg)
        def f6(idx: int, requests: int, *, seconds: float, interval: float
               ) -> int:
            request_validator.callback6(idx,
                                        requests,
                                        seconds=seconds,
                                        interval=interval)
            return idx + 42 + 6

        call_list.append(('f6',
                          '(i, requests_arg,'
                          'seconds=seconds_arg,'
                          'interval=send_interval_mult_arg)',
                          'i + 42 + 6'))

        ################################################################
        # Instantiate the validator
        ################################################################
        request_validator = RequestValidator(
            requests=requests_arg,
            seconds=seconds_arg,
            mode=Throttle.MODE_SYNC_EC,
            early_count=early_count_arg,
            lb_threshold=0,
            total_requests=num_reqs_to_do,
            send_interval=send_interval,
            send_intervals=send_intervals,
            t_throttle=eval(call_list[request_style_arg][0]).throttle)
        ################################################################
        # Invoke the functions
        ################################################################
        for i, s_interval in enumerate(send_intervals):
            request_validator.start_times.append(perf_counter_ns())
            pauser.pause(s_interval)  # first one is 0.0
            request_validator.before_req_times.append(perf_counter_ns())
            rc = eval(call_list[request_style_arg][0]
                      + call_list[request_style_arg][1])
            request_validator.after_req_times.append(perf_counter_ns())
            assert rc == eval(call_list[request_style_arg][2])
        request_validator.validate_series()  # validate for the series

    ####################################################################
    # test_throttle_sync_ec
    ####################################################################
    def test_pie_throttle_sync_ec(self,
                                  requests_arg: int,
                                  seconds_arg: IntFloat,
                                  early_count_arg: int,
                                  send_interval_mult_arg: float
                                  ) -> None:
        """Method to start throttle sync_ec tests.

        Args:
            requests_arg: number of requests per interval from fixture
            seconds_arg: interval for number of requests from fixture
            early_count_arg: count used for sync with early count algo
            send_interval_mult_arg: interval between each send of a
                                      request
        """
        ################################################################
        # Instantiate Request Validator
        ################################################################
        pauser = Pauser()
        send_interval = (seconds_arg / requests_arg) * send_interval_mult_arg

        ################################################################
        # get send interval list
        ################################################################
        num_reqs_to_do, send_intervals = self.build_send_intervals(
            send_interval)

        ################################################################
        # Decorate functions with throttle
        ################################################################
        @throttle(requests=requests_arg,
                  seconds=seconds_arg,
                  mode=Throttle.MODE_SYNC_EC,
                  early_count=early_count_arg)
        def f5(idx: int, *, interval: float) -> int:
            request_validator.callback5(idx,
                                        interval=interval)
            return idx + 42 + 5

        ################################################################
        # Instantiate the validator
        ################################################################
        request_validator = RequestValidator(requests=requests_arg,
                                             seconds=seconds_arg,
                                             mode=Throttle.MODE_SYNC_EC,
                                             early_count=early_count_arg,
                                             lb_threshold=0,
                                             total_requests=num_reqs_to_do,
                                             send_interval=send_interval,
                                             send_intervals=send_intervals,
                                             t_throttle=f5.throttle)
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
    def test_pie_throttle_sync_lb_args_style(self,
                                             request_style_arg: int
                                             ) -> None:
        """Method to start pie throttle sync ec mode tests.

        Args:
            request_style_arg: chooses which function args to use

        """
        ################################################################
        # Instantiate Request Validator
        ################################################################
        pauser = Pauser()
        requests_arg = 3
        seconds_arg = 0.7
        lb_threshold_arg = 4
        send_interval_mult_arg = 0.3

        send_interval = (seconds_arg / requests_arg) * send_interval_mult_arg

        ################################################################
        # get send interval list
        ################################################################
        num_reqs_to_do, send_intervals = self.build_send_intervals(
            send_interval)

        ################################################################
        # Decorate functions with throttle
        ################################################################
        call_list: list[tuple[str, str, str]] = []

        ################################################################
        # f0
        ################################################################
        @throttle(requests=requests_arg,
                  seconds=seconds_arg,
                  mode=Throttle.MODE_SYNC_LB,
                  lb_threshold=lb_threshold_arg)
        def f0() -> int:
            request_validator.callback0()
            return 42

        call_list.append(('f0', '()', '42'))

        ################################################################
        # f1
        ################################################################
        @throttle(requests=requests_arg,
                  seconds=seconds_arg,
                  mode=Throttle.MODE_SYNC_LB,
                  lb_threshold=lb_threshold_arg)
        def f1(idx: int) -> int:
            request_validator.callback1(idx)
            return idx + 42 + 1

        call_list.append(('f1', '(i)', 'i + 42 + 1'))

        ################################################################
        # f2
        ################################################################
        @throttle(requests=requests_arg,
                  seconds=seconds_arg,
                  mode=Throttle.MODE_SYNC_LB,
                  lb_threshold=lb_threshold_arg)
        def f2(idx: int, requests: int) -> int:
            request_validator.callback2(idx, requests)
            return idx + 42 + 2

        call_list.append(('f2', '(i, requests_arg)', 'i + 42 + 2'))

        ################################################################
        # f3
        ################################################################
        @throttle(requests=requests_arg,
                  seconds=seconds_arg,
                  mode=Throttle.MODE_SYNC_LB,
                  lb_threshold=lb_threshold_arg)
        def f3(*, idx: int) -> int:
            request_validator.callback3(idx=idx)
            return idx + 42 + 3

        call_list.append(('f3', '(idx=i)', 'i + 42 + 3'))

        ################################################################
        # f4
        ################################################################
        @throttle(requests=requests_arg,
                  seconds=seconds_arg,
                  mode=Throttle.MODE_SYNC_LB,
                  lb_threshold=lb_threshold_arg)
        def f4(*, idx: int, seconds: float) -> int:
            request_validator.callback4(idx=idx, seconds=seconds)
            return idx + 42 + 4

        call_list.append(('f4', '(idx=i, seconds=seconds_arg)',
                          'i + 42 + 4'))

        ################################################################
        # f5
        ################################################################
        @throttle(requests=requests_arg,
                  seconds=seconds_arg,
                  mode=Throttle.MODE_SYNC_LB,
                  lb_threshold=lb_threshold_arg)
        def f5(idx: int, *, interval: float) -> int:
            request_validator.callback5(idx,
                                        interval=interval)
            return idx + 42 + 5

        call_list.append(('f5', '(idx=i, interval=send_interval_mult_arg)',
                          'i + 42 + 5'))

        ################################################################
        # f6
        ################################################################
        @throttle(requests=requests_arg,
                  seconds=seconds_arg,
                  mode=Throttle.MODE_SYNC_LB,
                  lb_threshold=lb_threshold_arg)
        def f6(idx: int, requests: int, *, seconds: float, interval: float
               ) -> int:
            request_validator.callback6(idx,
                                        requests,
                                        seconds=seconds,
                                        interval=interval)
            return idx + 42 + 6

        call_list.append(('f6',
                          '(i, requests_arg,'
                          'seconds=seconds_arg,'
                          ' interval=send_interval_mult_arg)',
                          'i + 42 + 6'))

        ################################################################
        # Instantiate the validator
        ################################################################
        request_validator = RequestValidator(
            requests=requests_arg,
            seconds=seconds_arg,
            mode=Throttle.MODE_SYNC_LB,
            early_count=0,
            lb_threshold=lb_threshold_arg,
            total_requests=num_reqs_to_do,
            send_interval=send_interval,
            send_intervals=send_intervals,
            t_throttle=eval(call_list[request_style_arg][0]).throttle)
        ################################################################
        # Invoke the functions
        ################################################################
        for i, s_interval in enumerate(send_intervals):
            request_validator.start_times.append(perf_counter_ns())
            pauser.pause(s_interval)  # first one is 0.0
            request_validator.before_req_times.append(perf_counter_ns())
            rc = eval(call_list[request_style_arg][0]
                      + call_list[request_style_arg][1])
            request_validator.after_req_times.append(perf_counter_ns())
            assert rc == eval(call_list[request_style_arg][2])
        request_validator.validate_series()  # validate for the series

    ####################################################################
    # test_throttle_sync_lb
    ####################################################################
    def test_pie_throttle_sync_lb(self,
                                  requests_arg: int,
                                  seconds_arg: IntFloat,
                                  lb_threshold_arg: IntFloat,
                                  send_interval_mult_arg: float
                                  ) -> None:
        """Method to start throttle sync_lb tests.

        Args:
            requests_arg: number of requests per interval from fixture
            seconds_arg: interval for number of requests from fixture
            lb_threshold_arg: threshold used with sync leaky bucket algo
            send_interval_mult_arg: interval between each send of a
                                      request
        """
        ################################################################
        # Instantiate Request Validator
        ################################################################
        pauser = Pauser()
        send_interval = (seconds_arg / requests_arg) * send_interval_mult_arg

        ################################################################
        # get send interval list
        ################################################################
        num_reqs_to_do, send_intervals = self.build_send_intervals(
            send_interval)

        ################################################################
        # Decorate functions with throttle
        ################################################################
        @throttle(requests=requests_arg,
                  seconds=seconds_arg,
                  mode=Throttle.MODE_SYNC_LB,
                  lb_threshold=lb_threshold_arg)
        def f6(idx: int, requests: int, *, seconds: float, interval: float
               ) -> int:
            request_validator.callback6(idx,
                                        requests,
                                        seconds=seconds,
                                        interval=interval)
            return idx + 42 + 6

        ################################################################
        # Instantiate the validator
        ################################################################
        request_validator = RequestValidator(requests=requests_arg,
                                             seconds=seconds_arg,
                                             mode=Throttle.MODE_SYNC_LB,
                                             early_count=0,
                                             lb_threshold=lb_threshold_arg,
                                             total_requests=num_reqs_to_do,
                                             send_interval=send_interval,
                                             send_intervals=send_intervals,
                                             t_throttle=f6.throttle)

        ################################################################
        # Invoke function f6
        ################################################################
        for i, s_interval in enumerate(send_intervals):
            request_validator.start_times.append(perf_counter_ns())
            pauser.pause(s_interval)  # first one is 0.0
            request_validator.before_req_times.append(perf_counter_ns())
            rc = f6(i, requests_arg,
                    seconds=seconds_arg, interval=send_interval_mult_arg)
            request_validator.after_req_times.append(perf_counter_ns())
            assert rc == i + 42 + 6
        request_validator.validate_series()  # validate for the series


########################################################################
# issue_shutdown_log_entry
########################################################################
def issue_shutdown_log_entry(func_name: str,
                             req_time: ReqTime) -> None:
    """Log the shutdown progress message.

    Args:
        func_name: name of function for log message
        req_time: number of requests and time

    """
    t = time.time()
    prev_t = req_time.f_time
    f_interval = t - prev_t
    f_interval_str = (time.strftime('%S',
                                    time.localtime(f_interval))
                      + ('%.9f' % (f_interval % 1,))[1:6])
    req_time.f_time = t
    time_str = (time.strftime('%H:%M:%S', time.localtime(t))
                + ('%.9f' % (t % 1,))[1:6])
    req_time.num_reqs += 1
    logger.debug(f'{func_name} bumped count to {req_time.num_reqs} '
                 f'at {time_str}, interval={f_interval_str}')


########################################################################
# TestThrottleShutdown
########################################################################
class TestThrottleMisc:
    """Class TestThrottleMisc."""

    ####################################################################
    # test_get_interval_secs
    ####################################################################
    def test_get_interval_secs(self,
                               requests_arg: int,
                               seconds_arg: float) -> None:
        """Method to test get interval in seconds."""
        ################################################################
        # create a sync mode throttle
        ################################################################
        a_throttle1 = Throttle(requests=requests_arg,
                               seconds=seconds_arg,
                               mode=Throttle.MODE_SYNC)

        interval = seconds_arg / requests_arg
        assert interval == a_throttle1.get_interval_secs()

    ####################################################################
    # test_get_interval_ns
    ####################################################################
    def test_get_interval_ns(self,
                             requests_arg: int,
                             seconds_arg: float) -> None:
        """Method to test get interval in nanoseconds."""
        ################################################################
        # create a sync mode throttle
        ################################################################
        a_throttle1 = Throttle(requests=requests_arg,
                               seconds=seconds_arg,
                               mode=Throttle.MODE_SYNC)

        interval = (seconds_arg / requests_arg) * 1000000000
        assert interval == a_throttle1.get_interval_ns()

    ####################################################################
    # test_get_completion_time_secs
    ####################################################################
    def test_get_completion_time_secs(self,
                                      requests_arg: int,
                                      seconds_arg: float) -> None:
        """Method to test get completion time in seconds."""
        ################################################################
        # create a sync mode throttle
        ################################################################
        a_throttle1 = Throttle(requests=requests_arg,
                               seconds=seconds_arg,
                               mode=Throttle.MODE_SYNC)

        interval = seconds_arg / requests_arg
        for num_reqs in range(1, 10):
            exp_completion_time = (num_reqs - 1) * interval
            actual_completion_time = a_throttle1.get_completion_time_secs(
                requests=num_reqs, from_start=True)
            assert actual_completion_time == exp_completion_time

        for num_reqs in range(1, 10):
            exp_completion_time = num_reqs * interval
            actual_completion_time = a_throttle1.get_completion_time_secs(
                requests=num_reqs, from_start=False)
            assert actual_completion_time == exp_completion_time

    ####################################################################
    # test_get_completion_time_ns
    ####################################################################
    def test_get_completion_time_ns(self,
                                    requests_arg: int,
                                    seconds_arg: float) -> None:
        """Method to test get completion time in nanoseconds."""
        ################################################################
        # create a sync mode throttle
        ################################################################
        a_throttle1 = Throttle(requests=requests_arg,
                               seconds=seconds_arg,
                               mode=Throttle.MODE_SYNC)

        interval = (seconds_arg / requests_arg) * 1000000000
        for num_reqs in range(1, 10):
            exp_completion_time = (num_reqs - 1) * interval
            actual_completion_time = a_throttle1.get_completion_time_ns(
                requests=num_reqs, from_start=True)
            assert actual_completion_time == exp_completion_time

        for num_reqs in range(1, 10):
            exp_completion_time = num_reqs * interval
            actual_completion_time = a_throttle1.get_completion_time_ns(
                requests=num_reqs, from_start=False)
            assert actual_completion_time == exp_completion_time


########################################################################
# TestThrottleShutdown
########################################################################
class TestThrottleShutdownErrors:
    """Class TestThrottle error cases."""

    ####################################################################
    # test_attempt_sync_throttle_shutdown
    ####################################################################
    def test_attempt_sync_throttle_shutdown(self) -> None:
        """Method to test attempted shutdown in sync mode."""
        ################################################################
        # create a sync mode throttle
        ################################################################
        requests_arg = 4
        seconds_arg = 1
        interval = seconds_arg / requests_arg
        a_throttle1 = Throttle(requests=requests_arg,
                               seconds=seconds_arg,
                               mode=Throttle.MODE_SYNC)

        ################################################################
        # do some requests
        ################################################################
        start_time = time.time()
        a_req_time = ReqTime(num_reqs=0, f_time=start_time)

        def f1(req_time: ReqTime) -> None:
            issue_shutdown_log_entry(
                func_name='f1',
                req_time=req_time)

        num_requests_a = 4
        for i in range(num_requests_a):
            a_throttle1.send_request(f1, a_req_time)

        assert a_req_time.num_reqs == num_requests_a

        ################################################################
        # attempt to shutdown the sync mode throttle
        ################################################################
        with pytest.raises(AttemptedShutdownForSyncThrottle):
            a_throttle1.start_shutdown()

        ################################################################
        # ensure that throttle is still OK
        ################################################################
        # the following requests should not get ignored
        num_requests_b = 6
        for i in range(num_requests_b):
            a_throttle1.send_request(f1, a_req_time)

        # the count should now reflect the additional requests
        assert a_req_time.num_reqs == num_requests_a + num_requests_b

    ####################################################################
    # test_attempt_sync_throttle_shutdown
    ####################################################################
    def test_incorrect_shutdown_type(self) -> None:
        """Method to test incorrect shutdown type."""
        ################################################################
        # create an async mode throttle
        ################################################################
        requests_arg = 6
        seconds_arg = 2
        interval = seconds_arg / requests_arg
        a_throttle1 = Throttle(requests=requests_arg,
                               seconds=seconds_arg,
                               mode=Throttle.MODE_ASYNC)

        ################################################################
        # do some requests
        ################################################################
        start_time = time.time()
        a_req_time = ReqTime(num_reqs=0, f_time=start_time)

        def f1(req_time: ReqTime) -> None:
            issue_shutdown_log_entry(
                func_name='f1',
                req_time=req_time)

        num_requests_a = 4
        for i in range(num_requests_a):
            a_throttle1.send_request(f1, a_req_time)

        completion_time = (a_throttle1.get_completion_time_secs(
                num_requests_a, from_start=True)
                + (0.5 * a_throttle1.get_interval_secs()))
        logger.debug(f'about to sleep1 for {completion_time} seconds')
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

        completion_time = (a_throttle1.get_completion_time_secs(
            num_requests_b, from_start=True)
                           + (0.5 * a_throttle1.get_interval_secs()))
        logger.debug(f'about to sleep2 for {completion_time} seconds')
        time.sleep(completion_time)  # make sure requests are done
        # the count should be updated
        assert a_req_time.num_reqs == num_requests_a + num_requests_b

        a_throttle1.start_shutdown()  # must do a real shutdown

    # ####################################################################
    # # test_attempt_sync_throttle_shutdown
    # ####################################################################
    # def test_incorrect_timeout(self) -> None:
    #     """Method to test incorrect timeout specification."""
    #     ################################################################
    #     # create an async mode throttle
    #     ################################################################
    #     requests_arg = 8
    #     seconds_arg = 3
    #     interval = seconds_arg / requests_arg
    #     a_throttle1 = Throttle(requests=requests_arg,
    #                            seconds=seconds_arg,
    #                            mode=Throttle.MODE_ASYNC)
    #
    #     ################################################################
    #     # do some requests
    #     ################################################################
    #     start_time = time.time()
    #     a_req_time = ReqTime(num_reqs=0, f_time=start_time)
    #
    #     def f1(req_time: ReqTime) -> None:
    #         issue_shutdown_log_entry(
    #             func_name='f1',
    #             req_time=req_time)
    #
    #     num_requests_a = 4
    #     for i in range(num_requests_a):
    #         a_throttle1.send_request(f1, a_req_time)
    #
    #     completion_time = (a_throttle1.get_completion_time_secs(
    #             num_requests_a, from_start=True)
    #             + (0.5 * a_throttle1.get_interval_secs()))
    #     logger.debug(f'about to sleep1 for {completion_time} seconds')
    #     time.sleep(completion_time)  # make sure requests are done
    #     assert a_req_time.num_reqs == num_requests_a
    #
    #     ################################################################
    #     # attempt to shutdown the incorrect shutdown_type
    #     ################################################################
    #     with pytest.raises(IncorrectInputSpecified):
    #         a_throttle1.start_shutdown(timeout=-1)
    #
    #     ################################################################
    #     # ensure that throttle is still OK
    #     ################################################################
    #     # the following requests should not get ignored
    #     num_requests_b = 6
    #     for i in range(num_requests_b):
    #         a_throttle1.send_request(f1, a_req_time)
    #
    #     completion_time = (a_throttle1.get_completion_time_secs
    #             (num_requests_b, from_start=True)
    #              + (0.5 * a_throttle1.get_interval_secs()))
    #     logger.debug(f'about to sleep2 for {completion_time} seconds')
    #     time.sleep(completion_time)  # make sure requests are done
    #     # the count should be updated
    #     assert a_req_time.num_reqs == num_requests_a + num_requests_b
    #
    #     a_throttle1.start_shutdown()  # must do a real shutdown


########################################################################
# TestThrottleShutdown
########################################################################
class TestThrottleShutdown:
    """Class TestThrottle."""

    ####################################################################
    # test_throttle_shutdown
    ####################################################################
    def test_throttle_shutdown_timeout(
            self,
            requests_arg: int,
            sleep_delay_arg: float,
            timeout3_arg: float
            ) -> None:
        """Method to test shutdown scenarios.

        Args:
            requests_arg: how many requests per seconds
            seconds_arg: how many seconds between number of requests
            sleep_delay_arg: how many requests as a ratio to total
                               requests to schedule before starting
                               shutdown
            timeout3_arg: timeout value to use


        """
        seconds_arg = 0.3

        def f2(req_time: ReqTime) -> None:
            """F2 request function.

            Args:
                req_time: contains request number and time

            """
            issue_shutdown_log_entry(
                func_name='f2',
                req_time=req_time)

        num_reqs_to_make = 100
        a_throttle = Throttle(requests=requests_arg,
                              seconds=seconds_arg,
                              mode=Throttle.MODE_ASYNC)

        assert a_throttle.async_q
        assert a_throttle.request_scheduler_thread

        start_time = time.time()
        a_req_time = ReqTime(num_reqs=0, f_time=start_time)

        logger.debug(f'{requests_arg=}')
        logger.debug(f'{seconds_arg=}')
        # logger.debug(f'{shutdown1_type_arg=}')
        logger.debug(f'{sleep_delay_arg=}')
        logger.debug(f'{timeout3_arg=}')

        interval = a_throttle.get_interval_secs()
        logger.debug(f'{interval=}')

        ################################################################
        # calculate sleep times
        ################################################################
        sleep_reqs_to_do = min(num_reqs_to_make,
                               math.floor(num_reqs_to_make
                                          * sleep_delay_arg))
        logger.debug(f'{sleep_reqs_to_do=}')

        # Calculate the first sleep time to use
        # the get_completion_time_secs calculation is for the start of
        # a series where the first request has no delay.
        # Note that we add 1/2 interval to ensure we are between
        # requests when we come out of the sleep and verify the number
        # of requests. Without the extra time, we could come out of the
        # sleep just a fraction before the last request of the series
        # is made because of timing randomness.
        sleep_seconds = a_throttle.get_completion_time_secs(
            sleep_reqs_to_do, from_start=True) + (interval / 2)

        # calculate the subsequent sleep time to use by adding one
        # interval since the first request zero delay is no longer true
        sleep_seconds2 = a_throttle.get_completion_time_secs(
            sleep_reqs_to_do, from_start=False) + (interval / 2)
        logger.debug(f'{sleep_seconds=}')

        ################################################################
        # calculate timeout times
        ################################################################
        timeout_reqs_to_do = min(num_reqs_to_make,
                                 math.floor(num_reqs_to_make
                                            * timeout3_arg))
        logger.debug(f'{timeout_reqs_to_do=}')
        timeout_seconds = a_throttle.get_completion_time_secs(
                timeout_reqs_to_do, from_start=False)  # +(interval / 2)
        logger.debug(f'{timeout_seconds=}')

        logger.debug('start adding requests')
        start_time = time.time()
        ################################################################
        # We need a try/finally to make sure we can shut down the
        # throttle in the event that an assertion fails. In an earlier
        # version of this code before adding the try/finally, there were
        # test cases failing and leaving the throttle active with its
        # requests showing up in the next test case logs.
        ################################################################
        try:
            for _ in range(num_reqs_to_make):
                assert Throttle.RC_OK == a_throttle.send_request(
                    f2,
                    a_req_time)

            logger.debug('all requests added, elapsed time = '
                         f'{time.time() - start_time} seconds')

            prev_reqs_done = 0
            while True:
                sleep_time = sleep_seconds - (time.time() - a_req_time.f_time)
                logger.debug(f'about to sleep for {sleep_time=}')
                time.sleep(sleep_time)

                # switch to the longer sleep time from this point on
                # since the first request was done which has no delay
                sleep_seconds = sleep_seconds2

                exp_reqs_done = min(num_reqs_to_make,
                                    sleep_reqs_to_do + prev_reqs_done)
                assert a_req_time.num_reqs == exp_reqs_done

                prev_reqs_done = exp_reqs_done

                timeout = timeout_seconds - (time.time() - a_req_time.f_time)

                logger.debug(f'about to shutdown with {timeout=}')

                ret_code = a_throttle.start_shutdown(
                    shutdown_type=Throttle.TYPE_SHUTDOWN_SOFT,
                    timeout=timeout)

                exp_reqs_done = min(num_reqs_to_make,
                                    timeout_reqs_to_do + prev_reqs_done)

                assert a_req_time.num_reqs == exp_reqs_done

                prev_reqs_done = exp_reqs_done

                if exp_reqs_done == num_reqs_to_make:
                    assert ret_code is True
                    break
                else:
                    assert ret_code is False

            # logger.debug(f'shutdown complete with ret_code {ret_code}, '
            #              f'{shutdown1_reqs_time.num_reqs} reqs done, '
            #              f'elapsed time = {time.time() - start_time} seconds')

            ############################################################
            # verify new requests are rejected, q empty, and thread is
            # done
            ############################################################
            assert (Throttle.RC_SHUTDOWN
                    == a_throttle.send_request(f2, a_req_time))
            assert a_throttle.async_q.empty()
            assert not a_throttle.request_scheduler_thread.is_alive()

        finally:
            logger.debug('final shutdown to ensure throttle is closed')
            a_throttle.start_shutdown(Throttle.TYPE_SHUTDOWN_HARD)

        ################################################################
        # the following requests should get rejected
        ################################################################
        assert Throttle.RC_SHUTDOWN == a_throttle.send_request(
                f2, a_req_time)

    ####################################################################
    # test_throttle_shutdown
    ####################################################################
    def test_throttle_shutdown(
            self,
            requests_arg: int,
            seconds_arg: int,
            shutdown1_type_arg: int,
            shutdown2_type_arg: int,
            timeout1_arg: int,
            timeout2_arg: int,
            sleep_delay_arg: float) -> None:
        """Method to test shutdown scenarios.

        Args:
            requests_arg: how many requests per seconds
            seconds_arg: how many seconds between number of requests
            shutdown1_type_arg: soft or hard shutdown for first shutdown
            shutdown2_type_arg: soft or hard shutdown for second
                                  shutdown
            timeout1_arg: True or False to use timeout on shutdown1
            timeout2_arg: True or False to use timeout on shutdown2
            sleep_delay_arg: how many requests as a ratio to total
                               requests to schedule before starting
                               shutdown

        """
        def f2(req_time: ReqTime) -> None:
            issue_shutdown_log_entry(
                func_name='f2',
                req_time=req_time)

        num_reqs_to_make = 32
        a_throttle = Throttle(requests=requests_arg,
                               seconds=seconds_arg,
                               mode=Throttle.MODE_ASYNC)

        assert a_throttle.async_q
        assert a_throttle.request_scheduler_thread

        start_time = time.time()
        a_req_time = ReqTime(num_reqs=0, f_time=start_time)

        logger.debug(f'{requests_arg=}')
        logger.debug(f'{seconds_arg=}')
        logger.debug(f'{shutdown1_type_arg=}')
        logger.debug(f'{shutdown2_type_arg=}')
        logger.debug(f'{timeout1_arg=}')
        logger.debug(f'{timeout2_arg=}')
        logger.debug(f'{sleep_delay_arg=}')

        interval = seconds_arg/requests_arg
        logger.debug(f'{interval=}')

        ################################################################
        # calculate sleep1 times
        ################################################################
        sleep1_reqs_to_do = min(num_reqs_to_make,
                                math.floor(num_reqs_to_make
                                           * sleep_delay_arg))
        logger.debug(f'{sleep1_reqs_to_do=}')
        sleep1_sleep_seconds = (((sleep1_reqs_to_do - 1) * interval)
                                + (interval / 2))
        logger.debug(f'{sleep1_sleep_seconds=}')
        exp_sleep1_reqs_done = sleep1_reqs_to_do
        logger.debug(f'{exp_sleep1_reqs_done=}')
        sleep1_elapsed_seconds = (((exp_sleep1_reqs_done - 1) * interval)
                                  + (interval / 2))
        logger.debug(f'{sleep1_elapsed_seconds=}')

        shutdown1_nonzero_min_time = 1.1
        shutdown2_nonzero_min_time = 1.1
        if shutdown1_type_arg == Throttle.TYPE_SHUTDOWN_HARD:
            shutdown1_reqs_to_do = 0
            exp_shutdown1_reqs_done = exp_sleep1_reqs_done
            exp_shutdown1_ret_code = True
            sleep2_reqs_to_do = 0
            exp_sleep2_reqs_done = exp_shutdown1_reqs_done
            shutdown2_reqs_to_do = 0
            exp_shutdown2_reqs_done = exp_sleep2_reqs_done
            exp_total_reqs_done = exp_shutdown2_reqs_done
        else:  # first shutdown is soft
            if timeout1_arg:  # first shutdown is soft with timeout
                remaining_reqs = num_reqs_to_make - exp_sleep1_reqs_done
                third_reqs = math.floor(remaining_reqs / 3)
                shutdown1_reqs_to_do = third_reqs
                exp_shutdown1_reqs_done = (exp_sleep1_reqs_done
                                           + shutdown1_reqs_to_do)
                if remaining_reqs:
                    exp_shutdown1_ret_code = False
                    shutdown1_nonzero_min_time = 0.01
                else:
                    exp_shutdown1_ret_code = True
                sleep2_reqs_to_do = third_reqs
                exp_sleep2_reqs_done = (exp_shutdown1_reqs_done
                                        + sleep2_reqs_to_do)
                if shutdown2_type_arg == Throttle.TYPE_SHUTDOWN_HARD:
                    shutdown2_reqs_to_do = 0
                    exp_shutdown2_reqs_done = exp_sleep2_reqs_done
                    exp_total_reqs_done = exp_shutdown2_reqs_done
                else:
                    shutdown2_reqs_to_do = (num_reqs_to_make
                                            - exp_sleep2_reqs_done)
                    exp_shutdown2_reqs_done = (exp_sleep2_reqs_done
                                               + shutdown2_reqs_to_do)
                    exp_total_reqs_done = exp_shutdown2_reqs_done
            else:  # first shutdown is soft with no timeout
                shutdown1_reqs_to_do = num_reqs_to_make - exp_sleep1_reqs_done
                exp_shutdown1_reqs_done = (exp_sleep1_reqs_done
                                           + shutdown1_reqs_to_do)
                exp_shutdown1_ret_code = True
                sleep2_reqs_to_do = 0
                exp_sleep2_reqs_done = exp_shutdown1_reqs_done
                shutdown2_reqs_to_do = 0
                exp_shutdown2_reqs_done = (exp_sleep2_reqs_done
                                           + shutdown2_reqs_to_do)
                exp_total_reqs_done = exp_shutdown2_reqs_done

        ################################################################
        # calculate shutdown1 times
        ################################################################
        logger.debug(f'{shutdown1_reqs_to_do=}')
        shutdown1_timeout_seconds = ((shutdown1_reqs_to_do * interval)
                                     + (interval / 2))
        logger.debug(f'{shutdown1_timeout_seconds=}')

        logger.debug(f'{exp_shutdown1_reqs_done=}')
        shutdown1_elapsed_seconds = (((exp_shutdown1_reqs_done - 1) * interval)
                                     + (interval/2))
        logger.debug(f'{shutdown1_elapsed_seconds=}')

        ################################################################
        # calculate sleep2 times
        ################################################################
        logger.debug(f'{sleep2_reqs_to_do=}')
        sleep2_sleep_seconds = ((sleep2_reqs_to_do * interval)
                                + (interval / 2))
        logger.debug(f'{sleep2_sleep_seconds=}')

        logger.debug(f'{exp_sleep2_reqs_done=}')
        sleep2_elapsed_seconds = (((exp_sleep2_reqs_done - 1) * interval)
                                  + (interval / 2))
        logger.debug(f'{sleep2_elapsed_seconds=}')

        ################################################################
        # calculate shutdown2 times
        ################################################################
        logger.debug(f'{shutdown2_reqs_to_do=}')
        shutdown2_timeout_seconds = ((shutdown2_reqs_to_do * interval)
                                     + (interval / 2))
        logger.debug(f'{shutdown2_timeout_seconds=}')

        logger.debug(f'{exp_shutdown2_reqs_done=}')
        shutdown2_elapsed_seconds = (((exp_shutdown2_reqs_done - 1)
                                      * interval)
                                     + (interval / 2))
        logger.debug(f'{shutdown2_elapsed_seconds=}')

        ################################################################
        # calculate end times
        ################################################################
        logger.debug(f'{exp_total_reqs_done=}')
        total_reqs_elapsed_seconds = (exp_total_reqs_done - 1) * interval
        logger.debug(f'{total_reqs_elapsed_seconds=}')

        logger.debug('start adding requests')
        start_time = time.time()
        ################################################################
        # We need a try/finally to make sure we can shutdown the
        # throttle in the event that an assert fails. Before this, there
        # were test cases failing and leaving the throttle active with
        # its requests showing up in the next test case logs.
        ################################################################
        try:
            for _ in range(num_reqs_to_make):
                assert Throttle.RC_OK == a_throttle.send_request(
                    f2,
                    a_req_time)

            logger.debug('all requests added, elapsed time = '
                         f'{time.time() - start_time} seconds')

            ############################################################
            # first sleep to allow shutdown to progress
            ############################################################
            logger.debug(f'first sleep for {sleep1_sleep_seconds} seconds')
            sleep1_target_end_time = (start_time + sleep1_sleep_seconds)
            time.sleep(max(0.0, sleep1_target_end_time - time.time()))
            sleep1_reqs_time = copy.copy(a_req_time)
            logger.debug(f'sleep1 complete, {sleep1_reqs_time.num_reqs} '
                         f'reqs done, '
                         f'elapsed time = {time.time() - start_time} seconds')
            assert sleep1_reqs_time.num_reqs == exp_sleep1_reqs_done

            ############################################################
            # first shutdown
            ############################################################
            if timeout1_arg:
                l_msg = (f' with timeout for {shutdown1_timeout_seconds} '
                         'seconds')
            else:
                l_msg = ''
            logger.debug(f'starting shutdown1 {l_msg}')

            if timeout1_arg:
                shutdown1_target_end_time = (sleep1_reqs_time.f_time
                                             + shutdown1_timeout_seconds)
                if shutdown1_type_arg:
                    ret_code = a_throttle.start_shutdown(
                        shutdown_type=shutdown1_type_arg,
                        timeout=max(shutdown1_nonzero_min_time,
                                    shutdown1_target_end_time - time.time()
                                    ))
                else:
                    ret_code = a_throttle.start_shutdown(
                        timeout=max(shutdown1_nonzero_min_time,
                                    shutdown1_target_end_time - time.time()
                                    ))
            else:
                if shutdown1_type_arg:
                    ret_code = a_throttle.start_shutdown(
                        shutdown_type=shutdown1_type_arg)

                else:
                    ret_code = a_throttle.start_shutdown()

            shutdown1_reqs_time = copy.copy(a_req_time)
            logger.debug(f'shutdown1 complete with ret_code {ret_code}, '
                         f'{shutdown1_reqs_time.num_reqs} reqs done, '
                         f'elapsed time = {time.time() - start_time} seconds')
            assert shutdown1_reqs_time.num_reqs == exp_shutdown1_reqs_done
            assert ret_code is exp_shutdown1_ret_code

            ############################################################
            # second sleep
            ############################################################
            logger.debug(f'{sleep2_sleep_seconds=}')

            sleep2_target_end_time = (shutdown1_reqs_time.f_time
                                      + sleep2_sleep_seconds)

            time.sleep(max(0.0, sleep2_target_end_time - time.time()))
            sleep2_reqs_time = copy.copy(a_req_time)
            logger.debug(f'sleep2 complete, {sleep2_reqs_time.num_reqs} '
                         f'reqs done, '
                         f'elapsed time = {time.time() - start_time} seconds')
            assert sleep2_reqs_time.num_reqs == exp_sleep2_reqs_done

            ############################################################
            # second shutdown will succeed with or without time out
            ############################################################
            if timeout2_arg:
                l_msg = (f' with timeout for {shutdown2_timeout_seconds} '
                         'seconds')
            else:
                l_msg = ''
            logger.debug(f'starting shutdown2 {l_msg}')

            if timeout2_arg:
                shutdown2_target_end_time = (sleep2_reqs_time.f_time
                                             + shutdown2_timeout_seconds)
                ret_code = a_throttle.start_shutdown(
                    shutdown_type=shutdown2_type_arg,
                    timeout=max(shutdown2_nonzero_min_time,
                                shutdown2_target_end_time - time.time()
                                ))

            else:
                ret_code = a_throttle.start_shutdown(
                    shutdown_type=shutdown2_type_arg)

            shutdown_complete_secs = time.time() - start_time
            shutdown2_reqs_time = copy.copy(a_req_time)
            logger.debug(f'shutdown2 complete with ret_code {ret_code}, '
                         f'{shutdown2_reqs_time.num_reqs} reqs done, '
                         f'elapsed time = {time.time() - start_time} seconds')
            assert shutdown2_reqs_time.num_reqs == exp_total_reqs_done
            assert ret_code is True

            ############################################################
            # verify shutdown completed within expected time
            ############################################################
            exp_shutdown_complete_secs = interval * (exp_total_reqs_done - 1)

            logger.debug(f'{exp_shutdown_complete_secs=}')

            assert (exp_shutdown_complete_secs
                    <= shutdown_complete_secs
                    <= (exp_shutdown_complete_secs + 2.5))

            ############################################################
            # verify new requests are rejected, q empty, and thread is
            # done
            ############################################################
            assert (Throttle.RC_SHUTDOWN
                    == a_throttle.send_request(f2, a_req_time))
            assert a_throttle.async_q.empty()
            assert not a_throttle.request_scheduler_thread.is_alive()

        finally:
            logger.debug('final shutdown to ensure throttle is closed')
            a_throttle.start_shutdown()

        ################################################################
        # the following requests should get rejected
        ################################################################
        assert Throttle.RC_SHUTDOWN == a_throttle.send_request(
                f2, a_req_time)

    ####################################################################
    # test_pie_throttle_shutdown
    ####################################################################
    def test_pie_throttle_shutdown(
            self,
            requests_arg: int,
            seconds_arg: int,
            shutdown1_type_arg: int,
            shutdown2_type_arg: int,
            timeout1_arg: int,
            timeout2_arg: int,
            sleep_delay_arg: float,
            ) -> None:
        """Method to test shutdown scenarios.

        Args:
            requests_arg: how many requests per seconds
            seconds_arg: how many seconds between number of requests
            shutdown1_type_arg: soft or hard shutdown for first shutdown
            shutdown2_type_arg: soft or hard shutdown for second
                                  shutdown
            timeout1_arg: True or False to use timeout on shutdown1
            timeout2_arg: True or False to use timeout on shutdown2
            sleep_delay_arg: how many requests as a ratio to total
                               requests to schedule before starting
                               shutdown

        """
        @throttle(requests=requests_arg,
                  seconds=seconds_arg,
                  mode=Throttle.MODE_ASYNC)
        def f1(req_time: ReqTime) -> None:
            issue_shutdown_log_entry(
                func_name='f1',
                req_time=req_time)

        assert f1.throttle.async_q
        assert f1.throttle.request_scheduler_thread

        num_reqs_to_make = 32

        start_time = time.time()
        a_req_time = ReqTime(num_reqs=0, f_time=start_time)

        logger.debug(f'{requests_arg=}')
        logger.debug(f'{seconds_arg=}')
        logger.debug(f'{shutdown1_type_arg=}')
        logger.debug(f'{shutdown2_type_arg=}')
        logger.debug(f'{timeout1_arg=}')
        logger.debug(f'{timeout2_arg=}')
        logger.debug(f'{sleep_delay_arg=}')

        interval = seconds_arg/requests_arg
        logger.debug(f'{interval=}')

        ################################################################
        # calculate sleep1 times
        ################################################################
        sleep1_reqs_to_do = min(num_reqs_to_make,
                                math.floor(num_reqs_to_make
                                           * sleep_delay_arg))
        logger.debug(f'{sleep1_reqs_to_do=}')
        sleep1_sleep_seconds = (((sleep1_reqs_to_do - 1) * interval)
                                + (interval / 2))
        logger.debug(f'{sleep1_sleep_seconds=}')
        exp_sleep1_reqs_done = sleep1_reqs_to_do
        logger.debug(f'{exp_sleep1_reqs_done=}')
        sleep1_elapsed_seconds = (((exp_sleep1_reqs_done - 1) * interval)
                                  + (interval / 2))
        logger.debug(f'{sleep1_elapsed_seconds=}')

        shutdown1_nonzero_min_time = 1.1
        shutdown2_nonzero_min_time = 1.1
        if shutdown1_type_arg == Throttle.TYPE_SHUTDOWN_HARD:
            shutdown1_reqs_to_do = 0
            exp_shutdown1_reqs_done = exp_sleep1_reqs_done
            exp_shutdown1_ret_code = True
            sleep2_reqs_to_do = 0
            exp_sleep2_reqs_done = exp_shutdown1_reqs_done
            shutdown2_reqs_to_do = 0
            exp_shutdown2_reqs_done = exp_sleep2_reqs_done
            exp_total_reqs_done = exp_shutdown2_reqs_done
        else:  # first shutdown is soft
            if timeout1_arg:  # first shutdown is soft with timeout
                remaining_reqs = num_reqs_to_make - exp_sleep1_reqs_done
                third_reqs = math.floor(remaining_reqs / 3)
                shutdown1_reqs_to_do = third_reqs
                exp_shutdown1_reqs_done = (exp_sleep1_reqs_done
                                           + shutdown1_reqs_to_do)
                if remaining_reqs:
                    exp_shutdown1_ret_code = False
                    shutdown1_nonzero_min_time = 0.01
                else:
                    exp_shutdown1_ret_code = True
                sleep2_reqs_to_do = third_reqs
                exp_sleep2_reqs_done = (exp_shutdown1_reqs_done
                                        + sleep2_reqs_to_do)
                if shutdown2_type_arg == Throttle.TYPE_SHUTDOWN_HARD:
                    shutdown2_reqs_to_do = 0
                    exp_shutdown2_reqs_done = exp_sleep2_reqs_done
                    exp_total_reqs_done = exp_shutdown2_reqs_done
                else:
                    shutdown2_reqs_to_do = (num_reqs_to_make
                                            - exp_sleep2_reqs_done)
                    exp_shutdown2_reqs_done = (exp_sleep2_reqs_done
                                               + shutdown2_reqs_to_do)
                    exp_total_reqs_done = exp_shutdown2_reqs_done
            else:  # first shutdown is soft with no timeout
                shutdown1_reqs_to_do = num_reqs_to_make - exp_sleep1_reqs_done
                exp_shutdown1_reqs_done = (exp_sleep1_reqs_done
                                           + shutdown1_reqs_to_do)
                exp_shutdown1_ret_code = True
                sleep2_reqs_to_do = 0
                exp_sleep2_reqs_done = exp_shutdown1_reqs_done
                shutdown2_reqs_to_do = 0
                exp_shutdown2_reqs_done = (exp_sleep2_reqs_done
                                           + shutdown2_reqs_to_do)
                exp_total_reqs_done = exp_shutdown2_reqs_done

        ################################################################
        # calculate shutdown1 times
        ################################################################
        logger.debug(f'{shutdown1_reqs_to_do=}')
        shutdown1_timeout_seconds = ((shutdown1_reqs_to_do * interval)
                                     + (interval / 2))
        logger.debug(f'{shutdown1_timeout_seconds=}')

        logger.debug(f'{exp_shutdown1_reqs_done=}')
        shutdown1_elapsed_seconds = (((exp_shutdown1_reqs_done - 1) * interval)
                                     + (interval/2))
        logger.debug(f'{shutdown1_elapsed_seconds=}')

        ################################################################
        # calculate sleep2 times
        ################################################################
        logger.debug(f'{sleep2_reqs_to_do=}')
        sleep2_sleep_seconds = ((sleep2_reqs_to_do * interval)
                                + (interval / 2))
        logger.debug(f'{sleep2_sleep_seconds=}')

        logger.debug(f'{exp_sleep2_reqs_done=}')
        sleep2_elapsed_seconds = (((exp_sleep2_reqs_done - 1) * interval)
                                  + (interval / 2))
        logger.debug(f'{sleep2_elapsed_seconds=}')

        ################################################################
        # calculate shutdown2 times
        ################################################################
        logger.debug(f'{shutdown2_reqs_to_do=}')
        shutdown2_timeout_seconds = ((shutdown2_reqs_to_do * interval)
                                     + (interval / 2))
        logger.debug(f'{shutdown2_timeout_seconds=}')

        logger.debug(f'{exp_shutdown2_reqs_done=}')
        shutdown2_elapsed_seconds = (((exp_shutdown2_reqs_done - 1)
                                      * interval)
                                     + (interval / 2))
        logger.debug(f'{shutdown2_elapsed_seconds=}')

        ################################################################
        # calculate end times
        ################################################################
        logger.debug(f'{exp_total_reqs_done=}')
        total_reqs_elapsed_seconds = (exp_total_reqs_done - 1) * interval
        logger.debug(f'{total_reqs_elapsed_seconds=}')

        logger.debug('start adding requests')
        start_time = time.time()
        ################################################################
        # We need a try/finally to make sure we can shutdown the
        # throttle in the event that an assert fails. Before this, there
        # were test cases failing and leaving the throttle active with
        # its requests showing up in the next test case logs.
        ################################################################
        try:
            for _ in range(num_reqs_to_make):
                assert Throttle.RC_OK == f1(a_req_time)

            logger.debug('all requests added, elapsed time = '
                         f'{time.time() - start_time} seconds')

            ############################################################
            # first sleep to allow shutdown to progress
            ############################################################
            logger.debug(f'first sleep for {sleep1_sleep_seconds} seconds')
            sleep1_target_end_time = (start_time + sleep1_sleep_seconds)
            time.sleep(max(0.0, sleep1_target_end_time - time.time()))
            sleep1_reqs_time = copy.copy(a_req_time)
            logger.debug(f'sleep1 complete, {sleep1_reqs_time.num_reqs} '
                         f'reqs done, '
                         f'elapsed time = {time.time() - start_time} seconds')
            assert sleep1_reqs_time.num_reqs == exp_sleep1_reqs_done

            ############################################################
            # first shutdown
            ############################################################
            if timeout1_arg:
                l_msg = (f' with timeout for {shutdown1_timeout_seconds} '
                         'seconds')
            else:
                l_msg = ''
            logger.debug(f'starting shutdown1 {l_msg}')

            if timeout1_arg:
                shutdown1_target_end_time = (sleep1_reqs_time.f_time
                                             + shutdown1_timeout_seconds)
                if shutdown1_type_arg:
                    ret_code = f1.throttle.start_shutdown(
                        shutdown_type=shutdown1_type_arg,
                        timeout=max(shutdown1_nonzero_min_time,
                                    shutdown1_target_end_time - time.time()
                                    ))
                else:
                    ret_code = f1.throttle.start_shutdown(
                        timeout=max(shutdown1_nonzero_min_time,
                                    shutdown1_target_end_time - time.time()
                                    ))
            else:
                if shutdown1_type_arg:
                    ret_code = f1.throttle.start_shutdown(
                        shutdown_type=shutdown1_type_arg)

                else:
                    ret_code = f1.throttle.start_shutdown()

            shutdown1_reqs_time = copy.copy(a_req_time)
            logger.debug(f'shutdown1 complete with ret_code {ret_code}, '
                         f'{shutdown1_reqs_time.num_reqs} reqs done, '
                         f'elapsed time = {time.time() - start_time} seconds')
            assert shutdown1_reqs_time.num_reqs == exp_shutdown1_reqs_done
            assert ret_code is exp_shutdown1_ret_code

            ############################################################
            # second sleep
            ############################################################
            logger.debug(f'{sleep2_sleep_seconds=}')

            sleep2_target_end_time = (shutdown1_reqs_time.f_time
                                      + sleep2_sleep_seconds)

            time.sleep(max(0.0, sleep2_target_end_time - time.time()))
            sleep2_reqs_time = copy.copy(a_req_time)
            logger.debug(f'sleep2 complete, {sleep2_reqs_time.num_reqs} '
                         f'reqs done, '
                         f'elapsed time = {time.time() - start_time} seconds')
            assert sleep2_reqs_time.num_reqs == exp_sleep2_reqs_done

            ############################################################
            # second shutdown will succeed with or without time out
            ############################################################
            if timeout2_arg:
                l_msg = (f' with timeout for {shutdown2_timeout_seconds} '
                         'seconds')
            else:
                l_msg = ''
            logger.debug(f'starting shutdown2 {l_msg}')

            if timeout2_arg:
                shutdown2_target_end_time = (sleep2_reqs_time.f_time
                                             + shutdown2_timeout_seconds)
                ret_code = f1.throttle.start_shutdown(
                    shutdown_type=shutdown2_type_arg,
                    timeout=max(shutdown2_nonzero_min_time,
                                shutdown2_target_end_time - time.time()
                                ))
            else:
                ret_code = f1.throttle.start_shutdown(
                    shutdown_type=shutdown2_type_arg)

            shutdown_complete_secs = time.time() - start_time
            shutdown2_reqs_time = copy.copy(a_req_time)
            logger.debug(f'shutdown2 complete with ret_code {ret_code}, '
                         f'{shutdown2_reqs_time.num_reqs} reqs done, '
                         f'elapsed time = {time.time() - start_time} seconds')
            assert shutdown2_reqs_time.num_reqs == exp_total_reqs_done
            assert ret_code is True

            ############################################################
            # verify shutdown completed within expected time
            ############################################################
            exp_shutdown_complete_secs = interval * (exp_total_reqs_done - 1)

            logger.debug(f'{exp_shutdown_complete_secs=}')

            assert (exp_shutdown_complete_secs
                    <= shutdown_complete_secs
                    <= (exp_shutdown_complete_secs + 2.5))

            ############################################################
            # verify new requests are rejected, q empty, and thread is
            # done
            ############################################################
            assert Throttle.RC_SHUTDOWN == f1(a_req_time)
            assert f1.throttle.async_q.empty()
            assert not f1.throttle.request_scheduler_thread.is_alive()

        finally:
            logger.debug('final shutdown to ensure throttle is closed')
            f1.throttle.start_shutdown()

        ################################################################
        # the following requests should get rejected
        ################################################################
        assert Throttle.RC_SHUTDOWN == f1(a_req_time)

    ####################################################################
    # test_pie_throttle_shutdown_funcs
    ####################################################################
    def test_pie_throttle_shutdown_funcs(
            self,
            requests_arg: int,
            seconds_arg: int,
            shutdown1_type_arg: int,
            shutdown2_type_arg: int,
            timeout1_arg: int,
            timeout2_arg: int,
            sleep_delay_arg: float,
            ) -> None:
        """Method to test shutdown scenarios.

        Args:
            requests_arg: how many requests per seconds
            seconds_arg: how many seconds between number of requests
            shutdown1_type_arg: soft or hard shutdown for first shutdown
            shutdown2_type_arg: soft or hard shutdown for second
                                  shutdown
            timeout1_arg: True or False to use timeout on shutdown1
            timeout2_arg: True or False to use timeout on shutdown2
            sleep_delay_arg: how many requests as a ratio to total
                               requests to schedule before starting
                               shutdown

        """
        @throttle(requests=requests_arg,
                  seconds=seconds_arg,
                  mode=Throttle.MODE_ASYNC)
        def f1(req_time: ReqTime) -> None:
            issue_shutdown_log_entry(
                func_name='f1',
                req_time=req_time)

        assert f1.throttle.async_q
        assert f1.throttle.request_scheduler_thread

        num_reqs_to_make = 32

        start_time = time.time()
        a_req_time = ReqTime(num_reqs=0, f_time=start_time)

        logger.debug(f'{requests_arg=}')
        logger.debug(f'{seconds_arg=}')
        logger.debug(f'{shutdown1_type_arg=}')
        logger.debug(f'{shutdown2_type_arg=}')
        logger.debug(f'{timeout1_arg=}')
        logger.debug(f'{timeout2_arg=}')
        logger.debug(f'{sleep_delay_arg=}')

        interval = seconds_arg/requests_arg
        logger.debug(f'{interval=}')

        ################################################################
        # calculate sleep1 times
        ################################################################
        sleep1_reqs_to_do = min(num_reqs_to_make,
                                math.floor(num_reqs_to_make
                                           * sleep_delay_arg))
        logger.debug(f'{sleep1_reqs_to_do=}')
        sleep1_sleep_seconds = (((sleep1_reqs_to_do - 1) * interval)
                                + (interval / 2))
        logger.debug(f'{sleep1_sleep_seconds=}')
        exp_sleep1_reqs_done = sleep1_reqs_to_do
        logger.debug(f'{exp_sleep1_reqs_done=}')
        sleep1_elapsed_seconds = (((exp_sleep1_reqs_done - 1) * interval)
                                  + (interval / 2))
        logger.debug(f'{sleep1_elapsed_seconds=}')

        shutdown1_nonzero_min_time = 1.1
        shutdown2_nonzero_min_time = 1.1
        if shutdown1_type_arg == Throttle.TYPE_SHUTDOWN_HARD:
            shutdown1_reqs_to_do = 0
            exp_shutdown1_reqs_done = exp_sleep1_reqs_done
            exp_shutdown1_ret_code = True
            sleep2_reqs_to_do = 0
            exp_sleep2_reqs_done = exp_shutdown1_reqs_done
            shutdown2_reqs_to_do = 0
            exp_shutdown2_reqs_done = exp_sleep2_reqs_done
            exp_total_reqs_done = exp_shutdown2_reqs_done
        else:  # first shutdown is soft
            if timeout1_arg:  # first shutdown is soft with timeout
                remaining_reqs = num_reqs_to_make - exp_sleep1_reqs_done
                third_reqs = math.floor(remaining_reqs / 3)
                shutdown1_reqs_to_do = third_reqs
                exp_shutdown1_reqs_done = (exp_sleep1_reqs_done
                                           + shutdown1_reqs_to_do)
                if remaining_reqs:
                    exp_shutdown1_ret_code = False
                    shutdown1_nonzero_min_time = 0.01
                else:
                    exp_shutdown1_ret_code = True
                sleep2_reqs_to_do = third_reqs
                exp_sleep2_reqs_done = (exp_shutdown1_reqs_done
                                        + sleep2_reqs_to_do)
                if shutdown2_type_arg == Throttle.TYPE_SHUTDOWN_HARD:
                    shutdown2_reqs_to_do = 0
                    exp_shutdown2_reqs_done = exp_sleep2_reqs_done
                    exp_total_reqs_done = exp_shutdown2_reqs_done
                else:
                    shutdown2_reqs_to_do = (num_reqs_to_make
                                            - exp_sleep2_reqs_done)
                    exp_shutdown2_reqs_done = (exp_sleep2_reqs_done
                                               + shutdown2_reqs_to_do)
                    exp_total_reqs_done = exp_shutdown2_reqs_done
            else:  # first shutdown is soft with no timeout
                shutdown1_reqs_to_do = num_reqs_to_make - exp_sleep1_reqs_done
                exp_shutdown1_reqs_done = (exp_sleep1_reqs_done
                                           + shutdown1_reqs_to_do)
                exp_shutdown1_ret_code = True
                sleep2_reqs_to_do = 0
                exp_sleep2_reqs_done = exp_shutdown1_reqs_done
                shutdown2_reqs_to_do = 0
                exp_shutdown2_reqs_done = (exp_sleep2_reqs_done
                                           + shutdown2_reqs_to_do)
                exp_total_reqs_done = exp_shutdown2_reqs_done

        ################################################################
        # calculate shutdown1 times
        ################################################################
        logger.debug(f'{shutdown1_reqs_to_do=}')
        shutdown1_timeout_seconds = ((shutdown1_reqs_to_do * interval)
                                     + (interval / 2))
        logger.debug(f'{shutdown1_timeout_seconds=}')

        logger.debug(f'{exp_shutdown1_reqs_done=}')
        shutdown1_elapsed_seconds = (((exp_shutdown1_reqs_done - 1) * interval)
                                     + (interval/2))
        logger.debug(f'{shutdown1_elapsed_seconds=}')

        ################################################################
        # calculate sleep2 times
        ################################################################
        logger.debug(f'{sleep2_reqs_to_do=}')
        sleep2_sleep_seconds = ((sleep2_reqs_to_do * interval)
                                + (interval / 2))
        logger.debug(f'{sleep2_sleep_seconds=}')

        logger.debug(f'{exp_sleep2_reqs_done=}')
        sleep2_elapsed_seconds = (((exp_sleep2_reqs_done - 1) * interval)
                                  + (interval / 2))
        logger.debug(f'{sleep2_elapsed_seconds=}')

        ################################################################
        # calculate shutdown2 times
        ################################################################
        logger.debug(f'{shutdown2_reqs_to_do=}')
        shutdown2_timeout_seconds = ((shutdown2_reqs_to_do * interval)
                                     + (interval / 2))
        logger.debug(f'{shutdown2_timeout_seconds=}')

        logger.debug(f'{exp_shutdown2_reqs_done=}')
        shutdown2_elapsed_seconds = (((exp_shutdown2_reqs_done - 1)
                                      * interval)
                                     + (interval / 2))
        logger.debug(f'{shutdown2_elapsed_seconds=}')

        ################################################################
        # calculate end times
        ################################################################
        logger.debug(f'{exp_total_reqs_done=}')
        total_reqs_elapsed_seconds = (exp_total_reqs_done - 1) * interval
        logger.debug(f'{total_reqs_elapsed_seconds=}')

        logger.debug('start adding requests')
        start_time = time.time()
        ################################################################
        # We need a try/finally to make sure we can shutdown the
        # throttle in the event that an assert fails. Before this, there
        # were test cases failing and leaving the throttle active with
        # its requests showing up in the next test case logs.
        ################################################################
        try:
            for _ in range(num_reqs_to_make):
                assert Throttle.RC_OK == f1(a_req_time)

            logger.debug('all requests added, elapsed time = '
                         f'{time.time() - start_time} seconds')

            ############################################################
            # first sleep to allow shutdown to progress
            ############################################################
            logger.debug(f'first sleep for {sleep1_sleep_seconds} seconds')
            sleep1_target_end_time = (start_time + sleep1_sleep_seconds)
            time.sleep(max(0.0, sleep1_target_end_time - time.time()))
            sleep1_reqs_time = copy.copy(a_req_time)
            logger.debug(f'sleep1 complete, {sleep1_reqs_time.num_reqs} '
                         f'reqs done, '
                         f'elapsed time = {time.time() - start_time} seconds')
            assert sleep1_reqs_time.num_reqs == exp_sleep1_reqs_done

            ############################################################
            # first shutdown
            ############################################################
            if timeout1_arg:
                l_msg = (f' with timeout for {shutdown1_timeout_seconds} '
                         'seconds')
            else:
                l_msg = ''
            logger.debug(f'starting shutdown1 {l_msg}')

            if timeout1_arg:
                shutdown1_target_end_time = (sleep1_reqs_time.f_time
                                             + shutdown1_timeout_seconds)
                if shutdown1_type_arg:
                    ret_code = shutdown_throttle_funcs(
                        f1,
                        shutdown_type=shutdown1_type_arg,
                        timeout=max(shutdown1_nonzero_min_time,
                                    shutdown1_target_end_time - time.time()
                                    ))
                else:
                    ret_code = shutdown_throttle_funcs(
                        f1,
                        timeout=max(shutdown1_nonzero_min_time,
                                    shutdown1_target_end_time - time.time()
                                    ))
            else:
                if shutdown1_type_arg:
                    ret_code = shutdown_throttle_funcs(
                        f1,
                        shutdown_type=shutdown1_type_arg)

                else:
                    ret_code = shutdown_throttle_funcs(f1)

            shutdown1_reqs_time = copy.copy(a_req_time)
            logger.debug(f'shutdown1 complete with ret_code {ret_code}, '
                         f'{shutdown1_reqs_time.num_reqs} reqs done, '
                         f'elapsed time = {time.time() - start_time} seconds')
            assert shutdown1_reqs_time.num_reqs == exp_shutdown1_reqs_done
            assert ret_code is exp_shutdown1_ret_code

            ############################################################
            # second sleep
            ############################################################
            logger.debug(f'{sleep2_sleep_seconds=}')

            sleep2_target_end_time = (shutdown1_reqs_time.f_time
                                      + sleep2_sleep_seconds)

            time.sleep(max(0.0, sleep2_target_end_time - time.time()))
            sleep2_reqs_time = copy.copy(a_req_time)
            logger.debug(f'sleep2 complete, {sleep2_reqs_time.num_reqs} '
                         f'reqs done, '
                         f'elapsed time = {time.time() - start_time} seconds')
            assert sleep2_reqs_time.num_reqs == exp_sleep2_reqs_done

            ############################################################
            # second shutdown will succeed with or without time out
            ############################################################
            if timeout2_arg:
                l_msg = (f' with timeout for {shutdown2_timeout_seconds} '
                         'seconds')
            else:
                l_msg = ''
            logger.debug(f'starting shutdown2 {l_msg}')

            if timeout2_arg:
                shutdown2_target_end_time = (sleep2_reqs_time.f_time
                                             + shutdown2_timeout_seconds)

                ret_code = shutdown_throttle_funcs(
                    f1,
                    shutdown_type=shutdown2_type_arg,
                    timeout=max(shutdown2_nonzero_min_time,
                                shutdown2_target_end_time - time.time()
                                ))

            else:
                ret_code = shutdown_throttle_funcs(
                    f1,
                    shutdown_type=shutdown2_type_arg)

            shutdown_complete_secs = time.time() - start_time
            shutdown2_reqs_time = copy.copy(a_req_time)
            logger.debug(f'shutdown2 complete with ret_code {ret_code}, '
                         f'{shutdown2_reqs_time.num_reqs} reqs done, '
                         f'elapsed time = {time.time() - start_time} seconds')
            assert shutdown2_reqs_time.num_reqs == exp_total_reqs_done
            assert ret_code is True

            ############################################################
            # verify shutdown completed within expected time
            ############################################################
            exp_shutdown_complete_secs = interval * (exp_total_reqs_done - 1)

            logger.debug(f'{exp_shutdown_complete_secs=}')

            assert (exp_shutdown_complete_secs
                    <= shutdown_complete_secs
                    <= (exp_shutdown_complete_secs + 2.5))

            ############################################################
            # verify new requests are rejected, q empty, and thread is
            # done
            ############################################################
            assert Throttle.RC_SHUTDOWN == f1(a_req_time)
            assert f1.throttle.async_q.empty()
            assert not f1.throttle.request_scheduler_thread.is_alive()

        finally:
            logger.debug('final shutdown to ensure throttle is closed')
            f1.throttle.start_shutdown()

        ################################################################
        # the following requests should get rejected
        ################################################################
        assert Throttle.RC_SHUTDOWN == f1(a_req_time)

    ####################################################################
    # test_shutdown_throttle_funcs
    ####################################################################
    def test_shutdown_throttle_funcs(self,
                                     sleep2_delay_arg: float,
                                     num_shutdown1_funcs_arg: int,
                                     f1_num_reqs_arg: int,
                                     f2_num_reqs_arg: int,
                                     f3_num_reqs_arg: int,
                                     f4_num_reqs_arg: int
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
        ################################################################
        # f1
        ################################################################
        seconds_arg = .1
        f1_reqs = 1
        f2_reqs = 5
        f3_reqs = 2
        f4_reqs = 4

        @throttle(requests=f1_reqs,
                  seconds=seconds_arg,
                  mode=Throttle.MODE_ASYNC)
        def f1(req_time: ReqTime) -> None:
            issue_shutdown_log_entry(
                func_name='f1',
                req_time=req_time)

        ################################################################
        # f2
        ################################################################
        @throttle(requests=f2_reqs,
                  seconds=seconds_arg,
                  mode=Throttle.MODE_ASYNC)
        def f2(req_time: ReqTime) -> None:
            issue_shutdown_log_entry(
                func_name='f2',
                req_time=req_time)

        ################################################################
        # f3
        ################################################################
        @throttle(requests=f3_reqs,
                  seconds=seconds_arg,
                  mode=Throttle.MODE_ASYNC)
        def f3(req_time: ReqTime) -> None:
            issue_shutdown_log_entry(
                func_name='f3',
                req_time=req_time)

        ################################################################
        # f4
        ################################################################
        @throttle(requests=f4_reqs,
                  seconds=seconds_arg,
                  mode=Throttle.MODE_ASYNC)
        def f4(req_time: ReqTime) -> None:
            issue_shutdown_log_entry(
                func_name='f4',
                req_time=req_time)

        ################################################################
        # f5
        ################################################################
        # @throttle(requests=3,
        #           seconds=seconds_arg,
        #           mode=Throttle.MODE_ASYNC)
        # def f5(req_time: ReqTime) -> None:
        #     t = time.time()
        #     prev_t = req_time.f_time
        #     f_interval = t - prev_t
        #     f_interval_str = (time.strftime('%S',
        #                                     time.localtime(
        #                                          f_interval))
        #                       + ('%.9f' % (f_interval % 1,))[1:6])
        #     req_time.f_time = t
        #     time_str = (time.strftime('%H:%M:%S', time.localtime(t))
        #                 + ('%.9f' % (t % 1,))[1:6])
        #     req_time.num_reqs += 1
        #     logger.debug(f'f5 bumped count to {req_time.num_reqs} '
        #                  f'at {time_str}, interval={f_interval_str}')

        start_time = time.time()
        f1_req_time = ReqTime(num_reqs=0, f_time=start_time)
        f2_req_time = ReqTime(num_reqs=0, f_time=start_time)
        f3_req_time = ReqTime(num_reqs=0, f_time=start_time)
        f4_req_time = ReqTime(num_reqs=0, f_time=start_time)
        # f5_req_time = ReqTime(num_reqs=0, f_time=start_time)

        interval = seconds_arg/stats.mean([1, 2, 3, 4, 5])

        num_reqs_to_make = [f1_num_reqs_arg,
                            f2_num_reqs_arg,
                            f3_num_reqs_arg,
                            f4_num_reqs_arg]
        mean_reqs_to_make = stats.mean(num_reqs_to_make)

        if 0 <= mean_reqs_to_make <= 22:
            shutdown1_type_arg = None
        elif 22 <= mean_reqs_to_make <= 43:
            shutdown1_type_arg = Throttle.TYPE_SHUTDOWN_SOFT
        else:
            shutdown1_type_arg = Throttle.TYPE_SHUTDOWN_HARD

        f1_interval = seconds_arg / f1_reqs
        f2_interval = seconds_arg / f2_reqs
        f3_interval = seconds_arg / f3_reqs

        f1_exp_elapsed_seconds = f1_interval * f1_num_reqs_arg
        f2_exp_elapsed_seconds = f2_interval * f2_num_reqs_arg
        f3_exp_elapsed_seconds = f3_interval * f3_num_reqs_arg

        timeout_arg = None
        if ((shutdown1_type_arg != Throttle.TYPE_SHUTDOWN_HARD)
                and (num_shutdown1_funcs_arg == 2)
                and (f1_num_reqs_arg > 0)
                and (f2_num_reqs_arg > 0)):
            timeout_arg = min(f1_exp_elapsed_seconds,
                              f2_exp_elapsed_seconds) / 2
        elif ((shutdown1_type_arg != Throttle.TYPE_SHUTDOWN_HARD)
                and (num_shutdown1_funcs_arg == 3)
                and (f1_num_reqs_arg > 0)
                and (f2_num_reqs_arg > 0)
                and (f3_num_reqs_arg > 0)):
            timeout_arg = min(f1_exp_elapsed_seconds,
                              f2_exp_elapsed_seconds,
                              f3_exp_elapsed_seconds) / 2

        if timeout_arg:
            sleep_time: IntFloat = 0
        else:
            sleep_time = mean_reqs_to_make * sleep2_delay_arg * interval

        funcs_to_shutdown = list([f1, f2, f3, f4][0:num_shutdown1_funcs_arg])
        logger.debug(f'{funcs_to_shutdown=}')
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

        # for i in range(f5_num_reqs_arg):
        #     assert Throttle.RC_OK == f5(f5_req_time)

        ################################################################
        # allow some requests to be made
        ################################################################
        time.sleep(sleep_time)

        ################################################################
        # start shutdowns
        ################################################################
        if shutdown1_type_arg:
            if timeout_arg:
                ret_code = shutdown_throttle_funcs(
                    *funcs_to_shutdown,
                    shutdown_type=shutdown1_type_arg,
                    timeout=timeout_arg)
            else:
                ret_code = shutdown_throttle_funcs(
                    *funcs_to_shutdown,
                    shutdown_type=shutdown1_type_arg)
        else:
            if timeout_arg:
                ret_code = shutdown_throttle_funcs(
                    *funcs_to_shutdown,
                    timeout=timeout_arg)
            else:
                ret_code = shutdown_throttle_funcs(*funcs_to_shutdown)

        if timeout_arg:
            assert not ret_code
            assert (timeout_arg
                    <= time.time() - timeout_start_time
                    <= timeout_arg + 1)
        else:
            assert ret_code

        if shutdown1_type_arg:
            assert shutdown_throttle_funcs(
                f1, f2, f3, f4,
                shutdown_type=shutdown1_type_arg)

        else:
            assert shutdown_throttle_funcs(f1, f2, f3, f4)

        ################################################################
        # verify all funcs are shutdown
        ################################################################
        ################################################################
        # the following requests should get rejected
        ################################################################
        assert Throttle.RC_SHUTDOWN == f1(f1_req_time)
        assert Throttle.RC_SHUTDOWN == f2(f2_req_time)
        assert Throttle.RC_SHUTDOWN == f3(f3_req_time)
        assert Throttle.RC_SHUTDOWN == f4(f4_req_time)
        # assert Throttle.RC_SHUTDOWN == f5(f5_req_time)

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


########################################################################
# RequestValidator class
########################################################################
class RequestValidator:
    """Class to validate the requests."""

    ####################################################################
    # __init__
    ####################################################################
    def __init__(self,
                 requests: int,
                 seconds: float,
                 mode: int,
                 early_count: int,
                 lb_threshold: float,
                 total_requests: int,
                 send_interval: float,
                 send_intervals: list[float],
                 t_throttle: Throttle) -> None:
        """Initialize the RequestValidator object.

        Args:
            requests: number of requests per second
            seconds: number of seconds for number of requests
            mode: specifies whether async, sync, sync_ec, or sync_lb
            early_count: the early count for the throttle
            lb_threshold: the leaky bucket threshold
            total_requests: specifies how many requests to make for the
                              test
            send_interval: the interval between sends
            send_intervals: the list of send intervals
            t_throttle: the throttle being used for this test

        """
        self.t_throttle = t_throttle
        self.requests = requests
        self.seconds = seconds
        self.mode = mode
        self.early_count: int = early_count
        self.lb_threshold = lb_threshold
        self.send_interval = send_interval
        self.send_intervals = send_intervals
        self.send_times: list[float] = []
        self.num_async_overs: int = 0

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
        self.next_target_times: list[float] = []
        self.idx = -1

        self.target_times: list[float] = []
        self.target_intervals: list[float] = []

        self.expected_times: list[float] = []
        self.expected_intervals: list[float] = []

        self.diff_req_intervals: list[float] = []
        self.diff_req_ratio: list[float] = []

        self.before_req_times: list[float] = []
        self.arrival_times: list[float] = []
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
        self.norm_next_target_intervals: list[float] = []

        self.mean_before_req_interval = 0.0
        self.mean_arrival_interval = 0.0
        self.mean_req_interval = 0.0
        self.mean_after_req_interval = 0.0
        self.mean_start_interval = 0.0

        self.norm_next_target_times: list[float] = []

        self.mean_next_target_interval = 0.0

        self.path_times: list[list[float]] = []
        self.path_intervals: list[list[float]] = []

        self.path_async_times: list[list[float]] = []
        self.path_async_intervals: list[list[float]] = []

        # calculate parms

        self.total_requests: int = total_requests
        # if mode == Throttle.MODE_SYNC_EC:
        #     self.total_requests = ((((self.total_requests + 1)
        #                            // early_count)
        #                            * early_count)
        #                            + 1)

        self.target_interval = seconds / requests

        self.max_interval = max(self.target_interval,
                                self.send_interval)

        self.min_interval = min(self.target_interval,
                                self.send_interval)

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
        self.req_times = []
        self.after_req_times = []

        self.send_times = []
        self.target_times = []
        self.target_intervals = []

        self.expected_times = []
        self.expected_intervals = []

        self.diff_req_intervals = []
        self.diff_req_ratio = []

        self.before_req_times = []
        self.arrival_times = []
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
        self.norm_next_target_intervals = []

        self.mean_before_req_interval = 0.0
        self.mean_arrival_interval = 0.0
        self.mean_req_interval = 0.0
        self.mean_after_req_interval = 0.0

        self.next_target_times = []
        self.norm_next_target_times = []
        self.norm_next_target_intervals = []
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
        print(f'\n{self.requests=}')
        print(f'{self.seconds=}')
        print(f'{self.mode=}')
        print(f'{self.early_count=}')
        print(f'{self.lb_threshold=}')
        print(f'{self.send_interval=}')
        print(f'{self.total_requests=}')
        print(f'{self.target_interval=}')
        print(f'{self.send_interval=}')
        print(f'{self.min_interval=}')
        print(f'{self.max_interval=}')
        print(f'{self.exp_total_time=}')

    ####################################################################
    # add_func_throttles
    ####################################################################
    def add_func_throttles(self,
                           *args: FuncWithThrottleAttr[Callable[..., Any]]
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
            exp_interval_sum = (self.norm_req_times[idx-1]
                                + self.target_interval)
            self.exp_interval_sums.append(exp_interval_sum)

            if send_interval_sum <= exp_interval_sum:
                self.expected_intervals.append(self.target_interval)
            else:
                self.expected_intervals.append(self.target_interval
                                               + (send_interval_sum
                                                  - exp_interval_sum))
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
            self.expected_intervals.append(max(self.target_interval,
                                               send_interval))

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
            interval_remaining = (current_target_interval
                                  - current_interval_sum)
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
                    self.expected_intervals.append(send_interval
                                                   + interval_remaining)
                else:
                    current_early_count += 1
                    self.expected_intervals.append(send_interval)

    ####################################################################
    # build_sync_lb_exp_list
    ####################################################################
    def build_sync_lb_exp_list(self) -> None:
        """Build list of sync lb expected intervals."""
        self.expected_intervals = [0.0]
        bucket_capacity = self.lb_threshold * self.target_interval
        current_bucket_amt = self.target_interval  # first send
        for send_interval in self.send_intervals[1:]:
            # remove the amount that leaked since the last send
            current_bucket_amt = max(0.0,
                                     current_bucket_amt - send_interval)
            available_bucket_amt = bucket_capacity - current_bucket_amt
            # add target interval amount
            if self.target_interval <= available_bucket_amt:
                current_bucket_amt += self.target_interval
                self.expected_intervals.append(send_interval)
            else:
                reduction_needed = self.target_interval - available_bucket_amt
                self.expected_intervals.append(send_interval
                                               + reduction_needed)
                current_bucket_amt += (self.target_interval - reduction_needed)

    ####################################################################
    # build time lists
    ####################################################################
    def build_times(self) -> None:
        """Build lists of times and intervals."""
        ################################################################
        # create list of target times and intervals
        ################################################################
        self.target_intervals = (
                [0.0] + [self.target_interval
                         for _ in range(len(self.req_times)-1)])
        self.target_times = list(accumulate(self.target_intervals))

        ################################################################
        # create list of start times and intervals
        ################################################################
        assert len(self.start_times) == self.total_requests
        base_time = self.start_times[0]
        self.norm_start_times = [(item - base_time) * Pauser.NS_2_SECS
                                 for item in self.start_times]
        self.norm_start_intervals = list(
            map(lambda t1, t2: t1 - t2,
                self.norm_start_times,
                [0.0] + self.norm_start_times[:-1]))

        self.mean_start_interval = (self.norm_start_times[-1]
                                    / (self.total_requests - 1))

        ################################################################
        # create list of before request times and intervals
        ################################################################
        assert len(self.before_req_times) == self.total_requests
        self.norm_before_req_times = [(item - base_time) * Pauser.NS_2_SECS
                                      for item in self.before_req_times]
        self.norm_before_req_intervals = list(
            map(lambda t1, t2: t1 - t2,
                self.norm_before_req_times,
                [0.0] + self.norm_before_req_times[:-1]))

        self.mean_before_req_interval = (self.norm_before_req_times[-1]
                                         / (self.total_requests - 1))

        ################################################################
        # create list of arrival times and intervals
        ################################################################
        assert len(self.arrival_times) == self.total_requests
        # base_time2 = self.arrival_times[0]
        # self.norm_arrival_times = [
        # (item - base_time2) * Pauser.NS_2_SECS
        #                            for item in self.arrival_times]
        self.norm_arrival_times = [(item - base_time) * Pauser.NS_2_SECS
                                   for item in self.arrival_times]
        self.norm_arrival_intervals = list(
            map(lambda t1, t2: t1 - t2,
                self.norm_arrival_times,
                [0.0] + self.norm_arrival_times[:-1]))

        self.mean_arrival_interval = (self.norm_arrival_times[-1]
                                      / (self.total_requests - 1))

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
        self.norm_req_times = [(item[1] - base_time) * Pauser.NS_2_SECS
                               for item in self.req_times]
        self.norm_req_intervals = list(map(lambda t1, t2: t1 - t2,
                                           self.norm_req_times,
                                           [0.0]
                                           + self.norm_req_times[:-1]))
        self.mean_req_interval = (self.norm_req_times[-1]
                                  / (len(self.norm_req_times) - 1))

        ################################################################
        # create list of after request times and intervals
        ################################################################
        assert len(self.after_req_times) == self.total_requests
        self.norm_after_req_times = [(item - base_time) * Pauser.NS_2_SECS
                                     for item in self.after_req_times]
        self.norm_after_req_intervals = list(
            map(lambda t1, t2: t1 - t2,
                self.norm_after_req_times,
                [0.0] + self.norm_after_req_times[:-1]))

        self.mean_after_req_interval = (self.norm_after_req_times[-1]
                                        / (self.total_requests - 1))

        ################################################################
        # Build the expected intervals list
        ################################################################
        if self.mode == Throttle.MODE_ASYNC:
            self.build_async_exp_list()
        elif self.mode == Throttle.MODE_SYNC:
            self.build_sync_exp_list()
        elif self.mode == Throttle.MODE_SYNC_EC:
            self.build_sync_ec_exp_list()
        elif self.mode == Throttle.MODE_SYNC_LB:
            self.build_sync_lb_exp_list()

        self.expected_times = list(accumulate(self.expected_intervals))
        self.send_times = list(accumulate(self.send_intervals))

        ################################################################
        # create list of diff and diff pct on req_intervals/exp_req_int
        ################################################################
        self.diff_req_intervals = list(
            map(lambda t1, t2: t1 - t2,
                self.norm_req_intervals,
                self.expected_intervals))

        self.diff_req_ratio = [item/self.target_interval
                               for item in self.diff_req_intervals]

        ################################################################
        # create list of next target times and intervals
        ################################################################
        assert len(self.next_target_times) == self.total_requests
        # base_time = self.next_target_times[0]
        self.norm_next_target_times = [(item - base_time) * Pauser.NS_2_SECS
                                       for item in self.next_target_times]
        self.norm_next_target_intervals = list(
            map(lambda t1, t2: t1 - t2,
                self.norm_next_target_times,
                [0.0] + self.norm_next_target_times[:-1]))

        self.mean_next_target_interval = (self.norm_next_target_times[-1]
                                          / (self.total_requests - 1))

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
        for idx in range(self.total_requests):
            self.path_times.append([self.norm_start_times[idx],
                                    self.norm_before_req_times[idx],
                                    self.norm_arrival_times[idx],
                                    self.norm_req_times[idx],
                                    self.norm_after_req_times[idx]
                                    ])

        for item in self.path_times:
            self.path_intervals.append(
                [item[1] - item[0],
                 item[2] - item[1],
                 item[3] - item[2],
                 item[4] - item[3]]
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
        print(f'{self.norm_req_times[-1]=}')
        print(f'{self.mean_req_interval=}')
        print(f'{self.mean_before_req_interval=}')
        print(f'{self.mean_arrival_interval=}')
        print(f'{self.mean_after_req_interval=}')
        print(f'{self.mean_start_interval=}')
        print(f'{self.num_async_overs=}')

        ################################################################
        # build printable times
        ################################################################
        idx_list = list(range(self.total_requests))

        p_idx_list = list(map(lambda num: f'{num: 7}',
                              idx_list))
        # p_obtained_nowaits = list(map(lambda tf: f'{tf: 7}',
        #                               self.obtained_nowaits))
        p_send_times = list(map(lambda num: f'{num: 7.3f}',
                                self.send_times))
        p_send_interval_sums = list(map(lambda num: f'{num: 7.3f}',
                                        self.send_interval_sums))
        p_exp_interval_sums = list(map(lambda num: f'{num: 7.3f}',
                                       self.exp_interval_sums))
        p_target_times = list(map(lambda num: f'{num: 7.3f}',
                                  self.target_times))
        p_expected_times = list(map(lambda num: f'{num: 7.3f}',
                                    self.expected_times))

        # p_check_q_times = list(map(lambda num: f'{num: 7.3f}',
        #                        self.norm_check_async_q_times))

        p_before_req_times = list(map(lambda num: f'{num: 7.3f}',
                                      self.norm_before_req_times))
        p_arrival_times = list(map(lambda num: f'{num: 7.3f}',
                                   self.norm_arrival_times))
        p_req_times = list(map(lambda num: f'{num: 7.3f}',
                               self.norm_req_times))
        p_after_req_times = list(map(lambda num: f'{num: 7.3f}',
                                     self.norm_after_req_times))
        p_start_times = list(map(lambda num: f'{num: 7.3f}',
                                 self.norm_start_times))

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
        p_send_intervals = list(map(lambda num: f'{num: 7.3f}',
                                    self.send_intervals))
        p_target_intervals = list(map(lambda num: f'{num: 7.3f}',
                                      self.target_intervals))

        p_expected_intervals = list(map(lambda num: f'{num: 7.3f}',
                                        self.expected_intervals))

        # p_check_q_intervals = list(map(lambda num: f'{num: 7.3f}',
        #                            self.norm_check_async_q_intervals))

        p_before_req_intervals = list(map(lambda num: f'{num: 7.3f}',
                                          self.norm_before_req_intervals))
        p_arrival_intervals = list(map(lambda num: f'{num: 7.3f}',
                                   self.norm_arrival_intervals))
        p_req_intervals = list(map(lambda num: f'{num: 7.3f}',
                                   self.norm_req_intervals))
        p_after_req_intervals = list(map(lambda num: f'{num: 7.3f}',
                                         self.norm_after_req_intervals))
        p_start_intervals = list(map(lambda num: f'{num: 7.3f}',
                                     self.norm_start_intervals))

        p_diff_intervals = list(map(lambda num: f'{num: 7.3f}',
                                    self.diff_req_intervals))
        p_diff_ratio = list(map(lambda num: f'{num: 7.3f}',
                            self.diff_req_ratio))

        # p_time_traces_intervals = []
        # for time_trace in self.norm_time_traces_intervals:
        #     p_time_traces_interval = list(
        #     map(lambda num: f'{num: 7.3f}',
        #         time_trace))
        #     p_time_traces_intervals.append(p_time_traces_interval)
        #
        # p_stop_times_intervals = list(map(lambda num: f'{num: 7.3f}',
        #                               self.norm_stop_times_intervals))

        print(f'\n{p_idx_list            =}')
        # print(f'{p_obtained_nowaits    =}')
        print(f'{p_send_times          =}')
        print(f'{p_target_times        =}')
        print(f'{p_expected_times      =}')

        print(f'\n{p_start_times         =}')
        print(f'{p_before_req_times    =}')
        print(f'{p_arrival_times       =}')
        # print(f'{p_check_q_times       =}')
        print(f'{p_req_times           =}')
        print(f'{p_after_req_times     =}')

        print(f'\n{p_send_intervals      =}')
        print(f'{p_send_interval_sums  =}')
        print(f'{p_exp_interval_sums   =}')
        print(f'{p_target_intervals    =}')
        print(f'{p_expected_intervals  =}')

        print(f'\n{p_start_intervals     =}')
        print(f'{p_before_req_intervals=}')
        print(f'{p_arrival_intervals   =}')
        # print(f'{p_check_q_intervals   =}')
        print(f'{p_req_intervals       =}')
        print(f'{p_after_req_intervals =}')

        print(f'\n{p_diff_intervals      =}')
        print(f'{p_diff_ratio          =}')

        # if self.mode == Throttle.MODE_ASYNC:
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

        flowers(['path times:',
                 'idx  start   b4_req arrival   req    af_req    check '
                 '  pre-req pre-req2 '
                 '  req '
                 '  nxt-trg'])
        for idx, item in enumerate(self.path_times):
            line = (f'{item[0]: 7.3f} '
                    f'{item[1]: 7.3f} '
                    f'{item[2]: 7.3f} '
                    f'{item[3]: 7.3f} '
                    f'{item[4]: 7.3f} ')
            # line2 = (f'{self.path_async_times[idx][0]: 7.3f} '
            #          f'{self.path_async_times[idx][1]: 7.3f} '
            #          f'{self.path_async_times[idx][2]: 7.3f} '
            #          f'{self.path_async_times[idx][3]: 7.3f} '
            #          f'{self.path_async_times[idx][4]: 7.3f} ')
            # print(f'{idx:>3}: {line}   {line2}')
            print(f'{idx:>3}: {line}')

        flowers(['path intervals',
                 'idx  b4_req arrival   req    af_req    pre-req   '
                 'pre-req2 req '
                 '  nxt-trg'])
        for idx, item in enumerate(self.path_intervals):
            line = (f'{item[0]: 7.3f} '
                    f'{item[1]: 7.3f} '
                    f'{item[2]: 7.3f} '
                    f'{item[3]: 7.3f} ')

            # line2 = (f'{self.path_async_intervals[idx][0]: 7.3f} '
            #          f'{self.path_async_intervals[idx][1]: 7.3f} '
            #          f'{self.path_async_intervals[idx][2]: 7.3f} '
            #          f'{self.path_async_intervals[idx][3]: 7.3f} ')
            # print(f'{idx:>3}: {line}   {line2}')
            print(f'{idx:>3}: {line}')

        flowers('stats')
        diff_mean = stats.mean(self.diff_req_intervals[1:])
        print(f'{diff_mean=:.3f}')

        diff_median = stats.median(self.diff_req_intervals[1:])
        print(f'{diff_median=:.3f}')

        diff_pvariance = stats.pvariance(self.diff_req_intervals[1:])
        print(f'{diff_pvariance=:.5f}')

        diff_pstdev = stats.pstdev(self.diff_req_intervals[1:])
        print(f'{diff_pstdev=:.3f}')

        diff_variance = stats.variance(self.diff_req_intervals[1:])
        print(f'{diff_variance=:.5f}')

        diff_stdev = stats.stdev(self.diff_req_intervals[1:])
        print(f'{diff_stdev=:.3f}')

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

        if ((self.mode == Throttle.MODE_ASYNC) or
                (self.mode == Throttle.MODE_SYNC)):
            self.validate_async_sync()
        elif self.mode == Throttle.MODE_SYNC_EC:
            self.validate_sync_ec()
        elif self.mode == Throttle.MODE_SYNC_LB:
            self.validate_sync_lb()
        else:
            raise InvalidModeNum('Mode must be 1, 2, 3, or 4')

        self.reset()

    ####################################################################
    # validate_async_sync
    ####################################################################
    def validate_async_sync(self) -> None:
        """Validate results for sync."""
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

        print('num_requests_sent1:', self.total_requests)
        print('num_early1:', num_early)
        print('num_early_1pct1:', num_early_1pct)
        print('num_early_5pct1:', num_early_5pct)
        print('num_early_10pct1:', num_early_10pct)
        print('num_early_15pct1:', num_early_15pct)

        print('num_late1:', num_late)
        print('num_late_1pct1:', num_late_1pct)
        print('num_late_5pct1:', num_late_5pct)
        print('num_late_10pct1:', num_late_10pct)
        print('num_late_15pct1:', num_late_15pct)

        assert num_early_15pct == 0
        assert num_early_10pct == 0
        assert num_early_5pct == 0
        # assert num_early_1pct == 0

        assert num_late_15pct == 0
        assert num_late_10pct == 0
        assert num_late_5pct == 0
        # assert num_late_1pct == 0
        # assert num_late == 0

        assert self.target_interval <= self.mean_req_interval

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

        print(f'{num_early=}')
        print(f'{num_early_1pct=}')
        print(f'{num_early_5pct=}')
        print(f'{num_early_10pct=}')
        print(f'{num_early_15pct=}')

        print(f'{num_late=}')
        print(f'{num_late_1pct=}')
        print(f'{num_late_5pct=}')
        print(f'{num_late_10pct=}')
        print(f'{num_late_15pct=}')

        assert num_early_10pct == 0
        assert num_early_5pct == 0
        # assert num_long_early_1pct == 0

        assert num_late_15pct == 0
        assert num_late_10pct == 0
        assert num_late_5pct == 0
        # assert num_long_late_1pct == 0

        assert self.expected_times[-1] <= self.norm_req_times[-1]

        worst_case_mean_interval = (self.target_interval
                                    * (self.total_requests-self.early_count)
                                    ) / self.total_requests
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

        print(f'{num_early=}')
        print(f'{num_early_1pct=}')
        print(f'{num_early_5pct=}')
        print(f'{num_early_10pct=}')
        print(f'{num_early_15pct=}')

        print(f'{num_late=}')
        print(f'{num_late_1pct=}')
        print(f'{num_late_5pct=}')
        print(f'{num_late_10pct=}')
        print(f'{num_late_15pct=}')

        assert num_early_10pct == 0
        assert num_early_5pct == 0
        # assert num_long_early_1pct == 0

        assert num_late_15pct == 0
        assert num_late_10pct == 0
        assert num_late_5pct == 0
        # assert num_long_late_1pct == 0

        assert self.expected_times[-1] <= self.norm_req_times[-1]

        worst_case_mean_interval = (self.target_interval
                                    * (self.total_requests
                                       - self.lb_threshold)
                                    ) / self.total_requests
        assert worst_case_mean_interval <= self.mean_req_interval

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
        # self.check_async_q_times.append(self.t_throttle._check_async_q_time)
        assert idx == self.idx + 1
        assert interval == self.send_interval
        self.idx = idx
        return idx

    ####################################################################
    # request6
    ####################################################################
    def request6(self,
                 idx: int,
                 requests: int,
                 *,
                 seconds: int,
                 interval: float) -> int:
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
    def callback5(self,
                  idx: int,
                  *,
                  interval: float) -> None:
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
    def callback6(self,
                  idx: int,
                  requests: int,
                  *,
                  seconds: float,
                  interval: float) -> None:
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
        flowers('Example for README:')

        import time
        from scottbrian_throttle.throttle import throttle

        @throttle(requests=3, seconds=1, mode=Throttle.MODE_SYNC)
        def make_request(idx: int, previous_arrival_time: float) -> float:
            arrival_time = time.time()
            if idx == 0:
                previous_arrival_time = arrival_time
            interval = arrival_time - previous_arrival_time
            print(f'request {idx} interval from previous: {interval:0.2f} '
                  f'seconds')
            return arrival_time

        previous_time = 0.0
        for i in range(10):
            previous_time = make_request(i, previous_time)

    ####################################################################
    # test_throttle_example_2
    ####################################################################
    def test_throttle_example_2(self,
                                capsys: Any) -> None:
        """Method test_throttle_example_2.

        Args:
            capsys: pytest fixture to capture print output

        """
        from scottbrian_throttle.throttle import Throttle
        import time

        @throttle(requests=1, seconds=1, mode=Throttle.MODE_SYNC)
        def make_request() -> None:
            time.sleep(.1)  # simulate request that takes 1/10 second

        start_time = time.time()
        for i in range(10):
            make_request()
        elapsed_time = time.time() - start_time
        print(f'total time for 10 requests: {elapsed_time:0.1f} seconds')

        expected_result = 'total time for 10 requests: 9.1 seconds\n'

        captured = capsys.readouterr().out

        assert captured == expected_result

    ####################################################################
    # test_throttle_example_3
    ####################################################################
    def test_throttle_example_3(self,
                                capsys: Any) -> None:
        """Method test_throttle_example_3.

        Args:
            capsys: pytest fixture to capture print output

        """
        from scottbrian_throttle.throttle import Throttle
        import time
        a_throttle = Throttle(requests=1, seconds=1, mode=Throttle.MODE_SYNC)

        def make_request() -> None:
            time.sleep(.1)  # simulate request that takes 1/10 second
        start_time = time.time()
        for i in range(10):
            a_throttle.send_request(make_request)
        elapsed_time = time.time() - start_time
        print(f'total time for 10 requests: {elapsed_time:0.1f} seconds')

        expected_result = 'total time for 10 requests: 9.1 seconds\n'

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
