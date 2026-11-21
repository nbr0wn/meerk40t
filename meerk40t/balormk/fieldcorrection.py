"""
Generated field (lens) correction for BJJCZ/LMC galvo boards.

The board holds a 65x65 table of (dx, dy) offsets in galvo units, one node every
1024 units across 0..0xFFFF, and interpolates it for every output position. A
.cor file is one source for that table; this module computes one from a small
set of distortion parameters instead, in the spirit of EzCad's F3 field page.

Parameters are expressed in *scene* axes (X to the right, Y down, as MeerK40t
shows the bed) with coordinates normalised to -1..1 at the field edges. A
commanded point (x, y) is sent to the galvos as:

    x' = sx * x * (1 + tx*y + bx*y*y) + kx*y
    y' = sy * y * (1 + ty*x + by*x*x) + ky*x

    s  scale            (setting in %, 100 = unchanged)
    t  trapezoid        (setting in %: width change at the bottom edge)
    b  bulge            (setting in %: width change at the top/bottom edges)
    k  skew             (setting in % of the half field: shift at the bottom edge)

The y terms mirror the x terms with the axes exchanged.

Table layout (not documented by the vendor): nodes are sent row-major with the
row index along galvo Y and the column along galvo X (``transpose`` swaps that).
How far the board moves per table unit is the ``gain``: measured on a BJJCZ
LMCV4 fiber board (2026-11-21) the board moved the opposite way by about the
table value, so the default gain is -1 and the generated offsets are divided
by it. Successive calibration rounds measure it (``estimate_gain``).
"""

import math

GRID = 65
CENTER = 0x8000
HALF = 32768.0
NODE_STEP = 1024
MAX_OFFSET = 0x7FFF

AXES = ("x", "y")
TERMS = ("scale", "trapezoid", "bulge", "skew")

IDENTITY = {
    "scale_x": 100.0,
    "scale_y": 100.0,
    "trapezoid_x": 0.0,
    "trapezoid_y": 0.0,
    "bulge_x": 0.0,
    "bulge_y": 0.0,
    "skew_x": 0.0,
    "skew_y": 0.0,
}


def _coefficients(params):
    p = dict(IDENTITY)
    p.update({k: float(v) for k, v in params.items() if k in IDENTITY})
    return (
        p["scale_x"] / 100.0,
        p["trapezoid_x"] / 100.0,
        p["bulge_x"] / 100.0,
        p["skew_x"] / 100.0,
        p["scale_y"] / 100.0,
        p["trapezoid_y"] / 100.0,
        p["bulge_y"] / 100.0,
        p["skew_y"] / 100.0,
    )


def warp(coefficients, x, y):
    """Apply the distortion model to a normalised scene point."""
    sx, tx, bx, kx, sy, ty, by, ky = coefficients
    return (
        sx * x * (1.0 + tx * y + bx * y * y) + kx * y,
        sy * y * (1.0 + ty * x + by * x * x) + ky * x,
    )


def axis_map_from_view(view):
    """
    2x2 orthogonal matrix taking normalised native (galvo) offsets to normalised
    scene offsets, from a meerk40t View (flip, swap and rotate; no scale).
    """
    c = view.iposition(CENTER, CENTER)
    ex = view.iposition(CENTER + NODE_STEP, CENTER)
    ey = view.iposition(CENTER, CENTER + NODE_STEP)
    cols = []
    for e in (ex, ey):
        dx, dy = e[0] - c[0], e[1] - c[1]
        n = math.hypot(dx, dy)
        cols.append((round(dx / n), round(dy / n)))
    # columns are images of native x and native y
    return ((cols[0][0], cols[1][0]), (cols[0][1], cols[1][1]))


def _mul(m, v):
    return m[0][0] * v[0] + m[0][1] * v[1], m[1][0] * v[0] + m[1][1] * v[1]


def _transpose(m):
    return (m[0][0], m[1][0]), (m[0][1], m[1][1])


def encode_offset(v):
    """Board encoding: magnitude in 15 bits, 0x8000 marks a negative value."""
    v = int(round(v))
    if v >= 0:
        return min(v, MAX_OFFSET)
    return 0x8000 | min(-v, MAX_OFFSET)


DEFAULT_GAIN = -1.0


def build_offsets(
    params, axis_map=((1, 0), (0, 1)), transpose=False, gain=DEFAULT_GAIN
):
    """
    Signed (dx, dy) table values for all 65x65 nodes in upload order: the
    wanted galvo-unit shift divided by ``gain`` (board movement per table unit).

    @return: (offsets, clipped) where clipped counts components beyond the
             board's +-0x7FFF range (they are limited to it).
    """
    coeffs = _coefficients(params)
    inv = _transpose(axis_map)
    offsets = []
    clipped = 0
    for row in range(GRID):
        for col in range(GRID):
            gx, gy = (row, col) if transpose else (col, row)
            u = ((gx * NODE_STEP - CENTER) / HALF, (gy * NODE_STEP - CENTER) / HALF)
            s = _mul(axis_map, u)
            w = warp(coeffs, *s)
            n = _mul(inv, w)
            d = [(n[0] - u[0]) * HALF / gain, (n[1] - u[1]) * HALF / gain]
            for i in (0, 1):
                if abs(d[i]) > MAX_OFFSET:
                    clipped += 1
                    d[i] = math.copysign(MAX_OFFSET, d[i])
            offsets.append((d[0], d[1]))
    return offsets, clipped


def build_table(params, axis_map=((1, 0), (0, 1)), transpose=False, gain=DEFAULT_GAIN):
    """Encoded [dx, dy] words for upload, plus the clipped count."""
    offsets, clipped = build_offsets(params, axis_map, transpose, gain)
    return [[encode_offset(dx), encode_offset(dy)] for dx, dy in offsets], clipped


# ---------------------------------------------------------------------------
# Fitting from a measured test pattern
# ---------------------------------------------------------------------------
#
# The test pattern is a centred square with a cross through its centre. The
# eight measured lengths (corner to corner, or end to end for the cross) see
# every term of the model: top/bottom/middle widths give scale, trapezoid and
# bulge along X, left/right/middle heights the same along Y, and the diagonals
# the shared skew.

FIELDS = (
    "top",
    "bottom",
    "mid_h",
    "left",
    "right",
    "mid_v",
    "diag_tl_br",
    "diag_tr_bl",
)

# A pattern measurement within this of nominal everywhere counts as calibrated.
DONE_TOLERANCE_MM = 0.2


def test_side(lens_mm):
    """Side of the test square: about 60% of the field, in whole 10 mm."""
    return max(20, int(0.6 * lens_mm / 10) * 10)


def predict_square(coefficients, side_mm, lens_mm):
    """
    Measurements (mm) of the centred test pattern of side ``side_mm`` after the
    distortion ``coefficients``, as a dict keyed by FIELDS.
    """
    a = side_mm / lens_mm  # half side, normalised to the half field
    half = lens_mm / 2.0

    def w(x, y):
        return warp(coefficients, x, y)

    def d(p, q):
        return math.hypot(p[0] - q[0], p[1] - q[1]) * half

    tl, tr, br, bl = w(-a, -a), w(a, -a), w(a, a), w(-a, a)
    return {
        "top": d(tl, tr),
        "bottom": d(bl, br),
        "mid_h": d(w(-a, 0.0), w(a, 0.0)),
        "left": d(tl, bl),
        "right": d(tr, br),
        "mid_v": d(w(0.0, -a), w(0.0, a)),
        "diag_tl_br": d(tl, br),
        "diag_tr_bl": d(tr, bl),
    }


def nominal_square(side_mm):
    """Measurements of a perfect pattern: the default entry values."""
    values = {k: float(side_mm) for k in FIELDS}
    values["diag_tl_br"] = values["diag_tr_bl"] = side_mm * math.sqrt(2.0)
    values["side"] = float(side_mm)
    return values


def as_square(sq):
    """A measured pattern as a dict: from a dict, or (side, 8 lengths in FIELDS order)."""
    if isinstance(sq, dict):
        out = {"side": float(sq["side"])}
        out.update({k: float(sq[k]) for k in FIELDS})
        return out
    side, *values = sq
    if len(values) != len(FIELDS):
        raise ValueError(f"Each pattern needs its side and {len(FIELDS)} lengths.")
    out = {"side": float(side)}
    out.update({k: float(v) for k, v in zip(FIELDS, values)})
    return out


def max_error(squares):
    """Largest difference (mm) between any measured length and its nominal."""
    worst = 0.0
    for sq in squares:
        sq = as_square(sq)
        nominal = nominal_square(sq["side"])
        worst = max([worst] + [abs(sq[k] - nominal[k]) for k in FIELDS])
    return worst


def fit_residual(squares, lens_mm, damping=1e-3, iterations=50):
    """
    Distortion coefficients that best explain measured test patterns.

    @param squares: dicts with "side" and FIELDS, or (side, 8 lengths) sequences
    @return: (coefficients, rms_mm) of the residual distortion the machine shows
             with the correction that was active while marking.
    """
    import numpy as np

    parsed = [as_square(sq) for sq in squares]
    meas = np.array([sq[k] for sq in parsed for k in FIELDS])

    # Lengths cannot see rotation, and skew X with the opposite skew Y is a
    # rotation, so only the shared (pure shear) skew is fitted: kx = ky = k.
    # Fitted vector: sx, tx, bx, sy, ty, by, k.
    def coefficients(q):
        sx, tx, bx, sy, ty, by, k = q
        return (sx, tx, bx, k, sy, ty, by, k)

    p0 = np.array([1.0, 0, 0, 1.0, 0, 0, 0])
    p = p0.copy()

    def model(q):
        c = coefficients(q)
        out = []
        for sq in parsed:
            pred = predict_square(c, sq["side"], lens_mm)
            out.extend(pred[k] for k in FIELDS)
        return np.array(out)

    for _ in range(iterations):
        r = model(p) - meas
        jac = np.empty((len(r), len(p)))
        for i in range(len(p)):
            dp = np.zeros_like(p)
            dp[i] = 1e-6
            jac[:, i] = (model(p + dp) - model(p - dp)) / 2e-6
        a = jac.T @ jac + damping * np.eye(len(p))
        b = jac.T @ r + damping * (p - p0)
        step = np.linalg.solve(a, b)
        p = p - step
        if np.max(np.abs(step)) < 1e-10:
            break
    rms = float(np.sqrt(np.mean((model(p) - meas) ** 2)))
    return tuple(float(v) for v in coefficients(p)), rms


def sanity_warnings(params, rms):
    """Plain-language warnings for implausible fit results."""
    warnings = []
    if rms > 0.5:
        warnings.append(
            f"The measurements do not fit together well ({rms:.2f} mm rms); "
            "check that each value went into the field with the right letter."
        )
    for axis in ("x", "y"):
        if not 50.0 <= params[f"scale_{axis}"] <= 150.0:
            warnings.append(f"Scale {axis.upper()} is far from 100%.")
        for term, limit in (("trapezoid", 10.0), ("bulge", 10.0), ("skew", 5.0)):
            if abs(params[f"{term}_{axis}"]) > limit:
                warnings.append(
                    f"{term.capitalize()} {axis.upper()} is larger than {limit:g}%."
                )
    return warnings


def compose_correction(params, residual):
    """
    Updated parameters that cancel ``residual`` (first order), given the
    parameters that were active while the measured pattern was marked.
    """
    rx, tx, bx, kx, ry, ty, by, ky = residual
    p = dict(IDENTITY)
    p.update({k: float(v) for k, v in params.items() if k in IDENTITY})
    p["scale_x"] = p["scale_x"] / rx
    p["scale_y"] = p["scale_y"] / ry
    p["trapezoid_x"] -= tx * 100.0
    p["trapezoid_y"] -= ty * 100.0
    p["bulge_x"] -= bx * 100.0
    p["bulge_y"] -= by * 100.0
    p["skew_x"] -= kx * 100.0
    p["skew_y"] -= ky * 100.0
    return p


# ---------------------------------------------------------------------------
# Table response
# ---------------------------------------------------------------------------
#
# The table holds (wanted shift) / gain, and the board moves G * table, so a
# parameter's physical effect is its deviation from identity times G / gain.
# Two rounds marked with different corrections show how far the shape moved
# for the change asked, which gives G without a separate test.

GAIN_LIMITS = (0.2, 5.0)  # plausible |G|
MIN_GAIN_SIGNAL = 0.01  # table change (fraction of half field) needed to estimate


def rescale(params, factor):
    """Parameters whose deviation from identity is ``factor`` times as large."""
    p = dict(IDENTITY)
    p.update({k: float(v) for k, v in params.items() if k in IDENTITY})
    out = {}
    for key, value in p.items():
        out[key] = 100.0 + (value - 100.0) * factor if key.startswith("scale") else value * factor
    return out


def estimate_gain(before, after):
    """
    True table response from two rounds, or None if they cannot tell.

    Each round is a dict with ``params`` (correction active while marking),
    ``gain`` (table response it was sent with) and ``residual`` (fitted
    coefficients of the marked shape). Uses the scale terms: the measured scale
    is native * (1 + G * e) with e = (scale - 1) / gain the table value.
    """
    num = den = 0.0
    for key, index in (("scale_x", 0), ("scale_y", 4)):
        e0 = (float(before["params"].get(key, 100.0)) / 100.0 - 1.0) / before["gain"]
        e1 = (float(after["params"].get(key, 100.0)) / 100.0 - 1.0) / after["gain"]
        change = e1 - e0
        if abs(change) < MIN_GAIN_SIGNAL:
            continue
        ratio = after["residual"][index] / before["residual"][index]
        denominator = e1 - ratio * e0
        if denominator == 0:
            continue
        # weight each axis by how much it was asked to change
        num += (ratio - 1.0) / denominator * abs(change)
        den += abs(change)
    if den == 0:
        return None
    gain = num / den
    if not GAIN_LIMITS[0] <= abs(gain) <= GAIN_LIMITS[1]:
        return None
    return gain


def next_correction(params, round_gain, new_gain, residual):
    """
    Correction to send with ``new_gain`` that cancels ``residual``, measured
    while ``params`` was active with ``round_gain``.
    """
    return compose_correction(rescale(params, new_gain / round_gain), residual)
