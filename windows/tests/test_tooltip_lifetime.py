"""Tooltip lifetime races; no native windows or account stores."""
import tkinter as tk
import unittest
from unittest.mock import Mock, patch

from codexcontrol_windows.ui_components import ToolTip


class TooltipLifetimeTests(unittest.TestCase):
    def setUp(self):
        self.target = Mock(master=None)
        self.target._control_tooltips = []
        self.target.bind.return_value = ''
        self.target.winfo_exists.return_value = True
        self.target.winfo_viewable.return_value = True
        self.target.winfo_rootx.return_value = 100
        self.target.winfo_rooty.return_value = 100
        self.target.winfo_width.return_value = 30
        self.target.winfo_height.return_value = 30
        self.tooltip = ToolTip(self.target, 'Switch account')
        self.window = Mock()
        self.window.winfo_exists.return_value = True
        self.canvas = Mock()
        self.canvas.bbox.return_value = (11, 8, 100, 24)
        for name, value in (('tk.Toplevel', self.window), ('tk.Canvas', self.canvas),
                            ('ImageTk.PhotoImage', object()), ('_surface', object())):
            patcher = patch('codexcontrol_windows.ui_components.' + name, return_value=value)
            patcher.start()
            self.addCleanup(patcher.stop)
        patcher = patch('codexcontrol_windows.ui_components._workarea_for_widget',
                        return_value=(0, 0, 1920, 1080))
        self.workarea = patcher.start()
        self.addCleanup(patcher.stop)

    def test_target_destroyed_during_idle_never_queries_its_geometry(self):
        self.window.update_idletasks.side_effect = lambda: setattr(
            self.target.winfo_exists, 'return_value', False)
        self.tooltip.show()
        self.workarea.assert_not_called()
        self.window.geometry.assert_not_called()
        self.window.destroy.assert_called_once()
        self.assertIsNone(self.tooltip.window)

    def test_popup_destroyed_during_idle_is_safely_cleared(self):
        self.window.update_idletasks.side_effect = lambda: setattr(
            self.window.winfo_exists, 'return_value', False)
        self.tooltip.show()
        self.workarea.assert_not_called()
        self.window.deiconify.assert_not_called()
        self.assertIsNone(self.tooltip.window)

    def test_idle_cancellation_does_not_resume_the_old_popup(self):
        self.window.update_idletasks.side_effect = self.tooltip.hide
        self.tooltip.show()
        self.workarea.assert_not_called()
        self.window.deiconify.assert_not_called()
        self.window.destroy.assert_called_once()
        self.assertIsNone(self.tooltip.window)

    def test_idle_replacement_is_not_hidden_by_old_callback(self):
        replacement = Mock()

        def replace():
            self.tooltip.hide()
            self.tooltip.window = replacement

        self.window.update_idletasks.side_effect = replace
        self.tooltip.show()
        self.workarea.assert_not_called()
        self.window.deiconify.assert_not_called()
        replacement.destroy.assert_not_called()
        self.assertIs(replacement, self.tooltip.window)

    def test_geometry_and_workarea_tcl_errors_close_owned_popup(self):
        for location in ('workarea', 'geometry'):
            with self.subTest(location=location):
                self.window.reset_mock()
                self.workarea.side_effect = tk.TclError('bad window path') if location == 'workarea' else None
                self.window.geometry.side_effect = tk.TclError('bad window path') if location == 'geometry' else None
                self.tooltip.show()
                self.window.destroy.assert_called_once()
                self.window.deiconify.assert_not_called()
                self.assertIsNone(self.tooltip.window)

    def test_canvas_region_anchor_places_tooltip_above_its_exact_screen_rectangle(self):
        self.tooltip.anchor_rect = lambda: (300, 200, 338, 224)
        self.tooltip.show()
        self.workarea.assert_called_once_with(self.target, (300, 200, 338, 224))
        self.window.geometry.assert_called_once_with('111x32+263+161')
        self.window.deiconify.assert_called_once()

    def test_removed_or_scrolled_out_region_does_not_open_a_tooltip(self):
        self.tooltip.anchor_rect = lambda: None
        self.tooltip.show()
        self.workarea.assert_not_called()
        self.window.deiconify.assert_not_called()
        self.window.destroy.assert_called_once()
        self.assertIsNone(self.tooltip.window)


if __name__ == '__main__':
    unittest.main()
