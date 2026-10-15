from __future__ import annotations

import queue
import threading
import unittest
from unittest.mock import Mock, patch

from PIL import Image
import pystray
from pystray._util import win32

from codexcontrol_windows.app import CodexControlWindowsApp


class TrayActionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.app = CodexControlWindowsApp.__new__(CodexControlWindowsApp)
        self.app.root = Mock()
        self.app.events = queue.Queue()
        self.app._quitting = False
        self.app._create_icon_image = Mock(return_value=Image.new('RGBA', (16, 16)))
        with (
            patch.object(pystray.Icon, '_register_class', return_value=0),
            patch.object(pystray.Icon, 'run_detached'),
        ):
            self.app._setup_tray_icon()

    def _on_worker(self, callback) -> None:
        failures = []

        def run() -> None:
            try:
                callback()
            except Exception as error:
                failures.append(error)

        worker = threading.Thread(target=run)
        worker.start()
        worker.join(timeout=1)
        self.assertFalse(worker.is_alive(), 'Tray callback must not wait for the Tk thread')
        self.assertEqual(failures, [])

    def test_native_single_left_click_from_worker_only_queues_show(self) -> None:
        icon = self.app.tray_icon
        self.assertIsNotNone(icon)
        with patch.object(icon, 'update_menu'):
            # Exercise the actual Windows message handler on its own thread,
            # including repeated single clicks while the panel is already open.
            self._on_worker(lambda: icon._on_notify(0, win32.WM_LBUTTONUP))
            self._on_worker(lambda: icon._on_notify(0, win32.WM_LBUTTONUP))
        self.assertEqual(self.app.events.get_nowait(), ('tray_action', 'show'))
        self.assertEqual(self.app.events.get_nowait(), ('tray_action', 'show'))
        self.assertEqual(self.app.root.mock_calls, [])

    def test_right_click_commands_enqueue_without_calling_tk(self) -> None:
        menu = self.app.tray_icon.menu
        commands = [item for item in menu if item is not pystray.Menu.SEPARATOR]
        self.assertEqual([item.text for item in commands], [
            'Show Control Panel', 'Hide Control Panel', 'Refresh All', 'Add Account', 'Quit',
        ])
        for item, action in zip(commands, ('show', 'hide', 'refresh', 'add', 'quit')):
            self._on_worker(lambda item=item: item(self.app.tray_icon))
            self.assertEqual(self.app.events.get_nowait(), ('tray_action', action))
        self.assertEqual(self.app.root.mock_calls, [])

    def test_queued_show_is_dispatched_to_native_foreground_helper_on_main_thread(self) -> None:
        thread_ids = []
        with patch('codexcontrol_windows.app.bring_window_to_front', side_effect=lambda root: thread_ids.append(threading.get_ident())) as native_show:
            self.app._dispatch_event(('tray_action', 'show'))
        native_show.assert_called_once_with(self.app.root)
        self.assertEqual(thread_ids, [threading.get_ident()])

    def test_queued_hide_withdraws_window_on_main_thread(self) -> None:
        self.app._dispatch_event(('tray_action', 'hide'))
        self.app.root.withdraw.assert_called_once_with()

    def test_show_after_quit_does_not_reactivate_window(self) -> None:
        self.app._quitting = True
        with patch('codexcontrol_windows.app.bring_window_to_front') as native_show:
            self.app._dispatch_event(('tray_action', 'show'))
        native_show.assert_not_called()


if __name__ == '__main__':
    unittest.main()
