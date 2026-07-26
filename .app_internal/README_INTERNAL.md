# .app_internal

This is the application's source code. Hidden s.t. project root only shows
launchers (`Start_Windows.bat`, `Start_Linux.sh`).

Layout:
- `main.py` -- entry point, includes the startup splash-screen logic
- `controllers/` -- UI logic / threading
- `core/` -- backend math (`pv_math.py`) and I/O (`exporter.py`, `instrument_manager.py`)
- `gui/` -- all visual components (windows, panels, styling, plotting)
- `instruments/` -- low-level hardware drivers (Keithley SCPI, Numato serial)
- `tools/` -- standalone hardware bench-test scripts

You may activate the associated enviornment for quickly via:

```
cd ..
.venv\Scripts\activate      (Windows)
source ../.venv/bin/activate (Linux)
cd .app_internal
python main.py
```
