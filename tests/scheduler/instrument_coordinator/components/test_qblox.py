# pylint: disable=missing-class-docstring
# pylint: disable=missing-function-docstring
# pylint: disable=missing-module-docstring
# pylint: disable=redefined-outer-name
# pylint: disable=too-many-arguments
# pylint: disable=too-many-locals
# pylint: disable=unused-argument

# Repository: https://gitlab.com/quantify-os/quantify-scheduler
# Licensed according to the LICENCE file on the main branch
"""Tests for Qblox instrument coordinator components."""
import logging
from collections import defaultdict
from copy import deepcopy
from typing import List, Optional

import numpy as np
import pytest
import xarray as xr
from qblox_instruments import (
    Cluster,
    ClusterType,
    DummyBinnedAcquisitionData,
    Pulsar,
    PulsarType,
    SequencerState,
    SequencerStatus,
    SequencerStatusFlags,
)
from qcodes.instrument import Instrument, InstrumentChannel, InstrumentModule
from xarray import DataArray, Dataset

from quantify_scheduler.backends import SerialCompiler
from quantify_scheduler.device_under_test.transmon_element import BasicTransmonElement
from quantify_scheduler.enums import BinMode
from quantify_scheduler.instrument_coordinator.components import qblox
from quantify_scheduler.schedules.schedule import AcquisitionMetadata

from tests.fixtures.mock_setup import close_instruments


@pytest.fixture
def make_cluster_component(mocker):
    cluster_component: qblox.ClusterComponent = None

    def _make_cluster_component(
        name: str = "cluster0",
        sequencer_status: SequencerStatus = SequencerStatus.ARMED,
        sequencer_flags: Optional[List[SequencerStatusFlags]] = None,
    ) -> qblox.ClusterComponent:
        close_instruments([f"ic_{name}", name])
        cluster = Cluster(
            name=name,
            dummy_cfg={
                "1": ClusterType.CLUSTER_QCM,
                "2": ClusterType.CLUSTER_QCM_RF,
                "3": ClusterType.CLUSTER_QRM,
                "4": ClusterType.CLUSTER_QRM_RF,
                "10": ClusterType.CLUSTER_QCM,  # for flux pulsing q0_q3
                "12": ClusterType.CLUSTER_QCM,  # for flux pulsing q4
            },
        )

        nonlocal cluster_component
        cluster_component = qblox.ClusterComponent(cluster)

        mocker.patch.object(cluster, "reference_source", wraps=cluster.reference_source)

        for comp in cluster_component._cluster_modules.values():
            instrument = comp._instrument_module
            mocker.patch.object(
                instrument, "arm_sequencer", wraps=instrument.arm_sequencer
            )
            mocker.patch.object(
                instrument, "start_sequencer", wraps=instrument.start_sequencer
            )
            mocker.patch.object(
                instrument, "stop_sequencer", wraps=instrument.stop_sequencer
            )
            mocker.patch.object(
                instrument,
                "get_sequencer_state",
                return_value=SequencerState(
                    sequencer_status, sequencer_flags if sequencer_flags else []
                ),
            )
            mocker.patch.object(
                instrument,
                "store_scope_acquisition",
                wraps=instrument.store_scope_acquisition,
            )

        return cluster_component

    yield _make_cluster_component

    if cluster_component:
        for comp in cluster_component._cluster_modules.values():
            comp.close()
        cluster_component.close()


@pytest.fixture
def make_qcm_component(mocker):
    component: qblox.PulsarQCMComponent = None

    def _make_qcm_component(
        name: str = "qcm0",
        serial: str = "dummy",
        sequencer_status: SequencerStatus = SequencerStatus.ARMED,
        sequencer_flags: Optional[List[SequencerStatusFlags]] = None,
    ) -> qblox.PulsarQCMComponent:
        mocker.patch(
            "qblox_instruments.scpi.pulsar_qcm.PulsarQcm._set_reference_source"
        )
        close_instruments([f"ic_{name}", name])
        qcm = Pulsar(name=name, dummy_type=PulsarType.PULSAR_QCM)
        qcm._serial = serial

        mocker.patch.object(qcm, "arm_sequencer", wraps=qcm.arm_sequencer)
        mocker.patch.object(qcm, "start_sequencer", wraps=qcm.start_sequencer)
        mocker.patch.object(qcm, "stop_sequencer", wraps=qcm.stop_sequencer)

        nonlocal component
        component = qblox.PulsarQCMComponent(qcm)

        mocker.patch.object(component.instrument_ref, "get_instr", return_value=qcm)
        mocker.patch.object(
            component.instrument,
            "get_sequencer_state",
            return_value=SequencerState(
                sequencer_status, sequencer_flags if sequencer_flags else []
            ),
        )

        return component

    yield _make_qcm_component

    if component:
        component.close()


@pytest.fixture
def make_qrm_component(mocker):
    component: qblox.PulsarQRMComponent = None

    def _make_qrm_component(
        name: str = "qrm0",
        serial: str = "dummy",
        sequencer_status: SequencerStatus = SequencerStatus.ARMED,
        sequencer_flags: Optional[List[SequencerStatusFlags]] = None,
        patch_acquisitions: bool = False,
    ) -> qblox.PulsarQRMComponent:
        mocker.patch(
            "qblox_instruments.scpi.pulsar_qrm.PulsarQrm._set_reference_source"
        )
        close_instruments([f"ic_{name}", name])
        qrm = Pulsar(name=name, dummy_type=PulsarType.PULSAR_QRM)
        qrm._serial = serial

        mocker.patch.object(qrm, "arm_sequencer", wraps=qrm.arm_sequencer)
        mocker.patch.object(qrm, "start_sequencer", wraps=qrm.start_sequencer)
        mocker.patch.object(qrm, "stop_sequencer", wraps=qrm.stop_sequencer)
        mocker.patch.object(
            qrm, "store_scope_acquisition", wraps=qrm.store_scope_acquisition
        )

        mocker.patch.object(qrm, "arm_sequencer", wraps=qrm.arm_sequencer)
        mocker.patch.object(qrm, "start_sequencer", wraps=qrm.start_sequencer)
        mocker.patch.object(qrm, "stop_sequencer", wraps=qrm.stop_sequencer)

        nonlocal component
        component = qblox.PulsarQRMComponent(qrm)

        mocker.patch.object(component.instrument_ref, "get_instr", return_value=qrm)
        mocker.patch.object(
            component.instrument,
            "get_sequencer_state",
            return_value=SequencerState(
                sequencer_status, sequencer_flags if sequencer_flags else []
            ),
        )

        return component

    yield _make_qrm_component

    if component:
        component.close()


@pytest.fixture(name="mock_acquisition_data")
def fixture_mock_acquisition_data():
    acq_channel, acq_index_len = 0, 10  # mock 1 channel, N indices
    avg_count = 10
    data = {
        str(acq_channel): {
            "index": acq_channel,
            "acquisition": {
                "scope": {
                    "path0": {
                        "data": [0.0] * 2**14,
                        "out-of-range": False,
                        "avg_count": avg_count,
                    },
                    "path1": {
                        "data": [0.0] * 2**14,
                        "out-of-range": False,
                        "avg_count": avg_count,
                    },
                },
                "bins": {
                    "integration": {
                        "path0": [0.0] * acq_index_len,
                        "path1": [0.0] * acq_index_len,
                    },
                    "threshold": [0.12] * acq_index_len,
                    "avg_cnt": [avg_count] * acq_index_len,
                },
            },
        }
    }
    yield data


@pytest.fixture
def make_qcm_rf(mocker):
    component: qblox.QCMRFComponent = None

    def _make_qcm_rf(
        name: str = "qcm_rf0",
        serial: str = "dummy",
        sequencer_status: SequencerStatus = SequencerStatus.ARMED,
        sequencer_flags: Optional[List[SequencerStatusFlags]] = None,
    ) -> qblox.QCMRFComponent:
        close_instruments([name])
        qcm_rf = Pulsar(name=name, dummy_type=PulsarType._PULSAR_QCM_RF)
        qcm_rf._serial = serial

        mocker.patch.object(qcm_rf, "arm_sequencer", wraps=qcm_rf.arm_sequencer)
        mocker.patch.object(qcm_rf, "start_sequencer", wraps=qcm_rf.start_sequencer)
        mocker.patch.object(qcm_rf, "stop_sequencer", wraps=qcm_rf.stop_sequencer)

        nonlocal component
        component = qblox.QCMRFComponent(qcm_rf)

        mocker.patch.object(component.instrument_ref, "get_instr", return_value=qcm_rf)
        mocker.patch.object(
            component.instrument,
            "get_sequencer_state",
            return_value=SequencerState(
                sequencer_status, sequencer_flags if sequencer_flags else []
            ),
        )

        return component

    yield _make_qcm_rf

    if component:
        component.close()


@pytest.fixture
def make_qrm_rf(mocker):
    component: qblox.QRMRFComponent = None

    def _make_qrm_rf(
        name: str = "qrm_rf0",
        serial: str = "dummy",
        sequencer_status: SequencerStatus = SequencerStatus.ARMED,
        sequencer_flags: Optional[List[SequencerStatusFlags]] = None,
    ) -> qblox.QRMRFComponent:
        close_instruments([name])
        qrm_rf = Pulsar(name=name, dummy_type=PulsarType._PULSAR_QRM_RF)
        qrm_rf._serial = serial

        mocker.patch.object(qrm_rf, "arm_sequencer", wraps=qrm_rf.arm_sequencer)
        mocker.patch.object(qrm_rf, "start_sequencer", wraps=qrm_rf.start_sequencer)
        mocker.patch.object(qrm_rf, "stop_sequencer", wraps=qrm_rf.stop_sequencer)

        nonlocal component
        component = qblox.QRMRFComponent(qrm_rf)

        mocker.patch.object(component.instrument_ref, "get_instr", return_value=qrm_rf)
        mocker.patch.object(
            component.instrument,
            "get_sequencer_state",
            return_value=SequencerState(
                sequencer_status, sequencer_flags if sequencer_flags else []
            ),
        )

        return component

    yield _make_qrm_rf

    if component:
        component.close()


def test_sequencer_state_flag_info():
    assert len(SequencerStatusFlags) == len(
        qblox._SEQUENCER_STATE_FLAG_INFO
    ), "Verify all flags are represented"

    debug_status = [
        key
        for key, info in qblox._SEQUENCER_STATE_FLAG_INFO.items()
        if info.logging_level == logging.DEBUG
    ]
    assert len(debug_status) == 5, (
        "Verify no new flags were implicitly added "
        "(otherwise update `qblox._SequencerStateInfo.get_logging_level()`)"
    )


def test_initialize_pulsar_qcm_component(make_qcm_component):
    make_qcm_component("qblox_qcm0", "1234")


def test_initialize_pulsar_qrm_component(make_qrm_component):
    make_qrm_component("qblox_qrm0", "1234")


def test_initialize_pulsar_qcm_rf_component(make_qcm_rf):
    make_qcm_rf("qblox_qcm_rf0", "1234")


def test_initialize_pulsar_qrm_rf_component(make_qrm_rf):
    make_qrm_rf("qblox_qrm_rf0", "1234")


def test_initialize_cluster_component(make_cluster_component):
    make_cluster_component("cluster0")


def test_reset_qcodes_settings(
    schedule_with_measurement,
    hardware_cfg_pulsar,
    make_qcm_component,
    make_qrm_component,
    mock_setup_basic_transmon_with_standard_params,
):
    # Arrange
    qcm0: qblox.PulsarQCMComponent = make_qcm_component("qcm0", "1234")
    qrm2: qblox.PulsarQRMComponent = make_qrm_component("qrm2", "1234")

    hardware_cfg = deepcopy(hardware_cfg_pulsar)

    # Set some AWG offsets and gains directly (not through hardware settings).
    # These should be reset when `prepare` is called.
    for path in (0, 1):
        qcm0.instrument["sequencer0"].set(f"offset_awg_path{path}", 0.1234)
        qcm0.instrument["sequencer0"].set(f"gain_awg_path{path}", 0.4321)

    for seq in (0, 1):
        for path in (0, 1):
            qrm2.instrument[f"sequencer{seq}"].set(f"offset_awg_path{path}", 0.6789)
            qrm2.instrument[f"sequencer{seq}"].set(f"gain_awg_path{path}", 0.9876)

    # Act
    hardware_cfg["qcm0"]["complex_output_0"]["portclock_configs"][0][
        "init_offset_awg_path_0"
    ] = 0.25
    hardware_cfg["qcm0"]["complex_output_0"]["portclock_configs"][0][
        "init_offset_awg_path_1"
    ] = 0.33
    hardware_cfg["qrm2"]["real_output_0"]["portclock_configs"][0][
        "init_gain_awg_path_0"
    ] = 0.5
    hardware_cfg["qrm2"]["real_output_1"]["portclock_configs"][0][
        "init_gain_awg_path_1"
    ] = -0.5

    quantum_device = mock_setup_basic_transmon_with_standard_params["quantum_device"]
    quantum_device.hardware_config(hardware_cfg)
    config = quantum_device.generate_compilation_config()
    compiled_schedule = SerialCompiler(name="compiler").compile(
        schedule=schedule_with_measurement, config=config
    )
    prog = compiled_schedule["compiled_instructions"]

    qcm0.prepare(prog[qcm0.instrument.name])
    qrm2.prepare(prog[qrm2.instrument.name])

    # Assert
    qcm0_offset = defaultdict(lambda: 0.0)
    qcm0_gain = defaultdict(lambda: 1.0)
    qcm0_offset[0] = 0.25
    qcm0_offset[1] = 0.33
    for path in (0, 1):
        assert qcm0.instrument["sequencer0"].parameters[
            f"offset_awg_path{path}"
        ].get() == pytest.approx(qcm0_offset[path])
        assert qcm0.instrument["sequencer0"].parameters[
            f"gain_awg_path{path}"
        ].get() == pytest.approx(qcm0_gain[path])

    qrm2_offset = defaultdict(lambda: 0.0)
    qrm2_gain = defaultdict(lambda: 1.0)
    qrm2_gain["seq0_path0"] = 0.5
    qrm2_gain["seq1_path1"] = -0.5
    for seq in (0, 1):
        for path in (0, 1):
            assert qrm2.instrument[f"sequencer{seq}"].parameters[
                f"offset_awg_path{path}"
            ].get() == pytest.approx(qrm2_offset[f"seq{seq}_path{path}"])
            assert qrm2.instrument[f"sequencer{seq}"].parameters[
                f"gain_awg_path{path}"
            ].get() == pytest.approx(qrm2_gain[f"seq{seq}_path{path}"])


def test_marker_override_false(
    schedule_with_measurement_q2,
    hardware_cfg_pulsar_rf,
    make_qcm_rf,
    make_qrm_rf,
    mock_setup_basic_transmon_with_standard_params,
):
    # Arrange
    qcm_rf0: qblox.QCMRFComponent = make_qcm_rf("qcm_rf0", "1234")
    qrm_rf0: qblox.QRMRFComponent = make_qrm_rf("qrm_rf0", "1234")

    mock_setup = mock_setup_basic_transmon_with_standard_params
    mock_setup["q2"].clock_freqs.readout(7.5e9)
    mock_setup["q2"].clock_freqs.f01(6.03e9)

    # These should be reset when `prepare` is called.
    qcm_rf0.instrument["sequencer0"].set("marker_ovr_en", True)
    qrm_rf0.instrument["sequencer0"].set("marker_ovr_en", True)

    mock_setup["quantum_device"].hardware_config(hardware_cfg_pulsar_rf)
    compiled_schedule = SerialCompiler(name="compiler").compile(
        schedule=schedule_with_measurement_q2,
        config=mock_setup["quantum_device"].generate_compilation_config(),
    )
    prog = compiled_schedule["compiled_instructions"]

    qcm_rf0.prepare(prog[qcm_rf0.instrument.name])
    qrm_rf0.prepare(prog[qrm_rf0.instrument.name])

    # Assert
    assert qcm_rf0.instrument["sequencer0"].parameters["marker_ovr_en"].get() is False
    assert qrm_rf0.instrument["sequencer0"].parameters["marker_ovr_en"].get() is False


def test_init_qcodes_settings(
    mocker,
    schedule_with_measurement,
    hardware_cfg_pulsar,
    make_qcm_component,
    make_qrm_component,
    mock_setup_basic_transmon_with_standard_params,
):
    # Arrange
    qcm0: qblox.PulsarQCMComponent = make_qcm_component("qcm0", "1234")
    qrm2: qblox.PulsarQRMComponent = make_qrm_component("qrm2", "1234")

    for dev in (qcm0, qrm2):
        for seq in range(qcm0._hardware_properties.number_of_sequencers):
            mocker.patch.object(
                dev.instrument[f"sequencer{seq}"].parameters["offset_awg_path0"], "set"
            )
            mocker.patch.object(
                dev.instrument[f"sequencer{seq}"].parameters["offset_awg_path1"], "set"
            )
            mocker.patch.object(
                dev.instrument[f"sequencer{seq}"].parameters["gain_awg_path0"], "set"
            )
            mocker.patch.object(
                dev.instrument[f"sequencer{seq}"].parameters["gain_awg_path1"], "set"
            )
            mocker.patch.object(
                dev.instrument[f"sequencer{seq}"].parameters["sync_en"], "set"
            )

    hardware_cfg = deepcopy(hardware_cfg_pulsar)

    # Act
    hardware_cfg["qcm0"]["complex_output_0"]["portclock_configs"][0][
        "init_offset_awg_path_0"
    ] = 0.25
    hardware_cfg["qcm0"]["complex_output_0"]["portclock_configs"][0][
        "init_offset_awg_path_1"
    ] = 0.33
    hardware_cfg["qrm2"]["real_output_0"]["portclock_configs"][0][
        "init_gain_awg_path_0"
    ] = 0.5
    hardware_cfg["qrm2"]["real_output_1"]["portclock_configs"][0][
        "init_gain_awg_path_1"
    ] = -0.5

    quantum_device = mock_setup_basic_transmon_with_standard_params["quantum_device"]
    quantum_device.hardware_config(hardware_cfg)
    config = quantum_device.generate_compilation_config()
    compiled_schedule = SerialCompiler(name="compiler").compile(
        schedule=schedule_with_measurement, config=config
    )
    prog = compiled_schedule["compiled_instructions"]

    qcm0.prepare(prog[qcm0.instrument.name])
    qrm2.prepare(prog[qrm2.instrument.name])

    # Assert
    qcm0_offset = defaultdict(lambda: 0.0)
    qcm0_gain = defaultdict(lambda: 1.0)
    qcm0_offset[0] = 0.25
    qcm0_offset[1] = 0.33
    for path in (0, 1):
        qcm0.instrument["sequencer0"].parameters[
            f"offset_awg_path{path}"
        ].set.assert_called_once_with(qcm0_offset[path])
        qcm0.instrument["sequencer0"].parameters[
            f"gain_awg_path{path}"
        ].set.assert_called_once_with(qcm0_gain[path])

    qcm0.instrument["sequencer0"].parameters[f"sync_en"].set.assert_called_with(True)
    qrm2.instrument["sequencer0"].parameters[f"sync_en"].set.assert_called_with(True)

    qrm2_offset = defaultdict(lambda: 0.0)
    qrm2_gain = defaultdict(lambda: 1.0)
    qrm2_gain["seq0_path0"] = 0.5
    qrm2_gain["seq1_path1"] = -0.5
    for seq in (0, 1):
        for path in (0, 1):
            qrm2.instrument[f"sequencer{seq}"].parameters[
                f"offset_awg_path{path}"
            ].set.assert_called_once_with(qrm2_offset[f"seq{seq}_path{path}"])
            qrm2.instrument[f"sequencer{seq}"].parameters[
                f"gain_awg_path{path}"
            ].set.assert_called_once_with(qrm2_gain[f"seq{seq}_path{path}"])


def test_invalid_init_qcodes_settings(
    mocker,
    schedule_with_measurement,
    hardware_cfg_pulsar,
    make_qcm_component,
    mock_setup_basic_transmon_with_standard_params,
):
    # Arrange
    qcm0: qblox.PulsarQCMComponent = make_qcm_component("qcm0", "1234")

    for seq in range(qcm0._hardware_properties.number_of_sequencers):
        mocker.patch.object(
            qcm0.instrument[f"sequencer{seq}"].parameters["offset_awg_path0"], "set"
        )
        mocker.patch.object(
            qcm0.instrument[f"sequencer{seq}"].parameters["offset_awg_path1"], "set"
        )

    hardware_cfg = deepcopy(hardware_cfg_pulsar)

    # Act
    hardware_cfg["qcm0"]["complex_output_0"]["portclock_configs"][0][
        "init_offset_awg_path_0"
    ] = 1.25

    quantum_device = mock_setup_basic_transmon_with_standard_params["quantum_device"]
    quantum_device.hardware_config(hardware_cfg)
    config = quantum_device.generate_compilation_config()
    with pytest.raises(ValueError):
        _ = SerialCompiler(name="compiler").compile(
            schedule=schedule_with_measurement, config=config
        )


@pytest.mark.parametrize(
    "set_reference_source, force_set_parameters",
    [(False, False), (False, True), (True, False), (True, True)],
)
def test_prepare_qcm_qrm(
    mocker,
    schedule_with_measurement,
    mock_setup_basic_transmon_with_standard_params,
    hardware_cfg_pulsar,
    make_qcm_component,
    make_qrm_component,
    set_reference_source,
    force_set_parameters,
):
    # Arrange
    qcm0: qblox.PulsarQCMComponent = make_qcm_component("qcm0", "1234")
    qrm0: qblox.PulsarQRMComponent = make_qrm_component("qrm0", "1234")
    qrm2: qblox.PulsarQRMComponent = make_qrm_component("qrm2", "1234")

    mocker.patch.object(qcm0.instrument.parameters["out0_offset"], "set")
    mocker.patch.object(qcm0.instrument.parameters["out1_offset"], "set")
    mocker.patch.object(qcm0.instrument.parameters["out2_offset"], "set")
    mocker.patch.object(qcm0.instrument.parameters["out3_offset"], "set")

    mocker.patch.object(qrm0.instrument.parameters["out0_offset"], "set")
    mocker.patch.object(qrm0.instrument.parameters["out1_offset"], "set")
    mocker.patch.object(qrm0.instrument.parameters["in0_gain"], "set")
    mocker.patch.object(qrm0.instrument.parameters["in1_gain"], "set")

    mocker.patch.object(qrm2.instrument.parameters["in0_gain"], "set")
    mocker.patch.object(qrm2.instrument.parameters["in1_gain"], "set")

    hardware_cfg = hardware_cfg_pulsar
    if set_reference_source:
        qcm0.instrument.reference_source(hardware_cfg[qcm0.instrument.name]["ref"])
        qcm0.instrument._set_reference_source.reset_mock()

        qrm0.instrument.reference_source(hardware_cfg[qrm0.instrument.name]["ref"])
        qrm0.instrument._set_reference_source.reset_mock()

        qrm2.instrument.reference_source(hardware_cfg[qrm2.instrument.name]["ref"])
        qrm2.instrument._set_reference_source.reset_mock()

    qcm0.force_set_parameters(force_set_parameters)
    qrm0.force_set_parameters(force_set_parameters)
    qrm2.force_set_parameters(force_set_parameters)

    quantum_device = mock_setup_basic_transmon_with_standard_params["quantum_device"]
    quantum_device.hardware_config(hardware_cfg)
    quantum_device.get_element("q0").clock_freqs.readout(7.5e9)

    compiler = SerialCompiler(name="compiler")
    compiled_schedule = compiler.compile(
        schedule_with_measurement, config=quantum_device.generate_compilation_config()
    )
    prog = compiled_schedule["compiled_instructions"]

    qcm0.prepare(prog[qcm0.instrument.name])
    qrm0.prepare(prog[qrm0.instrument.name])
    qrm2.prepare(prog[qrm2.instrument.name])

    # Assert
    qcm0.instrument.arm_sequencer.assert_called_with(sequencer=0)
    qrm0.instrument.arm_sequencer.assert_called_with(sequencer=0)
    qrm2.instrument.arm_sequencer.assert_called_with(sequencer=1)

    if set_reference_source:
        if force_set_parameters:
            qcm0.instrument._set_reference_source.assert_called()
            qrm0.instrument._set_reference_source.assert_called()
            qrm2.instrument._set_reference_source.assert_called()
        else:
            qcm0.instrument._set_reference_source.assert_not_called()
            qrm0.instrument._set_reference_source.assert_not_called()
            qrm2.instrument._set_reference_source.assert_not_called()

    for qcodes_param, hw_config_param in [
        ("out0_offset", ["complex_output_0", "dc_mixer_offset_I"]),
        ("out1_offset", ["complex_output_0", "dc_mixer_offset_Q"]),
        ("out2_offset", ["complex_output_1", "dc_mixer_offset_I"]),
        ("out3_offset", ["complex_output_1", "dc_mixer_offset_Q"]),
    ]:
        qcm0.instrument.parameters[qcodes_param].set.assert_any_call(
            hardware_cfg[qcm0.instrument.name][hw_config_param[0]][hw_config_param[1]]
        )

    for qcodes_param, hw_config_param in [
        ("out0_offset", ["complex_output_0", "dc_mixer_offset_I"]),
        ("out1_offset", ["complex_output_0", "dc_mixer_offset_Q"]),
        ("in0_gain", ["complex_output_0", "input_gain_I"]),
        ("in1_gain", ["complex_output_0", "input_gain_Q"]),
    ]:
        qrm0.instrument.parameters[qcodes_param].set.assert_any_call(
            hardware_cfg[qrm0.instrument.name][hw_config_param[0]][hw_config_param[1]]
        )

    for qcodes_param, hw_config_param in [
        ("in0_gain", ["real_output_0", "input_gain_0"]),
        ("in1_gain", ["real_output_1", "input_gain_1"]),
    ]:
        qrm2.instrument.parameters[qcodes_param].set.assert_any_call(
            hardware_cfg[qrm2.instrument.name][hw_config_param[0]][hw_config_param[1]]
        )


@pytest.mark.parametrize("force_set_parameters", [False, True])
def test_prepare_cluster_rf(
    mocker,
    mock_setup_basic_transmon,
    make_schedule_with_measurement,
    hardware_compilation_config_qblox_example,
    make_cluster_component,
    force_set_parameters,
):
    # Arrange
    cluster_name = "cluster0"
    ic_cluster: qblox.ClusterComponent = make_cluster_component(cluster_name)

    qcm_rf = ic_cluster.instrument.module2
    mocker.patch.object(qcm_rf.parameters["out0_att"], "set")
    mocker.patch.object(qcm_rf.parameters["out1_att"], "set")
    mocker.patch.object(qcm_rf[f"sequencer0"].parameters["sync_en"], "set")

    qrm_rf = ic_cluster.instrument.module4
    mocker.patch.object(qrm_rf.parameters["out0_att"], "set")
    mocker.patch.object(qrm_rf.parameters["in0_att"], "set")
    mocker.patch.object(qrm_rf[f"sequencer0"].parameters["sync_en"], "set")

    ic_cluster.force_set_parameters(force_set_parameters)
    ic_cluster.instrument.reference_source("internal")  # Put it in a known state

    quantum_device = mock_setup_basic_transmon["quantum_device"]
    q5 = BasicTransmonElement("q5")
    quantum_device.add_element(q5)

    q5.rxy.amp180(0.213)
    q5.clock_freqs.f01(6.33e9)
    q5.clock_freqs.f12(6.09e9)
    q5.clock_freqs.readout(8.5e9)
    q5.measure.acq_delay(100e-9)

    sched = make_schedule_with_measurement("q5")

    quantum_device = mock_setup_basic_transmon["quantum_device"]
    quantum_device.hardware_config(hardware_compilation_config_qblox_example)

    compiler = SerialCompiler(name="compiler")
    compiled_schedule = compiler.compile(
        sched,
        config=quantum_device.generate_compilation_config(),
    )
    compiled_schedule_before_prepare = deepcopy(compiled_schedule)

    prog = compiled_schedule["compiled_instructions"]
    ic_cluster.prepare(prog[cluster_name])

    # Assert
    assert compiled_schedule == compiled_schedule_before_prepare

    qcm_rf.arm_sequencer.assert_called_with(sequencer=0)
    qrm_rf.arm_sequencer.assert_called_with(sequencer=0)

    # Assert it's only set in initialization
    ic_cluster.instrument.reference_source.assert_called_once()

    for qcodes_param, hw_options_param in [
        ("out0_att", ["output_att", "q5:mw-q5.01"]),
        ("out1_att", ["output_att", "q6:mw-q6.01"]),
    ]:
        qcm_rf.parameters[qcodes_param].set.assert_any_call(
            hardware_compilation_config_qblox_example["hardware_options"][
                hw_options_param[0]
            ][hw_options_param[1]]
        )
    qcm_rf["sequencer0"].parameters[f"sync_en"].set.assert_called_with(True)

    for qcodes_param, hw_options_param in [
        ("out0_att", ["output_att", "q0:res-q0.ro"]),
        ("in0_att", ["input_att", "q5:res-q5.ro"]),
    ]:
        qrm_rf.parameters[qcodes_param].set.assert_any_call(
            hardware_compilation_config_qblox_example["hardware_options"][
                hw_options_param[0]
            ][hw_options_param[1]]
        )
    qrm_rf["sequencer0"].parameters[f"sync_en"].set.assert_called_with(True)


def test_prepare_rf(
    mock_setup_basic_transmon_with_standard_params,
    schedule_with_measurement_q2,
    hardware_cfg_pulsar_rf,
    make_qcm_rf,
    make_qrm_rf,
):
    # Arrange
    qcm: qblox.QCMRFComponent = make_qcm_rf("qcm_rf0", "1234")
    qrm: qblox.QRMRFComponent = make_qrm_rf("qrm_rf0", "1234")

    mock_setup = mock_setup_basic_transmon_with_standard_params
    mock_setup["q2"].clock_freqs.readout(7.5e9)
    mock_setup["q2"].clock_freqs.f01(6.03e9)

    quantum_device = mock_setup["quantum_device"]
    quantum_device.hardware_config(hardware_cfg_pulsar_rf)

    compiler = SerialCompiler(name="compiler")
    compiled_schedule = compiler.compile(
        schedule_with_measurement_q2,
        config=quantum_device.generate_compilation_config(),
    )

    # Act
    prog = compiled_schedule["compiled_instructions"]
    qcm.prepare(prog["qcm_rf0"])
    qrm.prepare(prog["qrm_rf0"])

    # Assert
    qcm.instrument.arm_sequencer.assert_called_with(sequencer=0)
    qrm.instrument.arm_sequencer.assert_called_with(sequencer=0)


def test_prepare_exception_qcm(make_qcm_component):
    # Arrange
    qcm: qblox.PulsarQCMComponent = make_qcm_component("qcm0", "1234")

    invalid_config = {"sequencers": {"idontexist": "this is not used"}}

    # Act
    with pytest.raises(KeyError) as execinfo:
        qcm.prepare(invalid_config)

    # Assert
    assert execinfo.value.args[0] == (
        "Invalid program. Attempting to access non-existing sequencer with"
        ' name "idontexist".'
    )


def test_prepare_exception_qrm(make_qrm_component):
    # Arrange
    qrm: qblox.PulsarQRMComponent = make_qrm_component("qcm0", "1234")

    invalid_config = {"sequencers": {"idontexist": "this is not used"}}

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
    qcm: qblox.QCMRFComponent = make_qcm_rf("qcm_rf0", "1234")

    invalid_config = {"sequencers": {"idontexist": "this is not used"}}

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
    qrm: qblox.QRMRFComponent = make_qrm_rf("qcm_rf0", "1234")

    invalid_config = {"sequencers": {"idontexist": "this is not used"}}

    # Act
    with pytest.raises(KeyError) as execinfo:
        qrm.prepare(invalid_config)

    # Assert
    assert execinfo.value.args[0] == (
        "Invalid program. Attempting to access non-existing sequencer with"
        ' name "idontexist".'
    )


@pytest.mark.parametrize(
    "sequencer_status",
    [SequencerStatus.ARMED, SequencerStatus.RUNNING, SequencerStatus.STOPPED],
)
def test_is_running(make_qrm_component, sequencer_status):
    qrm: qblox.PulsarQRMComponent = make_qrm_component("qrm0", "1234", sequencer_status)
    assert qrm.is_running is (sequencer_status is SequencerStatus.RUNNING)


@pytest.mark.parametrize(
    "sequencer_status",
    [SequencerStatus.ARMED, SequencerStatus.RUNNING, SequencerStatus.STOPPED],
)
def test_is_running_cluster(make_cluster_component, sequencer_status):
    cluster: qblox.ClusterComponent = make_cluster_component(
        "cluster0", sequencer_status
    )
    assert cluster.is_running is (sequencer_status is SequencerStatus.RUNNING)


@pytest.mark.parametrize(
    "sequencer_flags",
    [[], [SequencerStatusFlags.ACQ_SCOPE_OVERWRITTEN_PATH_0]],
)
def test_wait_done(make_qrm_component, sequencer_flags):
    qrm: qblox.PulsarQRMComponent = make_qrm_component(
        "qrm0", "1234", SequencerStatus.ARMED, sequencer_flags
    )
    qrm.wait_done()


def test_wait_done_cluster(make_cluster_component):
    cluster: qblox.ClusterComponent = make_cluster_component("cluster0")
    cluster.wait_done()


def test_retrieve_acquisition_qcm(make_qcm_component):
    qcm: qblox.PulsarQCMComponent = make_qcm_component("qcm0", "1234")

    assert qcm.retrieve_acquisition() is None


def test_retrieve_acquisition_qrm(
    schedule_with_measurement,
    hardware_cfg_pulsar,
    make_qrm_component,
    mock_setup_basic_transmon_with_standard_params,
):
    # Arrange
    qrm: qblox.PulsarQRMComponent = make_qrm_component("qrm0", "1234")

    # Act
    quantum_device = mock_setup_basic_transmon_with_standard_params["quantum_device"]
    quantum_device.hardware_config(hardware_cfg_pulsar)
    quantum_device.get_element("q0").clock_freqs.readout(7.5e9)

    compiler = SerialCompiler(name="compiler")
    compiled_schedule = compiler.compile(
        schedule_with_measurement, config=quantum_device.generate_compilation_config()
    )
    prog = compiled_schedule["compiled_instructions"]
    prog = dict(prog)

    dummy_data = [
        DummyBinnedAcquisitionData(data=(100.0, 200.0), thres=0, avg_cnt=0),
    ]
    qrm.instrument.set_dummy_binned_acquisition_data(
        sequencer=0, acq_index_name="0", data=dummy_data
    )

    qrm.prepare(prog[qrm.instrument.name])
    qrm.start()
    acq = qrm.retrieve_acquisition()

    # Assert
    expected_dataset = Dataset(
        {0: (["acq_index_0"], [0.1 + 0.2j])},
        coords={"acq_index_0": [0]},
    )
    xr.testing.assert_equal(acq, expected_dataset)


def test_retrieve_acquisition_qcm_rf(make_qcm_rf):
    qcm_rf: qblox.QCMRFComponent = make_qcm_rf("qcm_rf0", "1234")

    assert qcm_rf.retrieve_acquisition() is None


def test_retrieve_acquisition_qrm_rf(
    mock_setup_basic_transmon_with_standard_params,
    schedule_with_measurement_q2,
    make_qrm_rf,
    hardware_cfg_pulsar_rf,
):
    # Arrange
    qrm_rf: qblox.QRMRFComponent = make_qrm_rf("qrm_rf0", "1234")

    mock_setup = mock_setup_basic_transmon_with_standard_params
    mock_setup["quantum_device"].hardware_config(hardware_cfg_pulsar_rf)
    mock_setup["q2"].clock_freqs.readout(7.3e9)

    compiler = SerialCompiler(name="compiler")
    compiled_schedule = compiler.compile(
        schedule=schedule_with_measurement_q2,
        config=mock_setup["quantum_device"].generate_compilation_config(),
    )
    prog = compiled_schedule["compiled_instructions"]
    prog = dict(prog)

    dummy_data = [
        DummyBinnedAcquisitionData(data=(100.0, 200.0), thres=0, avg_cnt=0),
    ]
    qrm_rf.instrument.set_dummy_binned_acquisition_data(
        sequencer=0, acq_index_name="0", data=dummy_data
    )

    qrm_rf.prepare(prog[qrm_rf.instrument.name])
    qrm_rf.start()
    acq = qrm_rf.retrieve_acquisition()

    expected_dataset = Dataset(
        {0: (["acq_index_0"], [0.1 + 0.2j])}, coords={"acq_index_0": [0]}
    )
    xr.testing.assert_equal(acq, expected_dataset)


def test_retrieve_acquisition_cluster(
    make_schedule_with_measurement,
    mock_setup_basic_transmon_with_standard_params,
    make_cluster_component,
    hardware_compilation_config_qblox_example,
):
    # Arrange
    mock_setup = mock_setup_basic_transmon_with_standard_params
    mock_setup["quantum_device"].hardware_config(
        hardware_compilation_config_qblox_example
    )

    q4 = mock_setup["q4"]
    q4.clock_freqs.f01.set(5040000000)
    q4.rxy.amp180(0.2)
    q4.clock_freqs.f12(5.41e9)
    q4.clock_freqs.readout(6950000000)
    q4.measure.acq_delay(1.2e-07)

    cluster_name = "cluster0"
    cluster: qblox.ClusterComponent = make_cluster_component(cluster_name)

    compiler = SerialCompiler(name="compiler")
    compiled_schedule = compiler.compile(
        schedule=make_schedule_with_measurement("q4"),
        config=mock_setup["quantum_device"].generate_compilation_config(),
    )

    # Act
    cluster.prepare(compiled_schedule["compiled_instructions"][cluster_name])
    cluster.start()
    acq = cluster.retrieve_acquisition()

    # Assert
    assert acq is not None


def test_start_qcm_qrm(
    schedule_with_measurement,
    hardware_cfg_pulsar,
    mock_setup_basic_transmon_with_standard_params,
    make_qcm_component,
    make_qrm_component,
):
    # Arrange
    qcm: qblox.PulsarQCMComponent = make_qcm_component("qcm0", "1234")
    qrm: qblox.PulsarQRMComponent = make_qrm_component("qrm0", "1234")

    quantum_device = mock_setup_basic_transmon_with_standard_params["quantum_device"]
    quantum_device.hardware_config(hardware_cfg_pulsar)
    quantum_device.get_element("q0").clock_freqs.readout(7.5e9)

    compiler = SerialCompiler(name="compiler")
    compiled_schedule = compiler.compile(
        schedule_with_measurement, config=quantum_device.generate_compilation_config()
    )
    prog = compiled_schedule["compiled_instructions"]

    qcm.prepare(prog["qcm0"])
    qrm.prepare(prog["qrm0"])

    qcm.start()
    qrm.start()

    # Assert
    qcm.instrument.start_sequencer.assert_called()
    qrm.instrument.start_sequencer.assert_called()


def test_start_qcm_qrm_rf(
    mock_setup_basic_transmon_with_standard_params,
    schedule_with_measurement_q2,
    hardware_cfg_pulsar_rf,
    make_qcm_rf,
    make_qrm_rf,
):
    # Arrange
    qcm_rf: qblox.QCMRFComponent = make_qcm_rf("qcm_rf0", "1234")
    qrm_rf: qblox.QRMRFComponent = make_qrm_rf("qrm_rf0", "1234")

    mock_setup = mock_setup_basic_transmon_with_standard_params
    mock_setup["quantum_device"].hardware_config(hardware_cfg_pulsar_rf)
    mock_setup["q2"].clock_freqs.readout(7.3e9)
    mock_setup["q2"].clock_freqs.f01(6.03e9)
    compilation_config = mock_setup["quantum_device"].generate_compilation_config()

    compiler = SerialCompiler(name="compiler")
    compiled_schedule = compiler.compile(
        schedule=schedule_with_measurement_q2, config=compilation_config
    )
    prog = compiled_schedule["compiled_instructions"]

    qcm_rf.prepare(prog["qcm_rf0"])
    qrm_rf.prepare(prog["qrm_rf0"])

    qcm_rf.start()
    qrm_rf.start()

    # Assert
    qcm_rf.instrument.start_sequencer.assert_called()
    qrm_rf.instrument.start_sequencer.assert_called()


def test_stop_qcm_qrm(make_qcm_component, make_qrm_component):
    # Arrange
    qcm: qblox.PulsarQCMComponent = make_qcm_component("qcm0", "1234")
    qrm: qblox.PulsarQRMComponent = make_qrm_component("qrm0", "1234")

    # Act
    qcm.stop()
    qrm.stop()

    # Assert
    qcm.instrument.stop_sequencer.assert_called()
    qrm.instrument.stop_sequencer.assert_called()


def test_stop_qcm_qrm_rf(make_qcm_rf, make_qrm_rf):
    # Arrange
    qcm_rf: qblox.QCMRFComponent = make_qcm_rf("qcm_rf0", "1234")
    qrm_rf: qblox.QRMRFComponent = make_qrm_rf("qrm_rf0", "1234")

    # Act
    qcm_rf.stop()
    qrm_rf.stop()

    # Assert
    qcm_rf.instrument.stop_sequencer.assert_called()
    qrm_rf.instrument.stop_sequencer.assert_called()


def test_stop_cluster(make_cluster_component):
    # Arrange
    cluster: qblox.ClusterComponent = make_cluster_component("cluster0")

    # Act
    cluster.stop()

    # Assert
    for comp in cluster._cluster_modules.values():
        comp.instrument.stop_sequencer.assert_called()


# ------------------- _QRMAcquisitionManager -------------------
def test_qrm_acquisition_manager__init__(make_qrm_component):
    qrm: qblox.PulsarQRMComponent = make_qrm_component("qrm0", "1234")
    qblox._QRMAcquisitionManager(
        parent=qrm,
        acquisition_metadata=dict(),
        scope_mode_sequencer_and_channel=None,
        acquisition_duration={},
        seq_name_to_idx_map={},
    )


def test_get_integration_data(make_qrm_component, mock_acquisition_data):
    qrm: qblox.PulsarQRMComponent = make_qrm_component("qrm0", "1234")
    acq_manager = qblox._QRMAcquisitionManager(
        parent=qrm,
        acquisition_metadata=dict(),
        scope_mode_sequencer_and_channel=None,
        acquisition_duration={0: 10},
        seq_name_to_idx_map={"seq0": 0},
    )
    acq_metadata = AcquisitionMetadata(
        "SSBIntegrationComplex", BinMode.AVERAGE, complex, {0: [0]}, 1
    )
    formatted_acquisitions = acq_manager._get_integration_data(
        acq_indices=list(range(10)),
        acquisitions=mock_acquisition_data,
        acquisition_metadata=acq_metadata,
        acq_duration=10,
        acq_channel=0,
    )

    np.testing.assert_almost_equal(formatted_acquisitions.values, [0.0] * 10)


def test_instrument_module():
    """InstrumentModule is treated like InstrumentChannel and added as
    self._instrument_module
    """
    # Arrange
    instrument = Instrument("test_instr")
    instrument_module = InstrumentModule(instrument, "test_instr_module")
    instrument_module.is_qcm_type = True
    instrument_module.is_rf_type = False

    # Act
    component = qblox.QCMComponent(instrument_module)

    # Assert
    assert component._instrument_module is instrument_module


def test_instrument_channel():
    """InstrumentChannel is added as self._instrument_module"""
    # Arrange
    instrument = Instrument("test_instr")
    instrument_channel = InstrumentChannel(instrument, "test_instr_channel")
    instrument_channel.is_qcm_type = True
    instrument_channel.is_rf_type = False

    # Act
    component = qblox.QCMComponent(instrument_channel)

    # Assert
    assert component._instrument_module is instrument_channel
