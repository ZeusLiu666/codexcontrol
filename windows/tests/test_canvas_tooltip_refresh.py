"""Stationary token tips retain exact values through asynchronous data refreshes."""
import unittest
import tkinter as tk

import test_dashboard_ui as fixtures


class CanvasTooltipRefreshTests(unittest.TestCase):
    def setUp(self):
        self.fixture = fixtures.DashboardTests(methodName='runTest')
        self.addCleanup(self.fixture.doCleanups)
        self.fixture.setUp()
        self.addCleanup(self.fixture.tearDown)
        self.app, self.scene = self.fixture.app, self.fixture.app.card_scene
        self.account = self.app.accounts[0]

    def _hover_token(self):
        region = next(r for r in self.scene.regions if r.key[:2] == (self.account.id, 'token'))
        self.scene.focus_region(region.key)
        self.fixture.pump(.01)
        self.scene.hide_tooltip()
        x1, y1, x2, y2 = region.rect
        self.app.canvas.event_generate('<Motion>', x=round((x1+x2)/2-self.app.canvas.canvasx(0)),
                                       y=round((y1+y2)/2-self.app.canvas.canvasy(0)))
        return region.key

    def _update_tokens(self, value):
        point = self.app.token_usage_states[self.account.id]['daily'][0]
        point['usage'] = dict(point['usage'], totalTokens=value)
        self.app._mark_runtime_dirty()
        self.app._render_now()

    def test_pending_hover_tip_survives_refresh_with_exact_new_value(self):
        key = self._hover_token()
        self.assertIsNotNone(self.scene.tooltip._job)
        self.assertIsNone(self.scene.tooltip.window)
        self._update_tokens(987654)
        self.assertEqual(self.scene._tip_key, key)
        self.assertIn('987,654 tokens', self.scene.tooltip.text)
        self.assertIsNotNone(self.scene.tooltip._job)
        self.fixture.pump(.14)
        self.assertIsNotNone(self.scene.tooltip.window)

    def test_visible_hover_tip_reappears_with_updated_value_after_refresh(self):
        key = self._hover_token()
        self.fixture.pump(.14)
        self.assertIsNotNone(self.scene.tooltip.window)
        self._update_tokens(456789)
        self.assertEqual(self.scene._tip_key, key)
        self.fixture.pump(.04)
        self.assertIsNotNone(self.scene.tooltip.window)
        self.assertIn('456,789 tokens', self.scene.tooltip.text)
        text = []
        for widget in fixtures.children(self.scene.tooltip.window):
            if 'text' in widget.keys():
                text.append(widget.cget('text'))
            if isinstance(widget, tk.Canvas):
                text.extend(widget.itemcget(item, 'text') for item in widget.find_all() if widget.type(item) == 'text')
        self.assertTrue(any('456,789 tokens' in line for line in text), text)

    def test_refresh_without_existing_tip_does_not_open_one(self):
        self.scene.hide_tooltip()
        self._update_tokens(135790)
        self.fixture.pump(.14)
        self.assertIsNone(self.scene.tooltip.window)
        self.assertIsNone(self.scene.tooltip._job)
        self.assertIsNone(self.scene._tip_key)

    def test_selection_and_scroll_close_existing_hover_tip(self):
        self._hover_token()
        self.fixture.pump(.14)
        self.assertIsNotNone(self.scene.tooltip.window)
        self.scene.invoke((self.account.id, 'details'))
        self.fixture.pump(.04)
        self.assertIsNone(self.scene.tooltip.window)
        self.assertIsNone(self.scene.tooltip._job)
        self.scene.invoke((self.account.id, 'details'))
        self.fixture.pump(.04)
        self._hover_token()
        self.fixture.pump(.14)
        self.assertIsNotNone(self.scene.tooltip.window)
        self.app.canvas.yview_moveto(1)
        self.fixture.pump(.04)
        self.assertIsNone(self.scene.tooltip.window)
        self.assertIsNone(self.scene.tooltip._job)


if __name__ == '__main__':
    unittest.main()
