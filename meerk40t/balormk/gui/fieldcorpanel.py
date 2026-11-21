"""
Field correction calibration page for the galvo configuration window.

Calibration runs in rounds:

1. Create the test pattern (a centred square with a cross) and burn it.
2. Measure the eight lettered lengths; the fields start at the values of a
   perfect pattern.
3. Apply: the correction is fitted, stored, enabled and sent to the laser.
   From the second round on the board's table response is measured as well.

Repeat until the page reports every length within tolerance. The raw
correction values and fit details are under "Show details".
"""

import json

import wx

from meerk40t.balormk.fieldcorrection import (
    DONE_TOLERANCE_MM,
    FIELDS,
    nominal_square,
)
from meerk40t.gui.choicepropertypanel import ChoicePropertyPanel
from meerk40t.gui.wxutils import (
    ScrolledPanel,
    StaticBoxSizer,
    TextCtrl,
    dip_size,
    wxButton,
    wxCheckBox,
    wxStaticText,
)

_ = wx.GetTranslation

LETTERS = dict(zip(FIELDS, "ABCDEFGH"))
GROUPS = (
    ("Widths", (("top", "Top"), ("bottom", "Bottom"), ("mid_h", "Middle"))),
    ("Heights", (("left", "Left"), ("right", "Right"), ("mid_v", "Middle"))),
    ("Diagonals", (("diag_tl_br", "↘"), ("diag_tr_bl", "↙"))),
)
TEXT_WIDTH = 520


class PatternDiagram(wx.Panel):
    """The test pattern with each measured length lettered."""

    def __init__(self, parent):
        super().__init__(parent, wx.ID_ANY)
        self.SetMinSize(dip_size(self, 260, 260))
        self.SetBackgroundStyle(wx.BG_STYLE_PAINT)
        self.Bind(wx.EVT_PAINT, self.on_paint)
        self.Bind(wx.EVT_SIZE, lambda e: self.Refresh())

    def on_paint(self, event):
        dc = wx.AutoBufferedPaintDC(self)
        bg = self.GetParent().GetBackgroundColour()
        fg = self.GetParent().GetForegroundColour()
        accent = wx.SystemSettings.GetColour(wx.SYS_COLOUR_HIGHLIGHT)
        dc.SetBackground(wx.Brush(bg))
        dc.Clear()
        gc = wx.GraphicsContext.Create(dc)
        if gc is None:
            return
        w, h = self.GetClientSize()
        size = min(w, h)
        margin = size * 0.14
        b2 = (size - 2 * margin) / 2  # half side in pixels
        cx, cy = w / 2, h / 2
        gap = margin * 0.45
        bold = self.GetFont().Bold()

        def label(field, x, y, colour):
            gc.SetFont(bold, colour)
            text = LETTERS[field]
            tw, th = gc.GetTextExtent(text)[:2]
            gc.DrawText(text, x - tw / 2, y - th / 2)

        # diagonals: measured corner to corner, not burned
        gc.SetPen(wx.Pen(fg, 1, wx.PENSTYLE_SHORT_DASH))
        gc.StrokeLine(cx - b2, cy - b2, cx + b2, cy + b2)
        gc.StrokeLine(cx + b2, cy - b2, cx - b2, cy + b2)
        # burned: the square and the cross
        gc.SetPen(wx.Pen(accent, 2))
        gc.StrokeLine(cx - b2, cy, cx + b2, cy)
        gc.StrokeLine(cx, cy - b2, cx, cy + b2)
        gc.SetPen(wx.Pen(fg, 2))
        gc.SetBrush(wx.TRANSPARENT_BRUSH)
        gc.DrawRectangle(cx - b2, cy - b2, 2 * b2, 2 * b2)

        label("top", cx, cy - b2 - gap, fg)
        label("bottom", cx, cy + b2 + gap, fg)
        label("left", cx - b2 - gap, cy, fg)
        label("right", cx + b2 + gap, cy, fg)
        label("mid_h", cx - 0.62 * b2, cy - 0.6 * gap, accent)
        label("mid_v", cx + 0.6 * gap, cy + 0.62 * b2, accent)
        k = 0.55 * b2
        label("diag_tl_br", cx - k + 0.5 * gap, cy - k - 0.5 * gap, fg)
        label("diag_tr_bl", cx + k - 0.5 * gap, cy - k - 0.5 * gap, fg)


class FieldCorrectionPanel(ScrolledPanel):
    def __init__(self, parent, context=None, **kwds):
        super().__init__(parent, wx.ID_ANY, **kwds)
        self.context = context
        self.fields = {}
        self.side = None

        main = wx.BoxSizer(wx.VERTICAL)
        steps = StaticBoxSizer(self, wx.ID_ANY, _("Calibrate"), wx.VERTICAL)

        self.round_label = wxStaticText(self, wx.ID_ANY, "")
        self.round_label.SetFont(self.round_label.GetFont().Bold())
        steps.Add(self.round_label, 0, wx.ALIGN_CENTER_HORIZONTAL)
        intro = wxStaticText(
            self,
            wx.ID_ANY,
            _(
                "1. Create the test pattern and burn it.\n"
                "2. Measure each lettered length: corner to corner, or end to "
                "end for the middle lines.\n"
                "3. Apply. Burn the pattern again and repeat until every length "
                "is within {tol:g} mm."
            ).format(tol=DONE_TOLERANCE_MM),
        )
        intro.Wrap(self.FromDIP(TEXT_WIDTH))
        steps.Add(intro, 0, wx.EXPAND)
        self.button_create = wxButton(self, wx.ID_ANY, _("Create test pattern"))
        steps.Add(self.button_create, 0, wx.EXPAND)
        steps.Add(PatternDiagram(self), 0, wx.ALIGN_CENTER_HORIZONTAL)

        field_size = wx.Size(self.FromDIP(80), -1)
        groups = wx.BoxSizer(wx.HORIZONTAL)
        for title, rows in GROUPS:
            column = wx.BoxSizer(wx.VERTICAL)
            column.Add(wxStaticText(self, wx.ID_ANY, _(title)), 0, wx.ALIGN_LEFT)
            grid = wx.FlexGridSizer(cols=3, vgap=0, hgap=self.FromDIP(4))
            for key, text in rows:
                grid.Add(
                    wxStaticText(self, wx.ID_ANY, LETTERS[key]),
                    0,
                    wx.ALIGN_CENTER_VERTICAL,
                )
                grid.Add(
                    wxStaticText(self, wx.ID_ANY, _(text)),
                    0,
                    wx.ALIGN_CENTER_VERTICAL,
                )
                ctrl = TextCtrl(self, wx.ID_ANY, check="float", size=field_size)
                ctrl.SetMinSize(field_size)
                ctrl.SetToolTip(_("Measured length in mm"))
                self.fields[key] = ctrl
                grid.Add(ctrl, 0)
            column.Add(grid, 0)
            groups.Add(column, 0, wx.LEFT | wx.RIGHT, self.FromDIP(8))
        steps.Add(groups, 0, wx.ALIGN_CENTER_HORIZONTAL)

        self.applied_label = wxStaticText(self, wx.ID_ANY, "")
        self.applied_label.SetFont(self.applied_label.GetFont().Bold())
        steps.Add(self.applied_label, 0, wx.ALIGN_CENTER_HORIZONTAL)

        buttons = wx.BoxSizer(wx.HORIZONTAL)
        self.button_calc = wxButton(self, wx.ID_ANY, _("Apply"))
        self.button_calc.SetToolTip(
            _("Fit the correction to these measurements and send it to the laser.")
        )
        self.button_clear = wxButton(self, wx.ID_ANY, _("Start over"))
        self.button_clear.SetToolTip(
            _(
                "Remove the correction and forget earlier rounds (the measured "
                "table response is kept). Burn the pattern again before round 1."
            )
        )
        buttons.Add(self.button_calc, 1, wx.EXPAND)
        buttons.Add(self.button_clear, 0, wx.EXPAND)
        steps.Add(buttons, 0, wx.EXPAND)

        self.message = wxStaticText(self, wx.ID_ANY, "")
        steps.Add(self.message, 0, wx.EXPAND)
        self.check_details = wxCheckBox(
            self, wx.ID_ANY, _("Show details and correction values")
        )
        steps.Add(self.check_details, 0, wx.EXPAND)
        main.Add(steps, 0, wx.EXPAND)

        self.details = StaticBoxSizer(self, wx.ID_ANY, _("Details"), wx.VERTICAL)
        self.result = TextCtrl(
            self, wx.ID_ANY, style=wx.TE_MULTILINE | wx.TE_READONLY | wx.TE_DONTWRAP
        )
        self.result.SetMinSize(dip_size(self, -1, 110))
        self.details.Add(self.result, 0, wx.EXPAND)
        self.button_apply = wxButton(self, wx.ID_ANY, _("Send to laser"))
        self.button_apply.SetToolTip(
            _("Send the current correction now (it is also sent on every connect).")
        )
        self.details.Add(self.button_apply, 0, wx.ALIGN_RIGHT)
        self.choices = ChoicePropertyPanel(
            self, wx.ID_ANY, context=context, choices="balor-fieldcor", scrolling=False
        )
        self.details.Add(self.choices, 0, wx.EXPAND)
        main.Add(self.details, 0, wx.EXPAND)

        self.SetSizer(main)
        self.load_fields()
        self.show_details(False)
        self.SetupScrolling(scroll_x=False)

        self.Bind(wx.EVT_BUTTON, self.on_create, self.button_create)
        self.Bind(wx.EVT_BUTTON, self.on_calculate, self.button_calc)
        self.Bind(wx.EVT_BUTTON, self.on_clear, self.button_clear)
        self.Bind(wx.EVT_BUTTON, self.on_send, self.button_apply)
        self.Bind(
            wx.EVT_CHECKBOX,
            lambda e: self.show_details(self.check_details.GetValue()),
            self.check_details,
        )
        for ctrl in self.fields.values():
            ctrl.Bind(wx.EVT_TEXT, self.on_field_edited)

    # ------------------------------------------------------------------

    def show_details(self, show):
        self.check_details.SetValue(show)
        self.GetSizer().Show(self.details, show, recursive=True)
        self.Layout()
        self.FitInside()

    def set_message(self, text):
        self.message.SetLabel(text)
        self.message.Wrap(self.FromDIP(TEXT_WIDTH))
        self.Layout()
        self.FitInside()

    def rounds(self):
        try:
            rounds = json.loads(self.context.fieldcor_rounds or "{}")
        except (AttributeError, TypeError, ValueError):
            rounds = {}
        return rounds if isinstance(rounds, dict) else {}

    def show_round(self):
        done = self.rounds().get("round", 0)
        if done:
            text = _("Round {n}").format(n=done + 1)
        elif getattr(self.context, "fieldcor_enabled", False):
            text = _("Round 1")
        else:
            text = _("Round 1: burn the pattern without correction")
        self.round_label.SetLabel(text)
        self.button_create.SetLabel(
            _("Create test pattern ({side} mm)").format(side=self.side)
        )
        self.Layout()

    def reset_fields(self):
        """Perfect-pattern values in every field."""
        nominal = nominal_square(self.side)
        for key in FIELDS:
            self.fields[key].ChangeValue(f"{nominal[key]:g}")
        self.save_fields(applied=None)
        self.show_applied(None)

    def load_fields(self):
        """Entries saved with the device settings, else perfect-pattern values."""
        self.side = self.context.field_test_side()
        try:
            saved = json.loads(self.context.fieldcor_measurements or "{}")
        except (AttributeError, TypeError, ValueError):
            saved = {}
        values = saved.get("values", {}) if saved.get("side") == self.side else {}
        nominal = nominal_square(self.side)
        for key in FIELDS:
            text = values.get(key)
            self.fields[key].ChangeValue(
                str(text) if text is not None else f"{nominal[key]:g}"
            )
        self.show_applied(saved.get("applied") if values else None)
        self.show_round()

    def save_fields(self, applied):
        state = {
            "side": self.side,
            "values": {key: ctrl.GetValue() for key, ctrl in self.fields.items()},
            "applied": applied,
        }
        try:
            self.context.fieldcor_measurements = json.dumps(state)
        except AttributeError:
            pass

    def show_applied(self, applied):
        """applied: True, False (edited since) or None (nothing entered)."""
        if applied:
            self.applied_label.SetLabel(_("✔ These measurements are applied"))
        elif applied is False:
            self.applied_label.SetLabel(_("Not applied yet"))
        else:
            self.applied_label.SetLabel("")
        self.Layout()

    def on_field_edited(self, event):
        self.save_fields(applied=False)
        self.show_applied(False)
        event.Skip()

    def measurements(self):
        """Entered values as a fit_residual pattern; raises ValueError on bad input."""
        sq = {"side": self.side}
        for key in FIELDS:
            text = self.fields[key].GetValue().strip()
            try:
                value = float(text)
            except ValueError:
                raise ValueError(
                    _("'{text}' is not a number (length {letter}).").format(
                        text=text, letter=LETTERS[key]
                    )
                )
            if value <= 0:
                raise ValueError(
                    _("Length {letter} must be positive.").format(letter=LETTERS[key])
                )
            sq[key] = value
        return [sq]

    def on_create(self, event):
        dlg = wx.MessageDialog(
            self,
            _("Remove all existing elements and operations first?")
            + "\n"
            + _("(Yes=Empty and Create, No=Keep existing)"),
            _("Create test pattern"),
            wx.YES_NO | wx.CANCEL | wx.ICON_QUESTION,
        )
        answer = dlg.ShowModal()
        dlg.Destroy()
        if answer == wx.ID_CANCEL:
            return
        self.context.create_field_test_pattern(clear=answer == wx.ID_YES)
        self.set_message(
            _("Test pattern created. Burn it, then enter the measurements.")
        )

    def on_calculate(self, event):
        if self.context.corfile_enabled:
            self.set_message(
                _("A correction file is enabled; disable it to use this correction.")
            )
            return
        try:
            squares = self.measurements()
        except ValueError as e:
            self.set_message(str(e))
            return
        res = self.context.apply_field_correction_fit(squares)
        self.save_fields(applied=True)
        self.show_applied(True)
        self.show_round()

        if res["done"]:
            summary = _(
                "Round {n}: every length is within {tol:g} mm. Calibration is done."
            ).format(n=res["round"], tol=DONE_TOLERANCE_MM)
        else:
            summary = _(
                "Round {n} applied (largest error {err:.2f} mm). Burn the pattern "
                "again, enter the new measurements and apply."
            ).format(n=res["round"], err=res["max_error"])
        lines = [summary]
        if res["gain_estimated"]:
            lines.append(
                _("Table response measured: {g:.2f} (was {b:g}).").format(
                    g=res["gain"], b=res["gain_before"]
                )
            )
        lines.extend(_("Check: {w}").format(w=_(w)) for w in res.get("warnings", ()))
        if res["clipped"]:
            lines.append(
                _("Warning: {n} offsets exceed the board range.").format(
                    n=res["clipped"]
                )
            )
        lines.append(self.send_message(res["sent"], _("Sent to the laser.")))
        self.set_message("\n".join(lines))
        self.result.SetValue("\n".join(self.detail_lines(res)))

    @staticmethod
    def detail_lines(res):
        lines = [
            _("Model matches the measurements to {rms:.3f} mm rms.").format(
                rms=res["rms"]
            ),
            _("Table response {b:g} -> {g:g}").format(
                b=res["gain_before"], g=res["gain"]
            ),
        ]
        p, u = res["previous"], res["updated"]
        for axis in ("x", "y"):
            lines.append(
                f"{axis.upper()}: "
                + ", ".join(
                    f"{_(term)} {p[f'{term}_{axis}']:{fmt}} -> {u[f'{term}_{axis}']:{fmt}}%"
                    for term, fmt in (
                        ("scale", ".3f"),
                        ("trapezoid", "+.3f"),
                        ("bulge", "+.3f"),
                        ("skew", "+.3f"),
                    )
                )
            )
        return lines

    @staticmethod
    def send_message(status, sent_text):
        if status == "sent":
            return sent_text
        if status == "busy":
            return _(
                "A job is running; press Send to laser under details when it has "
                "finished (it is also sent on the next connect)."
            )
        return _("Not connected; the correction is sent on the next connect.")

    def on_clear(self, event):
        status = self.context.reset_field_correction()
        self.reset_fields()
        self.show_round()
        self.set_message(
            _("Correction removed. Burn the pattern without correction for round 1.")
            + " "
            + self.send_message(status, _("Blank table sent to the laser."))
        )

    def on_send(self, event):
        status = self.context.send_correction_now()
        self.set_message(self.send_message(status, _("Correction sent.")))

    def pane_show(self):
        if self.context.field_test_side() != self.side:
            self.load_fields()  # lens size changed
        else:
            self.show_round()
        self.choices.pane_show()

    def pane_hide(self):
        self.choices.pane_hide()
