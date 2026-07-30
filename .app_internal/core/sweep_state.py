"""
Atom observable model for sweep-lifecycle state.

This is the Atom-side replacement for the pyqtSignal broadcasts
(`pixel_result`, `progress_update`, `log`, `finished_sweep`).
Enaml views observe these attributes directly instead of connecting to Qt signals.
"""
from atom.api import Atom, Bool, ContainerList, Dict, Int, Str


class SweepState(Atom):
    running = Bool(False)

    active_pixel = Str("--")
    progress_percent = Int(0)
    progress_text = Str("")

    log_lines = ContainerList(str)
    results = ContainerList(Dict())   # mirrors JVController.results, one dict per pixel_result
    faults = ContainerList(Dict())    # one dict per pixel_faulted: {pixel, area, fault, loop}

    finished_aborted = Bool(False)
    finished_had_error = Bool(False)
    finish_count = Int(0)    # increments on every finished_sweep, see module docstring
