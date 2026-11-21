import json
import unittest
from unittest import mock

import wx

from meerk40t.balormk import fieldcorrection as fc
from meerk40t.balormk.gui import fieldcorpanel


class _Choices(wx.Panel):
    def __init__(self, parent, *args, **kwargs):
        super().__init__(parent)

    def pane_show(self):
        pass

    def pane_hide(self):
        pass


class _Device:
    corfile_enabled = False
    fieldcor_enabled = False
    fieldcor_measurements = ""
    fieldcor_rounds = ""

    def __init__(self):
        self.fitted = []
        self.side = 100
        self.reset = False
        self.created = None
        self.result = {}

    def field_test_side(self):
        return self.side

    def apply_field_correction_fit(self, squares):
        self.fitted.append(squares)
        n = len(self.fitted)
        self.fieldcor_rounds = json.dumps({"round": n})
        self.fieldcor_enabled = True
        res = {
            "round": n,
            "previous": dict(fc.IDENTITY),
            "updated": dict(fc.IDENTITY, scale_x=90.0),
            "residual": None,
            "rms": 0.123,
            "gain_before": -2.0,
            "gain": -2.0,
            "gain_estimated": False,
            "max_error": 11.9,
            "done": False,
            "warnings": [],
            "clipped": 0,
            "sent": "offline",
        }
        res.update(self.result)
        return res

    def reset_field_correction(self):
        self.reset = True
        self.fieldcor_rounds = ""
        self.fieldcor_enabled = False
        return "offline"

    def create_field_test_pattern(self, clear=False):
        self.created = clear


class TestFieldCorrectionPanel(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = wx.App(False)

    def setUp(self):
        self.frame = wx.Frame(None)
        self.device = _Device()
        self.panel = self.make()

    def make(self):
        with mock.patch.object(fieldcorpanel, "ChoicePropertyPanel", _Choices):
            return fieldcorpanel.FieldCorrectionPanel(self.frame, context=self.device)

    def tearDown(self):
        self.frame.Destroy()

    def test_defaults_are_nominal_for_lens(self):
        f = self.panel.fields
        self.assertEqual(len(f), 8)
        self.assertEqual(f["top"].GetValue(), "100")
        self.assertEqual(f["mid_v"].GetValue(), "100")
        self.assertAlmostEqual(float(f["diag_tl_br"].GetValue()), 141.421, 2)
        self.assertIn("100 mm", self.panel.button_create.GetLabel())
        self.assertIn("Round 1", self.panel.round_label.GetLabel())
        self.assertIn("without correction", self.panel.round_label.GetLabel())

    def test_apply_passes_entered_values_and_reports(self):
        self.panel.fields["top"].SetValue("111.69")
        self.panel.fields["mid_h"].SetValue("110.9")
        self.panel.on_calculate(None)
        (sq,) = self.device.fitted[0]
        self.assertEqual(sq["side"], 100)
        self.assertEqual(sq["top"], 111.69)
        self.assertEqual(sq["mid_h"], 110.9)
        msg = self.panel.message.GetLabel()
        self.assertIn("Round 1 applied", msg)
        self.assertIn("11.90", msg)
        self.assertIn("90.000", self.panel.result.GetValue())
        self.assertIn("Round 2", self.panel.round_label.GetLabel())
        self.assertIn("applied", self.panel.applied_label.GetLabel())
        # entries are kept
        self.assertEqual(self.panel.fields["top"].GetValue(), "111.69")

    def test_gain_and_done_messages(self):
        self.device.result = {
            "gain_estimated": True,
            "gain": -1.04,
            "done": True,
            "max_error": 0.1,
        }
        self.panel.on_calculate(None)
        msg = self.panel.message.GetLabel()
        self.assertIn("Calibration is done", msg)
        self.assertIn("-1.04", msg)

    def test_bad_input_reported_not_fitted(self):
        self.panel.fields["left"].SetValue("abc")
        self.panel.on_calculate(None)
        self.assertEqual(self.device.fitted, [])
        self.assertIn("abc", self.panel.message.GetLabel())
        self.assertIn("D", self.panel.message.GetLabel())

    def test_entries_persist_with_applied_state(self):
        self.panel.fields["left"].SetValue("115.66")
        self.assertIn("Not applied", self.panel.applied_label.GetLabel())
        self.panel.on_calculate(None)
        again = self.make()
        self.assertEqual(again.fields["left"].GetValue(), "115.66")
        self.assertIn("applied", again.applied_label.GetLabel())
        again.fields["top"].SetValue("101")
        self.assertIn("Not applied", again.applied_label.GetLabel())

    def test_lens_change_resets_to_new_nominal(self):
        self.panel.fields["left"].SetValue("115.66")
        self.device.side = 60
        self.panel.pane_show()
        self.assertEqual(self.panel.fields["left"].GetValue(), "60")
        self.assertIn("60 mm", self.panel.button_create.GetLabel())

    def test_old_format_measurements_ignored(self):
        self.device.fieldcor_measurements = json.dumps(
            {"values": {"100:top": "111.69"}, "applied": True}
        )
        panel = self.make()
        self.assertEqual(panel.fields["top"].GetValue(), "100")
        self.assertEqual(panel.applied_label.GetLabel(), "")

    def test_start_over(self):
        self.panel.fields["left"].SetValue("120.1")
        self.panel.on_calculate(None)
        self.panel.on_clear(None)
        self.assertTrue(self.device.reset)
        self.assertEqual(self.panel.fields["left"].GetValue(), "100")
        self.assertEqual(self.panel.applied_label.GetLabel(), "")
        self.assertIn("without correction", self.panel.round_label.GetLabel())

    def test_details_hidden_until_checked(self):
        self.frame.Show()
        self.assertFalse(self.panel.result.IsShown())
        self.panel.show_details(True)
        self.assertTrue(self.panel.result.IsShown())

    def test_corfile_blocks_calculation(self):
        self.device.corfile_enabled = True
        self.panel.on_calculate(None)
        self.assertEqual(self.device.fitted, [])


if __name__ == "__main__":
    unittest.main()
