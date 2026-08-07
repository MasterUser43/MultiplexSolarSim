"""
Confirms JVController satisfies the MeasurementMode protocol.
"""
from unittest.mock import Mock

from controllers.jv_controller import JVController
from controllers.measurement_mode import MeasurementMode


def _make_controller():
    config_panel = Mock()
    # JVController.__init__ now calls _update_path_preview() once (dataset
    # card / auto-save toggle wiring), which reads these.
    config_panel.autosave_table_enabled.return_value = False
    config_panel.autosave_curves_enabled.return_value = False
    config_panel.get_selected_pixels.return_value = []
    config_panel.sample_name.return_value = "sample"

    return JVController(
        instrument_manager=Mock(),
        exporter=Mock(),
        config_panel=config_panel,
        plot_panel=Mock(),
        results_panel=Mock(),
        log_fn=Mock(),
        get_sample_name=Mock(return_value="sample"),
        tabs=Mock(),
        sweep_tab_index=1,
        parent_widget=Mock(),
    )


def test_jv_controller_satisfies_measurement_mode():
    controller = _make_controller()
    assert isinstance(controller, MeasurementMode)


def test_set_output_dir_writes_to_exporter():
    controller = _make_controller()
    controller.set_output_dir("/tmp/some/output")
    assert controller.exporter.output_dir == "/tmp/some/output"


def test_state_is_shared_sweep_state_instance():
    controller = _make_controller()
    # Not part of the protocol check itself, but pins down that `state`
    # is a real SweepState (not e.g. a plain dict) so future Enaml views
    # can rely on its ContainerList/Atom-observe behavior.
    from core.sweep_state import SweepState
    assert isinstance(controller.state, SweepState)
