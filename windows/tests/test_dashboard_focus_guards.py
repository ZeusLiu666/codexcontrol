"""Virtual focus survives refresh without delayed native focus restoration."""
import unittest
from unittest.mock import Mock

import test_dashboard_ui as fixtures


class DashboardFocusGuardTests(unittest.TestCase):
    def setUp(self):
        self.fixture = fixtures.DashboardTests(methodName='runTest')
        self.addCleanup(self.fixture.doCleanups)
        self.fixture.setUp()
        self.addCleanup(self.fixture.tearDown)
        self.app, self.scene = self.fixture.app, self.fixture.app.card_scene

    def test_background_refresh_does_not_steal_external_focus_or_scroll(self):
        self.scene.focus_region((self.app.accounts[-1].id, 'details'))
        self.app.search_entry.focus_force()
        self.fixture.pump(.04)
        offset = self.app.canvas.canvasy(0)
        self.app._mark_runtime_dirty()
        self.app._render_now()
        self.fixture.pump(.12)
        self.assertIs(self.app.root.focus_get(), self.app.search_entry)
        self.assertAlmostEqual(self.app.canvas.canvasy(0), offset, delta=1)

    def test_latest_virtual_focus_is_preserved_across_refresh(self):
        old_key = (self.app.accounts[-1].id, 'details')
        new_key = (self.app.accounts[1].id, 'details')
        self.scene.focus_region(old_key)
        self.scene.focus_region(new_key)
        self.scene.invoke(new_key)
        self.app._mark_runtime_dirty()
        self.app._render_now()
        self.fixture.pump(.12)
        self.assertEqual(self.scene.focus_key, new_key)
        self.assertEqual(self.app.selected_account_id, self.app.accounts[1].id)
        region = next(r for r in self.scene.regions if r.key == new_key)
        self.assertLessEqual(region.rect[3]-self.app.canvas.canvasy(0), self.app.canvas.winfo_height())
        self.assertGreaterEqual(region.rect[1]-self.app.canvas.canvasy(0), 0)

    def test_filter_removes_stale_focus_and_recovery_does_not_restore_it(self):
        removed = (self.app.accounts[-1].id, 'details')
        self.scene.focus_region(removed)
        self.app.search_entry.focus_force()
        self.app.search_var.set('demo2')
        self.fixture.pump(.12)
        self.assertNotEqual(self.scene.focus_key, removed)
        self.assertFalse(self.scene.focus_region(removed))
        self.assertIs(self.app.root.focus_get(), self.app.search_entry)
        self.app.search_var.set('')
        self.fixture.pump(.12)
        self.assertNotEqual(self.scene.focus_key, removed)
        self.assertIs(self.app.root.focus_get(), self.app.search_entry)

    def test_collapsing_details_moves_virtual_focus_to_summary(self):
        account = self.app.accounts[0]
        token = next(r.key for r in self.scene.regions if r.key[:2] == (account.id, 'token'))
        self.scene.focus_region(token)
        self.scene.invoke((account.id, 'details'))
        self.fixture.pump(.04)
        self.assertEqual(self.scene.focus_key, (account.id, 'details'))
        self.assertIsNone(self.scene.tooltip._job)
        self.assertIsNone(self.scene.tooltip.window)
        self.assertEqual(self.scene.tooltip_for(token), '')

    def test_removed_action_cannot_invoke_a_stale_account_callback(self):
        account = self.app.accounts[0]
        refresh_key = (account.id, 'refresh')
        self.assertTrue(any(r.key == refresh_key for r in self.scene.regions))
        self.app.refresh_account = Mock()
        self.scene.invoke((account.id, 'details'))
        self.scene.invoke(refresh_key)
        self.assertFalse(self.scene.focus_region(refresh_key))
        self.app.refresh_account.assert_not_called()

    def test_keyboard_reentry_scrolls_virtual_focus_back_into_view(self):
        key = (self.app.accounts[-1].id, 'details')
        self.scene.focus_region(key)
        self.app.search_entry.focus_force()
        self.fixture.pump(.04)
        self.app.canvas.yview_moveto(0)
        self.app.canvas.focus_force()
        self.fixture.pump(.04)
        region = next(r for r in self.scene.regions if r.key == key)
        self.assertGreaterEqual(region.rect[1]-self.app.canvas.canvasy(0), 0)
        self.assertLessEqual(region.rect[3]-self.app.canvas.canvasy(0), self.app.canvas.winfo_height())

    def test_mouse_focus_does_not_scroll_before_button_release(self):
        self.scene.focus_region((self.app.accounts[-1].id, 'details'))
        self.app.search_entry.focus_force()
        self.fixture.pump(.04)
        self.app.canvas.yview_moveto(0)
        key = (self.app.accounts[0].id, 'details')
        region = next(r for r in self.scene.regions if r.key == key)
        x = round((region.rect[0]+region.rect[2])/2-self.app.canvas.canvasx(0))
        y = round((region.rect[1]+region.rect[3])/2-self.app.canvas.canvasy(0))
        offset = self.app.canvas.canvasy(0)
        self.app.canvas.event_generate('<ButtonPress-1>', x=x, y=y)
        self.fixture.pump(.04)
        self.assertAlmostEqual(self.app.canvas.canvasy(0), offset, delta=1)
        self.assertEqual(self.scene.focus_key, key)
        self.app.canvas.event_generate('<ButtonRelease-1>', x=x, y=y)
        self.fixture.pump(.04)
        self.assertIsNone(self.app.selected_account_id)


if __name__ == '__main__':
    unittest.main()
