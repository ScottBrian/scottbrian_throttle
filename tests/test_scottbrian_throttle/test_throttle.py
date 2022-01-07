"""test_throttle.py module."""

import pytest
import math
import statistics as stats
import time
from typing import Any, cast, List, Optional, Tuple, Union
from enum import Enum
import threading
from dataclasses import dataclass
from scottbrian_utils.flower_box import print_flower_box_msg as flowers

from scottbrian_utils.throttle import Throttle, throttle
from scottbrian_utils.throttle import shutdown_throttle_funcs
from scottbrian_utils.throttle import IncorrectRequestsSpecified
from scottbrian_utils.throttle import IncorrectSecondsSpecified
from scottbrian_utils.throttle import IncorrectModeSpecified
from scottbrian_utils.throttle import IncorrectAsyncQSizeSpecified
from scottbrian_utils.throttle import AsyncQSizeNotAllowed
from scottbrian_utils.throttle import IncorrectEarlyCountSpecified
from scottbrian_utils.throttle import MissingEarlyCountSpecification
from scottbrian_utils.throttle import EarlyCountNotAllowed
from scottbrian_utils.throttle import IncorrectLbThresholdSpecified
from scottbrian_utils.throttle import MissingLbThresholdSpecification
from scottbrian_utils.throttle import LbThresholdNotAllowed
from scottbrian_utils.throttle import AttemptedShutdownForSyncThrottle
from scottbrian_utils.throttle import IncorrectShutdownTypeSpecified

import logging

logger = logging.getLogger(__name__)


###############################################################################
# Throttle test exceptions
###############################################################################
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


###############################################################################
# ReqTime data class used for shutdown testing
###############################################################################
@dataclass
class ReqTime:
    """ReqTime class contains number of completed requests and last time."""
    num_reqs: int = 0
    f_time: float = 0.0


###############################################################################
# requests_arg fixture
###############################################################################
requests_arg_list = [1, 2, 3]


@pytest.fixture(params=requests_arg_list)  # type: ignore
def requests_arg(request: Any) -> int:
    """Using different requests.

    Args:
        request: special fixture that returns the fixture params

    Returns:
        The params values are returned one at a time
    """
    return cast(int, request.param)


###############################################################################
# seconds_arg fixture
###############################################################################
seconds_arg_list = [0.3, 0.5, 1, 2]


@pytest.fixture(params=seconds_arg_list)  # type: ignore
def seconds_arg(request: Any) -> Union[int, float]:
    """Using different seconds.

    Args:
        request: special fixture that returns the fixture params

    Returns:
        The params values are returned one at a time
    """
    return cast(Union[int, float], request.param)


###############################################################################
# shutdown_requests_arg fixture
###############################################################################
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


###############################################################################
# f_num_reqs_arg fixture
###############################################################################
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


###############################################################################
# num_shutdown1_funcs_arg fixture
###############################################################################
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


###############################################################################
# shutdown_seconds_arg fixture
###############################################################################
shutdown_seconds_arg_list = [0.3, 1, 2]


@pytest.fixture(params=shutdown_seconds_arg_list)  # type: ignore
def shutdown_seconds_arg(request: Any) -> Union[int, float]:
    """Using different seconds.

    Args:
        request: special fixture that returns the fixture params

    Returns:
        The params values are returned one at a time
    """
    return cast(Union[int, float], request.param)


###############################################################################
# shutdown_type_arg fixture
###############################################################################
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


###############################################################################
# timeout_arg fixture
###############################################################################
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


###############################################################################
# sleep_delay_arg fixture
###############################################################################
sleep_delay_arg_list = [0.3, 1.1]


@pytest.fixture(params=sleep_delay_arg_list)  # type: ignore
def sleep_delay_arg(request: Any) -> float:
    """Whether to use timeout.

    Args:
        request: special fixture that returns the fixture params

    Returns:
        The params values are returned one at a time

    """
    return cast(float, request.param)


###############################################################################
# sleep2_delay_arg fixture
###############################################################################
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


###############################################################################
# which_throttle_arg fixture
###############################################################################
WT = Enum('WT',
          'PieThrottleDirectShutdown '
          'PieThrottleShutdownFuncs '
          'NonPieThrottle')

which_throttle_arg_list = [WT.PieThrottleDirectShutdown,
                           WT.PieThrottleShutdownFuncs,
                           WT.NonPieThrottle]


@pytest.fixture(params=which_throttle_arg_list)  # type: ignore
def which_throttle_arg(request: Any) -> int:
    """Using different requests.

    Args:
        request: special fixture that returns the fixture params

    Returns:
        The params values are returned one at a time
    """
    return cast(int, request.param)


###############################################################################
# mode_arg fixture
###############################################################################
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


###############################################################################
# mode_arg fixture
###############################################################################
lb_threshold_arg_list = [0.1, 1, 1.5, 3]


@pytest.fixture(params=lb_threshold_arg_list)  # type: ignore
def lb_threshold_arg(request: Any) -> Union[int, float]:
    """Using different lb_threshold values.

    Args:
        request: special fixture that returns the fixture params

    Returns:
        The params values are returned one at a time
    """
    return cast(Union[int, float], request.param)


###############################################################################
# early_count_arg fixture
###############################################################################
early_count_arg_list = [1, 2, 3]


@pytest.fixture(params=early_count_arg_list)  # type: ignore
def early_count_arg(request: Any) -> int:
    """Using different early_count values.

    Args:
        request: special fixture that returns the fixture params

    Returns:
        The params values are returned one at a time
    """
    return cast(int, request.param)


###############################################################################
# send_interval_mult_arg fixture
###############################################################################
send_interval_mult_arg_list = [0.0, 0.3, 0.9, 1.0, 1.1]


@pytest.fixture(params=send_interval_mult_arg_list)  # type: ignore
def send_interval_mult_arg(request: Any) -> float:
    """Using different send rates.

    Args:
        request: special fixture that returns the fixture params

    Returns:
        The params values are returned one at a time
    """
    return cast(float, request.param)


###############################################################################
# request_style_arg fixture
###############################################################################
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


###############################################################################
# TestThrottleBasic class to test Throttle methods
###############################################################################
class TestThrottleErrors:
    """TestThrottle class."""
    def test_throttle_bad_args(self) -> None:
        """test_throttle using bad arguments."""
        #######################################################################
        # bad requests
        #######################################################################
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

        #######################################################################
        # bad seconds
        #######################################################################
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

        #######################################################################
        # bad mode
        #######################################################################
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

        #######################################################################
        # bad async_q_size
        #######################################################################
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
        #######################################################################
        # bad early_count
        #######################################################################
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
        #######################################################################
        # bad lb_threshold
        #######################################################################
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


###############################################################################
# TestThrottleBasic class to test Throttle methods
###############################################################################
class TestThrottleBasic:
    """Test basic functions of Throttle."""

    ###########################################################################
    # len checks
    ###########################################################################
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
        # create a throttle with a long enough interval to ensure that we
        # can populate the async_q and get the length before we start
        # dequeing requests from it
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
            # start_shutdown will return when the request_q cleanup is complete
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

    ###########################################################################
    # task done check
    ###########################################################################
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
    #                           seconds=requests_arg * 0.25,  #  1/4 interval
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

    ###########################################################################
    # repr with mode async
    ###########################################################################
    def test_throttle_repr_async(self,
                                 requests_arg: int,
                                 seconds_arg: Union[int, float]
                                 ) -> None:
        """test_throttle repr mode 1 with various requests and seconds.

        Args:
            requests_arg: fixture that provides args
            seconds_arg: fixture that provides args

        """
        #######################################################################
        # throttle with async_q_size specified
        #######################################################################
        a_throttle = Throttle(requests=requests_arg,
                              seconds=seconds_arg,
                              mode=Throttle.MODE_ASYNC)

        expected_repr_str = \
            f'Throttle(' \
            f'requests={requests_arg}, ' \
            f'seconds={float(seconds_arg)}, ' \
            f'mode=Throttle.MODE_ASYNC, ' \
            f'async_q_size={Throttle.DEFAULT_ASYNC_Q_SIZE})'

        assert repr(a_throttle) == expected_repr_str

        a_throttle.start_shutdown()

        #######################################################################
        # throttle with async_q_size specified
        #######################################################################
        q_size = requests_arg * 3
        a_throttle = Throttle(requests=requests_arg,
                              seconds=seconds_arg,
                              mode=Throttle.MODE_ASYNC,
                              async_q_size=q_size)

        expected_repr_str = \
            f'Throttle(' \
            f'requests={requests_arg}, ' \
            f'seconds={float(seconds_arg)}, ' \
            f'mode=Throttle.MODE_ASYNC, ' \
            f'async_q_size={q_size})'

        assert repr(a_throttle) == expected_repr_str

        a_throttle.start_shutdown()

    ###########################################################################
    # repr with mode sync
    ###########################################################################
    def test_throttle_repr_sync(self,
                                requests_arg: int,
                                seconds_arg: Union[int, float],
                                ) -> None:
        """test_throttle repr mode 2 with various requests and seconds.

        Args:
            requests_arg: fixture that provides args
            seconds_arg: fixture that provides args
        """
        a_throttle = Throttle(requests=requests_arg,
                              seconds=seconds_arg,
                              mode=Throttle.MODE_SYNC)

        expected_repr_str = \
            f'Throttle(' \
            f'requests={requests_arg}, ' \
            f'seconds={float(seconds_arg)}, ' \
            f'mode=Throttle.MODE_SYNC)'

        assert repr(a_throttle) == expected_repr_str

    ###########################################################################
    # repr with mode sync early count
    ###########################################################################
    def test_throttle_repr_sync_ec(self,
                                   requests_arg: int,
                                   seconds_arg: Union[int, float],
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

        expected_repr_str = \
            f'Throttle(' \
            f'requests={requests_arg}, ' \
            f'seconds={float(seconds_arg)}, ' \
            f'mode=Throttle.MODE_SYNC_EC, ' \
            f'early_count={early_count_arg})'

        assert repr(a_throttle) == expected_repr_str

    ###########################################################################
    # repr with mode sync leaky bucket
    ###########################################################################
    def test_throttle_repr_sync_lb(self,
                                   requests_arg: int,
                                   seconds_arg: Union[int, float],
                                   lb_threshold_arg: Union[int, float],
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

        expected_repr_str = \
            f'Throttle(' \
            f'requests={requests_arg}, ' \
            f'seconds={float(seconds_arg)}, ' \
            f'mode=Throttle.MODE_SYNC_LB, ' \
            f'lb_threshold={float(lb_threshold_arg)})'

        assert repr(a_throttle) == expected_repr_str


###############################################################################
# TestThrottleDecoratorErrors class
###############################################################################
class TestThrottleDecoratorErrors:
    """TestThrottleDecoratorErrors class."""
    def test_pie_throttle_bad_args(self) -> None:
        """test_throttle using bad arguments."""
        #######################################################################
        # bad requests
        #######################################################################
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
        #######################################################################
        # bad seconds
        #######################################################################
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

        #######################################################################
        # bad mode
        #######################################################################
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

        #######################################################################
        # bad async_q_size
        #######################################################################
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

        #######################################################################
        # bad early_count
        #######################################################################
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
        #######################################################################
        # bad lb_threshold
        #######################################################################
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


###############################################################################
# TestThrottle class
###############################################################################
class TestThrottle:
    """Class TestThrottle.

    The following section tests each combination of arguments to the throttle.

    For the decorator, there are three styles of decoration (using pie,
    calling with the function as the first parameter, and calling the
    decorator with the function specified after the call. This test is
    especially useful to ensure that the type hints are working correctly,
    and that all combinations are accepted by python.

    The non-decorator cases will be simpler, with the exception of
    doing some explicit calls to shutdown the throttle (which is not possible
    with the decorator style - for this, we can set the start_shutdown_event.

    The following keywords with various values and in all combinations are
    tested:
        requests - various increments
        seconds - various increments, both int and float
        throttle_enabled - true/false

    """
    ###########################################################################
    # test_throttle_async
    ###########################################################################
    def test_throttle_async(self,
                            requests_arg: int,
                            seconds_arg: Union[int, float],
                            send_interval_mult_arg: float,
                            request_style_arg: int
                            ) -> None:
        """Method to start throttle mode1 tests.

        Args:
            requests_arg: number of requests per interval from fixture
            seconds_arg: interval for number of requests from fixture
            send_interval_mult_arg: interval between each send of a request
            request_style_arg: chooses function args mix
        """
        send_interval = (seconds_arg / requests_arg) * send_interval_mult_arg
        self.throttle_router(requests=requests_arg,
                             seconds=seconds_arg,
                             mode=Throttle.MODE_ASYNC,
                             early_count=0,
                             lb_threshold=0,
                             send_interval=send_interval,
                             request_style=request_style_arg)

    ###########################################################################
    # test_throttle_sync
    ###########################################################################
    def test_throttle_sync(self,
                           requests_arg: int,
                           seconds_arg: Union[int, float],
                           early_count_arg: int,
                           send_interval_mult_arg: float,
                           request_style_arg: int
                           ) -> None:
        """Method to start throttle sync tests.

        Args:
            requests_arg: number of requests per interval from fixture
            seconds_arg: interval for number of requests from fixture
            early_count_arg: count used for sync with early count algo
            send_interval_mult_arg: interval between each send of a request
            request_style_arg: chooses function args mix
        """
        send_interval = (seconds_arg / requests_arg) * send_interval_mult_arg
        self.throttle_router(requests=requests_arg,
                             seconds=seconds_arg,
                             mode=Throttle.MODE_SYNC_EC,
                             early_count=0,
                             lb_threshold=0,
                             send_interval=send_interval,
                             request_style=request_style_arg)

    ###########################################################################
    # test_throttle_sync_ec
    ###########################################################################
    def test_throttle_sync_ec(self,
                              requests_arg: int,
                              seconds_arg: Union[int, float],
                              early_count_arg: int,
                              send_interval_mult_arg: float,
                              request_style_arg: int
                              ) -> None:
        """Method to start throttle sync_ec tests.

        Args:
            requests_arg: number of requests per interval from fixture
            seconds_arg: interval for number of requests from fixture
            early_count_arg: count used for sync with early count algo
            send_interval_mult_arg: interval between each send of a request
            request_style_arg: chooses function args mix
        """
        send_interval = (seconds_arg / requests_arg) * send_interval_mult_arg
        self.throttle_router(requests=requests_arg,
                             seconds=seconds_arg,
                             mode=Throttle.MODE_SYNC_EC,
                             early_count=early_count_arg,
                             lb_threshold=0,
                             send_interval=send_interval,
                             request_style=request_style_arg)

    ###########################################################################
    # test_throttle_sync_lb
    ###########################################################################
    def test_throttle_sync_lb(self,
                              requests_arg: int,
                              seconds_arg: Union[int, float],
                              lb_threshold_arg: Union[int, float],
                              send_interval_mult_arg: float,
                              request_style_arg: int
                              ) -> None:
        """Method to start throttle sync_lb tests.

        Args:
            requests_arg: number of requests per interval from fixture
            seconds_arg: interval for number of requests from fixture
            lb_threshold_arg: threshold used with sync leaky bucket algo
            send_interval_mult_arg: interval between each send of a request
            request_style_arg: chooses function args mix
        """
        send_interval = (seconds_arg / requests_arg) * send_interval_mult_arg
        self.throttle_router(requests=requests_arg,
                             seconds=seconds_arg,
                             mode=Throttle.MODE_SYNC_LB,
                             early_count=0,
                             lb_threshold=lb_threshold_arg,
                             send_interval=send_interval,
                             request_style=request_style_arg)

    ###########################################################################
    # throttle_router
    ###########################################################################
    def throttle_router(self,
                        requests: int,
                        seconds: Union[int, float],
                        mode: int,
                        early_count: int,
                        lb_threshold: Union[int, float],
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
        request_multiplier = 32
        #######################################################################
        # Instantiate Throttle
        #######################################################################
        if mode == Throttle.MODE_ASYNC:
            a_throttle = Throttle(requests=requests,
                                  seconds=seconds,
                                  mode=Throttle.MODE_ASYNC,
                                  async_q_size=(requests
                                                * request_multiplier)
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

        #######################################################################
        # Instantiate Request Validator
        #######################################################################
        request_validator = RequestValidator(requests=requests,
                                             seconds=seconds,
                                             mode=mode,
                                             early_count=early_count,
                                             lb_threshold=lb_threshold,
                                             request_mult=request_multiplier,
                                             send_interval=send_interval)

        #######################################################################
        # Make requests and validate
        #######################################################################
        if request_style == 0:
            for i in range(requests * request_multiplier):
                # 0
                rc = a_throttle.send_request(request_validator.request0)
                if mode == Throttle.MODE_ASYNC:
                    assert rc is Throttle.RC_OK
                else:
                    assert rc == i
                time.sleep(send_interval)

            if mode == Throttle.MODE_ASYNC:
                a_throttle.start_shutdown(
                    shutdown_type=Throttle.TYPE_SHUTDOWN_SOFT)

            request_validator.validate_series()  # validate for the series

        elif request_style == 1:
            for i in range(requests * request_multiplier):
                # 1
                rc = a_throttle.send_request(request_validator.request1, i)
                exp_rc = i if mode != Throttle.MODE_ASYNC else Throttle.RC_OK
                assert rc == exp_rc
                time.sleep(send_interval)

            if mode == Throttle.MODE_ASYNC:
                a_throttle.start_shutdown(
                    shutdown_type=Throttle.TYPE_SHUTDOWN_SOFT)
            request_validator.validate_series()  # validate for the series

        elif request_style == 2:
            for i in range(requests * request_multiplier):
                # 2
                rc = a_throttle.send_request(request_validator.request2,
                                             i,
                                             requests)
                exp_rc = i if mode != Throttle.MODE_ASYNC else Throttle.RC_OK
                assert rc == exp_rc
                time.sleep(send_interval)

            if mode == Throttle.MODE_ASYNC:
                a_throttle.start_shutdown(
                    shutdown_type=Throttle.TYPE_SHUTDOWN_SOFT)
            request_validator.validate_series()  # validate for the series

        elif request_style == 3:
            for i in range(requests * request_multiplier):
                # 3
                rc = a_throttle.send_request(request_validator.request3, idx=i)
                exp_rc = i if mode != Throttle.MODE_ASYNC else Throttle.RC_OK
                assert rc == exp_rc
                time.sleep(send_interval)

            if mode == Throttle.MODE_ASYNC:
                a_throttle.start_shutdown(
                    shutdown_type=Throttle.TYPE_SHUTDOWN_SOFT)
            request_validator.validate_series()  # validate for the series

        elif request_style == 4:
            for i in range(requests * request_multiplier):
                # 4
                rc = a_throttle.send_request(request_validator.request4,
                                             idx=i,
                                             seconds=seconds)
                exp_rc = i if mode != Throttle.MODE_ASYNC else Throttle.RC_OK
                assert rc == exp_rc
                time.sleep(send_interval)

            if mode == Throttle.MODE_ASYNC:
                a_throttle.start_shutdown(
                    shutdown_type=Throttle.TYPE_SHUTDOWN_SOFT)
            request_validator.validate_series()  # validate for the series

        elif request_style == 5:
            for i in range(requests * request_multiplier):
                # 5
                rc = a_throttle.send_request(request_validator.request5,
                                             i,
                                             interval=send_interval)
                exp_rc = i if mode != Throttle.MODE_ASYNC else Throttle.RC_OK
                assert rc == exp_rc
                time.sleep(send_interval)

            if mode == Throttle.MODE_ASYNC:
                a_throttle.start_shutdown(
                    shutdown_type=Throttle.TYPE_SHUTDOWN_SOFT)
            request_validator.validate_series()  # validate for the series

        elif request_style == 6:
            for i in range(requests * request_multiplier):
                # 6
                rc = a_throttle.send_request(request_validator.request6,
                                             i,
                                             requests,
                                             seconds=seconds,
                                             interval=send_interval)
                exp_rc = i if mode != Throttle.MODE_ASYNC else Throttle.RC_OK
                assert rc == exp_rc
                time.sleep(send_interval)

            if mode == Throttle.MODE_ASYNC:
                a_throttle.start_shutdown(
                    shutdown_type=Throttle.TYPE_SHUTDOWN_SOFT)
            request_validator.validate_series()  # validate for the series

        else:
            raise BadRequestStyleArg('The request style arg must be 0 to 6')

    ###########################################################################
    # test_pie_throttle_async
    ###########################################################################
    def test_pie_throttle_async(self,
                                requests_arg: int,
                                seconds_arg: Union[int, float],
                                send_interval_mult_arg: float
                                ) -> None:
        """Method to start throttle mode1 tests.

        Args:
            requests_arg: number of requests per interval from fixture
            seconds_arg: interval for number of requests from fixture
            send_interval_mult_arg: interval between each send of a request
        """
        #######################################################################
        # Instantiate Request Validator
        #######################################################################
        request_multiplier = 32
        send_interval = (seconds_arg/requests_arg) * send_interval_mult_arg
        request_validator = RequestValidator(requests=requests_arg,
                                             seconds=seconds_arg,
                                             mode=Throttle.MODE_ASYNC,
                                             early_count=0,
                                             lb_threshold=0,
                                             request_mult=request_multiplier,
                                             send_interval=send_interval)

        #######################################################################
        # Decorate functions with throttle
        #######################################################################
        @throttle(requests=requests_arg,
                  seconds=seconds_arg,
                  mode=Throttle.MODE_ASYNC)
        def f0() -> None:
            request_validator.callback0()

        @throttle(requests=requests_arg,
                  seconds=seconds_arg,
                  mode=Throttle.MODE_ASYNC)
        def f1(idx: int) -> None:
            request_validator.callback1(idx)

        @throttle(requests=requests_arg,
                  seconds=seconds_arg,
                  mode=Throttle.MODE_ASYNC)
        def f2(idx: int, requests: int) -> None:
            request_validator.callback2(idx, requests)

        @throttle(requests=requests_arg,
                  seconds=seconds_arg,
                  mode=Throttle.MODE_ASYNC)
        def f3(*, idx: int) -> None:
            request_validator.callback3(idx=idx)

        @throttle(requests=requests_arg,
                  seconds=seconds_arg,
                  mode=Throttle.MODE_ASYNC)
        def f4(*, idx: int, seconds: float) -> None:
            request_validator.callback4(idx=idx, seconds=seconds)

        @throttle(requests=requests_arg,
                  seconds=seconds_arg,
                  mode=Throttle.MODE_ASYNC)
        def f5(idx: int, *, interval: float) -> None:
            request_validator.callback5(idx,
                                        interval=interval)

        @throttle(requests=requests_arg,
                  seconds=seconds_arg,
                  mode=Throttle.MODE_ASYNC)
        def f6(idx: int, requests: int, *, seconds: float, interval: float
               ) -> None:
            request_validator.callback6(idx,
                                        requests,
                                        seconds=seconds,
                                        interval=interval)

        request_validator.add_func_throttles(f0, f1, f2, f3, f4, f5, f6)
        #######################################################################
        # Invoke the functions
        #######################################################################
        about_to_send_time: List[float] = []
        after_send_time: List[float] = []
        start_time = time.time()
        for i in range(requests_arg * request_multiplier):
            about_to_send_time.append(time.time())
            rc = f0()
            sent_time = time.time()
            after_send_time.append(sent_time)
            assert rc == 0
            time.sleep((start_time + (send_interval * (i+1))) - time.time())

        # f0.throttle.start_shutdown()
        shutdown_throttle_funcs(f0)
        request_validator.validate_series(
            about_to_send_time=about_to_send_time,
            after_send_time=after_send_time)  # validate
        # for the series

        about_to_send_time: List[float] = []
        after_send_time: List[float] = []
        start_time = time.time()
        for i in range(requests_arg * request_multiplier):
            about_to_send_time.append(time.time())
            rc = f1(i)
            sent_time = time.time()
            after_send_time.append(sent_time)
            assert rc == 0
            time.sleep((start_time + (send_interval * (i+1))) - time.time())
        f1.throttle.start_shutdown()
        request_validator.validate_series(
            about_to_send_time=about_to_send_time,
            after_send_time=after_send_time)  # validate

        about_to_send_time: List[float] = []
        after_send_time: List[float] = []
        start_time = time.time()
        for i in range(requests_arg * request_multiplier):
            about_to_send_time.append(time.time())
            rc = f2(i, requests_arg)
            sent_time = time.time()
            after_send_time.append(sent_time)
            assert rc == 0
            time.sleep((start_time + (send_interval * (i+1))) - time.time())
        shutdown_throttle_funcs(f2)
        request_validator.validate_series(
            about_to_send_time=about_to_send_time,
            after_send_time=after_send_time)  # validate

        about_to_send_time: List[float] = []
        after_send_time: List[float] = []
        start_time = time.time()
        for i in range(requests_arg * request_multiplier):
            about_to_send_time.append(time.time())
            rc = f3(idx=i)
            sent_time = time.time()
            after_send_time.append(sent_time)
            assert rc == 0
            time.sleep((start_time + (send_interval * (i+1))) - time.time())
        f3.throttle.start_shutdown()
        request_validator.validate_series(
            about_to_send_time=about_to_send_time,
            after_send_time=after_send_time)  # validate

        about_to_send_time: List[float] = []
        after_send_time: List[float] = []
        start_time = time.time()
        for i in range(requests_arg * request_multiplier):
            about_to_send_time.append(time.time())
            rc = f4(idx=i, seconds=seconds_arg)
            sent_time = time.time()
            after_send_time.append(sent_time)
            assert rc == 0
            time.sleep((start_time + (send_interval * (i+1))) - time.time())
        shutdown_throttle_funcs(f4)
        request_validator.validate_series(
            about_to_send_time=about_to_send_time,
            after_send_time=after_send_time)  # validate

        about_to_send_time: List[float] = []
        after_send_time: List[float] = []
        start_time = time.time()
        for i in range(requests_arg * request_multiplier):
            about_to_send_time.append(time.time())
            rc = f5(idx=i, interval=send_interval)
            sent_time = time.time()
            after_send_time.append(sent_time)
            assert rc == 0
            time.sleep((start_time + (send_interval * (i+1))) - time.time())
        f5.throttle.start_shutdown()
        request_validator.validate_series(
            about_to_send_time=about_to_send_time,
            after_send_time=after_send_time)  # validate

        about_to_send_time: List[float] = []
        after_send_time: List[float] = []
        start_time = time.time()
        for i in range(requests_arg * request_multiplier):
            about_to_send_time.append(time.time())
            rc = f6(i, requests_arg,
                    seconds=seconds_arg, interval=send_interval)
            sent_time = time.time()
            after_send_time.append(sent_time)
            assert rc == 0
            time.sleep((start_time + (send_interval * (i+1))) - time.time())
        shutdown_throttle_funcs(f6)
        request_validator.validate_series(
            about_to_send_time=about_to_send_time,
            after_send_time=after_send_time)  # validate

    ###########################################################################
    # test_throttle_sync
    ###########################################################################
    def test_pie_throttle_sync(self,
                               requests_arg: int,
                               seconds_arg: Union[int, float],
                               send_interval_mult_arg: float
                               ) -> None:
        """Method to start throttle sync tests.

        Args:
            requests_arg: number of requests per interval from fixture
            seconds_arg: interval for number of requests from fixture
            send_interval_mult_arg: interval between each send of a request
        """
        #######################################################################
        # Instantiate Request Validator
        #######################################################################
        request_multiplier = 32
        send_interval = (seconds_arg / requests_arg) * send_interval_mult_arg
        request_validator = RequestValidator(requests=requests_arg,
                                             seconds=seconds_arg,
                                             mode=Throttle.MODE_SYNC,
                                             early_count=0,
                                             lb_threshold=0,
                                             request_mult=request_multiplier,
                                             send_interval=send_interval)

        #######################################################################
        # Decorate functions with throttle
        #######################################################################
        @throttle(requests=requests_arg,
                  seconds=seconds_arg,
                  mode=Throttle.MODE_SYNC)
        def f0() -> int:
            request_validator.callback0()
            return 42

        @throttle(requests=requests_arg,
                  seconds=seconds_arg,
                  mode=Throttle.MODE_SYNC)
        def f1(idx: int) -> int:
            request_validator.callback1(idx)
            return idx + 42 + 1

        @throttle(requests=requests_arg,
                  seconds=seconds_arg,
                  mode=Throttle.MODE_SYNC)
        def f2(idx: int, requests: int) -> int:
            request_validator.callback2(idx, requests)
            return idx + 42 + 2

        @throttle(requests=requests_arg,
                  seconds=seconds_arg,
                  mode=Throttle.MODE_SYNC)
        def f3(*, idx: int) -> int:
            request_validator.callback3(idx=idx)
            return idx + 42 + 3

        @throttle(requests=requests_arg,
                  seconds=seconds_arg,
                  mode=Throttle.MODE_SYNC)
        def f4(*, idx: int, seconds: float) -> int:
            request_validator.callback4(idx=idx, seconds=seconds)
            return idx + 42 + 4

        @throttle(requests=requests_arg,
                  seconds=seconds_arg,
                  mode=Throttle.MODE_SYNC)
        def f5(idx: int, *, interval: float) -> int:
            request_validator.callback5(idx,
                                        interval=interval)
            return idx + 42 + 5

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

        #######################################################################
        # Invoke the functions
        #######################################################################
        for i in range(requests_arg * request_multiplier):
            rc = f0()
            assert rc == 0
            time.sleep(send_interval)
        request_validator.validate_series()  # validate for the series

        for i in range(requests_arg * request_multiplier):
            rc = f1(i)
            assert rc == i + 42 + 1
            time.sleep(send_interval)
        request_validator.validate_series()  # validate for the series

        for i in range(requests_arg * request_multiplier):
            rc = f2(i, requests_arg)
            assert rc == i + 42 + 2
            time.sleep(send_interval)
        request_validator.validate_series()  # validate for the series

        for i in range(requests_arg * request_multiplier):
            rc = f3(idx=i)
            assert rc == i + 42 + 3
            time.sleep(send_interval)
        request_validator.validate_series()  # validate for the series

        for i in range(requests_arg * request_multiplier):
            rc = f4(idx=i, seconds=seconds_arg)
            assert rc == i + 42 + 4
            time.sleep(send_interval)
        request_validator.validate_series()  # validate for the series

        for i in range(requests_arg * request_multiplier):
            rc = f5(idx=i, interval=send_interval_mult_arg)
            assert rc == i + 42 + 5
            time.sleep(send_interval)
        request_validator.validate_series()  # validate for the series

        for i in range(requests_arg * request_multiplier):
            rc = f6(i, requests_arg,
                    seconds=seconds_arg, interval=send_interval_mult_arg)
            assert rc == i + 42 + 6
            time.sleep(send_interval)
        request_validator.validate_series()  # validate for the series

    ###########################################################################
    # test_throttle_sync_ec
    ###########################################################################
    def test_pie_throttle_sync_ec(self,
                                  requests_arg: int,
                                  seconds_arg: Union[int, float],
                                  early_count_arg: int,
                                  send_interval_mult_arg: float
                                  ) -> None:
        """Method to start throttle sync_ec tests.

        Args:
            requests_arg: number of requests per interval from fixture
            seconds_arg: interval for number of requests from fixture
            early_count_arg: count used for sync with early count algo
            send_interval_mult_arg: interval between each send of a request
        """
        #######################################################################
        # Instantiate Request Validator
        #######################################################################
        request_multiplier = 32
        send_interval = (seconds_arg / requests_arg) * send_interval_mult_arg
        request_validator = RequestValidator(requests=requests_arg,
                                             seconds=seconds_arg,
                                             mode=Throttle.MODE_SYNC_EC,
                                             early_count=early_count_arg,
                                             lb_threshold=0,
                                             request_mult=request_multiplier,
                                             send_interval=send_interval)

        #######################################################################
        # Decorate functions with throttle
        #######################################################################
        @throttle(requests=requests_arg,
                  seconds=seconds_arg,
                  mode=Throttle.MODE_SYNC_EC,
                  early_count=early_count_arg)
        def f0() -> int:
            request_validator.callback0()
            return 42

        @throttle(requests=requests_arg,
                  seconds=seconds_arg,
                  mode=Throttle.MODE_SYNC_EC,
                  early_count=early_count_arg)
        def f1(idx: int) -> int:
            request_validator.callback1(idx)
            return idx + 42 + 1

        @throttle(requests=requests_arg,
                  seconds=seconds_arg,
                  mode=Throttle.MODE_SYNC_EC,
                  early_count=early_count_arg)
        def f2(idx: int, requests: int) -> int:
            request_validator.callback2(idx, requests)
            return idx + 42 + 2

        @throttle(requests=requests_arg,
                  seconds=seconds_arg,
                  mode=Throttle.MODE_SYNC_EC,
                  early_count=early_count_arg)
        def f3(*, idx: int) -> int:
            request_validator.callback3(idx=idx)
            return idx + 42 + 3

        @throttle(requests=requests_arg,
                  seconds=seconds_arg,
                  mode=Throttle.MODE_SYNC_EC,
                  early_count=early_count_arg)
        def f4(*, idx: int, seconds: float) -> int:
            request_validator.callback4(idx=idx, seconds=seconds)
            return idx + 42 + 4

        @throttle(requests=requests_arg,
                  seconds=seconds_arg,
                  mode=Throttle.MODE_SYNC_EC,
                  early_count=early_count_arg)
        def f5(idx: int, *, interval: float) -> int:
            request_validator.callback5(idx,
                                        interval=interval)
            return idx + 42 + 5

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

        #######################################################################
        # Invoke the functions
        #######################################################################
        for i in range(requests_arg * request_multiplier):
            rc = f0()
            assert rc == 0
            time.sleep(send_interval)
        request_validator.validate_series()  # validate for the series

        for i in range(requests_arg * request_multiplier):
            rc = f1(i)
            assert rc == i + 42 + 1
            time.sleep(send_interval)
        request_validator.validate_series()  # validate for the series

        for i in range(requests_arg * request_multiplier):
            rc = f2(i, requests_arg)
            assert rc == i + 42 + 2
            time.sleep(send_interval)
        request_validator.validate_series()  # validate for the series

        for i in range(requests_arg * request_multiplier):
            rc = f3(idx=i)
            assert rc == i + 42 + 3
            time.sleep(send_interval)
        request_validator.validate_series()  # validate for the series

        for i in range(requests_arg * request_multiplier):
            rc = f4(idx=i, seconds=seconds_arg)
            assert rc == i + 42 + 4
            time.sleep(send_interval)
        request_validator.validate_series()  # validate for the series

        for i in range(requests_arg * request_multiplier):
            rc = f5(idx=i, interval=send_interval_mult_arg)
            assert rc == i + 42 + 5
            time.sleep(send_interval)
        request_validator.validate_series()  # validate for the series

        for i in range(requests_arg * request_multiplier):
            rc = f6(i, requests_arg,
                    seconds=seconds_arg, interval=send_interval_mult_arg)
            assert rc == i + 42 + 6
            time.sleep(send_interval)
        request_validator.validate_series()  # validate for the series

    ###########################################################################
    # test_throttle_sync_lb
    ###########################################################################
    def test_pie_throttle_sync_lb(self,
                                  requests_arg: int,
                                  seconds_arg: Union[int, float],
                                  lb_threshold_arg: Union[int, float],
                                  send_interval_mult_arg: float
                                  ) -> None:
        """Method to start throttle sync_lb tests.

        Args:
            requests_arg: number of requests per interval from fixture
            seconds_arg: interval for number of requests from fixture
            lb_threshold_arg: threshold used with sync leaky bucket algo
            send_interval_mult_arg: interval between each send of a request
        """
        #######################################################################
        # Instantiate Request Validator
        #######################################################################
        request_multiplier = 32
        send_interval = (seconds_arg / requests_arg) * send_interval_mult_arg
        request_validator = RequestValidator(requests=requests_arg,
                                             seconds=seconds_arg,
                                             mode=Throttle.MODE_SYNC_LB,
                                             early_count=0,
                                             lb_threshold=lb_threshold_arg,
                                             request_mult=request_multiplier,
                                             send_interval=send_interval)

        #######################################################################
        # Decorate functions with throttle
        #######################################################################
        @throttle(requests=requests_arg,
                  seconds=seconds_arg,
                  mode=Throttle.MODE_SYNC_LB,
                  lb_threshold=lb_threshold_arg)
        def f0() -> int:
            request_validator.callback0()
            return 42

        @throttle(requests=requests_arg,
                  seconds=seconds_arg,
                  mode=Throttle.MODE_SYNC_LB,
                  lb_threshold=lb_threshold_arg)
        def f1(idx: int) -> int:
            request_validator.callback1(idx)
            return idx + 42 + 1

        @throttle(requests=requests_arg,
                  seconds=seconds_arg,
                  mode=Throttle.MODE_SYNC_LB,
                  lb_threshold=lb_threshold_arg)
        def f2(idx: int, requests: int) -> int:
            request_validator.callback2(idx, requests)
            return idx + 42 + 2

        @throttle(requests=requests_arg,
                  seconds=seconds_arg,
                  mode=Throttle.MODE_SYNC_LB,
                  lb_threshold=lb_threshold_arg)
        def f3(*, idx: int) -> int:
            request_validator.callback3(idx=idx)
            return idx + 42 + 3

        @throttle(requests=requests_arg,
                  seconds=seconds_arg,
                  mode=Throttle.MODE_SYNC_LB,
                  lb_threshold=lb_threshold_arg)
        def f4(*, idx: int, seconds: float) -> int:
            request_validator.callback4(idx=idx, seconds=seconds)
            return idx + 42 + 4

        @throttle(requests=requests_arg,
                  seconds=seconds_arg,
                  mode=Throttle.MODE_SYNC_LB,
                  lb_threshold=lb_threshold_arg)
        def f5(idx: int, *, interval: float) -> int:
            request_validator.callback5(idx,
                                        interval=interval)
            return idx + 42 + 5

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

        #######################################################################
        # Invoke the functions
        #######################################################################
        for i in range(requests_arg * request_multiplier):
            rc = f0()
            assert rc == 0
            time.sleep(send_interval)
        request_validator.validate_series()  # validate for the series

        for i in range(requests_arg * request_multiplier):
            rc = f1(i)
            assert rc == i + 42 + 1
            time.sleep(send_interval)
        request_validator.validate_series()  # validate for the series

        for i in range(requests_arg * request_multiplier):
            rc = f2(i, requests_arg)
            assert rc == i + 42 + 2
            time.sleep(send_interval)
        request_validator.validate_series()  # validate for the series

        for i in range(requests_arg * request_multiplier):
            rc = f3(idx=i)
            assert rc == i + 42 + 3
            time.sleep(send_interval)
        request_validator.validate_series()  # validate for the series

        for i in range(requests_arg * request_multiplier):
            rc = f4(idx=i, seconds=seconds_arg)
            assert rc == i + 42 + 4
            time.sleep(send_interval)
        request_validator.validate_series()  # validate for the series

        for i in range(requests_arg * request_multiplier):
            rc = f5(idx=i, interval=send_interval_mult_arg)
            assert rc == i + 42 + 5
            time.sleep(send_interval)
        request_validator.validate_series()  # validate for the series

        for i in range(requests_arg * request_multiplier):
            rc = f6(i, requests_arg,
                    seconds=seconds_arg, interval=send_interval_mult_arg)
            assert rc == i + 42 + 6
            time.sleep(send_interval)
        request_validator.validate_series()  # validate for the series


###############################################################################
# TestThrottleShutdown
###############################################################################
class TestThrottleShutdown:
    """Class TestThrottle."""
    ###########################################################################
    # test_throttle_shutdown_error
    ###########################################################################
    def test_throttle_shutdown_errors(self) -> None:
        """Method to test attempted shutdown in sync mode."""
        #######################################################################
        # call start_shutdown for sync mode
        #######################################################################
        a_throttle1 = Throttle(requests=1,
                               seconds=1,
                               mode=Throttle.MODE_SYNC)

        a_var = [0]

        def f1(a: List[int]) -> None:
            a[0] += 1

        for i in range(4):
            a_throttle1.send_request(f1, a_var)

        with pytest.raises(AttemptedShutdownForSyncThrottle):
            a_throttle1.start_shutdown()

        with pytest.raises(IncorrectShutdownTypeSpecified):
            a_throttle1.start_shutdown(shutdown_type=1)

        assert a_var[0] == 4

        # the following requests should not get ignored
        for i in range(6):
            a_throttle1.send_request(f1, a_var)

        # the count should not have changed
        assert a_var[0] == 10

    ###########################################################################
    # test_throttle_shutdown_soft
    ###########################################################################
    def test_throttle_shutdown(self,
                               requests_arg: int,
                               seconds_arg: int,
                               shutdown1_type_arg: int,
                               shutdown2_type_arg: int,
                               timeout1_arg: int,
                               timeout2_arg: int,
                               sleep_delay_arg: float,
                               which_throttle_arg: int
                               ) -> None:
        """Method to test shutdown scenarios.

        Args:
            requests_arg: how many requests per seconds
            seconds_arg: how many seconds between number of requests
            shutdown1_type_arg: soft or hard shutdown for first shutdown
            shutdown2_type_arg: soft or hard shutdown for second shutdown
            timeout1_arg: True or False to use timeout on shutdown1
            timeout2_arg: True or False to use timeout on shutdown2
            sleep_delay_arg: how many requests as a ratio to total requests
                               to allow to get scheduled go before starting
                               shutdown
            which_throttle_arg: 1 for the pie decorator, 2 for the send_request
                                  style of throttle, 3 for pie call

        Raises:
            IncorrectWhichThrottle: which_throttle_arg must be 1 or 2

        """
        @throttle(requests=requests_arg,
                  seconds=seconds_arg,
                  mode=Throttle.MODE_ASYNC)
        def f1(b: List[Union[int, float]]) -> None:
            t = time.time()
            prev_t = b[1]
            f_interval = t - prev_t
            f_interval_str = (time.strftime('%S',
                                            time.localtime(f_interval))
                              + ('%.9f' % (f_interval % 1,))[1:6])
            b[1] = t
            time_str = (time.strftime('%H:%M:%S', time.localtime(t))
                        + ('%.9f' % (t % 1,))[1:6])
            b[0] += 1
            logger.debug(f'f1 bumped count to {b[0]} at {time_str}, '
                         f'interval={f_interval_str}')

        def f2(b: List[Union[int, float]]) -> None:
            t = time.time()
            prev_t = b[1]
            f_interval = t - prev_t
            f_interval_str = (time.strftime('%S',
                                            time.localtime(f_interval))
                              + ('%.9f' % (f_interval % 1,))[1:6])
            b[1] = t
            time_str = (time.strftime('%H:%M:%S', time.localtime(t))
                        + ('%.9f' % (t % 1,))[1:6])
            b[0] += 1
            logger.debug(f'f2 bumped count to {b[0]} at {time_str}, '
                         f'interval={f_interval_str}')

        num_reqs_to_make = 32
        b_throttle1 = Throttle(requests=requests_arg,
                               seconds=seconds_arg,
                               mode=Throttle.MODE_ASYNC)

        b_var = [0, time.time()]
        logger.debug(f'requests_arg = {requests_arg}')
        logger.debug(f'seconds_arg = {seconds_arg}')
        logger.debug(f'shutdown1_type_arg = {shutdown1_type_arg}')
        logger.debug(f'shutdown2_type_arg = {shutdown2_type_arg}')
        logger.debug(f'timeout1_arg = {timeout1_arg}')
        logger.debug(f'timeout2_arg = {timeout2_arg}')
        logger.debug(f'sleep_delay_arg = {sleep_delay_arg}')

        interval = seconds_arg/requests_arg
        logger.debug(f'interval = {interval}')

        #######################################################################
        # calculate sleep1 times
        #######################################################################
        sleep1_reqs_to_do = min(num_reqs_to_make,
                                math.floor(num_reqs_to_make
                                           * sleep_delay_arg))
        logger.debug(f'sleep1_reqs_to_do = {sleep1_reqs_to_do}')
        sleep1_sleep_seconds = (((sleep1_reqs_to_do - 1) * interval)
                                + (interval / 2))
        logger.debug(f'sleep1_sleep_seconds = {sleep1_sleep_seconds}')
        exp_sleep1_reqs_done = sleep1_reqs_to_do
        logger.debug(f'exp_sleep1_reqs_done = {exp_sleep1_reqs_done}')
        sleep1_elapsed_seconds = (((exp_sleep1_reqs_done - 1) * interval)
                                  + (interval / 2))
        logger.debug(f'sleep1_elapsed_seconds = {sleep1_elapsed_seconds}')

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

        #######################################################################
        # calculate shutdown1 times
        #######################################################################
        logger.debug(f'shutdown1_reqs_to_do = {shutdown1_reqs_to_do}')
        shutdown1_timeout_seconds = ((shutdown1_reqs_to_do * interval)
                                     + (interval / 2))
        logger.debug('shutdown1_timeout_seconds = '
                     f'{shutdown1_timeout_seconds}')

        logger.debug(f'exp_shutdown1_reqs_done = {exp_shutdown1_reqs_done}')
        shutdown1_elapsed_seconds = (((exp_shutdown1_reqs_done - 1) * interval)
                                     + (interval/2))
        logger.debug('shutdown1_elapsed_seconds = '
                     f'{shutdown1_elapsed_seconds}')

        #######################################################################
        # calculate sleep2 times
        #######################################################################
        logger.debug(f'sleep2_reqs_to_do = {sleep2_reqs_to_do}')
        sleep2_sleep_seconds = ((sleep2_reqs_to_do * interval)
                                + (interval / 2))
        logger.debug(f'sleep2_sleep_seconds = {sleep2_sleep_seconds}')

        logger.debug(f'exp_sleep2_reqs_done = {exp_sleep2_reqs_done}')
        sleep2_elapsed_seconds = (((exp_sleep2_reqs_done - 1) * interval)
                                  + (interval / 2))
        logger.debug(f'sleep2_elapsed_seconds = {sleep2_elapsed_seconds}')

        #######################################################################
        # calculate shutdown2 times
        #######################################################################
        logger.debug(f'shutdown2_reqs_to_do = {shutdown2_reqs_to_do}')
        shutdown2_timeout_seconds = ((shutdown2_reqs_to_do * interval)
                                     + (interval / 2))
        logger.debug('shutdown2_timeout_seconds = '
                     f'{shutdown2_timeout_seconds}')

        logger.debug(f'exp_shutdown2_reqs_done = {exp_shutdown2_reqs_done}')
        shutdown2_elapsed_seconds = (((exp_shutdown2_reqs_done - 1)
                                      * interval)
                                     + (interval / 2))
        logger.debug('shutdown2_elapsed_seconds = '
                     f'{shutdown2_elapsed_seconds}')

        #######################################################################
        # calculate end times
        #######################################################################
        logger.debug(f'total_reqs_to_do = {exp_total_reqs_done}')
        total_reqs_elapsed_seconds = (exp_total_reqs_done - 1) * interval
        logger.debug('total_reqs_elapsed_seconds = '
                     f'{total_reqs_elapsed_seconds}')

        logger.debug('start adding requests')
        start_time = time.time()
        #######################################################################
        # We need a try/finally to make sure we can shutdown the throttle
        # in the event that an assert fails. Before this, there were test
        # cases failing and leaving the throttle active with its requests
        # showing up in the next test case logs.
        #######################################################################
        try:
            if (which_throttle_arg == WT.PieThrottleDirectShutdown
                    or which_throttle_arg == WT.PieThrottleShutdownFuncs):
                for i in range(num_reqs_to_make):
                    assert Throttle.RC_OK == f1(b_var)
            elif which_throttle_arg == WT.NonPieThrottle:
                for i in range(num_reqs_to_make):
                    assert Throttle.RC_OK == b_throttle1.send_request(f2,
                                                                      b_var)
            else:
                raise IncorrectWhichThrottle('which_throttle must be 1 or 2')

            logger.debug('all requests added, elapsed time = '
                         f'{time.time() - start_time} seconds')

            ###################################################################
            # first sleep to allow shutdown to progress
            ###################################################################
            logger.debug(f'first sleep for {sleep1_sleep_seconds} seconds')
            sleep1_target_end_time = (start_time + sleep1_sleep_seconds)
            time.sleep(max(0, sleep1_target_end_time - time.time()))
            sleep1_reqs_time = b_var
            logger.debug(f'sleep1 complete, {sleep1_reqs_time[0]} reqs done, '
                         f'elapsed time = {time.time() - start_time} seconds')
            assert sleep1_reqs_time[0] == exp_sleep1_reqs_done

            ###################################################################
            # first shutdown
            ###################################################################
            if timeout1_arg:
                l_msg = (f' with timeout for {shutdown1_timeout_seconds} '
                         'seconds')
            else:
                l_msg = ''
            logger.debug(f'starting shutdown1 {l_msg}')

            if timeout1_arg:
                shutdown1_target_end_time = (sleep1_reqs_time[1]
                                             + shutdown1_timeout_seconds)
                if shutdown1_type_arg:
                    if which_throttle_arg == WT.PieThrottleDirectShutdown:
                        ret_code = f1.throttle.start_shutdown(
                            shutdown_type=shutdown1_type_arg,
                            timeout=max(shutdown1_nonzero_min_time,
                                        shutdown1_target_end_time - time.time()
                                        ))
                    elif which_throttle_arg == WT.PieThrottleShutdownFuncs:
                        ret_code = shutdown_throttle_funcs(
                            f1,
                            shutdown_type=shutdown1_type_arg,
                            timeout=max(shutdown1_nonzero_min_time,
                                        shutdown1_target_end_time - time.time()
                                        ))
                    else:
                        ret_code = b_throttle1.start_shutdown(
                            shutdown_type=shutdown1_type_arg,
                            timeout=max(shutdown1_nonzero_min_time,
                                        shutdown1_target_end_time - time.time()
                                        ))
                else:
                    if which_throttle_arg == WT.PieThrottleDirectShutdown:
                        ret_code = f1.throttle.start_shutdown(
                            timeout=max(shutdown1_nonzero_min_time,
                                        shutdown1_target_end_time - time.time()
                                        ))
                    elif which_throttle_arg == WT.PieThrottleShutdownFuncs:
                        ret_code = shutdown_throttle_funcs(
                            f1,
                            timeout=max(shutdown1_nonzero_min_time,
                                        shutdown1_target_end_time - time.time()
                                        ))
                    else:
                        ret_code = b_throttle1.start_shutdown(
                            timeout=max(shutdown1_nonzero_min_time,
                                        shutdown1_target_end_time - time.time()
                                        ))
            else:
                if shutdown1_type_arg:
                    if which_throttle_arg == WT.PieThrottleDirectShutdown:
                        ret_code = f1.throttle.start_shutdown(
                            shutdown_type=shutdown1_type_arg)
                    elif which_throttle_arg == WT.PieThrottleShutdownFuncs:
                        ret_code = shutdown_throttle_funcs(
                            f1,
                            shutdown_type=shutdown1_type_arg)
                    else:
                        ret_code = b_throttle1.start_shutdown(
                            shutdown_type=shutdown1_type_arg)

                else:
                    if which_throttle_arg == WT.PieThrottleDirectShutdown:
                        ret_code = f1.throttle.start_shutdown()
                    elif which_throttle_arg == WT.PieThrottleShutdownFuncs:
                        ret_code = shutdown_throttle_funcs(f1)
                    else:
                        ret_code = b_throttle1.start_shutdown()

            shutdown1_reqs_time = b_var
            logger.debug(f'shutdown1 complete with ret_code {ret_code}, '
                         f'{shutdown1_reqs_time[0]} reqs done, '
                         f'elapsed time = {time.time() - start_time} seconds')
            assert shutdown1_reqs_time[0] == exp_shutdown1_reqs_done
            assert ret_code is exp_shutdown1_ret_code

            ###################################################################
            # second sleep
            ###################################################################
            logger.debug(f'sleep2 for {sleep2_sleep_seconds} seconds')

            sleep2_target_end_time = (shutdown1_reqs_time[1]
                                      + sleep2_sleep_seconds)

            time.sleep(max(0, sleep2_target_end_time - time.time()))
            sleep2_reqs_time = b_var
            logger.debug(f'sleep2 complete, {sleep2_reqs_time[0]} reqs done, '
                         f'elapsed time = {time.time() - start_time} seconds')
            assert sleep2_reqs_time[0] == exp_sleep2_reqs_done

            ###################################################################
            # second shutdown will succeed with or without time out
            ###################################################################
            if timeout2_arg:
                l_msg = (f' with timeout for {shutdown2_timeout_seconds} '
                         'seconds')
            else:
                l_msg = ''
            logger.debug(f'starting shutdown2 {l_msg}')

            if timeout2_arg:
                shutdown2_target_end_time = (sleep2_reqs_time[1]
                                             + shutdown2_timeout_seconds)

                if which_throttle_arg == WT.PieThrottleDirectShutdown:
                    ret_code = f1.throttle.start_shutdown(
                        shutdown_type=shutdown2_type_arg,
                        timeout=max(shutdown2_nonzero_min_time,
                                    shutdown2_target_end_time - time.time()
                                    ))
                elif which_throttle_arg == WT.PieThrottleShutdownFuncs:
                    ret_code = shutdown_throttle_funcs(
                        f1,
                        shutdown_type=shutdown2_type_arg,
                        timeout=max(shutdown2_nonzero_min_time,
                                    shutdown2_target_end_time - time.time()
                                    ))
                else:
                    ret_code = b_throttle1.start_shutdown(
                        shutdown_type=shutdown2_type_arg,
                        timeout=max(shutdown2_nonzero_min_time,
                                    shutdown2_target_end_time - time.time()
                                    ))

            else:
                if which_throttle_arg == WT.PieThrottleDirectShutdown:
                    ret_code = f1.throttle.start_shutdown(
                        shutdown_type=shutdown2_type_arg)
                elif which_throttle_arg == WT.PieThrottleShutdownFuncs:
                    ret_code = shutdown_throttle_funcs(
                        f1,
                        shutdown_type=shutdown2_type_arg)
                else:
                    ret_code = b_throttle1.start_shutdown(
                        shutdown_type=shutdown2_type_arg)

            shutdown_complete_secs = time.time() - start_time
            shutdown2_reqs_time = b_var
            logger.debug(f'shutdown2 complete with ret_code {ret_code}, '
                         f'{shutdown2_reqs_time[0]} reqs done, '
                         f'elapsed time = {time.time() - start_time} seconds')
            assert shutdown2_reqs_time[0] == exp_total_reqs_done
            assert ret_code is True

            ###################################################################
            # verify shutdown completed within expected time
            ###################################################################
            exp_shutdown_complete_secs = interval * (exp_total_reqs_done - 1)

            logger.debug('exp_shutdown_complete_secs '
                         f'{exp_shutdown_complete_secs}')

            assert (exp_shutdown_complete_secs
                    <= shutdown_complete_secs
                    <= (exp_shutdown_complete_secs + 2.5))

            ###################################################################
            # verify new requests are rejected, q empty, and thread is done
            ###################################################################
            if (which_throttle_arg == WT.PieThrottleDirectShutdown
                    or which_throttle_arg == WT.PieThrottleShutdownFuncs):
                assert Throttle.RC_SHUTDOWN == f1(b_var)
                assert f1.throttle.async_q.empty()
                assert not f1.throttle.request_scheduler_thread.is_alive()
            else:
                assert (Throttle.RC_SHUTDOWN
                        == b_throttle1.send_request(f2, b_var))
                assert b_throttle1.async_q.empty()
                assert not b_throttle1.request_scheduler_thread.is_alive()

        finally:
            logger.debug('final shutdown to ensure throttle is closed')
            f1.throttle.start_shutdown()
            b_throttle1.start_shutdown()

        #######################################################################
        # the following requests should get rejected
        #######################################################################
        for i in range(num_reqs_to_make):
            assert Throttle.RC_SHUTDOWN == b_throttle1.send_request(f2, b_var)
        # assert Throttle.RC_SHUTDOWN == f1(f1_req_time)

    ###########################################################################
    # test_shutdown_throttle_funcs
    ###########################################################################
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
            sleep2_delay_arg: percentage of reqs to sleep before shutdown
            num_shutdown1_funcs_arg: number of funcs in first shutdown
            f1_num_reqs_arg: number of reqs to make
            f2_num_reqs_arg: number of reqs to make
            f3_num_reqs_arg: number of reqs to make
            f4_num_reqs_arg: number of reqs to make

        """
        #######################################################################
        # f1
        #######################################################################
        seconds_arg = .1
        f1_reqs = 1
        f2_reqs = 5
        f3_reqs = 2
        f4_reqs = 4

        @throttle(requests=f1_reqs,
                  seconds=seconds_arg,
                  mode=Throttle.MODE_ASYNC)
        def f1(req_time: ReqTime) -> None:
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
            logger.debug(f'f1 bumped count to {req_time.num_reqs} '
                         f'at {time_str}, interval={f_interval_str}')

        #######################################################################
        # f2
        #######################################################################
        @throttle(requests=f2_reqs,
                  seconds=seconds_arg,
                  mode=Throttle.MODE_ASYNC)
        def f2(req_time: ReqTime) -> None:
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
            logger.debug(f'f2 bumped count to {req_time.num_reqs} '
                         f'at {time_str}, interval={f_interval_str}')

        #######################################################################
        # f3
        #######################################################################
        @throttle(requests=f3_reqs,
                  seconds=seconds_arg,
                  mode=Throttle.MODE_ASYNC)
        def f3(req_time: ReqTime) -> None:
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
            logger.debug(f'f3 bumped count to {req_time.num_reqs} '
                         f'at {time_str}, interval={f_interval_str}')

        #######################################################################
        # f4
        #######################################################################
        @throttle(requests=f4_reqs,
                  seconds=seconds_arg,
                  mode=Throttle.MODE_ASYNC)
        def f4(req_time: ReqTime) -> None:
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
            logger.debug(f'f4 bumped count to {req_time.num_reqs} '
                         f'at {time_str}, interval={f_interval_str}')

        #######################################################################
        # f5
        #######################################################################
        # @throttle(requests=3,
        #           seconds=seconds_arg,
        #           mode=Throttle.MODE_ASYNC)
        # def f5(req_time: ReqTime) -> None:
        #     t = time.time()
        #     prev_t = req_time.f_time
        #     f_interval = t - prev_t
        #     f_interval_str = (time.strftime('%S',
        #                                     time.localtime(f_interval))
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
        f2_interval = seconds_arg/f2_reqs
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
            sleep_time = 0
        else:
            sleep_time = mean_reqs_to_make * sleep2_delay_arg * interval

        funcs_to_shutdown = list([f1, f2, f3, f4][0:num_shutdown1_funcs_arg])
        logger.debug(f'funcs_to_shutdown = {funcs_to_shutdown}')
        #######################################################################
        # start the requests
        #######################################################################
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

        #######################################################################
        # allow some requests to be made
        #######################################################################
        time.sleep(sleep_time)

        #######################################################################
        # start shutdowns
        #######################################################################
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

        #######################################################################
        # verify all funcs are shutdown
        #######################################################################
        #######################################################################
        # the following requests should get rejected
        #######################################################################
        assert Throttle.RC_SHUTDOWN == f1(f1_req_time)
        assert Throttle.RC_SHUTDOWN == f2(f2_req_time)
        assert Throttle.RC_SHUTDOWN == f3(f3_req_time)
        assert Throttle.RC_SHUTDOWN == f4(f4_req_time)
        # assert Throttle.RC_SHUTDOWN == f5(f5_req_time)

        assert f1.throttle.async_q.empty()
        assert f2.throttle.async_q.empty()
        assert f3.throttle.async_q.empty()
        assert f4.throttle.async_q.empty()
        # assert f5.throttle.async_q.empty()

        assert not f1.throttle.request_scheduler_thread.is_alive()
        assert not f2.throttle.request_scheduler_thread.is_alive()
        assert not f3.throttle.request_scheduler_thread.is_alive()
        assert not f4.throttle.request_scheduler_thread.is_alive()
        # assert not f5.throttle.request_scheduler_thread.is_alive()


###############################################################################
# RequestValidator class
###############################################################################
class RequestValidator:
    """Class to validate the requests."""
    def __init__(self,
                 requests: int,
                 seconds: float,
                 mode: int,
                 early_count: int,
                 lb_threshold: float,
                 request_mult: int,
                 send_interval: float) -> None:
        """Initialize the RequestValidator object.

        Args:
            requests: number of requests per second
            seconds: number of seconds for number of requests
            mode: specifies whether async, sync, sync_ec, or sync_lb
            early_count: the early count for the throttle
            lb_threshold: the leaky bucket threshold
            request_mult: specifies how many requests to make for the test
            send_interval: the interval between sends

        """
        self.requests = requests
        self.seconds = seconds
        self.mode = mode
        self.early_count = early_count
        self.lb_threshold = lb_threshold
        self.request_mult = request_mult
        self.send_interval = send_interval
        self.throttles: List[Throttle] = []
        self.next_send_times: List[float] = []
        self.idx = -1
        self.req_times: List[Tuple[int, float]] = []

        self.normalized_times: List[float] = []
        self.normalized_intervals: List[float] = []
        self.mean_interval = 0.0

        self.normalized_abts_times: List[float] = []
        self.normalized_abts_intervals: List[float] = []
        self.mean_abts_interval = 0.0

        self.normalized_ast_times: List[float] = []
        self.normalized_ast_intervals: List[float] = []
        self.mean_ast_interval = 0.0

        self.normalized_nst_times: List[float] = []
        self.normalized_nst_intervals: List[float] = []
        self.mean_nst_interval = 0.0

        # calculate parms

        self.total_requests = requests * request_mult
        print('total requests:', self.total_requests)
        self.target_interval = seconds / requests

        self.max_interval = max(self.target_interval,
                                self.send_interval)

        print('self.max_interval:', self.max_interval)
        self.min_interval = min(self.target_interval,
                                self.send_interval)

        self.exp_total_time = self.max_interval * self.total_requests
        print('self.exp_total_time:', self.exp_total_time)

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

    def reset(self) -> None:
        """Reset the variables to starting values."""
        self.idx = -1
        self.req_times = []
        self.normalized_times = []
        self.normalized_intervals = []
        self.mean_interval = 0.0

        self.normalized_abts_times = []
        self.normalized_abts_intervals = []
        self.mean_abts_interval = 0.0

        self.normalized_ast_times = []
        self.normalized_ast_intervals = []
        self.mean_ast_interval = 0.0

        self.next_send_times = []
        self.normalized_nst_times = []
        self.normalized_nst_intervals = []
        self.mean_nst_interval = 0.0

    def add_func_throttles(self, *args):
        """Add the throttles for decorated functions to the validator.

        Args:
            args: the function that have the throttles attached as attributes

        """
        self.throttles = []
        for func in args:
            self.throttles.append(func.throttle)

    def validate_series(self,
                        about_to_send_time: Optional[List[float]] = None,
                        after_send_time: Optional[List[float]] = None
                        ) -> None:
        """Validate the requests.

        Args:
            about_to_send_time: list if times before each request send
            after_send_time: list if times after each request send

        Raises:
            InvalidModeNum: Mode must be 1, 2, 3, or 4

        """
        assert len(self.req_times) == self.total_requests
        base_time = self.req_times[0][1]
        prev_time = base_time
        for idx, req_item in enumerate(self.req_times):
            assert idx == req_item[0]
            cur_time = req_item[1]
            self.normalized_times.append(cur_time - base_time)
            self.normalized_intervals.append(cur_time - prev_time)
            prev_time = cur_time

        self.mean_interval = (self.normalized_times[-1]
                              / (self.total_requests - 1))

        if about_to_send_time is not None:
            assert len(about_to_send_time) == self.total_requests
            base_time = about_to_send_time[0]
            prev_time = base_time
            for send_time in about_to_send_time:
                cur_time = send_time
                self.normalized_abts_times.append(cur_time - base_time)
                self.normalized_abts_intervals.append(cur_time - prev_time)
                prev_time = cur_time

        self.mean_abts_interval = (self.normalized_abts_times[-1]
                                   / (self.total_requests - 1))

        if after_send_time is not None:
            assert len(after_send_time) == self.total_requests
            base_time = after_send_time[0]
            prev_time = base_time
            for send_time in after_send_time:
                cur_time = send_time
                self.normalized_ast_times.append(cur_time - base_time)
                self.normalized_ast_intervals.append(cur_time - prev_time)
                prev_time = cur_time

        self.mean_ast_interval = (self.normalized_ast_times[-1]
                                  / (self.total_requests - 1))

        if self.next_send_times:
            assert len(self.next_send_times) == self.total_requests
            base_time = self.next_send_times[0]
            prev_time = base_time
            for send_time in self.next_send_times:
                cur_time = send_time
                self.normalized_nst_times.append(cur_time - base_time)
                self.normalized_nst_intervals.append(cur_time - prev_time)
                prev_time = cur_time

        self.mean_nst_interval = (self.normalized_nst_times[-1]
                                  / (self.total_requests - 1))

        if ((self.mode == Throttle.MODE_ASYNC) or
                (self.mode == Throttle.MODE_SYNC) or
                (self.target_interval <= self.send_interval)):
            self.validate_async_sync()
        elif self.mode == Throttle.MODE_SYNC_EC:
            self.validate_sync_ec()
        elif self.mode == Throttle.MODE_SYNC_LB:
            self.validate_sync_lb()
        else:
            raise InvalidModeNum('Mode must be 1, 2, 3, or 4')

        self.reset()

    def validate_async_sync(self) -> None:
        """Validate results for sync."""
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

        for interval in self.normalized_intervals[1:]:
            if interval < self.target_interval:
                num_early += 1
            if interval < self.target_interval - self.target_interval_1pct:
                num_early_1pct += 1
            if interval < self.target_interval - self.target_interval_5pct:
                num_early_5pct += 1
            if interval < self.target_interval - self.target_interval_10pct:
                num_early_10pct += 1
            if interval < self.target_interval - self.target_interval_15pct:
                num_early_15pct += 1

            if self.max_interval < interval:
                num_late += 1
            if self.max_interval + self.max_interval_1pct < interval:
                num_late_1pct += 1
            if self.max_interval + self.max_interval_5pct < interval:
                num_late_5pct += 1
            if self.max_interval + self.max_interval_10pct < interval:
                num_late_10pct += 1
            if self.max_interval + self.max_interval_15pct < interval:
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

        # assert num_early_10pct == 0
        # assert num_early_5pct == 0
        # assert num_early_1pct == 0

        if self.target_interval < self.send_interval:
            if num_early > 0:
                print('\nself.normalized_abts_intervals:\n',
                      self.normalized_abts_intervals)
                print('\nself.mean_abts_interval='
                      f'{self.mean_abts_interval}')

                print('\nself.normalized_nst_intervals:\n',
                      self.normalized_nst_intervals)
                print('\nself.mean_nst_interval'
                      f'={self.mean_nst_interval}')

                print('\nself.normalized_intervals:\n',
                      self.normalized_intervals)
                print('\nself.mean_interval'
                      f'={self.mean_interval}')

                print('\nself.normalized_ast_intervals:\n',
                      self.normalized_ast_intervals)
                print('\nself.mean_ast_interval'
                      f'={self.mean_ast_interval}')
            assert num_early == 0

        # assert num_late_15pct == 0
        # assert num_late_5pct == 0
        # assert num_late_1pct == 0
        # assert num_late == 0

        self.exp_total_time = self.max_interval * self.total_requests
        print('self.exp_total_time:', self.exp_total_time)
        extra_exp_total_time = self.mean_interval * self.total_requests
        print('extra_exp_total_time:', extra_exp_total_time)
        mean_late_pct = ((self.mean_interval - self.max_interval) /
                         self.max_interval) * 100
        print(f'mean_late_pct: {mean_late_pct:.2f}%')

        extra_time_pct = ((extra_exp_total_time - self.exp_total_time) /
                          self.exp_total_time) * 100

        print(f'extra_time_pct: {extra_time_pct:.2f}%')

        num_to_add = extra_exp_total_time - self.exp_total_time
        print(f'num_to_add: {num_to_add:.2f}')

        print('self.max_interval:', self.max_interval)
        print('self.mean_interval:', self.mean_interval)
        assert self.max_interval <= self.mean_interval

    def validate_sync_ec(self) -> None:
        """Validate results for sync early count."""
        num_short_early = 0
        num_short_early_1pct = 0
        num_short_early_5pct = 0
        num_short_early_10pct = 0

        num_short_late = 0
        num_short_late_1pct = 0
        num_short_late_5pct = 0
        num_short_late_10pct = 0

        num_long_early = 0
        num_long_early_1pct = 0
        num_long_early_5pct = 0
        num_long_early_10pct = 0

        num_long_late = 0
        num_long_late_1pct = 0
        num_long_late_5pct = 0
        num_long_late_10pct = 0

        long_interval = (((self.early_count + 1) * self.target_interval)
                         - (self.early_count * self.min_interval))

        for idx, interval in enumerate(self.normalized_intervals[1:], 1):
            if idx % (self.early_count + 1):  # if long interval expected
                if interval < long_interval:
                    num_long_early += 1
                if interval < long_interval - self.target_interval_1pct:
                    num_long_early_1pct += 1
                if interval < long_interval - self.target_interval_5pct:
                    num_long_early_5pct += 1
                if interval < (long_interval - self.target_interval_10pct):
                    num_long_early_10pct += 1

                if self.max_interval < interval:
                    num_long_late += 1
                if self.max_interval + self.max_interval_1pct < interval:
                    num_long_late_1pct += 1
                if self.max_interval + self.max_interval_5pct < interval:
                    num_long_late_5pct += 1
                if self.max_interval + self.max_interval_10pct < interval:
                    num_long_late_10pct += 1
            else:
                if interval < self.min_interval:
                    num_short_early += 1
                if interval < self.min_interval - self.min_interval_1pct:
                    num_short_early_1pct += 1
                if interval < self.min_interval - self.min_interval_5pct:
                    num_short_early_5pct += 1
                if interval < (self.min_interval - self.min_interval_10pct):
                    num_short_early_10pct += 1

                if self.min_interval < interval:
                    num_short_late += 1
                if self.min_interval + self.min_interval_1pct < interval:
                    num_short_late_1pct += 1
                if self.min_interval + self.min_interval_5pct < interval:
                    num_short_late_5pct += 1
                if self.min_interval + self.min_interval_10pct < interval:
                    num_short_late_10pct += 1

        print('num_requests_sent2:', self.total_requests)
        print('num_early2:', num_long_early)
        print('num_early_1pct2:', num_long_early_1pct)
        print('num_early_5pct2:', num_long_early_5pct)
        print('num_early_10pct2:', num_long_early_10pct)

        print('num_late2:', num_long_late)
        print('num_late_1pct2:', num_long_late_1pct)
        print('num_late_5pct2:', num_long_late_5pct)
        print('num_late_10pct2:', num_long_late_10pct)

        print('num_early2:', num_short_early)
        print('num_early_1pct2:', num_short_early_1pct)
        print('num_early_5pct2:', num_short_early_5pct)
        print('num_early_10pct2:', num_short_early_10pct)

        print('num_late2:', num_short_late)
        print('num_late_1pct2:', num_short_late_1pct)
        print('num_late_5pct2:', num_short_late_5pct)
        print('num_late_10pct2:', num_short_late_10pct)

        assert num_long_early_10pct == 0
        # assert num_long_early_5pct == 0
        # assert num_long_early_5pct == 0
        # assert num_long_early == 0

        assert num_long_late_10pct == 0
        # assert num_long_late_5pct == 0
        # assert num_long_late_1pct == 0
        # assert num_long_late == 0

        assert num_short_early_10pct == 0
        # assert num_short_early_5pct == 0
        # assert num_short_early_5pct == 0
        # assert num_short_early == 0

        assert num_short_late_10pct == 0
        # assert num_short_late_5pct == 0
        # assert num_short_late_1pct == 0
        # assert num_short_late == 0

        assert self.target_interval <= self.mean_interval

    def validate_sync_lb(self) -> None:
        """Validate the results for sync leaky bucket."""
        amt_added_per_send = self.target_interval - self.send_interval
        num_sends_before_trigger = (math.floor(self.lb_threshold /
                                               amt_added_per_send))
        amt_remaining_in_bucket = (self.lb_threshold
                                   - (num_sends_before_trigger
                                      * self.send_interval))
        amt_over = self.send_interval - amt_remaining_in_bucket

        trigger_interval = self.send_interval + amt_over
        trigger_interval_1pct = trigger_interval * 0.01
        trigger_interval_5pct = trigger_interval * 0.05
        trigger_interval_10pct = trigger_interval * 0.10

        num_short_early = 0
        num_short_early_1pct = 0
        num_short_early_5pct = 0
        num_short_early_10pct = 0

        num_short_late = 0
        num_short_late_1pct = 0
        num_short_late_5pct = 0
        num_short_late_10pct = 0

        num_trigger_early = 0
        num_trigger_early_1pct = 0
        num_trigger_early_5pct = 0
        num_trigger_early_10pct = 0

        num_trigger_late = 0
        num_trigger_late_1pct = 0
        num_trigger_late_5pct = 0
        num_trigger_late_10pct = 0

        num_early = 0
        num_early_1pct = 0
        num_early_5pct = 0
        num_early_10pct = 0

        num_late = 0
        num_late_1pct = 0
        num_late_5pct = 0
        num_late_10pct = 0

        # the following assert ensures our request_multiplier is sufficient
        # to get the bucket filled and then some
        assert (num_sends_before_trigger+8) < len(self.normalized_intervals)

        for idx, interval in enumerate(self.normalized_intervals[1:], 1):
            if idx <= num_sends_before_trigger:
                if interval < self.min_interval:
                    num_short_early += 1
                if interval < self.min_interval - self.min_interval_1pct:
                    num_short_early_1pct += 1
                if interval < self.min_interval - self.min_interval_5pct:
                    num_short_early_5pct += 1
                if interval < (self.min_interval - self.min_interval_10pct):
                    num_short_early_10pct += 1

                if self.min_interval < interval:
                    num_short_late += 1
                if self.min_interval + self.min_interval_1pct < interval:
                    num_short_late_1pct += 1
                if self.min_interval + self.min_interval_5pct < interval:
                    num_short_late_5pct += 1
                if self.min_interval + self.min_interval_10pct < interval:
                    num_short_late_10pct += 1
            elif idx == num_sends_before_trigger + 1:
                if interval < trigger_interval:
                    num_trigger_early += 1
                if interval < trigger_interval - trigger_interval_1pct:
                    num_trigger_early_1pct += 1
                if interval < trigger_interval - trigger_interval_5pct:
                    num_trigger_early_5pct += 1
                if interval < trigger_interval - trigger_interval_10pct:
                    num_trigger_early_10pct += 1

                if trigger_interval < interval:
                    num_trigger_late += 1
                if trigger_interval + trigger_interval_1pct < interval:
                    num_trigger_late_1pct += 1
                if trigger_interval + trigger_interval_5pct < interval:
                    num_trigger_late_5pct += 1
                if trigger_interval + trigger_interval_10pct < interval:
                    num_trigger_late_10pct += 1
            else:
                if interval < self.target_interval:
                    num_early += 1
                if interval < self.target_interval - self.target_interval_1pct:
                    num_early_1pct += 1
                if interval < self.target_interval - self.target_interval_5pct:
                    num_early_5pct += 1
                if interval < self.target_interval - \
                        self.target_interval_10pct:
                    num_early_10pct += 1

                if self.max_interval < interval:
                    num_late += 1
                if self.max_interval + self.max_interval_1pct < interval:
                    num_late_1pct += 1
                if self.max_interval + self.max_interval_5pct < interval:
                    num_late_5pct += 1
                if self.max_interval + self.max_interval_10pct < interval:
                    num_late_10pct += 1

        print('num_requests_sent3:', self.total_requests)

        print('num_short_early3:', num_short_early)
        print('num_short_early_1pct3:', num_short_early_1pct)
        print('num_short_early_5pct3:', num_short_early_5pct)
        print('num_short_early_10pct3:', num_short_early_10pct)

        print('num_short_late3:', num_short_late)
        print('num_short_late_1pct3:', num_short_late_1pct)
        print('num_short_late_5pct3:', num_short_late_5pct)
        print('num_short_late_10pct3:', num_short_late_10pct)

        print('num_trigger_early3:', num_trigger_early)
        print('num_trigger_early_1pct3:', num_trigger_early_1pct)
        print('num_trigger_early_5pct3:', num_trigger_early_5pct)
        print('num_trigger_early_10pct3:', num_trigger_early_10pct)

        print('num_trigger_late3:', num_trigger_late)
        print('num_trigger_late_1pct3:', num_trigger_late_1pct)
        print('num_trigger_late_5pct3:', num_trigger_late_5pct)
        print('num_trigger_late_10pct3:', num_trigger_late_10pct)

        print('num_early3:', num_early)
        print('num_early_1pct3:', num_early_1pct)
        print('num_early_5pct3:', num_early_5pct)
        print('num_early_10pct3:', num_early_10pct)

        print('num_late3:', num_late)
        print('num_late_1pct3:', num_late_1pct)
        print('num_late_5pct3:', num_late_5pct)
        print('num_late_10pct3:', num_late_10pct)

        assert num_short_early_10pct == 0
        assert num_short_late_10pct == 0

        assert num_trigger_early_10pct == 0
        assert num_trigger_late_10pct == 0

        assert num_early_10pct == 0
        assert num_late_10pct == 0

        exp_mean_interval = ((self.send_interval * num_sends_before_trigger)
                             + trigger_interval
                             + (self.target_interval
                                * (self.total_requests
                                   - (num_sends_before_trigger + 1)))
                             ) / (self.total_requests - 1)

        assert exp_mean_interval <= self.mean_interval

    def request0(self) -> int:
        """Request0 target.

        Returns:
            the index reflected back
        """
        self.idx += 1
        self.req_times.append((self.idx, time.time()))
        return self.idx

    def request1(self, idx: int) -> int:
        """Request1 target.

        Args:
            idx: the index of the call

        Returns:
            the index reflected back
        """
        self.req_times.append((idx, time.time()))
        assert idx == self.idx + 1
        self.idx = idx
        return idx

    def request2(self, idx: int, requests: int) -> int:
        """Request2 target.

        Args:
            idx: the index of the call
            requests: number of requests for the throttle

        Returns:
            the index reflected back
        """
        self.req_times.append((idx, time.time()))
        assert idx == self.idx + 1
        assert requests == self.requests
        self.idx = idx
        return idx

    def request3(self, *, idx: int) -> int:
        """Request3 target.

        Args:
            idx: the index of the call

        Returns:
            the index reflected back
        """
        self.req_times.append((idx, time.time()))
        assert idx == self.idx + 1
        self.idx = idx
        return idx

    def request4(self, *, idx: int, seconds: int) -> int:
        """Request4 target.

        Args:
            idx: the index of the call
            seconds: number of seconds for the throttle

        Returns:
            the index reflected back
        """
        self.req_times.append((idx, time.time()))
        assert idx == self.idx + 1
        assert seconds == self.seconds
        self.idx = idx
        return idx

    def request5(self, idx: int, *, interval: float) -> int:
        """Request5 target.

        Args:
            idx: the index of the call
            interval: the interval used between requests

        Returns:
            the index reflected back
        """
        self.req_times.append((idx, time.time()))
        assert idx == self.idx + 1
        assert interval == self.send_interval
        self.idx = idx
        return idx

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
        self.req_times.append((idx, time.time()))
        assert idx == self.idx + 1
        assert requests == self.requests
        assert seconds == self.seconds
        assert interval == self.send_interval
        self.idx = idx
        return idx

    ###########################################################################
    # Queue callback targets
    ###########################################################################
    def callback0(self) -> None:
        """Queue the callback for request0."""
        self.idx += 1
        self.req_times.append((self.idx, time.time()))
        self.next_send_times.append(self.throttles[0].next_send_time)

    def callback1(self, idx: int) -> None:
        """Queue the callback for request0.

        Args:
            idx: index of the request call
        """
        self.req_times.append((idx, time.time()))
        self.next_send_times.append(self.throttles[0].next_send_time)
        assert idx == self.idx + 1
        self.idx = idx

    def callback2(self, idx: int, requests: int) -> None:
        """Queue the callback for request0.

        Args:
            idx: index of the request call
            requests: number of requests for the throttle
        """
        self.req_times.append((idx, time.time()))
        self.next_send_times.append(self.throttles[0].next_send_time)
        assert idx == self.idx + 1
        assert requests == self.requests
        self.idx = idx

    def callback3(self, *, idx: int) -> None:
        """Queue the callback for request0.

        Args:
            idx: index of the request call
        """
        self.req_times.append((idx, time.time()))
        self.next_send_times.append(self.throttles[0].next_send_time)
        assert idx == self.idx + 1
        self.idx = idx

    def callback4(self, *, idx: int, seconds: float) -> None:
        """Queue the callback for request0.

        Args:
            idx: index of the request call
            seconds: number of seconds for the throttle
        """
        self.req_times.append((idx, time.time()))
        self.next_send_times.append(self.throttles[0].next_send_time)
        assert idx == self.idx + 1
        assert seconds == self.seconds
        self.idx = idx

    def callback5(self,
                  idx: int,
                  *,
                  interval: float) -> None:
        """Queue the callback for request0.

        Args:
            idx: index of the request call
            interval: interval between requests
        """
        self.req_times.append((idx, time.time()))
        self.next_send_times.append(self.throttles[0].next_send_time)
        assert idx == self.idx + 1
        assert interval == self.send_interval
        self.idx = idx

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
        self.req_times.append((idx, time.time()))
        self.next_send_times.append(self.throttles[0].next_send_time)
        assert idx == self.idx + 1
        assert requests == self.requests
        assert seconds == self.seconds
        assert interval == self.send_interval
        self.idx = idx


###############################################################################
# TestThrottleDocstrings class
###############################################################################
class TestThrottleDocstrings:
    """Class TestThrottleDocstrings."""
    def test_throttle_with_example_1(self) -> None:
        """Method test_throttle_with_example_1."""
        flowers('Example for README:')

        import time
        from scottbrian_utils.throttle import throttle

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

    # def test_throttle_with_example_2(self) -> None:
    #     """Method test_throttle_with_example_2."""
    #     print()
    #     print('#' * 50)
    #     print('Example for throttle decorator:')
    #     print()
    #
    #     @throttle(file=sys.stdout)
    #     def func2() -> None:
    #         print('2 * 3 =', 2*3)
    #
    #     func2()
    #
    # def test_throttle_with_example_3(self) -> None:
    #     """Method test_throttle_with_example_3."""
    #     print()
    #     print('#' * 50)
    #     print('Example of printing to stderr:')
    #     print()
    #
    #     @throttle(file=sys.stderr)
    #     def func3() -> None:
    #         print('this text printed to stdout, not stderr')
    #
    #     func3()
    #
    # def test_throttle_with_example_4(self) -> None:
    #     """Method test_throttle_with_example_4."""
    #     print()
    #     print('#' * 50)
    #     print('Example of statically wrapping function with throttle:')
    #     print()
    #
    #     _tbe = False
    #
    #     @throttle(throttle_enabled=_tbe, file=sys.stdout)
    #     def func4a() -> None:
    #         print('this is sample text for _tbe = False static example')
    #
    #     func4a()  # func4a is not wrapped by time box
    #
    #     _tbe = True
    #
    #     @throttle(throttle_enabled=_tbe, file=sys.stdout)
    #     def func4b() -> None:
    #         print('this is sample text for _tbe = True static example')
    #
    #     func4b()  # func4b is wrapped by time box
    #
    # def test_throttle_with_example_5(self) -> None:
    #     """Method test_throttle_with_example_5."""
    #     print()
    #     print('#' * 50)
    #     print('Example of dynamically wrapping function with throttle:')
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
    #     a_datetime_format: DT_Format = cast(DT_Format, '%m/%d/%y %H:%M:%S')
    #
    #     @throttle(dt_format=a_datetime_format)
    #     def func6() -> None:
    #         print('this is sample text for the datetime format example')
    #
    #     func6()
