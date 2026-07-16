"""
Pure PV data-analysis functions: JV-curve metric extraction and basic
fault detection.
"""
import numpy as np


def _interp_zero_crossing(x, y):
    x = np.asarray(x, dtype=float)
    y = np.asarray(y, dtype=float)
    valid = np.isfinite(x) & np.isfinite(y)
    x = x[valid]
    y = y[valid]

    if len(x) < 2:
        return np.nan

    exact = np.where(np.isclose(y, 0.0, atol=1e-15))[0]
    if exact.size:
        return float(x[exact[0]])

    sign_changes = np.where(np.diff(np.signbit(y)))[0]
    if sign_changes.size == 0:
        return np.nan

    idx = sign_changes[0]
    x0, x1 = x[idx], x[idx + 1]
    y0, y1 = y[idx], y[idx + 1]
    if np.isclose(y1, y0):
        return float((x0 + x1) / 2)
    return float(x0 + (0 - y0) * (x1 - x0) / (y1 - y0))


def extract_parameters(V, I, area_cm2, pin_mw_cm2=100):
    V = np.asarray(V, dtype=float)
    I = np.asarray(I, dtype=float)

    if area_cm2 <= 0:
        raise ValueError("Pixel area must be greater than zero.")
    if pin_mw_cm2 <= 0:
        raise ValueError("Incident power must be greater than zero.")

    # J is in mA/cm^2 because A/cm^2 * 1000 = mA/cm^2.
    J = (I / area_cm2) * 1000

    order_v = np.argsort(V)
    V_sorted = V[order_v]
    J_sorted = J[order_v]
    I_sorted = I[order_v]

    Voc = _interp_zero_crossing(V_sorted, I_sorted)
    Jsc_raw = _interp_zero_crossing(J_sorted, V_sorted)
    Jsc = abs(Jsc_raw) if np.isfinite(Jsc_raw) else np.nan

    # Electrical power density is V * J in mW/cm^2. The generated-power
    # quadrant is determined from the short-circuit current polarity, then
    # restricted to the photovoltaic operating region between 0 V and Voc.
    measured_power = V * J
    if np.isfinite(Jsc_raw) and not np.isclose(Jsc_raw, 0.0):
        current_polarity = np.sign(Jsc_raw)
    else:
        current_polarity = -1 if abs(np.nanmin(measured_power)) > abs(np.nanmax(measured_power)) else 1
    power_density = current_polarity * measured_power

    finite = np.isfinite(V) & np.isfinite(power_density)
    if np.isfinite(Voc):
        lo, hi = sorted((0.0, Voc))
        operating_region = finite & (V >= lo) & (V <= hi)
    else:
        operating_region = finite
    positive_region = operating_region & (power_density >= 0)
    candidates = np.where(positive_region)[0]
    if candidates.size == 0:
        candidates = np.where(finite)[0]
    if candidates.size == 0:
        raise ValueError("No finite IV data available for metric extraction.")

    mpp_idx = int(candidates[np.nanargmax(power_density[candidates])])
    Pmax = max(float(power_density[mpp_idx]), 0.0)
    Vmpp = float(V[mpp_idx])
    Jmpp = abs(float(J[mpp_idx]))

    denom = abs(Voc * Jsc) if np.isfinite(Voc) and np.isfinite(Jsc) else np.nan
    FF = Pmax / denom if denom and np.isfinite(denom) else np.nan
    PCE = (Pmax / pin_mw_cm2) * 100

    return {
        "Voc": float(Voc),
        "Jsc": float(Jsc),
        "Vmpp": Vmpp,
        "Jmpp": Jmpp,
        "Pmax": Pmax,
        "FF": float(FF),
        "PCE": float(PCE),
    }


def check_fault(I):
    I = np.asarray(I, dtype=float)
    if np.max(np.abs(I)) > 0.95:
        return "SHORT"
    if np.max(np.abs(I)) < 1e-6:
        return "OPEN"
    return None
