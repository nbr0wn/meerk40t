import wx
import wx.aui

from meerk40t.kernel import Module

_ = wx.GetTranslation


class MWindow(wx.Frame, Module):
    """
    Meerk40t window class does some of the more fancy operations for the meerk40t windows. This includes saving and
    loading the windows sizes and positions, ensuring the module for the class is correctly opened and closed.
    Deduplicating a lot of the repeat code and future proofing for other changes.

    MeerK40t Windows have a hook module_close and module_open into window_open and window_close to register and
    unregister hooks from the kernel. We register the acceleration table of the main window and handle the window/module
    open and close events.
    """

    def __init__(self, width, height, context, path, parent, *args, style=-1, **kwds):
        if style == -1:
            if parent is None:
                style = wx.DEFAULT_FRAME_STYLE
            else:
                style = (
                    wx.DEFAULT_FRAME_STYLE | wx.FRAME_FLOAT_ON_PARENT | wx.TAB_TRAVERSAL
                )
        self._start_width = width
        self._start_height = height
        self.root_context = context.root
        self.window_context = context.get_context(path)
        self.root_context.setting(bool, "windows_save", True)
        self.window_save = self.root_context.windows_save

        wx.Frame.__init__(self, parent, style=style)
        Module.__init__(self, context, path)
        self.window_context.themes.set_window_colors(self)
        self.Bind(wx.EVT_CLOSE, self.on_close, self)
        self.Bind(wx.EVT_LEFT_DOWN, self.on_mouse_left_down, self)
        self.Bind(wx.EVT_RIGHT_DOWN, self.on_menu_request, self)
        self.Bind(wx.EVT_MOVE, self.on_change_window, self)
        self.Bind(wx.EVT_SIZE, self.on_change_window, self)
        self.sizer = wx.BoxSizer(wx.VERTICAL)
        self.SetSizer(self.sizer)
        self.context.themes.set_window_colors(self)

    def restore_aspect(self, honor_initial_values=False):
        """
        Record how this window should be sized. The size itself is applied when
        the window is shown (see fit_to_content), once all content exists.

        honor_initial_values=True: the window has elastic content (consoles,
        lists, previews); the constructor size, or the size the user last left
        it at, is used as a minimum. Otherwise the window is sized to fit its
        content exactly.
        """
        self._honor_initial = honor_initial_values
        self.Raise()

    def _display_area(self):
        idx = wx.Display.GetFromWindow(self)
        if idx == wx.NOT_FOUND and self.GetParent() is not None:
            idx = wx.Display.GetFromWindow(self.GetParent())
        if idx == wx.NOT_FOUND:
            idx = 0
        return wx.Display(idx).GetClientArea()

    def _content_min_size(self):
        """
        Minimum client size needed to show all content without scrolling.

        Scrolled panels report a tiny best size, so for the measurement each one
        (innermost first) is temporarily given its sizer's minimum as its min
        size. The previous min sizes are restored afterwards so the panels can
        still shrink and scroll.
        """
        pinned = []

        def pin(win):
            for child in win.GetChildren():
                if not isinstance(child, wx.TopLevelWindow):
                    pin(child)
            if win is self or not isinstance(win, wx.ScrolledWindow):
                return
            sizer = win.GetSizer()
            if sizer is None:
                return
            need = sizer.CalcMin()
            cur = win.GetMinSize()
            pinned.append((win, cur))
            win.SetMinSize(
                wx.Size(max(cur.width, need.width), max(cur.height, need.height))
            )

        pin(self)
        try:
            sizer = self.GetSizer()
            if sizer is None:
                return self.GetBestSize()
            return sizer.CalcMin()
        finally:
            for win, size in reversed(pinned):
                win.SetMinSize(size)

    def _wrap_in_scroller(self):
        """Move the window's content into a vertically scrolling container."""
        sizer = self.GetSizer()
        scroller = wx.ScrolledWindow(self, wx.ID_ANY, style=wx.VSCROLL)
        scroller._mk_autoscroll = True
        for child in list(self.GetChildren()):
            if child is scroller or isinstance(
                child, (wx.TopLevelWindow, wx.StatusBar, wx.ToolBar, wx.MenuBar)
            ):
                continue
            child.Reparent(scroller)
        self.SetSizer(None, False)
        scroller.SetSizer(sizer)
        scroller.SetScrollRate(0, self.FromDIP(20))
        outer = wx.BoxSizer(wx.VERTICAL)
        outer.Add(scroller, wx.SizerFlags(1).Expand())
        self.SetSizer(outer)
        self.sizer = sizer
        self.window_context.themes.set_window_colors(scroller)
        return scroller

    def fit_to_content(self):
        """
        Size the window to its content, limited to the display. If the content
        is taller than the display and does not scroll by itself, it is put in
        a vertically scrolling container.
        """
        area = self._display_area()
        base = None
        if getattr(self, "_honor_initial", False):
            base = self.FromDIP(wx.Size(self._start_width, self._start_height))
            if self.window_save:
                base = wx.Size(
                    self.window_context.setting(int, "width", base.width),
                    self.window_context.setting(int, "height", base.height),
                )
        mgr = wx.aui.AuiManager.GetManager(self)
        if mgr is not None and mgr.GetManagedWindow() is self:
            # AUI lays these out itself (main window); keep the stored size.
            if base is None:
                base = self.GetSize()
            self.SetSize(
                wx.Size(min(base.width, area.width), min(base.height, area.height))
            )
            return self.GetSize()
        want = self.ClientToWindowSize(self._content_min_size())
        too_tall = want.height > area.height
        if too_tall:
            want.width += wx.SystemSettings.GetMetric(wx.SYS_VSCROLL_X, self)
        if base is not None:
            want = wx.Size(max(want.width, base.width), max(want.height, base.height))
        want = wx.Size(max(want.width, 100), max(want.height, 100))
        size = wx.Size(min(want.width, area.width), min(want.height, area.height))
        self.SetSize(size)
        self.Layout()
        if too_tall:
            sizer = self.GetSizer()
            if (
                sizer is not None
                and sizer.CalcMin().height > self.GetClientSize().height
            ):
                self._wrap_in_scroller()
                self.Layout()
        if self.window_save:
            self.window_context.width, self.window_context.height = self.GetSize()
        return size

    def _keep_on_display(self):
        area = self._display_area()
        x, y = self.GetPosition()
        w, h = self.GetSize()
        x = max(area.x, min(x, area.x + area.width - w))
        y = max(area.y, min(y, area.y + area.height - h))
        self.SetPosition((x, y))

    def on_mouse_left_down(self, event):
        # Convert mac Control+left click into right click
        if event.RawControlDown() and not event.ControlDown():
            self.on_menu_request(event)
        else:
            event.Skip()

    def on_menu_request(self, event):
        menu = wx.Menu()
        self.create_menu(menu.AppendSubMenu)

        if menu.MenuItemCount != 0:
            self.PopupMenu(menu)
            menu.Destroy()

    def on_change_window(self, event):
        if self.IsShown():
            try:
                self.window_context.width, self.window_context.height = self.Size
                self.window_context.x, self.window_context.y = self.GetPosition()
            except RuntimeError:
                pass
        event.Skip()

    def create_menu(self, append):
        pass

    def on_close(self, event):
        if self.state == 5:
            event.Veto()
        else:
            if hasattr(self, "window_close_veto") and self.window_close_veto():
                event.Veto()
                return
            self.state = 5
            self.context.close(self.name)
            event.Skip()  # Call 'destroy' as regular.

    def window_open(self):
        self.window_context.themes.set_window_colors(self)

    def restore(self, *args, **kwargs):
        if self.IsIconized():
            self.Iconize(False)

    def window_close(self):
        pass

    def window_preserve(self):
        return True

    def window_menu(self):
        return True

    def module_open(self, *args, **kwargs):
        self.context.close(self.name)
        if self.window_save:
            x, y = self.GetPosition()
            self.window_context.setting(int, "x", x)
            self.window_context.setting(int, "y", y)
            self.SetPosition((self.window_context.x, self.window_context.y))
            display = wx.Display.GetFromWindow(self)
            if display == wx.NOT_FOUND:
                self.SetPosition((x, y))
        self.fit_to_content()
        self._keep_on_display()
        self.Show()
        self.Raise()
        self.window_open()
        # Some windows fill in or resize content in window_open; fit again.
        wx.CallAfter(self._refit)

    def _refit(self):
        try:
            if not self.IsShown():
                return
        except RuntimeError:  # destroyed before the call ran
            return
        self.fit_to_content()
        self._keep_on_display()

    def module_close(self, *args, shutdown=False, **kwargs):
        self.window_close()
        # We put this in the try bracket, as after nuke_settings
        # all the context setting stuff will no longer work
        try:
            if self.window_save:
                self.window_context.setting(bool, "open_on_start", False)
                self.window_context.open_on_start = shutdown and self.window_preserve()
            self.Close()
        except (AttributeError, RuntimeError):
            pass
