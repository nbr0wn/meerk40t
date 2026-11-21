import types
import unittest

import wx

from meerk40t.gui.wxmtree import ShadowTree
from meerk40t.svgelements import Color


class TestTreeSwatch(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = wx.App(False)
        cls.frame = wx.Frame(None)
        cls.tree = wx.TreeCtrl(cls.frame)
        cls.tree.SetForegroundColour(wx.Colour(200, 200, 200))
        cls.tree.SetBackgroundColour(wx.Colour(40, 40, 40))

    @classmethod
    def tearDownClass(cls):
        cls.frame.Destroy()

    def _shadow(self, extra=True):
        st = types.SimpleNamespace(
            wxtree=self.tree, iconsize=20, swatch_width=8, swatch_gap=3
        )
        st._swatch_extra = st.swatch_width + st.swatch_gap if extra else 0
        return st

    def _icon(self):
        img = wx.Image(20, 20)
        img.SetRGB(wx.Rect(0, 0, 20, 20), 255, 255, 255)
        img.InitAlpha()
        return wx.Bitmap(img)

    def test_swatch_drawn_in_pen_colour(self):
        st = self._shadow()
        out = ShadowTree._list_bitmap(st, self._icon(), Color("red")).ConvertToImage()
        self.assertEqual((out.GetWidth(), out.GetHeight()), (31, 20))
        self.assertEqual(
            (out.GetRed(4, 10), out.GetGreen(4, 10), out.GetBlue(4, 10)), (255, 0, 0)
        )
        self.assertEqual(out.GetAlpha(4, 10), 255)
        # border is a mid-tone between text and background
        self.assertEqual(out.GetRed(0, 10), 120)
        # gap stays transparent, icon follows it
        self.assertEqual(out.GetAlpha(9, 10), 0)
        self.assertEqual(out.GetRed(20, 10), 255)
        self.assertEqual(out.GetAlpha(20, 10), 255)

    def test_no_pen_leaves_blank_slot(self):
        st = self._shadow()
        out = ShadowTree._list_bitmap(st, self._icon(), None).ConvertToImage()
        self.assertEqual(out.GetWidth(), 31)
        self.assertEqual(out.GetAlpha(4, 10), 0)
        self.assertEqual(out.GetAlpha(20, 10), 255)

    def test_pen_without_value_leaves_blank_slot(self):
        st = self._shadow()
        out = ShadowTree._list_bitmap(st, self._icon(), Color("none")).ConvertToImage()
        self.assertEqual(out.GetAlpha(4, 10), 0)

    def test_disabled_returns_icon_unchanged(self):
        st = self._shadow(extra=False)
        icon = self._icon()
        self.assertIs(ShadowTree._list_bitmap(st, icon, Color("red")), icon)

    def test_icon_colour_is_tree_text_colour(self):
        c = ShadowTree._icon_color(self._shadow())
        self.assertEqual((c.red, c.green, c.blue), (200, 200, 200))


if __name__ == "__main__":
    unittest.main()
