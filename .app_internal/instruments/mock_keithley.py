"""
Mock Keithley 2460
"""
import random

from core.pv_math import single_diode_model_current

_VT = 0.02585  # thermal voltage at room temperature, matches pv_math.py's own default


class MockKeithley:
    def __init__(self, iph=0.0012, i0=1e-10, n=1.4, rs=2.0, rsh=5000.0, noise_a=1e-6, seed=None):
        self.timeout = 2000
        self._source_voltage = 0.0
        self._output_on = False
        self._compliance_a = 0.105
        self._iph, self._i0, self._n, self._rs, self._rsh = iph, i0, n, rs, rsh
        self._noise_a = noise_a
        self._rng = random.Random(seed)

    def write(self, command):
        command = command.strip()
        if command == "*RST":
            self._source_voltage = 0.0
            self._output_on = False
        elif command == "*CLS":
            pass
        elif command.startswith(":SOUR:VOLT:ILIM"):
            try:
                self._compliance_a = float(command.split()[-1])
            except ValueError:
                pass
        elif command.startswith(":SOUR:VOLT"):
            try:
                self._source_voltage = float(command.split()[-1])
            except ValueError:
                pass
        elif command.startswith(":OUTPut:STATe"):
            self._output_on = command.strip().upper().endswith("ON")
        # :SENS:FUNC, :SENS:CURR:RANG:AUTO -- accepted, no state to track

    def query(self, command):
        command = command.strip()
        if command == "*IDN?":
            return "KEITHLEY INSTRUMENTS,MODEL 2460,MOCK,1.0.0"
        if command == ":SYST:ERR?":
            return '0,"No error"'
        if command == ":OUTPut:STATe?":
            return "1" if self._output_on else "0"
        if command.startswith(":SOUR:VOLT?"):
            return f"{self._source_voltage:.6f}"
        if command == ":READ?":
            return self._format_current(self._simulate_current())
        return "0"

    def read(self):
        return self._format_current(self._simulate_current())

    def close(self):
        pass

    def _simulate_current(self):
        if not self._output_on:
            return 0.0
        # Keithley source voltage is the negative of device voltage
        device_voltage = -self._source_voltage
        current = single_diode_model_current(
            [self._iph, self._i0, self._n, self._rs, self._rsh], [device_voltage], _VT,
        )[0]
        current += self._rng.uniform(-1, 1) * self._noise_a
        limit = self._compliance_a
        return max(-limit, min(limit, current))

    @staticmethod
    def _format_current(value):
        return f"{value:.9e}"
