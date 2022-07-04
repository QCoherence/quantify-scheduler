# Repository: https://gitlab.com/quantify-os/quantify-scheduler
# Licensed according to the LICENCE file on the main branch
"""Pulse and acquisition corrections for hardware compilation."""
import logging
from typing import Any, Dict, Optional, Tuple

import numpy as np

from quantify_scheduler import Schedule
from quantify_scheduler.backends.qblox import constants
from quantify_scheduler.backends.qblox.helpers import generate_waveform_data
from quantify_scheduler.helpers.importers import import_python_object_from_string
from quantify_scheduler.operations.pulse_library import NumericalPulse


def distortion_correct_pulse(  # pylint: disable=too-many-arguments
    pulse_data: Dict[str, Any],
    sampling_rate: int,
    filter_func_name: str,
    input_var_name: str,
    kwargs_dict: Dict[str, Any],
    clipping_values: Optional[Tuple[float]] = None,
) -> NumericalPulse:
    """
    Sample pulse and apply filter function to the sample to distortion correct it.

    Parameters
    ----------
    pulse_data
        Definition of the pulse.
    sampling_rate
        The sampling rate used to generate the time axis values.
    filter_func_name
        The filter function path of the dynamically loaded filter function.
        Example: ``"scipy.signal.lfilter"``.
    input_var_name
        The input variable name of the dynamically loaded filter function, most likely:
        ``"x"``.
    kwargs_dict
        Dictionary containing kwargs for the dynamically loaded filter function.
        Example: ``{"b": [0.0, 0.5, 1.0], "a": 1}``.
    clipping_values
        Min and max value to which the corrected pulse will be clipped, depending on
        allowed output values for the instrument.

    Returns
    -------
    :
        The sampled, distortion corrected pulse wrapped in a NumericalPulse.
    """

    waveform_data = generate_waveform_data(
        data_dict=pulse_data,
        sampling_rate=sampling_rate,
    )

    filter_func = import_python_object_from_string(filter_func_name)
    kwargs = {input_var_name: waveform_data, **kwargs_dict}
    corrected_waveform_data = filter_func(**kwargs)

    if clipping_values is not None and len(clipping_values) == 2:
        corrected_waveform_data = np.clip(
            corrected_waveform_data, clipping_values[0], clipping_values[1]
        )

    if corrected_waveform_data.size == 1:  # Interpolation requires two sample points
        corrected_waveform_data = np.append(
            corrected_waveform_data, corrected_waveform_data[-1]
        )

    corrected_pulse = NumericalPulse(
        samples=corrected_waveform_data,
        t_samples=np.linspace(
            start=0, stop=pulse_data["duration"], num=corrected_waveform_data.size
        ),
        port=pulse_data["port"],
        clock=pulse_data["clock"],
        t0=pulse_data["t0"],
    )

    return corrected_pulse


def apply_distortion_corrections(
    schedule: Schedule, hardware_cfg: Dict[str, Any]
) -> Schedule:
    """
    Apply distortion corrections to operations in the schedule, as defined via the
    hardware configuration file. Example:

    .. code-block::

        "distortion_corrections": {
            "q0:fl-cl0.baseband": {
                "filter_func": "scipy.signal.lfilter",
                "input_var_name": "x",
                "kwargs": {
                    "b": [0.0, 0.5, 1.0],
                    "a": 1
                },
                "clipping_values": [-2.5, 2.5]
            }
        }

    Clipping values are the boundaries to which the corrected pulses will be clipped,
    upon exceeding, these are optional to supply.

    For pulses in need of correcting (indicated by their port-clock combination) we are
    **only** replacing the dict in ``"pulse_info"`` associated to that specific
    pulse. This means that we can have a combination of corrected (i.e., pre-sampled)
    and uncorrected pulses in the same operation.

    Note that we are **not** updating the ``"operation_repr"`` key, used to reference
    the operation from the schedulable.

    Parameters
    ----------
    schedule
        The schedule that contains operations that are to be distortion corrected.
    hardware_cfg
        The hardware configuration of the setup.

    Returns
    -------
    :
        The schedule with distortion corrected operations.

    Raises
    ------
    KeyError
        when elements are missing in distortion correction config for a port-clock
        combination.
    KeyError
        when clipping values are supplied but not two values exactly, min and max.
    """

    distortion_corrections_key = "distortion_corrections"
    if distortion_corrections_key not in hardware_cfg:
        logging.info(f'No "{distortion_corrections_key}" supplied')
        return schedule

    for operation_repr in schedule.operations.keys():
        substitute_operation = None

        for pulse_info_idx, pulse_data in enumerate(
            schedule.operations[operation_repr].data["pulse_info"]
        ):
            portclock_key = f"{pulse_data['port']}-{pulse_data['clock']}"

            if portclock_key in hardware_cfg[distortion_corrections_key]:
                correction_cfg = hardware_cfg[distortion_corrections_key][portclock_key]

                filter_func_name = correction_cfg.get("filter_func", None)
                input_var_name = correction_cfg.get("input_var_name", None)
                kwargs_dict = correction_cfg.get("kwargs", None)
                clipping_values = correction_cfg.get("clipping_values", None)

                if None in (filter_func_name, input_var_name, kwargs_dict):
                    raise KeyError(
                        f"One or more elements missing in distortion correction config "
                        f'for "{portclock_key}"\n\n'
                        f'"filter_func": {filter_func_name}\n'
                        f'"input_var_name": {input_var_name}\n'
                        f'"kwargs": {kwargs_dict}'
                    )

                if clipping_values and len(clipping_values) != 2:
                    raise KeyError(
                        f'Clipping values for "{portclock_key}" should contain two '
                        "values, min and max.\n"
                        f'"clipping_values": {clipping_values}'
                    )

                corrected_pulse = distortion_correct_pulse(
                    pulse_data=pulse_data,
                    sampling_rate=constants.SAMPLING_RATE,
                    filter_func_name=filter_func_name,
                    input_var_name=input_var_name,
                    kwargs_dict=kwargs_dict,
                    clipping_values=clipping_values,
                )

                schedule.operations[operation_repr].data["pulse_info"][
                    pulse_info_idx
                ] = corrected_pulse.data["pulse_info"][0]

                if pulse_info_idx == 0:
                    substitute_operation = corrected_pulse

        # Convert to operation-type of first entry in pulse_info,
        # required as first entry in pulse_info is used to generate signature in __str__
        if substitute_operation is not None:
            substitute_operation.data["pulse_info"] = schedule.operations[
                operation_repr
            ].data["pulse_info"]
            schedule.operations[operation_repr] = substitute_operation

    return schedule
