import types
import unittest
from unittest import mock

import wx

from meerk40t.gui import wxmscene

refit = wxmscene.MeerK40tScenePanel._refit_bed_on_resize


def panel(size, view, fit):
    p = types.SimpleNamespace(_bed_fit=fit, _refit_pending=False)
    p.GetSize = lambda: size
    p._view_key = lambda: view
    p.focus_bed = lambda: None
    return p


class TestInitialFit(unittest.TestCase):
    def test_refit_when_resized_and_untouched(self):
        p = panel(wx.Size(800, 600), "v1", ("v1", (20, 20)))
        with mock.patch.object(wx, "CallAfter") as later:
            refit(p)
        later.assert_called_once_with(p.focus_bed)
        self.assertTrue(p._refit_pending)

    def test_no_refit_after_user_zoom(self):
        p = panel(wx.Size(800, 600), "zoomed", ("v1", (20, 20)))
        with mock.patch.object(wx, "CallAfter") as later:
            refit(p)
        later.assert_not_called()

    def test_no_refit_when_size_unchanged_or_pending(self):
        p = panel(wx.Size(800, 600), "v1", ("v1", (800, 600)))
        with mock.patch.object(wx, "CallAfter") as later:
            refit(p)
            p2 = panel(wx.Size(900, 600), "v1", ("v1", (800, 600)))
            p2._refit_pending = True
            refit(p2)
        later.assert_not_called()

    def test_no_fit_yet(self):
        p = panel(wx.Size(800, 600), "v1", None)
        with mock.patch.object(wx, "CallAfter") as later:
            refit(p)
        later.assert_not_called()


if __name__ == "__main__":
    unittest.main()
