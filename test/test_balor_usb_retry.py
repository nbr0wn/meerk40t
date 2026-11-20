import errno
import unittest
from unittest import mock

import usb.core

from meerk40t.balormk import usb_connection
from meerk40t.balormk.usb_connection import USBConnection

CMD = b"\x09\x00" + b"\x00" * 10  # GetSerialNo
LIST = b"\x00" * 0xC00
REPLY = bytes([1, 0, 2, 0, 3, 0, 4, 0])


def timeout():
    return usb.core.USBTimeoutError("Operation timed out", -7, errno.ETIMEDOUT)


def nodev():
    return usb.core.USBError("No such device", -4, errno.ENODEV)


class ScriptedDevice:
    """Fake LMC board: each write/read consumes the next scripted outcome."""

    bus = 1
    address = 35

    def __init__(self, writes=(), reads=()):
        self.writes = list(writes)  # None = accept, exception = raise
        self.reads = list(reads)  # bytes = reply, exception = raise
        self.written = []
        self.read_timeouts = []
        self.resets = 0

    def write(self, endpoint, data, timeout):
        outcome = self.writes.pop(0) if self.writes else None
        if outcome is not None:
            raise outcome
        self.written.append(bytes(data))
        return len(data)

    def read(self, endpoint, size_or_buffer, timeout):
        self.read_timeouts.append(timeout)
        outcome = self.reads.pop(0) if self.reads else timeout_exc()
        if isinstance(outcome, Exception):
            raise outcome
        return outcome

    def reset(self):
        self.resets += 1


def timeout_exc():
    return timeout()


def connection(device):
    conn = USBConnection(lambda *a, **k: None)
    conn.channel._ = lambda s: s
    conn.devices[0] = device
    conn.interface[0] = None
    conn.disconnect_dispose = lambda d: None
    conn.open = mock.Mock(side_effect=AssertionError("USB layer must not reopen"))
    return conn


class TestTransact(unittest.TestCase):
    def test_plain_reply(self):
        dev = ScriptedDevice(reads=[REPLY])
        self.assertEqual(connection(dev).transact(0, CMD), REPLY)
        self.assertEqual(dev.written, [CMD])

    def test_late_reply_is_waited_for_not_resent(self):
        dev = ScriptedDevice(reads=[timeout(), REPLY])
        conn = connection(dev)
        self.assertEqual(conn.transact(0, CMD), REPLY)
        self.assertEqual(dev.written, [CMD])
        self.assertEqual(
            dev.read_timeouts, [conn.timeout, usb_connection.LATE_REPLY_TIMEOUT_MS]
        )
        self.assertEqual(dev.resets, 0)

    def test_lost_reply_resends_command(self):
        dev = ScriptedDevice(reads=[timeout(), timeout(), REPLY])
        conn = connection(dev)
        self.assertEqual(conn.transact(0, CMD), REPLY)
        self.assertEqual(dev.written, [CMD, CMD])
        self.assertEqual(dev.resets, 0)
        self.assertTrue(conn.is_open(0))

    def test_no_reply_at_all_drops_device_once(self):
        dev = ScriptedDevice(reads=[])
        conn = connection(dev)
        with self.assertRaises(ConnectionError):
            conn.transact(0, CMD)
        self.assertEqual(len(dev.written), 1 + usb_connection.RESENDS)
        self.assertEqual(dev.resets, 1)
        self.assertFalse(conn.is_open(0))

    def test_device_gone_raises_without_keyerror(self):
        dev = ScriptedDevice(writes=[nodev()])
        conn = connection(dev)
        with self.assertRaises(ConnectionError):
            conn.transact(0, CMD)
        self.assertFalse(conn.is_open(0))
        with self.assertRaises(ConnectionError):  # was KeyError: 0
            conn.write(0, CMD)


class TestWrite(unittest.TestCase):
    def test_command_write_timeout_is_resent(self):
        dev = ScriptedDevice(writes=[timeout(), None])
        conn = connection(dev)
        conn.write(0, CMD)
        self.assertEqual(dev.written, [CMD])
        self.assertEqual(dev.resets, 0)
        self.assertTrue(conn.is_open(0))

    def test_list_write_timeout_is_not_resent(self):
        dev = ScriptedDevice(writes=[timeout(), None])
        conn = connection(dev)
        with self.assertRaises(ConnectionError):
            conn.write(0, LIST)
        self.assertEqual(dev.written, [])
        self.assertEqual(dev.resets, 1)
        self.assertFalse(conn.is_open(0))


class FailingConnection:
    """Opens fine but the board never answers."""

    def __init__(self):
        self.opened = False
        self.opens = 0
        self.closes = 0

    def is_open(self, index=0):
        return self.opened

    def open(self, index=0):
        self.opens += 1
        self.opened = True
        return index

    def close(self, index=0):
        self.closes += 1
        self.opened = False

    def transact(self, index, packet):
        self.close(index)
        raise ConnectionError("no reply")

    def write(self, index, packet):
        raise ConnectionError("no reply")


class TestControllerConnect(unittest.TestCase):
    def test_silent_board_bounded_connect_attempts(self):
        from test import bootstrap

        kernel = bootstrap.bootstrap()
        try:
            kernel.console("service device start -i balor 0\n")
            controller = kernel.device.driver.connection
            fake = FailingConnection()
            controller.connection = fake
            controller.service.setting(bool, "mock", False)
            with mock.patch("meerk40t.balormk.controller.time.sleep"):
                with self.assertRaises(ConnectionRefusedError):
                    controller.connect_if_needed()
            self.assertEqual(fake.opens, 10)  # not unbounded
            self.assertTrue(controller._disable_connect)
            self.assertIsNone(controller._opening_thread)
        finally:
            kernel()


class TestControllerConnectHealthy(unittest.TestCase):
    def test_mock_connect_initialises(self):
        from test import bootstrap

        kernel = bootstrap.bootstrap()
        try:
            kernel.console("service device start -i balor 0\n")
            kernel.device.mock = True
            controller = kernel.device.driver.connection
            controller.connect_if_needed()
            self.assertTrue(controller.connected)
            self.assertFalse(controller._disable_connect)
            self.assertIsNone(controller._opening_thread)
        finally:
            kernel()


if __name__ == "__main__":
    unittest.main()
