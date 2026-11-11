import threading
import unittest

from minescope.models.server import Edition, ScanResult, ServerTarget
from minescope.monitoring.monitor import Monitor

T = [ServerTarget("a.test", 1, Edition.JAVA), ServerTarget("b.test", 2, Edition.JAVA)]


def scan(t):
    return ScanResult(t.label, t.host, t.port, "java", True)


class MonitorTests(unittest.TestCase):
    def test_runs_max_cycles(self):
        seen = []
        m = Monitor(T, scan, interval=0.01, on_cycle=lambda n, r: seen.append((n, len(r))))
        self.assertEqual(m.run(max_cycles=3), 3)
        self.assertEqual(seen, [(1, 2), (2, 2), (3, 2)])

    def test_graceful_stop_from_another_thread(self):
        m = Monitor(T, scan, interval=60)  # would block a minute without stop()
        thread = threading.Thread(target=m.run)
        thread.start()
        while m.cycles_completed < 1:
            pass
        m.stop()
        thread.join(2)
        self.assertFalse(thread.is_alive())
        self.assertEqual(m.cycles_completed, 1)

    def test_callback_error_does_not_stop_monitoring(self):
        def bad(n, r):
            raise RuntimeError("boom")
        m = Monitor(T, scan, interval=0.01, on_cycle=bad)
        with self.assertLogs("minescope.monitoring.monitor", "ERROR"):
            self.assertEqual(m.run(max_cycles=2), 2)

    def test_stop_before_run(self):
        m = Monitor(T, scan, interval=0.01)
        m.stop()
        self.assertEqual(m.run(), 0)


if __name__ == "__main__":
    unittest.main()
