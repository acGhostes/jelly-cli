import threading
import unittest
from jelly_cli.reporting import PlaybackReports


class ReportingTests(unittest.TestCase):
    def test_serial_reports_and_server_watch_state(self):
        calls, refreshed, errors = [], [], []
        gate = threading.Event()
        class Client:
            def request(self, path, body):
                calls.append((path, body))
                if path == 'Sessions/Playing':
                    gate.wait(2)
            def detail(self, item_id):
                return {'Id': item_id, 'UserData': {'Played': False}}
        reports = PlaybackReports(Client(), 'item', 'source', 'session', errors.append, refreshed.append)
        reports.start({'PositionTicks': 0, 'IsPaused': False})
        # A slow start cannot cause a progress backlog or let stop overtake it.
        reports.progress({'PositionTicks': 100})
        reports.stop({'PositionTicks': 200})
        reports.progress({'PositionTicks': 300})
        reports.stop({'PositionTicks': 400})
        gate.set()
        reports.executor.shutdown(wait=True)
        self.assertEqual([x[0] for x in calls], ['Sessions/Playing', 'Sessions/Playing/Stopped'])
        self.assertEqual(calls[-1][1]['PositionTicks'], 200)
        self.assertEqual(calls[-1][1]['PlaySessionId'], 'session')
        self.assertEqual(refreshed[0]['UserData'], {'Played': False})
        self.assertFalse(errors)

    def test_errors_surface_and_stop_is_still_attempted(self):
        calls, errors = [], []
        class Client:
            def request(self, path, body):
                calls.append(path)
                raise RuntimeError('offline')
        reports = PlaybackReports(Client(), 'item', 'source', 'session', errors.append, lambda _: None)
        reports.start({'PositionTicks': 0})
        reports.stop({'PositionTicks': 10}, failed=True)
        reports.executor.shutdown(wait=True)
        self.assertEqual(calls, ['Sessions/Playing', 'Sessions/Playing/Stopped'])
        self.assertEqual(errors, ['offline', 'offline'])

    def test_failed_load_does_not_create_session(self):
        class Client:
            def request(self, *args, **kwargs):
                raise AssertionError('No report should be sent before file-loaded')
        reports = PlaybackReports(Client(), 'item', 'source', 'session', lambda _: None, lambda _: None)
        reports.stop({'PositionTicks': 0}, failed=True)
        reports.executor.shutdown(wait=True)
        self.assertFalse(reports.started)
