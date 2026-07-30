"""
MeasurementMode: the contract a mode controller (for JV, SPO, etc. future).

This is a typing.Protocol, and mode controllers do NOT inherit
from it. Since every mode controller is a QObject, structural/duck typing is the only
option. `@runtime_checkable` still allows `isinstance(controller, MeasurementMode)`
w/o inheritance.
"""
from typing import Protocol, runtime_checkable

from core.sweep_state import SweepState


@runtime_checkable
class MeasurementMode(Protocol):
    state: SweepState

    def set_output_dir(self, path: str) -> None:
        """Set the directory exported results/plots are written to."""
        ...

    def run_measurement(self) -> None:
        """Validate config and start a sweep on a background worker."""
        ...

    def abort_measurement(self) -> None:
        """Request the in-progress sweep stop early."""
        ...
