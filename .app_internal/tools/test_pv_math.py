"""
Tests for core/pv_math.py.

Pure math, no hardware/Qt involved. Run from .app_internal:

    pytest tests/test_pv_math.py -v

Two checks here:
  1. Exact hand-derived cases for the zero-crossing interpolation and the
     fault/validation guards (deterministic, no tolerance needed).
  2. A synthetic single-diode JV curve (built with single_diode_model_current
     using known Iph/I0/n/Rs/Rsh) fed back through extract_parameters and
     diode_fit_resistances, checked against the known ground-truth values.
     This pins down the current numeric behavior so future changes to the
     interpolation/fit logic show up as a failing test here.
"""
import numpy as np
import pytest

from core.pv_math import (
    _interp_zero_crossing,
    check_fault,
    derivative_resistances,
    diode_fit_resistances,
    extract_parameters,
    full_iv_report,
    single_diode_model_current,
)


# --- _interp_zero_crossing -------------------------------------------------

def test_interp_zero_crossing_exact_hit():
    assert _interp_zero_crossing([0, 1, 2], [0.0, 1, 2]) == 0.0


def test_interp_zero_crossing_linear_interpolation():
    # y goes -2, -1, 1, 2 -> crosses zero 1/2 way between x=1 (y=-1) and x=2 (y=1)
    result = _interp_zero_crossing([0, 1, 2, 3], [-2, -1, 1, 2])
    assert result == pytest.approx(1.5)


def test_interp_zero_crossing_no_sign_change():
    assert np.isnan(_interp_zero_crossing([0, 1, 2], [1, 2, 3]))


def test_interp_zero_crossing_insufficient_points():
    assert np.isnan(_interp_zero_crossing([0], [0]))
    assert np.isnan(_interp_zero_crossing([], []))


def test_interp_zero_crossing_ignores_non_finite():
    result = _interp_zero_crossing([0, 1, 2, 3], [-2, np.nan, 1, 2])
    # with the nan point dropped: x=[0,2,3], y=[-2,1,2] -> crossing between x=0(-2), x=2(1)
    assert result == pytest.approx(4 / 3)


# --- check_fault -------------------------------------------------------

def test_check_fault_short():
    assert check_fault(np.array([0.1, 0.96, 0.2])) == "SHORT"


def test_check_fault_open():
    assert check_fault(np.array([1e-8, -1e-9, 0.0])) == "OPEN"


def test_check_fault_normal():
    assert check_fault(np.array([0.01, 0.05, -0.02])) is None


def test_check_fault_boundaries_are_exclusive():
    # exactly at the thresholds should NOT trip (code uses strict > / <)
    assert check_fault(np.array([0.95])) is None
    assert check_fault(np.array([1e-6])) is None


# --- extract_parameters: input validation -------------------------------

def test_extract_parameters_rejects_zero_area():
    with pytest.raises(ValueError):
        extract_parameters([0, 1], [0, 1], area_cm2=0)


def test_extract_parameters_rejects_negative_pin():
    with pytest.raises(ValueError):
        extract_parameters([0, 1], [0, 1], area_cm2=0.1, pin_mw_cm2=-5)


# --- extract_parameters / diode_fit_resistances against a known curve ---

# A synthetic curve generated from the model itself, so the true Iph/I0/n/Rs/Rsh
# are known exactly and can be checked against what the pure-math functions recover.
_VT = 0.02585
_TRUE_PARAMS = dict(Iph=0.030, I0=1e-10, n=1.4, Rs=2.0, Rsh=5000.0)
_AREA_CM2 = 0.108  # default 12-pixel area


def _synthetic_curve(n_points=300):
    V = np.linspace(-0.05, 0.75, n_points)  # wide enough to bracket Voc (~0.706V)
    I = single_diode_model_current(list(_TRUE_PARAMS.values()), V, _VT)
    return V, I


def test_extract_parameters_recovers_voc_and_jsc():
    V, I = _synthetic_curve()
    result = extract_parameters(V, I, _AREA_CM2)

    # Reference Isc/Voc solved directly from the same model, independent of
    # extract_parameters' interpolation logic.
    I_at_zero = single_diode_model_current(list(_TRUE_PARAMS.values()), np.array([0.0]), _VT)[0]
    jsc_ref = abs(I_at_zero / _AREA_CM2 * 1000)

    assert result["Voc"] == pytest.approx(0.70623, abs=1e-3)
    assert result["Jsc"] == pytest.approx(jsc_ref, rel=1e-3)
    assert 0.0 < result["FF"] < 1.0
    assert result["Pmax"] > 0.0
    # PCE == Pmax numerically when pin_mw_cm2 defaults to 100
    assert result["PCE"] == pytest.approx(result["Pmax"])


def test_diode_fit_resistances_recovers_true_rs_rsh():
    V, I = _synthetic_curve()
    Rs_fit, Rsh_fit = diode_fit_resistances(V, I)

    assert Rs_fit == pytest.approx(_TRUE_PARAMS["Rs"], rel=1e-2)
    assert Rsh_fit == pytest.approx(_TRUE_PARAMS["Rsh"], rel=1e-2)


def test_diode_fit_resistances_insufficient_points():
    V, I = _synthetic_curve(n_points=9)  # fewer than the 10-point minimum
    Rs_fit, Rsh_fit = diode_fit_resistances(V, I)
    assert np.isnan(Rs_fit)
    assert np.isnan(Rsh_fit)


# --- derivative_resistances: sanity, not ground truth ------------
# The docstring calls this a noisier local-slope approximation, so it's
# checked for physically-sane behavior rather than an exact regression value.

def test_derivative_resistances_insufficient_points():
    Rs, Rsh = derivative_resistances([0, 1, 2, 3, 4], [0, 1, 2, 3, 4])
    assert np.isnan(Rs)
    assert np.isnan(Rsh)


def test_derivative_resistances_sane_on_synthetic_curve():
    V, I = _synthetic_curve()
    Rs, Rsh = derivative_resistances(V, I)

    assert np.isfinite(Rs) and Rs > 0
    assert np.isfinite(Rsh) and Rsh > 0
    # Shunt resistance should be orders of magnitude larger than series
    # resistance for a healthy cell -- true here by construction (2 vs 5000).
    assert Rsh > Rs


# --- full_iv_report: wiring / fit_resistances flag ----------------------

def test_full_iv_report_skips_diode_fit_when_disabled():
    V, I = _synthetic_curve()
    result = full_iv_report(V, I, _AREA_CM2, fit_resistances=False)

    assert np.isnan(result["Rs_diode_eq"])
    assert np.isnan(result["Rsh_diode_eq"])
    # derivative estimate always runs regardless of the flag
    assert np.isfinite(result["Rs_derivative"])
    assert np.isfinite(result["Rsh_derivative"])


def test_full_iv_report_includes_diode_fit_when_enabled():
    V, I = _synthetic_curve()
    result = full_iv_report(V, I, _AREA_CM2, fit_resistances=True)

    assert result["Rs_diode_eq"] == pytest.approx(_TRUE_PARAMS["Rs"], rel=1e-2)
    assert result["Rsh_diode_eq"] == pytest.approx(_TRUE_PARAMS["Rsh"], rel=1e-2)
