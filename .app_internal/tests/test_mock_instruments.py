"""
Tests for --mock dev mode: mock instrument drivers + InstrumentManager's
mock branch.
"""
import numpy as np
import pytest

from core.instrument_manager import InstrumentManager
from core.pv_math import full_iv_report
from instruments.keithley2460 import keithley_read_current
from instruments.mock_keithley import MockKeithley
from instruments.mock_relay import MockRelay


def _sweep_mock_keithley(k, v0=-0.05, v1=0.75, points=100):
    k.write("*RST")
    k.write(":SOUR:VOLT:ILIM 0.105")
    k.write(":OUTPut:STATe ON")
    V = np.linspace(v0, v1, points)
    I = np.array([keithley_read_current(k, v, 0.0)[0] for v in V])
    return V, I


def test_mock_keithley_produces_a_realistic_curve():
    V, I = _sweep_mock_keithley(MockKeithley(seed=42))
    report = full_iv_report(V, I, area_cm2=0.0396, pin_mw_cm2=100, fit_resistances=False)

    # Real crystalline-silicon-ish test cell ranges.
    assert 0.3 < report["Voc"] < 0.9
    assert 5 < report["Jsc"] < 50
    assert 0.4 < report["FF"] < 0.9
    assert 1 < report["PCE"] < 30


def test_mock_keithley_output_off_reads_zero():
    k = MockKeithley(seed=1)
    k.write("*RST")
    k.write(":OUTPut:STATe OFF")
    current, raw, kv = keithley_read_current(k, 0.3, 0.0)
    assert current == 0.0


def test_mock_keithley_respects_compliance_limit():
    k = MockKeithley(iph=10.0, seed=1)  # absurdly high Iph to force compliance clamp
    k.write("*RST")
    k.write(":SOUR:VOLT:ILIM 0.05")
    k.write(":OUTPut:STATe ON")
    current, raw, kv = keithley_read_current(k, 0.0, 0.0)
    assert abs(current) <= 0.05 + 1e-9


def test_mock_keithley_idn_and_error_queries():
    k = MockKeithley()
    assert "2460" in k.query("*IDN?")
    assert k.query(":SYST:ERR?").startswith("0,")


def test_mock_relay_writeall_and_readall_roundtrip():
    r = MockRelay()
    r.write(b"relay writeall 02A1\r")
    r.write(b"relay readall\r")
    assert r.read(64) == b"02A1\r"


def test_mock_relay_on_off_individual_channel():
    r = MockRelay()
    r.write(b"relay on 5\r")
    r.write(b"relay readall\r")
    state_after_on = int(r.read(64).strip(), 16)
    assert state_after_on & (1 << 5)

    r.write(b"relay off 5\r")
    r.write(b"relay readall\r")
    state_after_off = int(r.read(64).strip(), 16)
    assert not (state_after_off & (1 << 5))


def test_mock_relay_hex_channel_token():
    r = MockRelay()
    r.write(b"relay on A\r")  # channel 10
    r.write(b"relay readall\r")
    state = int(r.read(64).strip(), 16)
    assert state & (1 << 10)


def test_instrument_manager_mock_mode_connects_without_hardware():
    mgr = InstrumentManager(mock=True)
    logs = []
    keithley_ok, relay_ok = mgr.connect_all(logger=logs.append)

    assert keithley_ok is True
    assert relay_ok is True
    assert isinstance(mgr.keithley, MockKeithley)
    assert isinstance(mgr.relay, MockRelay)
    assert any("MOCK" in line for line in logs)


def test_instrument_manager_real_mode_unaffected(monkeypatch):
    """mock=False must still take the real hardware-search path."""
    import core.instrument_manager as im

    monkeypatch.setattr(im, "find_keithley", lambda logger=None: (_ for _ in ()).throw(RuntimeError("no hw")))
    monkeypatch.setattr(im, "find_numato", lambda logger=None: (_ for _ in ()).throw(RuntimeError("no hw")))

    mgr = InstrumentManager(mock=False)
    keithley_ok, relay_ok = mgr.connect_all()
    assert keithley_ok is False
    assert relay_ok is False
