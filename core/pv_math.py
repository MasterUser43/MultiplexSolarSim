"""
Pure PV data-analysis functions: JV-curve metric extraction and basic
fault detection. 

Runnable and testable from a plain terminal against numpy arrays of voltage/current.
"""
import numpy as np
from scipy.optimize import least_squares


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


def derivative_resistances(V, I):
    """Closed-form Rs/Rsh estimate from local IV slope.

    Rs comes from the slope dV/dI near Voc (I ~ 0); Rsh comes from the
    slope dV/dI near Isc (V ~ 0). 
    
    Always runs, but noisier than the diode-model fit below.
    """
    V = np.asarray(V, dtype=float)
    I = np.asarray(I, dtype=float)

    finite = np.isfinite(V) & np.isfinite(I)
    V = V[finite]
    I = I[finite]

    if len(V) < 6:
        return np.nan, np.nan

    order = np.argsort(V)
    V = V[order]
    I = I[order]

    # Rs near Voc
    try:
        voc_idx = np.argmin(np.abs(I))
        rs_lo = max(0, voc_idx - 3)
        rs_hi = min(len(V), voc_idx + 4)
        V_rs = V[rs_lo:rs_hi]
        I_rs = I[rs_lo:rs_hi]

        if len(V_rs) >= 3:
            p = np.polyfit(I_rs, V_rs, 1)
            Rs = abs(p[0])
        else:
            Rs = np.nan
    except Exception:
        Rs = np.nan

    # Rsh near Isc
    try:
        mask = np.abs(V) <= 0.05
        V_rsh = V[mask]
        I_rsh = I[mask]

        if len(V_rsh) >= 3:
            p = np.polyfit(I_rsh, V_rsh, 1)
            Rsh = abs(p[0])
        else:
            Rsh = np.nan
    except Exception:
        Rsh = np.nan

    return Rs, Rsh


def single_diode_model_current(params, V, vt):
    """
    Solves the single-diode equation for current (I) at each voltage (V).

    Uses the Newton-Raphson method to iteratively solve the implicit, transcendental 
    Shockley diode equation with series and shunt resistances.

    Parameters
    ----------
    params : tuple or list of float
        A 5-element sequence containing:
        - `Iph` (float): Photocurrent (A).
        - `I0` (float): Diode saturation current (A).
        - `n` (float): Diode ideality factor (dimensionless).
        - `Rs` (float): Series resistance (Ohms).
        - `Rsh` (float): Shunt resistance (Ohms).
    V : array_like
        Voltages at which to evaluate the current (V).
    vt : float
        Thermal voltage (kT/q) in V (~0.02585 V at room temperature).

    Returns
    -------
    ndarray
        Calculated diode current (A) for each voltage point in `V`.
    """
    Iph, I0, n, Rs, Rsh = params

    I = np.full_like(V, Iph, dtype=float)

    for _ in range(60):
        exp_term = np.exp(np.clip((V + I * Rs) / (n * vt), -100, 100))

        f = (
            Iph
            - I0 * (exp_term - 1)
            - (V + I * Rs) / Rsh
            - I
        )

        df = (
            -I0 * exp_term * (Rs / (n * vt))
            - Rs / Rsh
            - 1
        )

        step = f / df
        I -= step

        if np.max(np.abs(step)) < 1e-12:
            break

    return I


def diode_fit_resistances(V, I):
    """Fit the single-diode model to a JV curve and return (Rs, Rsh).

    Uses bounded least-squares to fit the five-parameter diode model. 
    To improve convergence, I0 and Rsh are optimized in log10-space.

    Returns (Rs, Rsh) in Ohms. Returns (nan, nan) if the fit fails.
    """
    V = np.asarray(V, dtype=float)
    I = np.asarray(I, dtype=float)

    finite = np.isfinite(V) & np.isfinite(I)
    V = V[finite]
    I = I[finite]

    if len(V) < 10:
        return np.nan, np.nan

    vt = 0.02585  # thermal voltage at room temperature

    # Unpack log-space parameters [Iph, log10(I0), n, Rs, log10(Rsh)]
    def unpack(x):
        Iph, log_I0, n, Rs, log_Rsh = x
        return [Iph, 10 ** log_I0, n, Rs, 10 ** log_Rsh]

    # Initial guesses and bounds
    x0 = [
        max(np.max(I), 1e-9),  # Iph guess
        -10.0,                 # log10(I0) guess  (I0 ~ 1e-10)
        1.5,                   # n guess
        20,                    # Rs guess
        5.0,                   # log10(Rsh) guess (Rsh ~ 1e5)
    ]
    lower = [0, -15, 1.0, 0, 1]
    upper = [1, -3, 4.0, 1e4, 9]

    # Dynamically size f_scale to 1% of current range to prevent loss saturation
    f_scale = max(0.01 * np.max(np.abs(I)), 1e-12)

    def residuals(params_x):
        try:
            modeled = single_diode_model_current(unpack(params_x), V, vt)
            return modeled - I
        except Exception:
            return np.ones_like(I) * 1e6

    try:
        result = least_squares(
            residuals,
            x0,
            bounds=(lower, upper),
            loss="soft_l1",
            f_scale=f_scale,
            max_nfev=2000,
            x_scale="jac",
        )

        Iph, I0, n, Rs, Rsh = unpack(result.x)

        # Clip Rsh to a sensible physical maximum
        if Rsh > 1e8:
            Rsh = 1e8

        return float(Rs), float(Rsh)
    except Exception:
        return np.nan, np.nan


def extract_parameters(V, I, area_cm2, pin_mw_cm2=100):
    """
    Extracts J-V characteristics from raw solar cell sweep data.

    Calculates key performance metrics including open-circuit voltage, 
    short-circuit current density, fill factor, and power conversion efficiency.

    Parameters
    ----------
    V : array_like
        Measured voltage points (V).
    I : array_like
        Measured current points (A).
    area_cm2 : float
        Active solar cell pixel area in cm^2.
    pin_mw_cm2 : float, optional
        Incident light power density in mW/cm^2. Defaults to 100.

    Returns
    -------
    dict
        A dictionary containing the extracted performance metrics:
        - "Voc" (float): Open-circuit voltage (V).
        - "Jsc" (float): Short-circuit current density (mA/cm^2).
        - "Vmpp" (float): Voltage at the maximum power point (V).
        - "Jmpp" (float): Current density at the maximum power point (mA/cm^2).
        - "Pmax" (float): Maximum electrical power density (mW/cm^2).
        - "FF" (float): Fill factor (dimensionless, 0 to 1).
        - "PCE" (float): Power conversion efficiency (%).
    """
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


def full_iv_report(V, I, area_cm2, pin_mw_cm2=100, fit_resistances=True):
    """
    Extracts standard JV parameters and calculates series/shunt resistances.

    This function wraps `extract_parameters` and appends both local slope (derivative)
    and single-diode model least-squares fit estimates of Rs and Rsh.

    Parameters
    ----------
    V : array_like
        Measured voltage points (V).
    I : array_like
        Measured current points (A).
    area_cm2 : float
        Active solar cell pixel area in cm^2.
    pin_mw_cm2 : float, optional
        Incident light power density in mW/cm^2. Defaults to 100.
    fit_resistances : bool, optional
        If True, runs the single-diode model fit using a bounded least-squares
        optimization. If False, skips the fit to save processing time. Defaults to True.

    Returns
    -------
    dict
        A dictionary containing all standard J-V metrics, with the following 
        additional keys:
        - "Rs_derivative": Series resistance from local Voc slope (Ohms).
        - "Rsh_derivative": Shunt resistance from local zero-bias slope (Ohms).
        - "Rs_diode_eq": Series resistance from the diode-model fit (Ohms or NaN).
        - "Rsh_diode_eq": Shunt resistance from the diode-model fit (Ohms or NaN).

    Notes
    -----
    **Convergence Caveat:**
    The non-linear single-diode model fit is sensitive to initial parameter guesses and 
    can stall or converge poorly on degraded, highly resistive, or extremely noisy curves. 
    In these instances, the least-squares results may rest near their initial bounds. Use 
    the faster, closed-form 'derivative' outputs as a physical sanity check.
    """
    metrics = extract_parameters(V, I, area_cm2, pin_mw_cm2)

    Rs_derivative, Rsh_derivative = derivative_resistances(V, I)
    metrics["Rs_derivative"] = float(Rs_derivative)
    metrics["Rsh_derivative"] = float(Rsh_derivative)

    if fit_resistances:
        Rs_diode_eq, Rsh_diode_eq = diode_fit_resistances(V, I)
    else:
        Rs_diode_eq, Rsh_diode_eq = np.nan, np.nan
    metrics["Rs_diode_eq"] = float(Rs_diode_eq)
    metrics["Rsh_diode_eq"] = float(Rsh_diode_eq)

    return metrics
