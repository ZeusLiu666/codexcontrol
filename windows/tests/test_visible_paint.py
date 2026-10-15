"""Visible native paint invalidation without a display or account store."""
import tkinter as tk
import unittest
from unittest.mock import patch

from codexcontrol_windows.ui_components import RoundedPanel


class Widget:
    def __init__(self, name, rectangle, *, parent=None, mapped=True, log=None):
        self.name = name
        self.rectangle = rectangle
        self.master = parent
        self.mapped = mapped
        self.exists = True
        self.children = []
        self.log = log if log is not None else parent.log if parent else []
        self.on_expose = None
        if parent:
            parent.children.append(self)

    def winfo_exists(self):
        return self.exists

    def winfo_ismapped(self):
        return self.mapped

    def winfo_rootx(self):
        return self.rectangle[0]

    def winfo_rooty(self):
        return self.rectangle[1]

    def winfo_width(self):
        return self.rectangle[2] - self.rectangle[0]

    def winfo_height(self):
        return self.rectangle[3] - self.rectangle[1]

    def winfo_children(self):
        return self.children

    def event_generate(self, event, **kwargs):
        self.log.append((self.name, event, kwargs))
        if self.on_expose:
            self.on_expose()


class Panel(Widget):
    flush_visible_paint = RoundedPanel.flush_visible_paint

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._destroyed = False
        self._paint_flush_running = False
        self.flush_count = 0
        self.on_flush = None
        self.canvas = Widget('canvas', self.rectangle, parent=self)

    def update_idletasks(self):
        self.flush_count += 1
        if self.on_flush:
            self.on_flush()


class VisiblePaintTests(unittest.TestCase):
    def test_native_queue_is_flushed_before_explicit_tk_expose(self):
        panel = Panel('panel', (0, 0, 100, 100))
        order = []
        panel.canvas.on_expose = lambda: order.append('tk')
        with patch('codexcontrol_windows.ui_components.flush_native_paint',
                   side_effect=lambda widget: order.append('native')) as native:
            self.assertEqual(1, panel.flush_visible_paint())
        native.assert_called_once_with(panel.canvas)
        self.assertEqual(['native', 'tk'], order)

    def test_visible_subtree_receives_explicit_clipped_rectangles_before_one_flush(self):
        panel = Panel('panel', (10, 20, 110, 120))
        inner = Widget('inner', (15, 25, 105, 225), parent=panel.canvas)
        Widget('visible', (20, 30, 80, 50), parent=inner)
        Widget('partial', (20, 100, 100, 150), parent=inner)
        Widget('below', (20, 160, 100, 190), parent=inner)
        Widget('hidden', (20, 30, 80, 50), parent=inner, mapped=False)

        self.assertEqual(4, panel.flush_visible_paint())
        self.assertEqual(['canvas', 'inner', 'visible', 'partial'], [x[0] for x in panel.log])
        self.assertEqual({'x': 0, 'y': 0, 'width': 80, 'height': 20,
                          'count': 0, 'when': 'now'}, panel.log[-1][2])
        self.assertTrue(all(event == '<Expose>' for _, event, _ in panel.log))
        self.assertEqual(1, panel.flush_count)
        self.assertFalse(panel._paint_flush_running)

    def test_parent_viewport_clips_left_top_and_bottom(self):
        viewport = Widget('viewport', (30, 50, 90, 90))
        panel = Panel('panel', (10, 20, 110, 120), parent=viewport)
        Widget('inner', (10, 20, 110, 220), parent=panel.canvas)
        self.assertEqual(2, panel.flush_visible_paint())
        for _, _, rectangle in panel.log:
            self.assertEqual({'x': 20, 'y': 30, 'width': 60, 'height': 40,
                              'count': 0, 'when': 'now'}, rectangle)

    def test_reentrant_requests_do_not_dispatch_more_paint(self):
        panel = Panel('panel', (0, 0, 100, 100))
        nested = []
        panel.canvas.on_expose = lambda: nested.append(panel.flush_visible_paint())
        panel.on_flush = lambda: nested.append(panel.flush_visible_paint())
        self.assertEqual(1, panel.flush_visible_paint())
        self.assertEqual([0, 0], nested)
        self.assertEqual(1, panel.flush_count)

    def test_destroyed_unmapped_or_fully_clipped_do_not_flush(self):
        for case in ('destroyed', 'unmapped', 'ancestor_unmapped', 'clipped'):
            with self.subTest(case=case):
                viewport = Widget('viewport', (0, 0, 100, 100))
                panel = Panel('panel', (0, 0, 100, 100), parent=viewport)
                if case == 'destroyed':
                    panel._destroyed = True
                elif case == 'unmapped':
                    panel.mapped = False
                elif case == 'ancestor_unmapped':
                    viewport.mapped = False
                else:
                    viewport.rectangle = (200, 200, 300, 300)
                self.assertEqual(0, panel.flush_visible_paint())
                self.assertEqual(0, panel.flush_count)
                self.assertEqual([], panel.log)
                self.assertFalse(panel._paint_flush_running)

    def test_retired_widget_during_idle_flush_resets_guard(self):
        panel = Panel('panel', (0, 0, 100, 100))

        def retire():
            panel._destroyed = True
            raise tk.TclError('application has been destroyed')

        panel.on_flush = retire
        self.assertEqual(1, panel.flush_visible_paint())
        self.assertFalse(panel._paint_flush_running)
        self.assertEqual(0, panel.flush_visible_paint())


if __name__ == '__main__':
    unittest.main()
