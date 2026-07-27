"""
Pure display-formatting helpers with no Qt/widget dependency, 
shared by any results-table panel.
"""
import numpy as np


def format_metric(value, decimals):
    if value is None or not np.isfinite(value):
        return "--"
    return f"{value:.{decimals}f}"


def format_resistance(value):
    """
    SI-style formatter for resistances.
    Converts raw ohms into readable k and M suffixes.
    """
    if value is None or not np.isfinite(value):
        return "--"

    abs_val = abs(value)

    # Millions (Mega-ohms)
    if abs_val >= 1_000_000:
        return f"{value / 1_000_000:.2f} M"

    # Thousands (Kilo-ohms)
    elif abs_val >= 1_000:
        # For large Rsh (over 10k), 1 decimal: [e.g. 133.2 k]
        # For small Rs errors (under 10k), 2 decimal: [e.g. 3.29 k]
        if abs_val >= 10_000:
            return f"{value / 1_000:.1f} k"
        return f"{value / 1_000:.2f} k"

    # Standard Ohms
    elif abs_val >= 1:
        return f"{value:.2f}"

    # Sub-ohm values
    else:
        return f"{value:.3f}"
