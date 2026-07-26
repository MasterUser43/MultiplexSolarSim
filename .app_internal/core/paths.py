"""
Centralized path resolution.

Everything that used to derive its save location from sys.argv[0] or the
current working directory goes through here instead.
"""
import os

# .app_internal/core/paths.py -> .app_internal/core -> .app_internal -> root
_THIS_FILE = os.path.abspath(__file__)
_APP_INTERNAL_DIR = os.path.dirname(os.path.dirname(_THIS_FILE))
_PROJECT_ROOT = os.path.dirname(_APP_INTERNAL_DIR)


def get_project_root():
    """Absolute path to the MultiplexSolarSim folder."""
    return _PROJECT_ROOT


def get_data_dir():
    """Top-level data/ folder for JV results, exported TXT/CSV, and plot images.
    Created on first use if it doesn't exist yet."""
    path = os.path.join(_PROJECT_ROOT, "data")
    os.makedirs(path, exist_ok=True)
    return path


def get_logs_dir():
    """Top-level logs/ folder for exported System Event Log files.
    Shares its name with the terminal-output logs/ folder the launcher
    scripts already create, so all logs live in one place."""
    path = os.path.join(_PROJECT_ROOT, "logs")
    os.makedirs(path, exist_ok=True)
    return path
