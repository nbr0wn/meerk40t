import os
import tempfile
import unittest
from unittest import mock

import usb.core

from meerk40t.balormk import usb_connection, usbtrace


class FakeDevice:
    bus = 1
    address = 32

    def __init__(self, fail_writes=0):
        self.fail_writes = fail_writes
        self.resets = 0

    def write(self, endpoint, data, timeout):
        if self.fail_writes:
            self.fail_writes -= 1
            raise usb.core.USBTimeoutError("Operation timed out", -7, 110)
        return len(data)

    def read(self, endpoint, size_or_buffer, timeout):
        return bytes([1, 2, 3, 4, 5, 6, 7, 8])

    def reset(self):
        self.resets += 1


class TestUsbTrace(unittest.TestCase):
    def setUp(self):
        fd, self.path = tempfile.mkstemp(suffix=".log")
        os.close(fd)
        self._patch = mock.patch.multiple(
            usbtrace, PATH=self.path, _file=None, _last_dump=0.0
        )
        self._patch.start()
        usbtrace._ring.clear()

    def tearDown(self):
        if usbtrace._file is not None:
            usbtrace._file.close()
        self._patch.stop()
        os.unlink(self.path)

    def _connection(self, device):
        conn = usb_connection.USBConnection(lambda *a, **k: None)
        conn.channel._ = lambda s: s
        conn.devices[0] = device
        # Reopen hands back the same fake device without touching real USB.
        conn.find_device = lambda index=0: device
        conn.set_config = lambda d: None
        conn.get_active_config = lambda d: None
        conn.detach_kernel = lambda d, i: None
        conn.claim_interface = lambda d, i: None
        conn.disconnect_detach = lambda d, i: None
        conn.unclaim_interface = lambda d, i: None
        conn.disconnect_dispose = lambda d: None
        return conn

    def test_clean_transfers_stay_in_ring(self):
        conn = self._connection(FakeDevice())
        conn.write(0, b"\x00" * 12)
        conn.read(0)
        self.assertEqual(len(usbtrace._ring), 2)
        self.assertEqual(os.path.getsize(self.path), 0)

    def test_write_timeout_dumps_ring_and_logs_resend(self):
        dev = FakeDevice(fail_writes=1)
        conn = self._connection(dev)
        conn.read(0)  # something to appear in the ring dump
        conn.write(0, b"\x25\x00" + b"\x00" * 10)
        usbtrace._file.flush()
        text = open(self.path).read()
        self.assertIn("ring buffer (1 entries)", text)
        self.assertIn("ERROR write attempt=0", text)
        self.assertIn("errno=110", text)
        self.assertIn("data=25 00", text)
        self.assertNotIn("RESET", text)
        self.assertEqual(dev.resets, 0)

    def test_disabled_writes_nothing(self):
        with mock.patch.object(usbtrace, "PATH", None):
            conn = self._connection(FakeDevice(fail_writes=1))
            conn.write(0, b"\x00" * 12)
        self.assertEqual(len(usbtrace._ring), 0)
        self.assertEqual(os.path.getsize(self.path), 0)


if __name__ == "__main__":
    unittest.main()
