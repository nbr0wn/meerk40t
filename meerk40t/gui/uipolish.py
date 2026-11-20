"""
Prototype UI polish switches (GTK-focused).

Controlled by environment variables so variants can be compared side by side:

    MK_NATIVE_COLORS=1   Stop MeerK40t from explicitly colouring standard
                         controls/windows; let the GTK theme draw them.
                         Also stops AUI notebooks being recoloured, which on
                         dark GTK themes makes inactive tab labels unreadable.
    MK_SIZER_BORDER=N    Give every window or static-box group added to a sizer
                         with no border an N-pixel (DIP) border on all sides.
                         Plain nested sizers and spacers are left alone to
                         avoid double padding.
"""

import os

import wx

_installed = False


def _env_int(name, default=0):
    try:
        return int(os.environ.get(name, default))
    except ValueError:
        return default


NATIVE_COLORS = os.environ.get("MK_NATIVE_COLORS", "0") not in ("", "0")
SIZER_BORDER = _env_int("MK_SIZER_BORDER", 0)


def blend(c1, c2, t):
    """Linear mix of two wx.Colours: t=0 gives c1, t=1 gives c2 (opaque result)."""
    return wx.Colour(
        *(int(round(a + (b - a) * t)) for a, b in zip(c1.Get(False), c2.Get(False)))
    )


_BORDER_BITS = wx.LEFT | wx.RIGHT | wx.TOP | wx.BOTTOM


_ADD_PARAMS = ("proportion", "flag", "border", "userData")


def _pad(item, args, kwargs):
    """
    For a window added via the (proportion, flag, border, userData) overload with
    no border, return keyword args with a default border on all sides.
    Anything else (sizers, spacers, SizerFlags) is returned unchanged (None).
    """
    if isinstance(item, wx.StaticBoxSizer):
        dip_source = item.GetStaticBox()
    elif isinstance(item, wx.Window):
        dip_source = item
    else:
        return None
    if any(isinstance(a, wx.SizerFlags) for a in args) or "flags" in kwargs:
        return None
    if len(args) > len(_ADD_PARAMS):
        return None
    vals = dict(zip(_ADD_PARAMS, args))
    vals.update(kwargs)
    flag = vals.get("flag", 0)
    border = vals.get("border", 0)
    if (flag & _BORDER_BITS) and border:
        return None
    if not flag & _BORDER_BITS:
        flag |= wx.ALL
    if not border:
        border = dip_source.FromDIP(SIZER_BORDER)
    vals["flag"] = flag
    vals["border"] = border
    return vals


def _install_sizer_border():
    orig_add = wx.Sizer.Add
    orig_prepend = wx.Sizer.Prepend
    orig_insert = wx.Sizer.Insert

    def Add(self, item, *args, **kwargs):
        vals = _pad(item, args, kwargs)
        if vals is None:
            return orig_add(self, item, *args, **kwargs)
        return orig_add(self, item, **vals)

    def Prepend(self, item, *args, **kwargs):
        vals = _pad(item, args, kwargs)
        if vals is None:
            return orig_prepend(self, item, *args, **kwargs)
        return orig_prepend(self, item, **vals)

    def Insert(self, index, item, *args, **kwargs):
        vals = _pad(item, args, kwargs)
        if vals is None:
            return orig_insert(self, index, item, *args, **kwargs)
        return orig_insert(self, index, item, **vals)

    wx.Sizer.Add = Add
    wx.Sizer.Prepend = Prepend
    wx.Sizer.Insert = Insert


def _install_native_tab_art():
    import wx.aui

    def ignore(self, colour):
        pass

    for name in dir(wx.aui):
        cls = getattr(wx.aui, name)
        if isinstance(cls, type) and "TabArt" in name:
            for meth in ("SetColour", "SetActiveColour"):
                if meth in cls.__dict__:
                    setattr(cls, meth, ignore)


def install():
    global _installed
    if _installed:
        return
    _installed = True
    if NATIVE_COLORS:
        _install_native_tab_art()
    if SIZER_BORDER > 0:
        _install_sizer_border()
