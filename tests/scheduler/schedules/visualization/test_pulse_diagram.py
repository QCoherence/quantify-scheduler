# pylint: disable=missing-module-docstring
# pylint: disable=missing-class-docstring
# pylint: disable=missing-function-docstring

import numpy as np
import matplotlib.pyplot as plt
import pytest

from quantify_scheduler import Schedule
from quantify_scheduler.backends import SerialCompiler
from quantify_scheduler.compilation import determine_absolute_timing
from quantify_scheduler.operations.acquisition_library import SSBIntegrationComplex
from quantify_scheduler.operations.gate_library import CZ, Measure, Reset, Rxy
from quantify_scheduler.operations.pulse_library import SquarePulse, WindowOperation
from quantify_scheduler.resources import BasebandClockResource
from quantify_scheduler.schedules._visualization.pulse_diagram import (
    get_window_operations,
    plot_acquisition_operations,
    plot_window_operations,
    pulse_diagram_matplotlib,
    pulse_diagram_plotly,
    sample_schedule,
)


# Proper verification of this, probably requires some horrible selenium malarkey
def test_pulse_diagram_plotly(device_compile_config_basic_transmon) -> None:
    sched = Schedule("Test schedule")

    # Define the resources
    q0, q2 = ("q0", "q2")

    sched.add(Reset(q0, q2))
    sched.add(Rxy(90, 0, qubit=q0))
    sched.add(operation=CZ(qC=q0, qT=q2))
    sched.add(Rxy(theta=90, phi=0, qubit=q0))
    sched.add(Measure(q0, q2), label="M0")

    # Pulse information is added
    compiler = SerialCompiler(name="compiler")
    compiled_sched = compiler.compile(
        schedule=sched, config=device_compile_config_basic_transmon
    )

    # It should be possible to generate this visualization after compilation
    fig = pulse_diagram_plotly(compiled_sched)

    assert fig.data


def test_pulse_diagram_matplotlib() -> None:
    schedule = Schedule("test")
    schedule.add(SquarePulse(amp=0.2, duration=4e-6, port="SDP"))
    schedule.add(SquarePulse(amp=0.3, duration=6e-6, port="SDP"))
    schedule.add(
        WindowOperation(window_name="second pulse", duration=6e-6), ref_pt="start"
    )
    schedule.add(SquarePulse(amp=0.25, duration=6e-6, port="SDP"))
    determine_absolute_timing(schedule=schedule)

    plt.figure(1)
    plt.clf()
    pulse_diagram_matplotlib(schedule, sampling_rate=20e6)

    window_operations = get_window_operations(schedule)
    plot_window_operations(schedule)

    assert len(window_operations) == 1
    window = window_operations[0]
    assert window[0] == pytest.approx(4e-6)
    assert window[1] == pytest.approx(10e-6)
    assert isinstance(window[2], WindowOperation)

    plt.close(1)


def test_pulse_diagram_matplotlib_multiple_subplots() -> None:
    schedule = Schedule("test")
    schedule.add(SquarePulse(amp=0.2, duration=4e-9, port="SDP"))
    schedule.add(SquarePulse(amp=-0.2, duration=6e-9, port="T"), ref_pt="start")
    schedule.add(SquarePulse(amp=0.3, duration=6e-9, port="SDP"))
    determine_absolute_timing(schedule=schedule)

    plt.figure(1)
    plt.clf()
    _, axs = pulse_diagram_matplotlib(
        schedule, sampling_rate=0.5e9, x_range=(0, 1.21e-8), multiple_subplots=True
    )

    assert len(axs) == 2
    np.testing.assert_array_almost_equal(
        axs[0].get_lines()[0].get_xdata(), np.array([0.0, 2e-9, 4e-9])
    )
    np.testing.assert_array_almost_equal(
        axs[0].get_lines()[0].get_ydata(), np.array([0.2, 0.2, 0.2])
    )

    np.testing.assert_array_almost_equal(
        axs[0].get_lines()[1].get_xdata(), np.array([6e-9, 8e-9, 1e-8, 1.2e-8])
    )
    np.testing.assert_array_almost_equal(
        axs[0].get_lines()[1].get_ydata(), np.array([0.3, 0.3, 0.3, 0.3])
    )

    np.testing.assert_array_almost_equal(
        axs[1].get_lines()[0].get_xdata(), np.array([0.0, 2e-9, 4e-9, 6e-9])
    )
    np.testing.assert_array_almost_equal(
        axs[1].get_lines()[0].get_ydata(), np.array([-0.2, -0.2, -0.2, -0.2])
    )

    plt.close(1)


def test_plot_acquisition_operations() -> None:
    schedule = Schedule("test")
    schedule.add(SquarePulse(amp=0.2, duration=4e-6, port="SDP"))
    determine_absolute_timing(schedule=schedule)
    handles = plot_acquisition_operations(schedule)
    assert len(handles) == 0

    schedule.add(SSBIntegrationComplex("P", clock="cl0.baseband", duration=2e-6))
    determine_absolute_timing(schedule=schedule)
    handles = plot_acquisition_operations(schedule)
    assert len(handles) == 1


def test_sample_schedule() -> None:
    schedule = Schedule("test")
    schedule.add(SquarePulse(amp=0.2, duration=4e-9, port="SDP"))
    schedule.add(SquarePulse(amp=-0.2, duration=6e-9, port="T"), ref_pt="start")
    schedule.add(SquarePulse(amp=0.3, duration=6e-9, port="SDP"))
    determine_absolute_timing(schedule=schedule)

    waveforms = sample_schedule(schedule, sampling_rate=0.5e9, x_range=(0, 1.21e-8))

    np.testing.assert_array_almost_equal(
        waveforms["SDP"][0].time,
        np.array([0.0, 2e-9, 4e-9]),
    )
    np.testing.assert_array_almost_equal(
        waveforms["SDP"][0].signal,
        np.array([0.2, 0.2, 0.2]),
    )

    np.testing.assert_array_almost_equal(
        waveforms["T"][0].time,
        np.array(
            [0.0, 2e-9, 4e-9, 6e-9],
        ),
    )
    np.testing.assert_array_almost_equal(
        waveforms["T"][0].signal,
        np.array(
            [-0.2, -0.2, -0.2, -0.2],
        ),
    )

    np.testing.assert_array_almost_equal(
        waveforms["SDP"][1].time,
        np.array([6e-9, 8e-9, 1e-8, 1.2e-8]),
    )
    np.testing.assert_array_almost_equal(
        waveforms["SDP"][1].signal,
        np.array([0.3, 0.3, 0.3, 0.3]),
    )


def test_sample_modulated_waveform() -> None:
    schedule = Schedule("test")
    clock0 = BasebandClockResource("clock0")
    clock0["freq"] = 0.15e9
    schedule.add_resource(clock0)

    square_pulse_op = SquarePulse(amp=0.2, duration=3e-9, port="SDP", clock="clock0")
    schedule.add(square_pulse_op)
    square_pulse_op = SquarePulse(amp=0.2, duration=3e-9, port="T")
    schedule.add(square_pulse_op, ref_pt="start")
    determine_absolute_timing(schedule=schedule)

    waveforms = sample_schedule(
        schedule,
        sampling_rate=1e9,
        modulation="clock",
    )

    assert waveforms["SDP"][0].signal.dtype.kind == "c"
    np.testing.assert_array_almost_equal(
        waveforms["SDP"][0].signal,
        np.array(
            [
                0.2 + 0.0j,
                0.117557 + 0.161803j,
                -0.061803 + 0.190211j,
                -0.190211 + 0.061803j,
            ]
        ),
    )
    np.testing.assert_array_almost_equal(
        waveforms["T"][0].signal, np.array([0.2, 0.2, 0.2, 0.2])
    )


def test_sample_custom_port_list() -> None:
    schedule = Schedule("test")
    r = SquarePulse(amp=0.2, duration=4e-9, port="SDP")
    schedule.add(r)
    determine_absolute_timing(schedule=schedule)

    waveforms = sample_schedule(schedule, sampling_rate=0.5e9, port_list=["SDP"])
    assert list(waveforms.keys()) == ["SDP"]


def test_sample_empty_schedule() -> None:
    schedule = Schedule("test")

    with pytest.raises(RuntimeError):
        _ = pulse_diagram_matplotlib(schedule, sampling_rate=1e9)
