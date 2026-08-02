"""
One full JV sweep: validates inputs, starts/stops the
MeasurementWorker, routes its signals into the plot/results panels, and
handles the JV-specific exports (per-pixel TXT, results table, PNG, CSV).
"""
import os
import time

import numpy as np
from PySide6.QtCore import QObject, Signal
from PySide6.QtWidgets import QFileDialog

from controllers.jv_worker import MeasurementWorker
from core.sweep_state import SweepState
from gui.formatting import format_metric

_METRIC_KEYS = (
    "Voc", "Jsc", "Vmpp", "Jmpp", "Pmax", "FF", "PCE",
    "Rs_diode_eq", "Rsh_diode_eq", "Rs_derivative", "Rsh_derivative",
)


class JVController(QObject):

    def __init__(
        self,
        instrument_manager,
        exporter,
        config_panel,
        plot_panel,
        results_panel,
        log_fn,
        get_sample_name,
        tabs,
        sweep_tab_index,
        parent_widget,
        parent=None,
    ):
        super().__init__(parent)
        self.inst = instrument_manager
        self.exporter = exporter
        self.config_panel = config_panel
        self.plot_panel = plot_panel
        self.results_panel = results_panel
        self.log = log_fn
        self.get_sample_name = get_sample_name
        self.tabs = tabs
        self.sweep_tab_index = sweep_tab_index
        self.parent_widget = parent_widget

        self.results = []
        self.worker = None
        self.state = SweepState()  # Atom mirror of the signals below, for Enaml views

        self.plot_panel.set_logger(self.log)
        self.config_panel.observe("run_requested", lambda change: self.run_measurement())
        self.plot_panel.observe("abort_requested", lambda change: self.abort_measurement())
        self.plot_panel.observe("export_png_requested", lambda change: self.export_plot_png())
        self.results_panel.observe("export_txt_requested", lambda change: self.save_results(auto=False))
        self.results_panel.observe("export_csv_requested", lambda change: self.export_results_csv())

        # Dataset card (Name/Auto-Save/pixel-selection) drives the live
        # path-preview strip.
        self.config_panel.observe("name_changed", self._update_path_preview)
        self.config_panel.observe("auto_save_toggled", self._update_path_preview)
        self.config_panel.observe("layout_changed", self._update_path_preview)

        # Nothing to export yet at startup.
        self.results_panel.set_export_enabled(False)
        self._update_path_preview()

    # --- Sweep lifecycle ---

    def validate(self):
        if not self.inst.keithley:
            self.log("ERROR: instruments are not connected")
            return False

        selected = self.config_panel.get_selected_pixels()
        needs_relay = any(channel is not None for _pixel, channel, _area in selected)
        if needs_relay and not self.inst.relay:
            self.log("ERROR: instruments are not connected")
            return False

        err = self.config_panel.validate()
        if err:
            self.log(err)
            return False
        return True

    def run_measurement(self):
        if not self.validate():
            self.tabs.setCurrentIndex(0)
            return

        if self.worker is not None and self.worker.isRunning():
            self.log("ERROR: a sweep is already running")
            return

        selected = self.config_panel.get_selected_pixels()
        if not selected:
            self.log("ERROR: select at least one pixel")
            return

        self.results = []
        self.state.results = []
        self.state.faults = []
        self.results_panel.clear()
        self.results_panel.set_export_enabled(False)
        self.plot_panel.reset_for_new_run()

        sweep_params = self.config_panel.get_sweep_params()
        self.plot_panel.prepare_legends(selected, sweep_params["loops"])
        self._set_running(True)

        # Pass the active hardware connections to the background thread.
        # To prevent connection conflicts and crashes, do not command or
        # query the instruments from this GUI thread while the sweep runs.
        self.worker = MeasurementWorker(self.inst.keithley, self.inst.relay, selected, sweep_params)
        self.worker.log.connect(self._on_log)
        self.worker.pixel_started.connect(self._on_pixel_started)
        self.worker.pixel_result.connect(self._on_pixel_result)
        self.worker.pixel_faulted.connect(self._on_pixel_faulted)
        self.worker.finished_sweep.connect(self._on_sweep_finished)
        self.worker.progress_update.connect(self._on_progress_update)
        self.tabs.setCurrentIndex(self.sweep_tab_index)
        self.worker.start()

    def abort_measurement(self):
        if self.worker is not None and self.worker.isRunning():
            self.worker.request_abort()
            self.log("Abort requested")

    def _set_running(self, running):
        self.state.running = running
        self.config_panel.set_running(running)
        self.plot_panel.set_running(running)

    # --- Worker signal slots ---

    def _on_log(self, message):
        self.state.log_lines.append(message)
        self.log(message)

    def _on_pixel_started(self, pixel):
        self.state.active_pixel = pixel
        self.plot_panel.set_active_pixel(pixel)
        self._update_path_preview()

    def _on_pixel_result(self, record):
        self.results.append(record)
        self.state.results.append(record)
        V = np.asarray(record["voltage_v"], dtype=float)
        J = np.asarray(record["current_density_ma_cm2"], dtype=float)
        self.plot_panel.plot_curve(V, J, record["channel"], record["loop"])

        metrics = {k: record[k] for k in _METRIC_KEYS}
        self.results_panel.add_result_row(record["pixel"], record["area_cm2"], metrics, "OK", record["loop"])

        self.plot_panel.set_active_pixel(record["pixel"])
        self.plot_panel.set_hud_metrics(
            format_metric(metrics["Voc"], 3),
            format_metric(metrics["Jsc"], 2),
            format_metric(metrics["PCE"], 2),
            format_metric(metrics["FF"], 2),
        )

    def _on_pixel_faulted(self, pixel, area, fault, loop_number):
        self.state.faults.append(
            {"pixel": pixel, "area": area, "fault": fault, "loop": loop_number}
        )
        self.results_panel.add_result_row(pixel, area, None, fault, loop_number)

    def _on_sweep_finished(self, aborted, had_error):
        self.state.finished_aborted = aborted
        self.state.finished_had_error = had_error
        self.state.finish_count += 1
        self.state.active_pixel = "--"

        self.plot_panel.set_active_pixel("--")
        self._set_running(False)

        if aborted:
            self.log("Sweep aborted")
        elif had_error:
            self.log("Sweep ended with an error")
        else:
            self.log("Sweep complete")

        # Auto-saving after every completed run with results is preserved,
        # gated behind the Enable Auto-Save checkbox.
        if self.results:
            if self.config_panel.auto_save_enabled():
                self.save_results(auto=True)
            else:
                self.log("Results kept in memory -- export from the Results tab when ready")

        self.results_panel.set_export_enabled(bool(self.results))
        self._update_path_preview()

    def _on_progress_update(self, percent, text):
        self.state.progress_percent = percent
        self.state.progress_text = text

    # --- Output directory / exports ---

    def set_output_dir(self, path):
        self.exporter.output_dir = path
        self._update_path_preview()

    def _update_path_preview(self, change=None):
        """Live preview of where the next auto-saved file will land, or a
        warning telling the researcher they'll need to export manually."""
        panel = self.config_panel

        if not panel.auto_save_enabled():
            panel.set_path_preview(
                "\u26A0\uFE0F Auto-save disabled. Use the \"Results\" tab to "
                "manually export raw curves (.txt) and results table (.csv) "
                "once the sweep completes.",
                is_warning=True,
            )
            return

        active = self.state.active_pixel
        pixel = active if active and active != "--" else None
        if pixel is None:
            selected = panel.get_selected_pixels()
            pixel = selected[0][0] if selected else None

        if pixel is None:
            panel.set_path_preview("Select at least one pixel to preview the save path.", is_warning=False)
            return

        self.exporter.sample_name = panel.sample_name() or "solar_iv_data"
        path = self.exporter.preview_txt_path(pixel)
        panel.set_path_preview(f"Auto-saving to: {path}", is_warning=False)

    def save_results(self, auto=False):
        if not self.results:
            if not auto:
                self.log("WARNING: No results to save")
            return

        self.exporter.sample_name = self.get_sample_name() or "solar_iv_data"

        if not auto:
            chosen_dir = QFileDialog.getExistingDirectory(
                self.parent_widget, "Choose Folder to Save TXT Results", self.exporter.output_dir,
                QFileDialog.ShowDirsOnly | QFileDialog.DontResolveSymlinks
            )
            if not chosen_dir:
                return  # user cancelled
            self.exporter.output_dir = chosen_dir

        self.exporter.save_results(self.results, auto=auto)

    def export_plot_png(self):
        try:
            import pyqtgraph.exporters

            self.exporter.sample_name = self.get_sample_name() or "solar_iv_data"
            folder = self.exporter.build_daily_output_dir()
            timestamp = time.strftime("%H%M%S")
            basename = self.exporter._basename()
            suggested_path = os.path.join(folder, f"{basename}_ivcurve_{timestamp}.png")

            path, _ = QFileDialog.getSaveFileName(
                self.parent_widget, "Export IV Curve Image", suggested_path, "PNG Image (*.png)"
            )
            if not path:
                return  # user cancelled

            image_exporter = pyqtgraph.exporters.ImageExporter(self.plot_panel.plot_manager.plot.getPlotItem())
            image_exporter.parameters()["width"] = 1600
            image_exporter.export(path)
            self.log(f"OK: Exported plot image to {path}")
        except Exception as e:
            self.log(f"ERROR: could not export plot image: {e}")

    def export_results_csv(self):
        if not self.results_panel.has_rows():
            self.log("WARNING: No results to export")
            return

        try:
            import csv

            self.exporter.sample_name = self.get_sample_name() or "solar_iv_data"
            folder = self.exporter.build_daily_output_dir()
            timestamp = time.strftime("%H%M%S")
            basename = self.exporter._basename()
            suggested_path = os.path.join(folder, f"{basename}_results_{timestamp}.csv")

            path, _ = QFileDialog.getSaveFileName(
                self.parent_widget, "Export Results CSV", suggested_path, "CSV File (*.csv)"
            )
            if not path:
                return  # user cancelled

            headers, rows = self.results_panel.get_export_data()
            with open(path, "w", newline="") as f:
                writer = csv.writer(f)
                writer.writerow(headers)
                for row in rows:
                    writer.writerow(row)
            self.log(f"OK: Exported {len(rows)} row(s) to {path}")
        except Exception as e:
            self.log(f"ERROR: could not export CSV: {e}")
