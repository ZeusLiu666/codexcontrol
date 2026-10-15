"""Keyboard navigation of virtual account controls in the scrolling Canvas."""
import unittest
from unittest.mock import Mock

import test_dashboard_ui as fixtures


class DashboardKeyboardTests(unittest.TestCase):
    def setUp(self):
        self.fixture = fixtures.DashboardTests(methodName='runTest')
        self.addCleanup(self.fixture.doCleanups)
        self.fixture.setUp()
        self.addCleanup(self.fixture.tearDown)
        self.app, self.scene = self.fixture.app, self.fixture.app.card_scene

    def test_keyboard_focus_scrolls_hidden_account_into_view(self):
        key = (self.app.accounts[-1].id, 'details')
        self.assertTrue(self.scene.focus_region(key))
        self.fixture.pump(.04)
        region = next(r for r in self.scene.regions if r.key == key)
        top = region.rect[1] - self.app.canvas.canvasy(0)
        self.assertGreaterEqual(top, 0)
        self.assertLessEqual(region.rect[3] - self.app.canvas.canvasy(0), self.app.canvas.winfo_height())
        self.assertEqual(self.scene.focus_key, key)

    def test_expansion_keeps_virtual_focus_and_restart_disables_removal(self):
        account = self.app.accounts[1]
        key = (account.id, 'details')
        self.scene.focus_region(key)
        self.app.canvas.focus_force()
        self.fixture.pump(.04)
        self.app.canvas.event_generate('<KeyPress-Return>')
        self.app.canvas.event_generate('<KeyRelease-Return>')
        self.fixture.pump(.12)
        self.assertEqual(self.app.selected_account_id, account.id)
        self.assertEqual(self.scene.focus_key, key)
        self.assertIs(self.app.root.focus_get(), self.app.canvas)
        self.app._desktop_restart_busy = True
        self.app._render_now()
        self.fixture.pump(.04)
        remove = next(r for r in self.scene.regions if r.key == (account.id, 'trash'))
        self.assertFalse(remove.enabled)
        self.app.remove_account = Mock()
        self.scene.invoke(remove.key)
        self.assertFalse(self.scene.focus_region(remove.key))
        self.app.remove_account.assert_not_called()


if __name__ == '__main__':
    unittest.main()
