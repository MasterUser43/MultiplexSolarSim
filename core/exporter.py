"""
Handles building output paths and writing per-pixel TXT files and the
summary results table. Pure I/O.
"""
import os
import time

import numpy as np


class ResultsExporter:
    def __init__(self, output_dir, sample_name="Sample", logger=None):
        self.output_dir = output_dir
        self.sample_name = sample_name
        self.logger = logger or (lambda msg: None)

    @staticmethod
    def safe_filename_part(text):
        allowed = []
        for ch in text:
            if ch.isalnum() or ch in ("-", "_"):
                allowed.append(ch)
            elif ch in (" ", ".", "/"):
                allowed.append("_")
        return "".join(allowed).strip("_") or "solar_iv_data"

    def build_daily_output_dir(self):
        date_folder = time.strftime("%Y%m%d")
        path = os.path.abspath(os.path.join(self.output_dir, date_folder))
        os.makedirs(path, exist_ok=True)
        return path

    def _basename(self):
        basename = os.path.basename((self.sample_name or "").strip() or "solar_iv_data")
        root, ext = os.path.splitext(basename)
        if ext:
            basename = root
        return self.safe_filename_part(basename)

    def build_txt_path(self, row, timestamp):
        basename = self._basename()
        pixel = self.safe_filename_part(str(row["pixel"]))
        loop = int(row.get("loop", 1))
        filename = f"{basename}_pixel_{pixel}_loop_{loop}_{timestamp}.txt"
        return os.path.join(self.build_daily_output_dir(), filename)

    def build_results_table_path(self, timestamp):
        basename = self._basename()
        filename = f"{basename}_results_{timestamp}.txt"
        return os.path.join(self.build_daily_output_dir(), filename)

    def save_results_table(self, results, timestamp):
        path = self.build_results_table_path(timestamp)
        rows = sorted(
            results,
            key=lambda row: (int(row.get("loop", 1)), int(row.get("channel", 0))),
        )

        with open(path, "w") as f:
            f.write(
                "# loop\tpixel\tarea_cm2\tVoc_V\tJsc_mA_cm2\tFF\t"
                "PCE_percent\tVmpp_V\tJmp_mA_cm2\tPmax_mW_cm2\t"
                "Rs_diode_eq_ohm\tRsh_diode_eq_ohm\tRs_derivative_ohm\tRsh_derivative_ohm\t"
                "status\n"
            )
            for row in rows:
                f.write(
                    f"{int(row.get('loop', 1))}\t"
                    f"{row['pixel']}\t"
                    f"{row['area_cm2']:.8g}\t"
                    f"{row['Voc']:.8g}\t"
                    f"{row['Jsc']:.8g}\t"
                    f"{row['FF']:.8g}\t"
                    f"{row['PCE']:.8g}\t"
                    f"{row['Vmpp']:.8g}\t"
                    f"{row['Jmpp']:.8g}\t"
                    f"{row['Pmax']:.8g}\t"
                    f"{row.get('Rs_diode_eq', float('nan')):.8g}\t"
                    f"{row.get('Rsh_diode_eq', float('nan')):.8g}\t"
                    f"{row.get('Rs_derivative', float('nan')):.8g}\t"
                    f"{row.get('Rsh_derivative', float('nan')):.8g}\t"
                    "OK\n"
                )
        return path

    def save_results(self, results, auto=False):
        if not results:
            self.logger("No results to save")
            return

        timestamp = time.strftime("%H%M%S")
        saved_paths = []

        try:
            for row in results:
                path = self.build_txt_path(row, timestamp)
                V = np.asarray(row["voltage_v"], dtype=float)
                I = np.asarray(row["current_a"], dtype=float)
                J = (I / row["area_cm2"]) * 1000

                with open(path, "w") as f:
                    f.write("# voltage_v\tcurrent_density_mA_cm2\n")
                    for voltage, current_density in zip(V, J):
                        f.write(f"{voltage:.8g}\t{current_density:.8g}\n")
                saved_paths.append(path)

            self.save_results_table(results, timestamp)

            mode = "Auto-saved" if auto else "Saved"
            folder = self.build_daily_output_dir()
            self.logger(
                f"{mode} {len(saved_paths)} JV text file(s) and "
                f"1 results table file to {folder}"
            )
        except Exception as e:
            self.logger(f"ERROR: could not save TXT files: {e}")
