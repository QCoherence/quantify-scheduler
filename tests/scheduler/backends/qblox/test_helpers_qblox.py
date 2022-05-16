# pylint: disable=missing-class-docstring
# pylint: disable=missing-function-docstring
# pylint: disable=redefined-outer-name
# pylint: disable=missing-module-docstring
# pylint: disable=no-self-use

# Repository: https://gitlab.com/quantify-os/quantify-scheduler
# Licensed according to the LICENCE file on the main branch
"""Tests for the helpers module."""

import pytest

from quantify_scheduler.backends.qblox import helpers
from quantify_scheduler.backends.qblox import constants


@pytest.mark.parametrize("phase", [0.0, 360.0, 10.0, 11.11, 123.123, 90.0, -90.0])
def test_get_nco_phase_arguments(phase: float):
    coarse, fine, ufine = helpers.get_nco_phase_arguments(phase)

    phase_shift_returned = (
        coarse * constants.NCO_PHASE_DEG_STEP_COARSE
        + fine * constants.NCO_PHASE_DEG_STEP_FINE
        + ufine * constants.NCO_PHASE_DEG_STEP_U_FINE
    )

    expected_phase = phase + 360 if phase < 0 else phase

    # approx due to floating point rounding errors
    assert phase_shift_returned == pytest.approx(expected_phase)
