"""
Keithley and Numato connections used throughout the app. The GUI
creates one InstrumentManager, connects it once when the user clicks
"Connect Instruments", and hands the open instrument objects onward to
whatever runs the measurement.
"""
from instruments.keithley2460 import find_keithley
from instruments.numato_relay import find_numato


class InstrumentManager:
    def __init__(self, mock=False):
        self.keithley = None
        self.relay = None
        self.mock = mock

    def connect_all(self, logger=None):
        self.keithley = None
        self.relay = None

        if self.mock:
            # Dev-only path (--mock): no real hardware search at all.
            from instruments.mock_keithley import MockKeithley
            from instruments.mock_relay import MockRelay

            self.keithley = MockKeithley()
            self.relay = MockRelay()
            if logger:
                logger("OK: Keithley connected (MOCK)")
                logger(f"OK: Numato relay connected on {self.relay.port} (MOCK)")
            return True, True

        try:
            self.keithley = find_keithley(logger=logger)
            if logger:
                logger("OK: Keithley connected")
        except Exception as e:
            if logger:
                logger(f"ERROR: Keithley connection failed: {e}")

        try:
            self.relay = find_numato(logger=logger)
            if logger:
                logger(f"OK: Numato relay connected on {self.relay.port}")
        except Exception as e:
            if logger:
                logger(f"ERROR: Relay connection failed: {e}")

        return self.keithley is not None, self.relay is not None
