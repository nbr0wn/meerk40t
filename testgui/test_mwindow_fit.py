import unittest

import wx
import wx.lib.scrolledpanel

from meerk40t.gui.mwindow import MWindow


class _Themes:
    def set_window_colors(self, win):
        pass


class _Context:
    """Just enough of a kernel Context for MWindow."""

    def __init__(self):
        self.root = self
        self.kernel = self
        self.themes = _Themes()
        self._children = {}

    def setting(self, _type, name, default=None):
        if not hasattr(self, name):
            setattr(self, name, default)
        return getattr(self, name)

    def get_context(self, path):
        return self._children.setdefault(path, _Context())

    def close(self, name):
        pass


def _scrolled(parent, w, h):
    panel = wx.lib.scrolledpanel.ScrolledPanel(parent)
    sizer = wx.BoxSizer(wx.VERTICAL)
    sizer.Add(w, h)
    panel.SetSizer(sizer)
    panel.SetupScrolling()
    return panel


def _plain(parent, w, h):
    panel = wx.Panel(parent)
    sizer = wx.BoxSizer(wx.VERTICAL)
    sizer.Add(w, h)
    panel.SetSizer(sizer)
    return panel


class _Win(MWindow):
    def __init__(self, context, make, w, h, honor=False, start=(200, 150)):
        super().__init__(*start, context, "window/test", None)
        self.panel = make(self, w, h)
        self.sizer.Add(self.panel, wx.SizerFlags(1).Expand())
        self.restore_aspect(honor_initial_values=honor)


def _wrapper(win):
    for child in win.GetChildren():
        if getattr(child, "_mk_autoscroll", False):
            return child
    return None


class TestMWindowFit(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = wx.App(False)

    def setUp(self):
        self.ctx = _Context()
        self.windows = []

    def tearDown(self):
        for w in self.windows:
            w.Destroy()

    def _make(self, *args, **kwargs):
        win = _Win(self.ctx, *args, **kwargs)
        self.windows.append(win)
        return win

    def _area(self, win):
        return win._display_area()

    def test_scrolled_content_sets_window_size(self):
        # A ScrolledPanel reports a tiny best size; the window must still fit
        # the panel's real content.
        win = self._make(_scrolled, 420, 380)
        win.fit_to_content()
        cs = win.GetClientSize()
        self.assertEqual((cs.width, cs.height), (420, 380))
        self.assertIsNone(_wrapper(win))

    def test_scrolled_panel_min_size_restored(self):
        win = self._make(_scrolled, 420, 380)
        before = win.panel.GetMinSize()
        win.fit_to_content()
        self.assertEqual(win.panel.GetMinSize(), before)

    def test_saved_size_ignored_for_fitted_window(self):
        self.ctx.get_context("window/test").width = 1000
        self.ctx.get_context("window/test").height = 900
        win = self._make(_plain, 300, 200)
        win.fit_to_content()
        cs = win.GetClientSize()
        self.assertEqual((cs.width, cs.height), (300, 200))

    def test_tall_plain_content_is_wrapped_in_scroller(self):
        win = self._make(_plain, 300, 5000)
        area = self._area(win)
        win.fit_to_content()
        self.assertEqual(win.GetSize().height, area.height)
        scroller = _wrapper(win)
        self.assertIsNotNone(scroller)
        self.assertIs(win.panel.GetParent(), scroller)
        self.assertGreaterEqual(scroller.GetVirtualSize().height, 5000)
        # Room for the vertical scrollbar so the content is not clipped.
        self.assertGreater(win.GetClientSize().width, 300)

    def test_tall_scrolled_content_not_wrapped(self):
        win = self._make(_scrolled, 300, 5000)
        area = self._area(win)
        win.fit_to_content()
        self.assertEqual(win.GetSize().height, area.height)
        self.assertIsNone(_wrapper(win))

    def test_refit_after_wrap_is_stable(self):
        win = self._make(_plain, 300, 5000)
        win.fit_to_content()
        first = win.GetSize()
        win.fit_to_content()
        self.assertEqual(win.GetSize(), first)
        self.assertEqual(
            sum(1 for c in win.GetChildren() if getattr(c, "_mk_autoscroll", 0)), 1
        )

    def test_honor_initial_is_minimum(self):
        win = self._make(_plain, 50, 40, honor=True, start=(500, 400))
        win.fit_to_content()
        want = win.FromDIP(wx.Size(500, 400))
        self.assertEqual(win.GetSize(), want)

    def test_honor_grows_to_content(self):
        win = self._make(_plain, 700, 40, honor=True, start=(500, 400))
        win.fit_to_content()
        self.assertGreaterEqual(win.GetClientSize().width, 700)

    def test_honor_tall_refit_does_not_creep(self):
        win = self._make(_scrolled, 300, 5000, honor=True)
        win.fit_to_content()
        first = win.GetSize()
        win.fit_to_content()
        win.fit_to_content()
        self.assertEqual(win.GetSize(), first)


if __name__ == "__main__":
    unittest.main()
