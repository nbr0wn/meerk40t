import os
import socket
import tempfile
import unittest
from unittest import mock

import wx

from meerk40t.gui import wxmeerk40t


class _Dialog:
    shown = []

    def __init__(self, parent, message, caption, style):
        _Dialog.shown.append(message)

    def ShowModal(self):
        return wx.ID_OK

    def Destroy(self):
        pass


class TestNoReportUpload(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = wx.App(False)

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.cwd = os.getcwd()
        os.chdir(self.tmp)
        _Dialog.shown.clear()

    def tearDown(self):
        os.chdir(self.cwd)

    def _no_network(self, *a, **k):
        raise AssertionError("tried to open a network connection")

    def test_send_data_saves_locally_without_network(self):
        with mock.patch.object(socket, "socket", self._no_network), mock.patch.object(
            wx, "MessageDialog", _Dialog
        ):
            wxmeerk40t.send_data_to_developers("bug.txt", "something broke")
        path = os.path.join(self.tmp, "bug.txt")
        with open(path) as f:
            self.assertEqual(f.read(), "something broke")
        self.assertIn("disabled", _Dialog.shown[0])
        self.assertIn(path, _Dialog.shown[0])

    def test_existing_crash_log_not_overwritten(self):
        path = os.path.join(self.tmp, "MeerK40t-crash.txt")
        with open(path, "w") as f:
            f.write("full log")
        with mock.patch.object(socket, "socket", self._no_network), mock.patch.object(
            wx, "MessageDialog", _Dialog
        ):
            wxmeerk40t.send_file_to_developers(path)
        with open(path) as f:
            self.assertEqual(f.read(), "full log")


if __name__ == "__main__":
    unittest.main()
