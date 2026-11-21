import math
import unittest
from test import bootstrap

from meerk40t.balormk import fieldcorrection as fc
from meerk40t.core.units import Length
from meerk40t.balormk.controller import GalvoController

SWAP = ((0, 1), (1, 0))


def node(offsets, row, col):
    return offsets[row * fc.GRID + col]


def coeffs(**params):
    return fc._coefficients(params)


def simulate(correction, machine, side, lens_mm, response=1.0):
    """
    Measured pattern (dict) of a centred test pattern: the correction applied
    with ``response`` times its intended effect (true / assumed table
    response), then the machine distortion.
    """
    c = coeffs(**fc.rescale(correction, response))
    a = side / lens_mm
    half = lens_mm / 2.0

    def w(x, y):
        return fc.warp(machine, *fc.warp(c, x, y))

    def d(p, q):
        return math.hypot(p[0] - q[0], p[1] - q[1]) * half

    tl, tr, br, bl = w(-a, -a), w(a, -a), w(a, a), w(-a, a)
    return {
        "side": side,
        "top": d(tl, tr),
        "bottom": d(bl, br),
        "mid_h": d(w(-a, 0), w(a, 0)),
        "left": d(tl, bl),
        "right": d(tr, br),
        "mid_v": d(w(0, -a), w(0, a)),
        "diag_tl_br": d(tl, br),
        "diag_tr_bl": d(tr, bl),
    }


class TestFieldCorrectionTable(unittest.TestCase):
    def test_identity_is_all_zero(self):
        offsets, clipped = fc.build_offsets({})
        self.assertEqual(len(offsets), 65 * 65)
        self.assertEqual(clipped, 0)
        self.assertTrue(all(abs(dx) < 1e-9 and abs(dy) < 1e-9 for dx, dy in offsets))

    def test_scale_x_moves_columns(self):
        offsets, _ = fc.build_offsets({"scale_x": 110}, gain=1.0)
        self.assertAlmostEqual(node(offsets, 32, 64)[0], 0.1 * 32768)
        self.assertAlmostEqual(node(offsets, 32, 0)[0], -0.1 * 32768)
        self.assertAlmostEqual(node(offsets, 32, 64)[1], 0)
        # same along a column regardless of row
        self.assertAlmostEqual(node(offsets, 0, 64)[0], node(offsets, 64, 64)[0])

    def test_swapped_view_maps_scene_x_to_native_y(self):
        offsets, _ = fc.build_offsets({"scale_x": 110}, axis_map=SWAP, gain=1.0)
        self.assertAlmostEqual(node(offsets, 64, 32)[1], 0.1 * 32768)
        self.assertAlmostEqual(node(offsets, 64, 32)[0], 0)

    def test_flip_keeps_scale_symmetric(self):
        flip = ((-1, 0), (0, 1))
        offsets, _ = fc.build_offsets({"scale_x": 110}, axis_map=flip, gain=1.0)
        self.assertAlmostEqual(node(offsets, 32, 64)[0], 0.1 * 32768)

    def test_transpose_and_negative_gain(self):
        offsets, _ = fc.build_offsets({"scale_x": 110}, transpose=True, gain=-1.0)
        self.assertAlmostEqual(node(offsets, 64, 32)[0], -0.1 * 32768)

    def test_default_gain_is_minus_one(self):
        # Measured on the BJJCZ LMCV4 board: it moves the opposite way by about
        # the table value, so the table holds the negated wanted shift.
        self.assertEqual(fc.DEFAULT_GAIN, -1.0)
        offsets, _ = fc.build_offsets({"scale_x": 110})
        self.assertAlmostEqual(node(offsets, 32, 64)[0], -0.1 * 32768)

    def test_gain_scales_table(self):
        one, _ = fc.build_offsets({"scale_y": 90, "bulge_x": 2}, gain=1.0)
        half, _ = fc.build_offsets({"scale_y": 90, "bulge_x": 2}, gain=-2.0)
        for (a, b), (c, d) in zip(one, half):
            self.assertAlmostEqual(c, -a / 2)
            self.assertAlmostEqual(d, -b / 2)

    def test_trapezoid_widens_bottom(self):
        c = coeffs(trapezoid_x=10)
        self.assertAlmostEqual(fc.warp(c, 1, 1)[0], 1.1)  # bottom edge (y down)
        self.assertAlmostEqual(fc.warp(c, 1, -1)[0], 0.9)  # top edge

    def test_encoding_and_clip(self):
        self.assertEqual(fc.encode_offset(5), 5)
        self.assertEqual(fc.encode_offset(-5), 0x8005)
        self.assertEqual(fc.encode_offset(-100000), 0xFFFF)
        table, clipped = fc.build_table({"scale_x": 500})
        self.assertGreater(clipped, 0)
        self.assertTrue(all(0 <= w <= 0xFFFF for pair in table for w in pair))


class TestFieldCorrectionFit(unittest.TestCase):
    lens = 175.0
    side = 100
    # roughly this machine: oversize, a little keystone, shear and bulge
    machine = coeffs(
        scale_x=111.8,
        scale_y=115.9,
        trapezoid_x=0.4,
        trapezoid_y=-0.3,
        bulge_x=0.7,
        bulge_y=2.6,
        skew_x=0.4,
        skew_y=0.4,
    )

    def test_one_pattern_recovers_every_term(self):
        residual, rms = fc.fit_residual(
            [simulate({}, self.machine, self.side, self.lens)], self.lens
        )
        self.assertLess(rms, 1e-4)
        for got, want in zip(residual, self.machine):
            self.assertAlmostEqual(got, want, places=4)

    def test_iterated_correction_makes_pattern_square(self):
        params = dict(fc.IDENTITY)
        for _ in range(3):
            sq = simulate(params, self.machine, self.side, self.lens)
            residual, _rms = fc.fit_residual([sq], self.lens)
            params = fc.compose_correction(params, residual)
        sq = simulate(params, self.machine, self.side, self.lens)
        self.assertLess(fc.max_error([sq]), 0.05)

    def test_bulge_seen_as_edge_vs_middle(self):
        out = fc.predict_square(coeffs(bulge_x=5), 100, self.lens)
        self.assertGreater(out["top"], out["mid_h"])
        self.assertAlmostEqual(out["top"], out["bottom"])
        self.assertAlmostEqual(out["mid_v"], out["left"], places=6)

    def test_sequence_form_and_nominal(self):
        n = fc.nominal_square(100)
        self.assertAlmostEqual(n["diag_tl_br"], 141.4214, places=3)
        self.assertEqual(n["mid_h"], 100)
        seq = [100] + [n[k] for k in fc.FIELDS]
        residual, rms = fc.fit_residual([seq], self.lens)
        self.assertAlmostEqual(residual[0], 1.0, places=6)
        self.assertLess(rms, 1e-9)
        self.assertEqual(fc.max_error([n]), 0)
        with self.assertRaises(ValueError):
            fc.as_square([100, 1, 2, 3])

    def test_test_side(self):
        self.assertEqual(fc.test_side(175), 100)
        self.assertEqual(fc.test_side(110), 60)
        self.assertEqual(fc.test_side(20), 20)


class TestTableResponse(unittest.TestCase):
    lens = 175.0
    machine = TestFieldCorrectionFit.machine

    def round(self, params, gain, true_gain):
        sq = simulate(params, self.machine, 100, self.lens, true_gain / gain)
        residual, _ = fc.fit_residual([sq], self.lens)
        return {"params": params, "gain": gain, "residual": residual}

    def test_estimate_from_two_rounds(self):
        # the user's case: board responds -1, table built for -2
        first = self.round(dict(fc.IDENTITY), -2.0, -1.0)
        params = fc.next_correction(first["params"], -2.0, -2.0, first["residual"])
        second = self.round(params, -2.0, -1.0)
        self.assertAlmostEqual(fc.estimate_gain(first, second), -1.0, delta=0.02)

    def test_wrong_sign_assumption_is_measured(self):
        first = self.round(dict(fc.IDENTITY), 1.0, -1.0)
        params = fc.next_correction(first["params"], 1.0, 1.0, first["residual"])
        second = self.round(params, 1.0, -1.0)
        self.assertAlmostEqual(fc.estimate_gain(first, second), -1.0, delta=0.02)

    def test_no_change_between_rounds_gives_none(self):
        first = self.round(dict(fc.IDENTITY), -1.0, -1.0)
        second = self.round(dict(fc.IDENTITY), -1.0, -1.0)
        self.assertIsNone(fc.estimate_gain(first, second))

    def test_implausible_estimate_rejected(self):
        first = {"params": dict(fc.IDENTITY), "gain": -1.0, "residual": [1.1] * 8}
        second = {
            "params": dict(fc.IDENTITY, scale_x=90, scale_y=90),
            "gain": -1.0,
            "residual": [1.1] * 8,  # asked -10%, nothing changed
        }
        self.assertIsNone(fc.estimate_gain(first, second))

    def test_rescale(self):
        p = fc.rescale(dict(fc.IDENTITY, scale_x=90, bulge_y=2), 0.5)
        self.assertAlmostEqual(p["scale_x"], 95)
        self.assertAlmostEqual(p["bulge_y"], 1)
        self.assertAlmostEqual(p["scale_y"], 100)


class TestFitRobustness(unittest.TestCase):
    def test_noisy_measurements_never_produce_rotation(self):
        # Regression: the free kx/ky fit drifted into a ~12 degree rotation
        # (skew X +20.7%, skew Y -20.9%) on real, slightly noisy measurements.
        import random

        rng = random.Random(1)
        lens = 175.0
        machine = coeffs(scale_x=110, scale_y=113, trapezoid_x=0.2, bulge_y=1)
        for _ in range(50):
            sq = simulate({}, machine, 100, lens)
            for k in fc.FIELDS:
                sq[k] += rng.uniform(-0.3, 0.3)
            residual, _rms = fc.fit_residual([sq], lens)
            self.assertEqual(residual[3], residual[7])  # pure shear, no rotation
            self.assertLess(abs(residual[3]), 0.01)

    def test_sanity_warnings(self):
        good = dict(fc.IDENTITY, scale_x=91, skew_x=0.3)
        self.assertEqual(fc.sanity_warnings(good, 0.1), [])
        bad = dict(fc.IDENTITY, skew_x=20.7, skew_y=-20.9)
        self.assertEqual(len(fc.sanity_warnings(bad, 0.1)), 2)
        self.assertEqual(len(fc.sanity_warnings(fc.IDENTITY, 2.0)), 1)


class _Service:
    corfile_enabled = False
    corfile = None
    fieldcor_enabled = False

    def field_correction_table(self):
        return fc.build_table({"scale_x": 110}, gain=1.0)


def _controller(service):
    ctrl = GalvoController.__new__(GalvoController)
    ctrl.service = service
    ctrl.calls = []
    ctrl.usb_log = lambda *a: None
    ctrl.write_cor_table = lambda table=True: ctrl.calls.append(("table", table))
    ctrl.write_cor_line = lambda dx, dy, non_first: ctrl.calls.append(
        (dx, dy, non_first)
    )
    return ctrl


class TestSendCorrection(unittest.TestCase):
    def test_blank_when_disabled(self):
        ctrl = _controller(_Service())
        ctrl.send_correction()
        self.assertEqual(ctrl.calls, [("table", False)])

    def test_generated_table_uploaded(self):
        service = _Service()
        service.fieldcor_enabled = True
        ctrl = _controller(service)
        ctrl.send_correction()
        self.assertEqual(ctrl.calls[0], ("table", True))
        self.assertEqual(len(ctrl.calls), 1 + 65 * 65)
        self.assertEqual(ctrl.calls[1][2], 0)
        self.assertEqual(ctrl.calls[2][2], 1)
        # row 32, col 64 carries +10% of half field in dx
        self.assertEqual(ctrl.calls[1 + 32 * 65 + 64][:2], (3277, 0))

    def test_corfile_takes_priority(self):
        service = _Service()
        service.fieldcor_enabled = True
        service.corfile_enabled = True
        ctrl = _controller(service)
        sent = []
        ctrl.write_correction_file = sent.append
        ctrl.send_correction()
        self.assertEqual(sent, [None])
        self.assertEqual(ctrl.calls, [])


class TestDeviceFieldCorrection(unittest.TestCase):
    def setUp(self):
        self.kernel = bootstrap.bootstrap()
        self.kernel.console("service device start -i balor 0\n")
        self.device = self.kernel.device

    def tearDown(self):
        self.kernel()

    def measure(self, machine, true_gain):
        """Burn the pattern on a simulated machine with the device's correction."""
        dev = self.device
        lens = Length(dev.lens_size).mm
        params = dev.field_correction_params() if dev.fieldcor_enabled else {}
        return simulate(
            params, machine, dev.field_test_side(), lens, true_gain / dev.fieldcor_gain
        )

    def test_settings_and_table(self):
        dev = self.device
        self.assertFalse(dev.fieldcor_enabled)
        self.assertEqual(dev.field_correction_params(), fc.IDENTITY)
        self.assertEqual(dev.fieldcor_gain, -1.0)
        self.assertEqual(dev.field_test_side(), 60)  # default 110 mm lens
        table, clipped = dev.field_correction_table({"scale_x": 110})
        self.assertEqual(len(table), 65 * 65)
        self.assertEqual(clipped, 0)

    def test_rounds_converge_and_measure_table_response(self):
        dev = self.device
        dev.fieldcor_gain = -2.0  # wrong guess; the board responds -1
        machine = coeffs(scale_x=111.8, scale_y=115.9, trapezoid_x=0.4, bulge_y=2.6)
        results = []
        for _ in range(3):
            results.append(dev.apply_field_correction_fit([self.measure(machine, -1.0)]))
        self.assertEqual([r["round"] for r in results], [1, 2, 3])
        self.assertFalse(results[0]["gain_estimated"])
        self.assertTrue(results[1]["gain_estimated"])
        self.assertAlmostEqual(dev.fieldcor_gain, -1.0, delta=0.03)
        self.assertLess(fc.max_error([self.measure(machine, -1.0)]), 0.2)

    def test_repeat_apply_is_idempotent(self):
        dev = self.device
        machine = coeffs(scale_x=105, trapezoid_x=2)
        sq = self.measure(machine, -1.0)
        first = dev.apply_field_correction_fit([sq])
        params = dev.field_correction_params()
        again = dev.apply_field_correction_fit([dict(sq)])
        self.assertEqual(again["round"], first["round"])
        for k, v in params.items():
            self.assertAlmostEqual(dev.field_correction_params()[k], v, 3)

    def test_fit_command(self):
        dev = self.device
        machine = coeffs(scale_x=105, trapezoid_x=2)
        sq = self.measure(machine, -1.0)
        nums = [sq["side"]] + [sq[k] for k in fc.FIELDS]
        self.kernel.console(
            "fieldcorrection fit " + " ".join(f"{v:.4f}" for v in nums) + "\n"
        )
        self.assertTrue(dev.fieldcor_enabled)
        self.assertAlmostEqual(dev.fieldcor_scale_x, 100 / 1.05, delta=0.05)
        self.assertAlmostEqual(dev.fieldcor_trapezoid_x, -2, delta=0.05)
        # manual table response from the test-table widths
        self.kernel.console("fieldcorrection gain 56 51\n")
        self.assertAlmostEqual(dev.fieldcor_gain, -1.0 * (51 / 56 - 1) / 0.1, 2)

    def test_create_pattern_and_start_over(self):
        dev = self.device
        elements = self.kernel.elements
        before_ops = len(list(elements.ops()))
        nodes = dev.create_field_test_pattern(clear=False)
        self.assertEqual([n.type for n in nodes], ["elem rect", "elem line", "elem line"])
        cx, cy = dev.view.iposition(0x8000, 0x8000)
        s = float(Length("60mm"))
        for node in nodes:
            bb = node.bbox(with_stroke=False)
            self.assertAlmostEqual((bb[0] + bb[2]) / 2, cx, delta=1)
            self.assertAlmostEqual((bb[1] + bb[3]) / 2, cy, delta=1)
        bb = nodes[0].bbox(with_stroke=False)
        self.assertAlmostEqual(bb[2] - bb[0], s, delta=1)
        self.assertAlmostEqual(nodes[1].bbox(with_stroke=False)[2] - nodes[1].bbox(with_stroke=False)[0], s, delta=1)
        ops = list(elements.ops())
        self.assertEqual(len(ops), before_ops + 1)
        self.assertEqual(len(ops[-1].children), 3)

        dev.apply_field_correction_fit([self.measure(coeffs(scale_x=105), -1.0)])
        dev.fieldcor_gain = -1.2
        dev.reset_field_correction()
        self.assertFalse(dev.fieldcor_enabled)
        self.assertEqual(dev.field_correction_params(), fc.IDENTITY)
        self.assertEqual(dev.fieldcor_rounds, "")
        self.assertEqual(dev.fieldcor_gain, -1.2)  # kept
        dev.create_field_test_pattern(clear=True)
        self.assertEqual(len(list(elements.ops())), 1)
        self.assertEqual(len(list(elements.elems())), 3)


if __name__ == "__main__":
    unittest.main()
