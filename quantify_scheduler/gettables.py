# Repository: https://gitlab.com/quantify-os/quantify-scheduler
# Licensed according to the LICENCE file on the main branch
r"""
Module containing :class:`quantify_core.measurement.types.Gettable`\s for use with
quantify-scheduler.

.. warning::

    The gettable module is expected to change significantly as the
    acquisition protocols (#36 and #80) get fully supported by the scheduler.
    Currently different Gettables are required for different acquisition modes.
    The intent is to have one generic ``ScheduleGettable``.
    Expect breaking changes.
"""
# pylint: disable-all
from __future__ import annotations

import json
import logging
import os
import time
import warnings
import zipfile
from typing import TYPE_CHECKING, Any, Callable

import numpy as np
from qcodes.parameters import Parameter
from qcodes.utils.json_utils import NumpyJSONEncoder

from quantify_core.data.handling import gen_tuid, get_datadir, snapshot
from quantify_scheduler.enums import BinMode
from quantify_scheduler.helpers.schedule import (
    AcquisitionMetadata,
    extract_acquisition_metadata_from_schedule,
)

if TYPE_CHECKING:
    from numpy.typing import NDArray
    from xarray import Dataset

    from quantify_scheduler import CompiledSchedule, Schedule
    from quantify_scheduler.device_under_test.quantum_device import QuantumDevice

logger = logging.getLogger(__name__)


class AcquisitionProtocolError(TypeError):
    pass


class AcquisitionProtocolNotSupportedError(NotImplementedError):
    pass


class ScheduleGettable:
    """
    Generic gettable for a quantify schedule using vector (I,Q) acquisition. Can be
    set to return either static (demodulated) I and Q values or magnitude and phase.

    The gettable evaluates the parameters passed as `schedule_kwargs`, then generates
    the :class:`quantify_scheduler.schedules.schedule.Schedule` using the
    `schedule_function`, this is then compiled and finally executed by the
    :class:`~.InstrumentCoordinator`.
    """

    def __init__(
        self,
        quantum_device: QuantumDevice,
        schedule_function: Callable[..., Schedule],
        schedule_kwargs: dict[str, Any],
        num_channels: int = 1,
        data_labels: list[str] | None = None,
        real_imag: bool = True,
        batched: bool = False,
        max_batch_size: int = 1024,
        always_initialize: bool = True,
    ) -> None:
        """
        Create a new instance of ScheduleGettable which is used to do I and Q
        acquisition or alternatively magnitude and phase.

        Parameters
        ----------
        quantum_device
            The qcodes instrument representing the quantum device under test (DUT)
            containing quantum device properties and setup configuration information.
        schedule_function
            A function which returns a
            :class:`quantify_scheduler.schedules.schedule.Schedule`. The
            function is required to have the `repetitions` keyword argument.
        schedule_kwargs
            The schedule function keyword arguments, when a value in this dictionary is
            a :class:`~qcodes.instrument.parameter.Parameter`, this parameter will be
            evaluated every time :code:`.get()` is called before being passed to the
            :code:`schedule_function`.
        num_channels
            The number of channels to expect in the acquisition data.
        data_labels
            Allows to specify custom labels. Needs to be precisely 2*num_channels if
            specified. The order is [Voltage I 0, Voltage Q 0, Voltage I 1, Voltage Q 1,
            ...], in case real_imag==True, otherwise [Magnitude 0, Phase 0, Magnitude 1,
            Phase 1, ...].
        real_imag
            If true, the gettable returns I, Q values. Otherwise, magnitude and phase
            (degrees) are returned.
        batched
            Used to indicate if the experiment is performed in batches or in an
            iterative fashion.
        max_batch_size:
            Determines the maximum number of points to acquire when acquiring in batched
            mode. Can be used to split up a program in parts if required due to hardware
            constraints.
        always_initialize:
            If True, then reinitialize the schedule on each invocation of `get`. If
            False, then only initialize the first invocation of `get`.
        """
        self._data_labels_specified = data_labels is not None

        self.always_initialize = always_initialize
        self.is_initialized = False
        self._compiled_schedule: CompiledSchedule | None = None

        self.real_imag = real_imag
        if self.real_imag:
            self.name = ["I", "Q"] * num_channels
            if data_labels:
                self.label = data_labels
            else:
                self.label = [
                    f"Voltage {iq}{ch}"
                    for ch in range(num_channels)
                    for iq in ["I", "Q"]
                ]
                logger.info(f"Auto-generating labels. {self.label}")
            self.unit = ["V", "V"] * num_channels
        else:
            self.name = ["magn", "phase"] * num_channels
            if data_labels:
                self.label = data_labels
            else:
                self.label = [
                    f"{val_label}{ch}"
                    for ch in range(num_channels)
                    for val_label in ["Magnitude", "Phase"]
                ]
                logger.info(f"Auto-generating labels. {self.label}")
            self.unit = ["V", "deg"] * num_channels

        self.batched = batched
        self.batch_size = max_batch_size

        # schedule arguments
        self.schedule_function = schedule_function
        self.schedule_kwargs = schedule_kwargs
        self._evaluated_sched_kwargs = {}

        # the quantum device object containing setup configuration information
        self.quantum_device = quantum_device

        # The backend used for compilation. Available as a private variable
        # to facilitate debugging. Will be assigned upon compilation in self.initialize
        self._backend = None

    def __call__(self) -> tuple[float, ...] | tuple[np.ndarray, ...]:
        """Acquire and return data"""
        return self.get()

    def _compile(self, sched: Schedule) -> None:
        """Compile schedule, separated to allow for profiling compilation duration."""
        compilation_config = self.quantum_device.generate_compilation_config()

        # made into a private variable for debugging and future caching functionality
        self._backend = compilation_config.backend(name=compilation_config.name)
        self._compiled_schedule = self._backend.compile(
            schedule=sched, config=compilation_config
        )

    def initialize(self) -> None:
        """
        This generates the schedule and uploads the compiled instructions to the
        hardware using the instrument coordinator.
        """
        logger.debug("Initializing schedule gettable.")
        self._evaluated_sched_kwargs = _evaluate_parameter_dict(self.schedule_kwargs)

        # generate a schedule using the evaluated keyword arguments dict
        sched = self.schedule_function(
            **self._evaluated_sched_kwargs,
            repetitions=self.quantum_device.cfg_sched_repetitions(),
        )
        self._compile(sched)

        instr_coordinator = self.quantum_device.instr_instrument_coordinator.get_instr()
        instr_coordinator.prepare(self._compiled_schedule)

        self.is_initialized = True

    @property
    def compiled_schedule(self) -> CompiledSchedule | None:
        """Return the schedule used in this class"""
        return self._compiled_schedule

    def get(self) -> tuple[float, ...] | tuple[np.ndarray, ...]:
        """
        Start the experimental sequence and retrieve acquisition data.

        The data format returned is dependent on the type of acquisitions used
        in the schedule. These data formats can be found in the :ref:`user guide
        <sec-user-guide-acquisition-data-schedulegettable>`.

        Returns
        -------
        :
            A tuple of acquisition data per acquisition channel as specified above.
        """
        instr_coordinator = self.quantum_device.instr_instrument_coordinator.get_instr()

        # ensure the instruments are not running and we are starting from a clean state
        # We switch on allow_failure so that some instruments which require the prepare
        # before the stop can fail.
        instr_coordinator.stop(allow_failure=True)

        if not self.is_initialized or self.always_initialize:
            self.initialize()

        if self.compiled_schedule is None:
            raise RuntimeError(
                "No compiled schedule was found. Either the schedule was not "
                "compiled, or the compiled schedule was not assigned to the "
                "correct attribute."
            )

        instr_coordinator.start()
        acquired_data = instr_coordinator.retrieve_acquisition()
        instr_coordinator.stop()

        acq_metadata = extract_acquisition_metadata_from_schedule(
            self.compiled_schedule
        )

        if len(acquired_data) == 0 and len(acq_metadata.acq_indices) != 0:
            raise RuntimeError(
                f"InstrumentCoordinator.retrieve_acquisition() "
                f"('{instr_coordinator.name}') "
                f"did not return any data, but was expected to return data based on "
                f"the acquisition metadata in the compiled schedule: "
                f"{acq_metadata.acq_indices=}"
            )

        result = self.process_acquired_data(acquired_data, acq_metadata)
        return result

    def _reshape_data(
        self, acq_metadata: AcquisitionMetadata, vals: NDArray
    ) -> list[NDArray]:
        if acq_metadata.acq_protocol == "TriggerCount":
            return [vals.real.astype(np.uint64)]

        if acq_metadata.acq_protocol in (
            "Trace",
            "SSBIntegrationComplex",
            "WeightedIntegratedComplex",
        ):
            ret_val = []
            if self.real_imag:
                ret_val.append(vals.real)
                ret_val.append(vals.imag)
                return ret_val
            else:
                ret_val.append(np.abs(vals))
                ret_val.append(np.angle(vals, deg=True))
                return ret_val

        raise NotImplementedError(
            f"Acquisition protocol {acq_metadata.acq_protocol} with bin"
            f" mode {acq_metadata.bin_mode} is not supported."
        )

    def _process_acquired_data_trigger_count(
        self, acquired_data: Dataset, acq_metadata: AcquisitionMetadata
    ) -> dict[int, np.ndarray]:
        """Reformat acquired data in a dictionary. Used by process_acquired_data.

        Parameters
        ----------
        acquired_data
            Acquired data as returned by instrument coordinator
        acq_metadata
            Acquisition metadata from schedule

        Returns
        -------
        :
            Dictionary with reformatted data. Keys correspond to the acquisition
            channel. Values are 1d numpy arrays with trigger counts.

        Raises
        ------
        NotImplementedError
            If acquisition protocol other than BinMode.APPEND is used.
        """
        dataset = {}
        for acq_channel, acq_indices in acq_metadata.acq_indices.items():
            dataset[acq_channel] = dataset[acq_channel] = (
                acquired_data[acq_channel].sel(repetition=0).values
            )
        return dataset

    def process_acquired_data(  # noqa: PLR0912
        self,
        acquired_data: Dataset,
        acq_metadata: AcquisitionMetadata,
        repetitions: int | None = None,
    ) -> tuple[float, ...] | tuple[NDArray[np.float_], ...]:
        """
        Reshapes the data as returned from the instrument coordinator into the form
        accepted by the measurement control.

        Parameters
        ----------
        acquired_data
            Data that is returned by instrument coordinator.
        acq_metadata
            Acquisition metadata from schedule. It is supposed to be generated by
            :func:`~quantify_scheduler.helpers.schedule.extract_acquisition_metadata_from_schedule`.
        repetitions
            (deprecated) Should not be specified. Will be removed in
            quantify-scheduler-0.16.

        Returns
        -------
        :
            A tuple of data, casted to a historical conventions on data format.
        """
        # FIXME: this reshaping should happen inside the instrument coordinator
        # blocked by quantify-core#187, and quantify-core#233

        # retrieve the acquisition results
        # FIXME: acq_metadata should be an attribute of the schedule, see also #192
        if repetitions is not None:
            warnings.warn(
                "`repetitions` argument of `ScheduleGettable.process_acquired_data()`"
                " function has no effect and will be removed in"
                " quantify-scheduler-0.17.",
                FutureWarning,
            )
        if acq_metadata.acq_protocol == "TriggerCount":
            # We haven't yet formalized and implemented acquisition protocols and
            # correspondent data shape for TriggerCount acquisiton protocol.
            dataset = self._process_acquired_data_trigger_count(
                acquired_data, acq_metadata
            )

        elif (
            acq_metadata.acq_protocol == "Trace"
            and acq_metadata.bin_mode == BinMode.AVERAGE
        ):
            dataset = {}
            for acq_channel in acq_metadata.acq_indices:
                channel_data = acquired_data[acq_channel]
                if (num_dims := len(channel_data.dims)) != 2 or not np.iscomplexobj(
                    channel_data
                ):
                    raise AcquisitionProtocolError(
                        "Data returned by an instrument coordinator component for"
                        f" {acq_metadata.acq_protocol} acquisition protocol in"
                        f" {acq_metadata.bin_mode} bin mode is expected to be an"
                        f" array of complex numbers with with two dimensions:"
                        " acquisition index and trace index. This is not the case for"
                        f" acquisition channel {acq_channel}, that has data"
                        f" type {channel_data.dtype} and {num_dims} dimensions:"
                        f" {', '.join((str(dim) for dim in channel_data.dims))}."
                    )
                if channel_data.shape[0] != 1:
                    raise AcquisitionProtocolNotSupportedError(
                        "Trace acquisition protocol with several acquisitions on the"
                        " same acquisition channel is not supported by"
                        " a ScheduleGettable"
                    )
                dataset[acq_channel] = channel_data.to_numpy().reshape((-1,))

        elif (
            acq_metadata.acq_protocol
            in ("SSBIntegrationComplex", "WeightedIntegratedComplex")
            and acq_metadata.bin_mode == BinMode.AVERAGE
        ):
            dataset = {}
            for acq_channel in acq_metadata.acq_indices:
                channel_data = acquired_data[acq_channel]
                if (num_dims := len(channel_data.dims)) != 1 or not np.iscomplexobj(
                    channel_data
                ):
                    raise AcquisitionProtocolError(
                        "Data returned by an instrument coordinator component for"
                        f" {acq_metadata.acq_protocol} acquisition protocol in"
                        f" {acq_metadata.bin_mode} bin mode is expected to be an"
                        f" array of complex numbers with one dimension: acquisition"
                        " index. This is not the case for acquisition channel"
                        f" {acq_channel}, that has data type {channel_data.dtype} and"
                        f" {num_dims} dimensions:"
                        f" {', '.join((str(dim) for dim in channel_data.dims))}."
                    )
                dataset[acq_channel] = channel_data.to_numpy()

        elif (
            acq_metadata.acq_protocol
            in ("SSBIntegrationComplex", "WeightedIntegratedComplex")
            and acq_metadata.bin_mode == BinMode.APPEND
        ):
            dataset = {}
            for acq_channel in acq_metadata.acq_indices:
                channel_data = acquired_data[acq_channel]
                if (num_dims := len(channel_data.dims)) != 2 or not np.iscomplexobj(
                    channel_data
                ):
                    raise AcquisitionProtocolError(
                        "Data returned by an instrument coordinator component for"
                        f" {acq_metadata.acq_protocol} acquisition protocol in"
                        f" {acq_metadata.bin_mode} bin mode is expected to be an "
                        f" array of complex numbers with two dimensions: repetition"
                        " index and acquisition index. This is not the case for"
                        f" acquisition channel {acq_channel}, that has data type"
                        f" {channel_data.dtype} and {num_dims} dimensions:"
                        f" {', '.join((str(dim) for dim in channel_data.dims))}."
                    )
                dataset[acq_channel] = channel_data.to_numpy().reshape((-1,))

        else:
            raise AcquisitionProtocolNotSupportedError(
                f"ScheduleGettable does not support {acq_metadata.acq_protocol}"
                f' acquisition protocol in "{acq_metadata.bin_mode}" bin mode.'
            )

        # Reshaping of the data before returning
        return_data = []
        for idx, (acq_channel, vals) in enumerate(dataset.items()):
            if not self._data_labels_specified and idx != acq_channel:
                logger.warning(
                    f"Default data_labels may not match the acquisition channel. "
                    f"Element {idx} with label {self.label[idx]} corresponds to "
                    f"acq_channel {acq_channel}, while they were expected to match. To "
                    f"fix this behavior either specify custom data_labels, or ensure "
                    f"your acquisition channels are sequential starting from 0."
                )

            if self.batched is False and len(vals) != 1:
                raise ValueError(
                    f"For iterative mode, only one value is expected for each"
                    f" acquisition channel. Got {len(vals)} values for acquisition"
                    f" channel '{acq_channel}' instead."
                )

            return_data.extend(self._reshape_data(acq_metadata, vals))

        logger.debug(f"Returning {len(return_data)} values.")
        return tuple(return_data)

    def generate_diagnostics_report(
        self, execute_get: bool = False, update: bool = False
    ) -> str:
        """
        Create a report that saves all information contained in this `ScheduleGettable`
        and save it in the quantify datadir with its own `tuid`. The information in
        the report includes the generated schedule, device config, hardware config
        and snapshot of the instruments.

        Parameters
        ----------
        execute_get
            When ``True``, executes ``self.get()`` before generating the report.
        update
            When ``True``, updates all parameters before saving the snapshot.

        Returns
        -------
        :
            The `tuid` of the generated report.
        """
        tuid = gen_tuid()
        if execute_get:
            self.get()
        if not self.is_initialized:
            raise RuntimeError(
                "`generate_diagnostics_report` can only run for an initialized "
                "`ScheduleGettable`. Please initialize manually or run with "
                "`execute_get=True`"
            )

        device_cfg = self.quantum_device.generate_device_config().dict()
        hardware_cfg = self.quantum_device.generate_hardware_config()

        gettable_config = {
            "repetitions": self.quantum_device.cfg_sched_repetitions(),
            "evaluated_schedule_kwargs": self._evaluated_sched_kwargs,
        }

        sched = self.schedule_function(
            **self._evaluated_sched_kwargs,
            repetitions=self.quantum_device.cfg_sched_repetitions(),
        )

        filename = os.path.join(get_datadir(), f"{tuid}.zip")
        with zipfile.ZipFile(
            filename, mode="w", compression=zipfile.ZIP_DEFLATED, compresslevel=9
        ) as zip_file:
            zip_file.writestr("time.txt", str(time.time()))
            zip_file.writestr(
                "device_cfg.json",
                json.dumps(device_cfg, cls=NumpyJSONEncoder, indent=4),
            )
            zip_file.writestr(
                "hardware_cfg.json",
                json.dumps(hardware_cfg, cls=NumpyJSONEncoder, indent=4),
            )
            zip_file.writestr(
                "gettable.json",
                json.dumps(gettable_config, cls=NumpyJSONEncoder, indent=4),
            )
            zip_file.writestr("schedule.json", sched.to_json())
            zip_file.writestr(
                "snapshot.json",
                json.dumps(snapshot(update=update), cls=NumpyJSONEncoder, indent=4),
            )

        return filename


def _evaluate_parameter_dict(parameters: dict[str, Any]) -> dict[str, Any]:
    r"""
    Loop over the keys and values in a dict and replaces parameters with their current
    value.

    Parameters
    ----------
    parameters
        A dictionary containing a mix of
        :class:`~qcodes.instrument.parameter.Parameter`\s and normal values.

    Returns
    -------
    :
        The `parameters` dictionary, but with the parameters replaced by their current
        value.

    Raises
    ------
    TypeError
        If a parameter returns None

    """
    evaluated_parameters = dict()

    for key, val in parameters.items():
        if isinstance(val, Parameter):
            # evaluate the parameter
            evaluated_parameters[key] = val.get()
            # verify that the parameter has a value, a missing value typically indicates
            # that it was not initialized.
            if evaluated_parameters[key] is None:
                raise TypeError(
                    f"{key}: parameter {val} returns None. "
                    "It is possible this parameter was not configured correctly."
                )

        else:
            evaluated_parameters[key] = val

    return evaluated_parameters
