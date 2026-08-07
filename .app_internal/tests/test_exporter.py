"""
Tests for the auto-save manifest/raw_curves backend (core/exporter.py).

Uses a real temp directory and real file I/O.
"""
import csv
import os

import pytest

from core.exporter import ResultsExporter, MANIFEST_FILENAME, RAW_CURVES_SUBDIR


def _make_record(pixel="A", loop=1, area=0.0396):
    return {
        "pixel": pixel, "loop": loop, "area_cm2": area,
        "voltage_v": [0.0, 0.1, 0.2], "current_density_ma_cm2": [10.0, 8.0, 5.0],
        "Voc": 0.706, "Jsc": 277.7, "FF": 0.727, "PCE": 14.3,
        "Vmpp": 0.552, "Jmpp": 258.4, "Pmax": 142.7,
        "Rs_diode_eq": 2.0, "Rsh_diode_eq": 5000.0,
        "Rs_derivative": 3.2, "Rsh_derivative": 5001.6,
    }


def _save_pixel_now(exp, record):
    """save_curve_now()+save_table_row_now() together."""
    curve_path, curve_filename = exp.save_curve_now(record)
    exp.save_table_row_now(record, curve_filename)
    return curve_path


def test_raw_curves_dir_and_manifest_path(tmp_path):
    exp = ResultsExporter(str(tmp_path), sample_name="Sample_A")
    assert exp.raw_curves_dir() == os.path.join(str(tmp_path), RAW_CURVES_SUBDIR)
    assert os.path.isdir(exp.raw_curves_dir())  # create=True by default
    assert exp.manifest_path() == os.path.join(str(tmp_path), MANIFEST_FILENAME)


def test_preview_txt_path_no_disk_side_effects(tmp_path):
    exp = ResultsExporter(str(tmp_path), sample_name="Sample_A")
    preview = exp.preview_txt_path("A", loop=1)
    assert "raw_curves" in preview
    assert "Sample_A_pixel_A_loop_1_JV.txt" in preview
    # must not have created raw_curves/ just from previewing
    assert not os.path.isdir(os.path.join(str(tmp_path), RAW_CURVES_SUBDIR))


def test_save_pixel_now_writes_raw_curve_and_manifest_row(tmp_path):
    exp = ResultsExporter(str(tmp_path), sample_name="Sample_A")
    path = _save_pixel_now(exp, _make_record(pixel="A", loop=1))

    assert os.path.isfile(path)
    assert path == os.path.join(exp.raw_curves_dir(), "Sample_A_pixel_A_loop_1_JV.txt")
    with open(path) as f:
        content = f.read()
    assert "voltage_v" in content
    assert "0.1\t8" in content  # a real data row made it to disk

    with open(exp.manifest_path(), newline="") as f:
        rows = list(csv.reader(f))
    assert rows[0][:5] == ["timestamp", "sample_name", "loop", "pixel", "area_cm2"]
    assert rows[1][1] == "Sample_A"
    assert rows[1][3] == "A"
    assert rows[1][-1] == "Sample_A_pixel_A_loop_1_JV.txt"  # raw_curve_file column


def test_save_pixel_now_appends_without_rewriting_header(tmp_path):
    exp = ResultsExporter(str(tmp_path), sample_name="Sample_A")
    _save_pixel_now(exp, _make_record(pixel="A", loop=1))
    _save_pixel_now(exp, _make_record(pixel="B", loop=1))

    with open(exp.manifest_path(), newline="") as f:
        rows = list(csv.reader(f))
    assert len(rows) == 3  # header + 2 data rows, not 2 separate headers
    assert rows[1][3] == "A"
    assert rows[2][3] == "B"


def test_save_pixel_now_safe_overwrite_on_collision(tmp_path):
    """Re-running w/o changing the Name field."""
    exp = ResultsExporter(str(tmp_path), sample_name="Sample_A")
    path1 = _save_pixel_now(exp, _make_record(pixel="A", loop=1))
    path2 = _save_pixel_now(exp, _make_record(pixel="A", loop=1))

    assert path1 != path2
    assert os.path.isfile(path1)
    assert os.path.isfile(path2)
    assert "_(001)" in path2

    # both manifest rows still present.
    with open(exp.manifest_path(), newline="") as f:
        rows = list(csv.reader(f))
    assert len(rows) == 3


def test_preview_matches_actual_save_path_including_safe_overwrite(tmp_path):
    """The live preview should show the REAL eventual filename, including
    the safe-overwrite suffix."""
    exp = ResultsExporter(str(tmp_path), sample_name="Sample_A")
    _save_pixel_now(exp, _make_record(pixel="A", loop=1))

    preview = exp.preview_txt_path("A", loop=1)
    assert "_(001)" in preview

    actual = _save_pixel_now(exp, _make_record(pixel="A", loop=1))
    assert preview == actual


def test_save_curve_now_alone_does_not_touch_manifest(tmp_path):
    """Curves-only autosave (table checkbox off): raw curve file written,
    manifest never created."""
    exp = ResultsExporter(str(tmp_path), sample_name="Sample_A")
    curve_path, filename = exp.save_curve_now(_make_record(pixel="A", loop=1))

    assert os.path.isfile(curve_path)
    assert filename == "Sample_A_pixel_A_loop_1_JV.txt"
    assert not os.path.exists(exp.manifest_path())


def test_save_table_row_now_alone_does_not_touch_raw_curves(tmp_path):
    """Table-only autosave (curves checkbox off)"""
    exp = ResultsExporter(str(tmp_path), sample_name="Sample_A")
    exp.save_table_row_now(_make_record(pixel="A", loop=1))

    with open(exp.manifest_path(), newline="") as f:
        rows = list(csv.reader(f))
    assert rows[1][3] == "A"
    assert rows[1][-1] == ""  # raw_curve_file left blank -- no curve was saved
    assert not os.path.isdir(os.path.join(str(tmp_path), RAW_CURVES_SUBDIR))


def test_manual_export_uses_raw_curves_folder_like_autosave(tmp_path):
    """Export .TXT (save_results) now writes curve files into raw_curves/"""
    exp = ResultsExporter(str(tmp_path), sample_name="Sample_A")
    row = {**_make_record(pixel="A", loop=1), "current_a": [0.001, 0.0008, 0.0005]}
    exp.save_results([row], auto=True)

    curves_dir = exp.raw_curves_dir(create=False)
    assert os.path.isdir(curves_dir)
    assert os.path.isfile(os.path.join(curves_dir, "Sample_A_pixel_A_loop_1_JV.txt"))

    # results table under output_dir, not raw_curves/
    top_level_files = [
        f for f in os.listdir(str(tmp_path))
        if os.path.isfile(os.path.join(str(tmp_path), f))
    ]
    assert any(f.endswith(".txt") and "results" in f for f in top_level_files)

    # manual export must NOT touch the auto-save manifest
    assert not os.path.exists(exp.manifest_path())


def test_manual_export_collides_safely_with_existing_autosaved_curve(tmp_path):
    """A manual Export .TXT for a pixel/loop that was already auto-saved
    gets the same _(001) collision suffix as a second auto-save would"""
    exp = ResultsExporter(str(tmp_path), sample_name="Sample_A")
    record = _make_record(pixel="A", loop=1)
    exp.save_curve_now(record)  # simulate an earlier auto-saved curve

    row = {**record, "current_a": [0.001, 0.0008, 0.0005]}
    exp.save_results([row], auto=False)

    curves_dir = exp.raw_curves_dir(create=False)
    files = sorted(os.listdir(curves_dir))
    assert files == ["Sample_A_pixel_A_loop_1_JV.txt", "Sample_A_pixel_A_loop_1_JV_(001).txt"]

