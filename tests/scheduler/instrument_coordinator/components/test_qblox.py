# Repository: https://gitlab.com/quantify-os/quantify-scheduler
# Licensed according to the LICENCE file on the master branch
# pylint: disable=missing-module-docstring
# pylint: disable=missing-class-docstring
# pylint: disable=missing-function-docstring
# pylint: disable=redefined-outer-name
from __future__ import annotations

import inspect
import json
import tempfile
from pathlib import Path

import numpy as np
import pytest
from pulsar_qcm import pulsar_qcm
from pulsar_qrm import pulsar_qrm
from quantify_core.data.handling import set_datadir  # pylint: disable=no-name-in-module
import quantify_scheduler.schemas.examples as es
from quantify_scheduler.compilation import qcompile
from quantify_scheduler.instrument_coordinator.components import qblox
from quantify_scheduler.helpers import waveforms

esp = inspect.getfile(es)

cfg_f = Path(esp).parent / "transmon_test_config.json"
with open(cfg_f, "r") as f:
    DEVICE_CFG = json.load(f)

map_f = Path(esp).parent / "qblox_test_mapping.json"
with open(map_f, "r") as f:
    HARDWARE_MAPPING = json.load(f)


@pytest.fixture
def make_qcm(mocker):
    def _make_qcm(
        name: str = "qcm0", serial: str = "dummy"
    ) -> qblox.PulsarQCMComponent:
        mocker.patch("qcodes.instrument.Instrument.record_instance")
        qcm: pulsar_qcm.pulsar_qcm_qcodes = mocker.create_autospec(
            pulsar_qcm.pulsar_qcm_qcodes, instance=True
        )
        qcm.name = name
        qcm._serial = serial

        component = qblox.PulsarQCMComponent(qcm)
        mocker.patch.object(component.instrument_ref, "get_instr", return_value=qcm)
        mocker.patch.object(
            component.instrument,
            "get_sequencer_state",
            return_value={"status": "ARMED"},
        )

        return component

    yield _make_qcm


@pytest.fixture
def make_qrm(mocker):
    def _make_qrm(
        name: str = "qrm0", serial: str = "dummy"
    ) -> qblox.PulsarQRMComponent:
        mocker.patch("qcodes.instrument.Instrument.record_instance")
        qrm: pulsar_qrm.pulsar_qrm_qcodes = mocker.create_autospec(
            pulsar_qrm.pulsar_qrm_qcodes, instance=True
        )
        qrm.name = name
        qrm._serial = serial

        component = qblox.PulsarQRMComponent(qrm)
        mocker.patch.object(component.instrument_ref, "get_instr", return_value=qrm)
        mocker.patch.object(
            component.instrument,
            "get_sequencer_state",
            return_value={"status": "ARMED"},
        )

        return component

    yield _make_qrm

@pytest.fixture
def make_qcm_rf(mocker):
    def _make_qcm_rf(
        name: str = "qcm_rf0", serial: str = "dummy"
    ) -> qblox.PulsarQCMRFComponent:
        mocker.patch("qcodes.instrument.Instrument.record_instance")

        class pulsar_qcm_rf(pulsar_qcm.pulsar_qcm_qcodes):
            def _get_lo_hw_present(self):
                return True

        qcm_rf: pulsar_qcm_rf = mocker.create_autospec(
            pulsar_qcm_rf, instance=True
        )
        qcm_rf.name = name
        qcm_rf._serial = serial

        component = qblox.PulsarQCMRFComponent(qcm_rf)
        mocker.patch.object(component.instrument_ref, "get_instr", return_value=qcm_rf)
        mocker.patch.object(
            component.instrument,
            "get_sequencer_state",
            return_value={"status": "ARMED"},
        )

        return component

    yield _make_qcm_rf

@pytest.fixture
def make_qrm_rf(mocker):
    def _make_qrm_rf(
        name: str = "qrm_rf0", serial: str = "dummy"
    ) -> qblox.PulsarQRMRFComponent:
        mocker.patch("qcodes.instrument.Instrument.record_instance")

        class pulsar_qrm_rf(pulsar_qrm.pulsar_qrm_qcodes):
            def _get_lo_hw_present(self):
                return True

        qrm_rf: pulsar_qrm_rf = mocker.create_autospec(
            pulsar_qrm_rf, instance=True
        )
        qrm_rf.name = name
        qrm_rf._serial = serial

        component = qblox.PulsarQRMRFComponent(qrm_rf)
        mocker.patch.object(component.instrument_ref, "get_instr", return_value=qrm_rf)
        mocker.patch.object(
            component.instrument,
            "get_sequencer_state",
            return_value={"status": "ARMED"},
        )

        return component

    yield _make_qrm_rf

def test_initialize_pulsar_qcm_component(make_qcm):
    make_qcm("qblox_qcm0", "1234")


def test_initialize_pulsar_qrm_component(make_qrm):
    make_qrm("qblox_qrm0", "1234")

def test_initialize_pulsar_qcm_rf_component(make_qcm_rf):
    make_qcm_rf("qblox_qcm_rf0", "1234")


def test_initialize_pulsar_qrm_rf_component(make_qrm_rf):
    make_qrm_rf("qblox_qrm_rf0", "1234")


def test_prepare(schedule_with_measurement, make_qcm, make_qrm):
    # Arrange
    qcm: qblox.PulsarQCMComponent = make_qcm("qcm0", "1234")
    qrm: qblox.PulsarQRMComponent = make_qrm("qrm0", "1234")

    # Act
    with tempfile.TemporaryDirectory() as tmp_dir:
        set_datadir(tmp_dir)

        prog = qcompile(schedule_with_measurement, DEVICE_CFG, HARDWARE_MAPPING)

        qcm.prepare(prog["qcm0"])
        qrm.prepare(prog["qrm0"])

    # Assert
    qcm.instrument.arm_sequencer.assert_called_with(sequencer=0)
    qrm.instrument.arm_sequencer.assert_called_with(sequencer=0)

def test_prepare_rf(schedule_with_measurement, make_qcm_rf, make_qrm_rf):
    # Arrange
    qcm: qblox.PulsarQCMRFComponent = make_qcm_rf("qcm_rf0", "1234")
    qrm: qblox.PulsarQRMRFComponent = make_qrm_rf("qrm_rf0", "1234")

    # Act
    with tempfile.TemporaryDirectory() as tmp_dir:
        set_datadir(tmp_dir)

        prog = qcompile(schedule_with_measurement, DEVICE_CFG, HARDWARE_MAPPING)

        qcm.prepare(prog["qcm_rf0"])
        qrm.prepare(prog["qrm_rf0"])

    # Assert
    qcm.instrument.arm_sequencer.assert_called_with(sequencer=0)
    qrm.instrument.arm_sequencer.assert_called_with(sequencer=0)


def test_prepare_exception_qcm(make_qcm):
    # Arrange
    qcm: qblox.PulsarQCMComponent = make_qcm("qcm0", "1234")

    invalid_config = {"idontexist": "this is not used"}

    # Act
    with pytest.raises(KeyError) as execinfo:
        qcm.prepare(invalid_config)

    # Assert
    assert execinfo.value.args[0] == (
        "Invalid program. Attempting to access non-existing sequencer with"
        ' name "idontexist".'
    )


def test_prepare_exception_qrm(make_qrm):
    # Arrange
    qrm: qblox.PulsarQRMComponent = make_qrm("qcm0", "1234")

    invalid_config = {"idontexist": "this is not used"}

    # Act
    with pytest.raises(KeyError) as execinfo:
        qrm.prepare(invalid_config)

    # Assert
    assert execinfo.value.args[0] == (
        "Invalid program. Attempting to access non-existing sequencer with"
        ' name "idontexist".'
    )

def test_prepare_exception_qcm_rf(make_qcm_rf):
    # Arrange
    qcm: qblox.PulsarQCMComponent = make_qcm_rf("qcm_rf0", "1234")

    invalid_config = {"idontexist": "this is not used"}

    # Act
    with pytest.raises(KeyError) as execinfo:
        qcm.prepare(invalid_config)

    # Assert
    assert execinfo.value.args[0] == (
        "Invalid program. Attempting to access non-existing sequencer with"
        ' name "idontexist".'
    )


def test_prepare_exception_qrm_rf(make_qrm_rf):
    # Arrange
    qrm: qblox.PulsarQRMComponent = make_qrm_rf("qcm_rf0", "1234")

    invalid_config = {"idontexist": "this is not used"}

    # Act
    with pytest.raises(KeyError) as execinfo:
        qrm.prepare(invalid_config)

    # Assert
    assert execinfo.value.args[0] == (
        "Invalid program. Attempting to access non-existing sequencer with"
        ' name "idontexist".'
    )


def test_retrieve_acquisition_qcm(make_qcm):
    # Arrange
    qcm: qblox.PulsarQCMComponent = make_qcm("qcm0", "1234")

    # Act
    acq = qcm.retrieve_acquisition()

    # Assert
    assert acq is None


def test_retrieve_acquisition_qrm(schedule_with_measurement, make_qrm):
    # Arrange
    qrm: qblox.PulsarQRMComponent = make_qrm("qcm0", "1234")

    # Act
    with tempfile.TemporaryDirectory() as tmp_dir:
        set_datadir(tmp_dir)
        prog = qcompile(schedule_with_measurement, DEVICE_CFG, HARDWARE_MAPPING)
        prog = dict(prog)

        qrm.prepare(prog[qrm.instrument.name])
        qrm.start()
        acq = qrm.retrieve_acquisition()

    # Assert
    assert len(acq) == 2

def test_retrieve_acquisition_qcm_rf(make_qcm_rf):
    # Arrange
    qcm_rf: qblox.PulsarQCMRFComponent = make_qcm_rf("qcm_rf0", "1234")

    # Act
    acq = qcm_rf.retrieve_acquisition()

    # Assert
    assert acq is None


def test_retrieve_acquisition_qrm_rf(schedule_with_measurement, make_qrm_rf):
    # Arrange
    qrm_rf: qblox.PulsarQRMComponent = make_qrm_rf("qcm_rf0", "1234")

    # Act
    with tempfile.TemporaryDirectory() as tmp_dir:
        set_datadir(tmp_dir)
        prog = qcompile(schedule_with_measurement, DEVICE_CFG, HARDWARE_MAPPING)
        prog = dict(prog)

        qrm_rf.prepare(prog[qrm_rf.instrument.name])
        qrm_rf.start()
        acq = qrm_rf.retrieve_acquisition()

    # Assert
    assert len(acq) == 2

def test_start_qcm_qrm(schedule_with_measurement, make_qcm, make_qrm):
    # Arrange
    qcm: qblox.PulsarQCMComponent = make_qcm("qcm0", "1234")
    qrm: qblox.PulsarQRMComponent = make_qrm("qrm0", "1234")

    # Act
    with tempfile.TemporaryDirectory() as tmp_dir:
        set_datadir(tmp_dir)

        prog = qcompile(schedule_with_measurement, DEVICE_CFG, HARDWARE_MAPPING)

        qcm.prepare(prog["qcm0"])
        qrm.prepare(prog["qrm0"])

        qcm.start()
        qrm.start()

    # Assert
    qcm.instrument.start_sequencer.assert_called()
    qrm.instrument.start_sequencer.assert_called()

def test_start_qcm_qrm_rf(schedule_with_measurement, make_qcm_rf, make_qrm_rf):
    # Arrange
    qcm_rf: qblox.PulsarQCMRFComponent = make_qcm_rf("qcm_rf0", "1234")
    qrm_rf: qblox.PulsarQRMRFComponent = make_qrm_rf("qrm_rf0", "1234")

    # Act
    with tempfile.TemporaryDirectory() as tmp_dir:
        set_datadir(tmp_dir)

        prog = qcompile(schedule_with_measurement, DEVICE_CFG, HARDWARE_MAPPING)

        qcm_rf.prepare(prog["qcm0"])
        qrm_rf.prepare(prog["qrm0"])

        qcm_rf.start()
        qrm_rf.start()

    # Assert
    qcm_rf.instrument.start_sequencer.assert_called()
    qrm_rf.instrument.start_sequencer.assert_called()


def test_stop_qcm_qrm(make_qcm, make_qrm):
    # Arrange
    qcm: qblox.PulsarQCMComponent = make_qcm("qcm0", "1234")
    qrm: qblox.PulsarQRMComponent = make_qrm("qrm0", "1234")

    # Act
    qcm.stop()
    qrm.stop()

    # Assert
    qcm.instrument.stop_sequencer.assert_called()
    qrm.instrument.stop_sequencer.assert_called()

def test_stop_qcm_qrm_rf(make_qcm, make_qrm):
    # Arrange
    qcm_rf: qblox.PulsarQCMRFComponent = make_qcm("qcm_rf0", "1234")
    qrm_rf: qblox.PulsarQRMRFComponent = make_qrm("qrm_rf0", "1234")

    # Act
    qcm_rf.stop()
    qrm_rf.stop()

    # Assert
    qcm_rf.instrument.stop_sequencer.assert_called()
    qrm_rf.instrument.stop_sequencer.assert_called()


def test_demodulate_trace():
    # Arrange
    data = np.ones(1_000_000)
    freq = 10e6
    sampling_rate = 1e9

    t = np.arange(0, len(data) / sampling_rate, 1 / sampling_rate)
    mod_data = waveforms.modulate_waveform(t, data, freq)

    # Act
    demod_data = qblox._demodulate_trace(
        freq, mod_data.real, mod_data.imag, sampling_rate
    )

    # Assert
    np.testing.assert_allclose(data, demod_data)
