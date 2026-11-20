import unittest

import wx

from meerk40t.gui import uipolish


class TestSizerBorder(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = wx.App(False)
        uipolish.SIZER_BORDER = 5
        uipolish._installed = False
        uipolish.install()
        cls.frame = wx.Frame(None)

    @classmethod
    def tearDownClass(cls):
        cls.frame.Destroy()

    def _border(self, item):
        return item.GetFlag() & uipolish._BORDER_BITS, item.GetBorder()

    def test_bare_window_gets_border(self):
        s = wx.BoxSizer(wx.VERTICAL)
        item = s.Add(wx.Button(self.frame))
        self.assertEqual(self._border(item), (wx.ALL, self.frame.FromDIP(5)))

    def test_positional_flags_preserved(self):
        s = wx.BoxSizer(wx.VERTICAL)
        item = s.Add(wx.Button(self.frame), 1, wx.EXPAND)
        self.assertEqual(item.GetProportion(), 1)
        self.assertTrue(item.GetFlag() & wx.EXPAND)
        self.assertEqual(self._border(item), (wx.ALL, self.frame.FromDIP(5)))

    def test_explicit_border_untouched(self):
        s = wx.BoxSizer(wx.VERTICAL)
        item = s.Add(wx.Button(self.frame), 0, wx.LEFT, 2)
        self.assertEqual(self._border(item), (wx.LEFT, 2))

    def test_keyword_args(self):
        s = wx.BoxSizer(wx.VERTICAL)
        item = s.Add(wx.Button(self.frame), proportion=2, flag=wx.EXPAND)
        self.assertEqual(item.GetProportion(), 2)
        self.assertEqual(self._border(item), (wx.ALL, self.frame.FromDIP(5)))

    def test_nested_sizer_and_spacer_untouched(self):
        s = wx.BoxSizer(wx.VERTICAL)
        self.assertEqual(self._border(s.Add(wx.BoxSizer(wx.HORIZONTAL))), (0, 0))
        self.assertEqual(self._border(s.Add(10, 10)), (0, 0))

    def test_static_box_group_gets_border(self):
        s = wx.BoxSizer(wx.VERTICAL)
        group = wx.StaticBoxSizer(wx.VERTICAL, self.frame, "Group")
        item = s.Add(group, 1, wx.EXPAND)
        self.assertEqual(self._border(item), (wx.ALL, self.frame.FromDIP(5)))

    def test_sizerflags_untouched(self):
        s = wx.BoxSizer(wx.VERTICAL)
        item = s.Add(wx.Button(self.frame), wx.SizerFlags(1))
        self.assertEqual(self._border(item), (0, 0))

    def test_insert_and_prepend(self):
        s = wx.BoxSizer(wx.VERTICAL)
        s.Add(wx.Button(self.frame), 0, wx.ALL, 1)
        a = s.Insert(0, wx.Button(self.frame))
        b = s.Prepend(wx.Button(self.frame), 1)
        self.assertEqual(self._border(a), (wx.ALL, self.frame.FromDIP(5)))
        self.assertEqual(self._border(b), (wx.ALL, self.frame.FromDIP(5)))
        self.assertEqual(b.GetProportion(), 1)


class TestBlend(unittest.TestCase):
    def test_blend_endpoints_and_mid(self):
        a, b = wx.Colour(0, 0, 0, 10), wx.Colour(200, 100, 50, 255)
        self.assertEqual(uipolish.blend(a, b, 0).Get(), (0, 0, 0, 255))
        self.assertEqual(uipolish.blend(a, b, 1).Get(), (200, 100, 50, 255))
        self.assertEqual(uipolish.blend(a, b, 0.5).Get(), (100, 50, 25, 255))


class TestNativeTabArt(unittest.TestCase):
    def test_tab_art_colour_setters_ignored(self):
        import wx.aui

        app = wx.App(False)
        uipolish._install_native_tab_art()
        frame = wx.Frame(None)
        art = wx.aui.AuiNotebook(frame).GetArtProvider()
        art.SetColour(wx.RED)
        art.SetActiveColour(wx.RED)  # must not raise; no observable getter
        frame.Destroy()
        del app


if __name__ == "__main__":
    unittest.main()
