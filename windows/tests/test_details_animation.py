"""Details regressions for complete Canvas commits, without native card children."""
from __future__ import annotations

import unittest

import test_dashboard_ui as dashboard_fixture


class DetailsAnimationTests(unittest.TestCase):
    def setUp(self):
        self.fixture = dashboard_fixture.DashboardTests(methodName='runTest')
        self.addCleanup(self.fixture.doCleanups)
        self.fixture.setUp()
        self.addCleanup(self.fixture.tearDown)
        self.app, self.scene = self.fixture.app, self.fixture.app.card_scene
        self.account = self.app.accounts[1]

    def _height(self, account):
        _, top, _, bottom = self.scene.card_bounds[account.id]
        return bottom-top

    def _toggle(self, account=None):
        self.scene.invoke(((account or self.account).id, 'details'))
        self.fixture.pump(.04)

    def _assert_pure_canvas(self):
        self.assertEqual(self.app.canvas.winfo_children(), [])
        self.assertNotIn('window', [self.app.canvas.type(item) for item in self.app.canvas.find_all()])

    def test_expansion_and_collapse_keep_canvas_and_fixed_viewport_top(self):
        canvas = self.app.canvas
        first = self.app.accounts[0]
        canvas.yview_moveto(0)
        initial_top = canvas.canvasy(0)
        expanded_height = self._height(first)
        self._toggle(first)
        collapsed_height = self._height(first)
        self.assertLess(collapsed_height, expanded_height-50)
        self.assertAlmostEqual(canvas.canvasy(0), initial_top, delta=1)
        self._toggle(first)
        self.assertEqual(self._height(first), expanded_height)
        self.assertAlmostEqual(canvas.canvasy(0), initial_top, delta=1)
        self.assertIs(self.app.canvas, canvas)
        self.assertEqual(set(self.scene.card_bounds), {a.id for a in self.app.accounts})
        self._assert_pure_canvas()

    def test_details_toggle_never_maps_native_card_windows(self):
        events = []
        self.app.canvas.bind('<Map>', lambda event: events.append(('map', event.widget)), add='+')
        self.app.canvas.bind('<Unmap>', lambda event: events.append(('unmap', event.widget)), add='+')
        canvas_id = self.app.canvas.winfo_id()
        self._toggle()
        self.assertEqual(len([r for r in self.scene.regions if r.key[:2] == (self.account.id, 'token')]), 7)
        self._assert_pure_canvas()
        self._toggle()
        self._assert_pure_canvas()
        self.assertEqual(events, [])
        self.assertEqual(self.app.canvas.winfo_id(), canvas_id)

    def test_collapsed_details_leave_no_tab_stops_or_pending_tooltips(self):
        self._toggle()
        tokens = [r for r in self.scene.regions if r.key[:2] == (self.account.id, 'token')]
        self.assertEqual(len(tokens), 7)
        self.assertTrue(self.scene.focus_region(tokens[0].key))
        self.assertIsNotNone(self.scene.tooltip._job)
        self._toggle()
        self.assertFalse(any(r.key[0] == self.account.id and r.key[1] in ('token', 'refresh', 'key', 'trash')
                             for r in self.scene.regions))
        self.assertFalse(self.scene.focus_region(tokens[0].key))
        self.assertIsNone(self.scene.tooltip._job)
        self.assertIsNone(self.scene.tooltip.window)

    def test_rapid_clicks_keep_latest_selection(self):
        collapsed_height = self._height(self.account)
        for _ in range(9):
            self.scene.invoke((self.account.id, 'details'))
        self.fixture.pump(.04)
        self.assertEqual(self.app.selected_account_id, self.account.id)
        self.assertGreater(self._height(self.account), collapsed_height+50)
        for _ in range(5):
            self.scene.invoke((self.account.id, 'details'))
        self.fixture.pump(.04)
        self.assertIsNone(self.app.selected_account_id)
        self.assertEqual(self._height(self.account), collapsed_height)
        self._assert_pure_canvas()

    def test_wide_cards_keep_horizontal_geometry_when_details_open(self):
        self.app.root.geometry('1040x900+5000+5000')
        self.fixture.pump(.3)
        original = {key: (rect[0], rect[2]) for key, rect in self.scene.card_bounds.items()}
        self._toggle()
        self.assertEqual({key: (rect[0], rect[2]) for key, rect in self.scene.card_bounds.items()}, original)
        self.assertEqual(len({rect[0] for rect in self.scene.card_bounds.values()}), 2)

    def test_runtime_refresh_after_details_click_shows_latest_quota(self):
        self.scene.invoke((self.account.id, 'details'))
        def refresh():
            self.app.runtime_states[self.account.id].snapshot.primary_window.used_percent = 63
            self.app._mark_runtime_dirty()
            self.app._render_now()
        self.app.root.after_idle(refresh)
        self.fixture.pump(.12)
        self.assertEqual(self.app.selected_account_id, self.account.id)
        self.assertIn('37%', self.fixture.canvas_texts())
        self.assertEqual(len([r for r in self.scene.regions if r.key[:2] == (self.account.id, 'token')]), 7)
        self._assert_pure_canvas()

    def test_dispose_with_pending_tooltip_cancels_callbacks(self):
        self._toggle()
        token = next(r for r in self.scene.regions if r.key[:2] == (self.account.id, 'token'))
        self.scene.focus_region(token.key)
        self.assertIsNotNone(self.scene.tooltip._job)
        self.scene.dispose()
        self.assertIsNone(self.scene.tooltip._job)
        marker = []
        self.app.root.after(30, lambda: marker.append('alive'))
        self.fixture.pump(.12)
        self.assertEqual(marker, ['alive'])
        self.assertFalse(self.scene.regions)
        self.assertFalse(self.scene.card_bounds)
        self.assertEqual(self.fixture.errors, [])


if __name__ == '__main__':
    unittest.main()
