import types
import unittest

import wx

from meerk40t.gui.ribbon import _colour_key, button_background


def button(desc):
    return types.SimpleNamespace(button_dict=desc)


class TestButtonBackground(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = wx.App(False)

    def test_no_background(self):
        self.assertIsNone(button_background(button({"label": "x"})))
        self.assertIsNone(button_background(button(None)))

    def test_callable_colour(self):
        c = button_background(button({"background": lambda: wx.Colour(1, 2, 3)}))
        self.assertEqual(c.Get(False), (1, 2, 3))

    def test_callable_returning_none_or_failing(self):
        self.assertIsNone(button_background(button({"background": lambda: None})))

        def broken():
            raise AttributeError

        self.assertIsNone(button_background(button({"background": broken})))

    def test_cache_key_changes_with_colour(self):
        self.assertIsNone(_colour_key(None))
        self.assertNotEqual(
            _colour_key(wx.Colour(0, 255, 0)), _colour_key(wx.Colour(255, 0, 0))
        )


if __name__ == "__main__":
    unittest.main()
