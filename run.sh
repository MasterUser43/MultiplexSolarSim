#!/usr/bin/env bash
# run.sh
# Start the Multiplex Solar Simulator.
# Usage:
#   bash run.sh            - start normally, log panel + terminal output
#   bash run.sh --no-log   - skip writing to logs/, terminal output only

if [ ! -f ".venv/bin/activate" ]; then
    echo "[ERROR] Virtual environment not found. Please run 'bash install.sh' first."
    exit 1
fi

source .venv/bin/activate

# --- Resolve a working interpreter inside the venv ---
PYEXE=""
if command -v python3 &>/dev/null; then
    PYEXE="python3"
elif command -v python &>/dev/null; then
    PYEXE="python"
fi

if [ -z "$PYEXE" ]; then
    echo "[ERROR] Python not found in the virtual environment."
    echo "Delete the .venv folder and re-run install.sh."
    exit 1
fi

echo "[INFO] Launching Multiplex Solar Simulator..."

# Unlike Windows' pythonw, a normal Linux launch keeps a terminal attached
# by default, which is useful for a lab tool -- crashes are visible
# immediately rather than silent. We also tee everything to a timestamped
# log file so a session can be reviewed after the fact (e.g. if a sweep
# had unexpected results and you want to check for WARNING/ERROR lines).
if [ "$1" = "--no-log" ]; then
    shift
    "$PYEXE" -u main.py "$@"
else
    mkdir -p logs
    LOGFILE="logs/run_$(date +%Y%m%d_%H%M%S).log"
    echo "[INFO] Logging this session to $LOGFILE"
    "$PYEXE" -u main.py "$@" 2>&1 | tee "$LOGFILE"
fi
