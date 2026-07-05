"""
Keithley and Numato connections used throughout the app. The GUI
creates one InstrumentManager, connects it once when the user clicks
"Connect Instruments", and hands the open instrument objects onward to
whatever runs the measurement.
"""
from instruments.keithley2460 import find_keithley
from instruments.numato_relay import find_numato


class InstrumentManager:
    def __init__(self):
        self.keithley = None
        self.relay = None

    def connect_all(self, logger=None):
        self.keithley = None
        self.relay = None

        try:
            self.keithley = find_keithley()
            if logger:
                logger("OK: Keithley connected")
        except Exception as e:
            if logger:
                logger(f"ERROR: Keithley connection failed: {e}")

        try:
            self.relay = find_numato()
            if logger:
                logger(f"OK: Numato relay connected on {self.relay.port}")
        except Exception as e:
            if logger:
                logger(f"ERROR: Relay connection failed: {e}")

        return self.keithley is not None, self.relay is not None
