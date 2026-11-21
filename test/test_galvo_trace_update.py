import threading
import time
import types
import unittest

from meerk40t.balormk.device import BalorDevice
from meerk40t.balormk.livelightjob import LiveLightJob


class FakeConnection:
    def __init__(self):
        self.calls = []
        self.lock = threading.Lock()

    def _log(self, name):
        with self.lock:
            self.calls.append(name)

    def light(self, *a, **k):
        self._log("light")
        time.sleep(0.001)

    def dark(self, *a, **k):
        self._log("dark")

    def abort(self, *a, **k):
        self._log("abort")

    def send_correction(self):
        self._log("send_correction")

    def get_last_xy(self):
        return 0x8000, 0x8000

    def __getattr__(self, name):
        # light_mode, light_off, write_port, goto_xy, rapid_mode ...
        return lambda *a, **k: self._log(name)


def running_job(connection):
    service = types.SimpleNamespace(
        redlight_speed=100, redlight_delay_dark=0, redlight_delay_light=0
    )
    job = LiveLightJob.__new__(LiveLightJob)
    job.service = service
    job.redlight_lock = threading.RLock()
    job._hold_requested = threading.Event()
    job._holding = threading.Event()
    job._travel_speed = None
    job.stopped = False
    job.started = True
    job.changed = False
    job.update_method = None
    job.bounded = False
    job._connection = connection
    job.points = [complex(1000 + i, 2000) for i in range(200)]
    thread = threading.Thread(target=job.jobevent, daemon=True)
    thread.start()
    return job, thread


class TestTraceHold(unittest.TestCase):
    def test_hold_stops_tracing_then_restarts(self):
        con = FakeConnection()
        job, thread = running_job(con)
        try:
            time.sleep(0.05)
            with job.held():
                with con.lock:
                    n = len(con.calls)
                time.sleep(0.1)
                with con.lock:
                    during = con.calls[n:]
                con.send_correction()
            self.assertEqual(during, [])  # nothing traced while held
            time.sleep(0.1)
            with con.lock:
                after = con.calls[n + 1 :]
            # trace restarted from scratch: abort (re-init) then tracing again
            self.assertIn("abort", after)
            self.assertIn("light", after[after.index("abort") :])
        finally:
            job.stopped = True
            thread.join(1)

    def test_hold_on_unstarted_job_does_not_wait(self):
        job = LiveLightJob.__new__(LiveLightJob)
        job._hold_requested = threading.Event()
        job._holding = threading.Event()
        job.redlight_lock = threading.RLock()
        job.started = False
        job.stopped = False
        job._connection = None
        t = time.perf_counter()
        with job.held():
            pass
        self.assertLess(time.perf_counter() - t, 0.5)
        self.assertTrue(job.changed)


class _Spooler:
    """Mirrors meerk40t.core.spoolers.Spooler: is_idle is a property."""

    def __init__(self, idle):
        self.idle = idle

    @property
    def is_idle(self):
        return self.idle


def device(connected=True, idle=True, job=None):
    con = FakeConnection()
    dev = types.SimpleNamespace(
        driver=types.SimpleNamespace(connected=connected, connection=con),
        spooler=_Spooler(idle),
        job=job,
        key=("k", 1),
    )
    dev._correction_key = lambda: dev.key
    dev.send_correction_now = lambda: BalorDevice.send_correction_now(dev)
    dev._send_if_changed = lambda: BalorDevice._send_if_changed(dev)
    return dev, con


class TestSendCorrectionNow(unittest.TestCase):
    def test_offline(self):
        dev, con = device(connected=False)
        self.assertEqual(dev.send_correction_now(), "offline")
        self.assertEqual(con.calls, [])

    def test_idle_sends(self):
        dev, con = device()
        self.assertEqual(dev.send_correction_now(), "sent")
        self.assertEqual(con.calls, ["send_correction"])
        self.assertEqual(dev._correction_sent_key, ("k", 1))

    def test_burn_running_not_sent(self):
        dev, con = device(idle=False)
        self.assertEqual(dev.send_correction_now(), "busy")
        self.assertEqual(con.calls, [])

    def test_trace_running_is_held_around_upload(self):
        held = []

        class Job(LiveLightJob):
            def __init__(self):
                self.started = True
                self.stopped = False

            def held(self, timeout=2.0):
                job = self

                class _Ctx:
                    def __enter__(self):
                        held.append("enter")

                    def __exit__(self, *a):
                        held.append("exit")

                return _Ctx()

        dev, con = device(idle=False, job=Job())  # trace counts as running job
        self.assertEqual(dev.send_correction_now(), "sent")
        self.assertEqual(held, ["enter", "exit"])
        self.assertEqual(con.calls, ["abort", "send_correction"])

    def test_unchanged_key_not_resent(self):
        dev, con = device()
        dev._send_if_changed()
        dev._send_if_changed()
        self.assertEqual(con.calls, ["send_correction"])
        dev.key = ("k", 2)
        dev._send_if_changed()
        self.assertEqual(con.calls, ["send_correction", "send_correction"])


class TestDebounce(unittest.TestCase):
    def test_burst_of_changes_sends_once(self):
        dev, con = device()
        for _ in range(5):
            BalorDevice.on_field_correction_changed(dev, "balor")
        time.sleep(0.8)
        self.assertEqual(con.calls, ["send_correction"])

    def test_offline_changes_ignored(self):
        dev, con = device(connected=False)
        BalorDevice.on_field_correction_changed(dev, "balor")
        self.assertIsNone(getattr(dev, "_correction_timer", None))


if __name__ == "__main__":
    unittest.main()
