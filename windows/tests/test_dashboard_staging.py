"""Atomic Canvas refresh keeps a complete scene until its replacement is ready."""
import unittest
from unittest.mock import patch

import test_dashboard_ui as fixtures


class DashboardStagingTests(unittest.TestCase):
    def setUp(self):
        self.fixture = fixtures.DashboardTests(methodName='runTest')
        self.addCleanup(self.fixture.doCleanups)
        self.fixture.setUp()
        self.addCleanup(self.fixture.tearDown)
        self.app, self.scene = self.fixture.app, self.fixture.app.card_scene
        self.account = self.app.accounts[0]

    def _refresh(self, used):
        self.app.runtime_states[self.account.id].snapshot.primary_window.used_percent = used
        self.app._mark_runtime_dirty()
        self.app._render_now()

    def test_refresh_keeps_complete_old_scene_until_new_scene_commits(self):
        old_texts = self.fixture.canvas_texts()
        old_ids = set(self.app.canvas.find_all())
        observations = []
        build_card = self.scene._card
        def inspect_build(*args, **kwargs):
            result = build_card(*args, **kwargs)
            observations.append(self.fixture.canvas_texts())
            return result
        with patch.object(self.scene, '_card', side_effect=inspect_build):
            self._refresh(63)
        self.assertEqual(len(observations), len(self.app.accounts))
        self.assertTrue(all(texts == old_texts for texts in observations))
        self.assertIn('37%', self.fixture.canvas_texts())
        self.assertFalse(old_ids.intersection(self.app.canvas.find_all()))
        self.assertEqual(set(self.scene.card_bounds), {a.id for a in self.app.accounts})
        self.assertEqual(self.app.canvas.winfo_children(), [])

    def test_repeated_refreshes_present_latest_complete_quota(self):
        canvas_id = self.app.canvas.winfo_id()
        for used, expected in ((63, '37%'), (74, '26%'), (81, '19%')):
            self._refresh(used)
            self.assertIn(expected, self.fixture.canvas_texts())
            self.assertEqual(len(self.scene.card_bounds), len(self.app.accounts))
        self.fixture.pump(.12)
        self.assertIn('19%', self.fixture.canvas_texts())
        self.assertEqual(self.app.canvas.winfo_id(), canvas_id)
        self.assertEqual(self.fixture.errors, [])

    def test_failed_drawing_preserves_visible_scene_and_next_refresh_recovers(self):
        before = self.fixture.canvas_texts()
        regions = [r.key for r in self.scene.regions]
        original = self.scene._card
        count = 0
        def fail_second_card(*args, **kwargs):
            nonlocal count
            count += 1
            if count == 2:
                raise RuntimeError('synthetic renderer failure')
            return original(*args, **kwargs)
        with patch.object(self.scene, '_card', side_effect=fail_second_card):
            with self.assertRaisesRegex(RuntimeError, 'synthetic renderer failure'):
                self._refresh(63)
        self.assertEqual(self.fixture.canvas_texts(), before)
        self.assertEqual([r.key for r in self.scene.regions], regions)
        self._refresh(81)
        self.assertIn('19%', self.fixture.canvas_texts())
        self.assertEqual(len(self.scene.card_bounds), len(self.app.accounts))

    def test_post_commit_editor_error_keeps_the_complete_new_scene_visible(self):
        with patch.object(self.scene, '_sync_editor', side_effect=RuntimeError('synthetic editor failure')):
            with self.assertRaisesRegex(RuntimeError, 'synthetic editor failure'):
                self._refresh(63)
        self.assertIn('37%', self.fixture.canvas_texts())
        self.assertEqual(set(self.scene.card_bounds), {a.id for a in self.app.accounts})
        self.assertTrue(self.app.canvas.find_all())
        self._refresh(81)
        self.assertIn('19%', self.fixture.canvas_texts())


if __name__ == '__main__':
    unittest.main()
