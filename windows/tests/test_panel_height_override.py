"""Height-animation primitives tested without app imports or visible windows."""
import tkinter as tk
import unittest
from unittest.mock import patch

from codexcontrol_windows.ui_components import RoundedPanel


class PanelHeightOverrideTests(unittest.TestCase):
    def setUp(self):
        self.root = tk.Tk()
        self.root.withdraw()
        self.errors = []
        self.root.report_callback_exception = lambda *args: self.errors.append(args)
        self.panel = RoundedPanel(self.root, width=260, padding=10)
        self.panel.pack(fill='x')
        self.content = tk.Frame(self.panel.inner, width=220, height=180)
        self.content.pack()
        self.root.update_idletasks()

    def tearDown(self):
        self.root.destroy()
        self.assertFalse(self.errors, self.errors)

    def test_override_clips_surface_without_squeezing_content_and_restores(self):
        natural = self.panel.inner.winfo_reqheight() + 2*self.panel.pad_y
        self.assertEqual(200, natural)
        self.panel.set_height_override(64)
        self.root.update_idletasks()
        self.assertEqual(64, self.panel.canvas.winfo_reqheight())
        self.assertEqual(64, self.panel._photo.height())
        self.assertEqual(180, self.panel.inner.winfo_reqheight())
        self.panel.set_height_override(None)
        self.root.update_idletasks()
        self.assertEqual(natural, self.panel.canvas.winfo_reqheight())
        self.assertEqual(natural, self.panel._photo.height())

    def test_content_changes_during_animation_use_latest_natural_height_on_restore(self):
        self.panel.set_height_override(50)
        self.root.update_idletasks()
        self.content.configure(height=260)
        self.root.update_idletasks()
        self.assertEqual(50, self.panel.canvas.winfo_reqheight())
        self.panel.set_height_override(None)
        self.root.update_idletasks()
        self.assertEqual(280, self.panel.canvas.winfo_reqheight())

    def test_override_stays_clipped_when_parent_allocates_extra_height(self):
        self.panel.pack_forget()
        self.panel.place(x=0, y=0, width=260, height=300)
        self.panel.set_height_override(64)
        self.root.update_idletasks()
        self.assertEqual(300, self.panel.winfo_height())
        self.assertEqual(64, self.panel.canvas.winfo_height())
        self.assertEqual(180, self.panel.inner.winfo_reqheight())
        self.panel.set_height_override(None)
        self.root.update_idletasks()
        self.assertEqual(300, self.panel.canvas.winfo_height())

    def test_expansion_attaches_full_background_before_any_height_request(self):
        observed_requests = []
        panel_configure = self.panel.configure
        canvas_configure = self.panel.canvas.configure

        def watch(original):
            def configure(*args, **kwargs):
                if 'height' in kwargs:
                    requested = int(kwargs['height'])
                    observed_requests.append(requested)
                    self.assertGreaterEqual(self.panel._photo.height(), requested)
                    self.assertEqual(str(self.panel._photo), self.panel.canvas.itemcget(self.panel._image_item, 'image'))
                return original(*args, **kwargs)
            return configure

        with patch.object(self.panel, 'configure', side_effect=watch(panel_configure)), \
             patch.object(self.panel.canvas, 'configure', side_effect=watch(canvas_configure)):
            self.panel.set_height_override(460)
        self.assertEqual([460, 460], observed_requests)

    def test_replacing_surface_keeps_old_image_alive_until_new_image_is_attached(self):
        old_name = str(self.panel._photo)
        itemconfigure = self.panel.canvas.itemconfigure
        swaps = []

        def watch(item, *args, **kwargs):
            if item == self.panel._image_item and 'image' in kwargs:
                self.assertIn(old_name, self.root.tk.call('image', 'names'))
                swaps.append(str(kwargs['image']))
            return itemconfigure(item, *args, **kwargs)

        with patch.object(self.panel.canvas, 'itemconfigure', side_effect=watch):
            self.panel.set_height_override(240)
        self.assertEqual([str(self.panel._photo)], swaps)
        self.assertNotEqual(old_name, swaps[0])

    def test_many_updates_coalesce_and_zero_is_a_safe_minimum(self):
        self.panel.set_height_override(100)
        pending = self.panel._job
        for height in (80, 60, 40, 0):
            self.panel.set_height_override(height)
            self.assertEqual(pending, self.panel._job)
        self.root.update_idletasks()
        self.assertEqual(1, self.panel.canvas.winfo_reqheight())
        self.assertEqual(1, self.panel._photo.height())
        self.assertIsNone(self.panel._job)

    def test_destroy_cancels_pending_animation_layout_and_late_updates_are_safe(self):
        self.panel.set_height_override(70)
        pending = self.panel._job
        self.assertIsNotNone(pending)
        self.panel.destroy()
        self.assertNotIn(pending, self.root.tk.call('after', 'info'))
        self.panel.set_height_override(30)
        self.panel.set_height_override(None)
        self.root.update_idletasks()
        self.assertIsNone(self.panel._job)


if __name__ == '__main__':
    unittest.main()
