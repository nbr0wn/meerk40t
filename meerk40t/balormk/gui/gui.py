def plugin(service, lifecycle):
    if lifecycle == "service":
        return "provider/device/balor"
    if lifecycle == "invalidate":
        return not service.has_feature("wx")
    if lifecycle == "added":
        # Needed to test wx import.
        import wx  # pylint: disable=unused-import

        from meerk40t.gui.icons import (
            icon_balor_bounds,
            icon_balor_full,
            icon_balor_hull,
            icon_balor_regmarks,
            icons8_center_of_gravity,
            icons8_computer_support,
            icons8_connected,
            icons8_flash_off,
            icons8_flash_on,
            icons8_light_off,
            icons8_light_on,
        )

        from .balorconfig import BalorConfiguration
        from .balorcontroller import BalorController
        from .baloroperationproperties import BalorOperationPanel

        service.register("window/Controller", BalorController)
        service.register("window/Configuration", BalorConfiguration)

        service.register("winpath/Controller", service)
        service.register("winpath/Configuration", service)

        _ = service.kernel.translation

        def connection_state():
            """'connected', 'connecting' or 'disconnected'."""
            driver = service.driver
            try:
                if driver.connected:
                    return "connected"
                if driver.connection.is_connecting:
                    return "connecting"
            except AttributeError:
                pass
            return "disconnected"

        connect_colours = {
            "connected": wx.Colour(0x00, 0xDF, 0x00),
            "connecting": wx.Colour(0xDF, 0xDF, 0x00),
            "disconnected": wx.Colour(0xFF, 0x50, 0x50),
        }

        def toggle_connection(event=None):
            """Same as the Controller window's connection button."""
            controller = service.driver.connection
            state = connection_state()
            if state == "connecting":
                controller.abort_connect()
                controller.set_disable_connect(False)
            elif state == "connected":
                service("usb_disconnect\n")
                controller.set_disable_connect(False)
            else:
                controller.set_disable_connect(False)
                service("usb_connect\n")

        service.register(
            "button/control/Controller",
            {
                "label": _("Connect"),
                "icon": icons8_connected,
                "tip": _(
                    "Connect to or disconnect from the laser. Green: connected, "
                    "yellow: connecting (click to abort), red: not connected. "
                    "Right-click opens the Controller window."
                ),
                "help": "devicebalor",
                "action": toggle_connection,
                "action_right": lambda e: service("window toggle Controller\n"),
                "background": lambda: connect_colours[connection_state()],
            },
        )
        kernel = service.kernel
        if not (
            hasattr(kernel.args, "lock_device_config")
            and kernel.args.lock_device_config
        ):
            service.register(
                "button/device/Configuration",
                {
                    "label": _("Config"),
                    "icon": icons8_computer_support,
                    "tip": _("Opens device-specific configuration window"),
                    "help": "devicebalor",
                    "action": lambda v: service("window toggle Configuration\n"),
                },
            )

        service.register("property/RasterOpNode/Balor", BalorOperationPanel)
        service.register("property/CutOpNode/Balor", BalorOperationPanel)
        service.register("property/EngraveOpNode/Balor", BalorOperationPanel)
        service.register("property/ImageOpNode/Balor", BalorOperationPanel)
        service.register("property/DotsOpNode/Balor", BalorOperationPanel)
        service.register(
            "button/control/Light_On",
            {
                "label": _("Galvo Light"),
                "icon": icons8_light_on,
                "tip": _("Runs outline on selection"),
                "help": "devicebalor",
                "identifier": "light_default",
                "multi": [
                    {
                        "identifier": "live-full",
                        "label": _("Live Full"),
                        "icon": icon_balor_full,
                        "help": "devicebalor",
                        "action": lambda e: service("full-light\n"),
                        "multi_autoexec": False,
                    },
                    # {
                    #     "identifier": "live-regmark",
                    #     "label": _("Regmarks"),
                    #     "icon": icon_balor_regmarks,
                    #     "help": "devicebalor",
                    #     "action": lambda e: service("regmark-light\n"),
                    # },
                    {
                        "identifier": "live",
                        "label": _("Live Bounds"),
                        "icon": icon_balor_bounds,
                        "help": "devicebalor",
                        "action": lambda e: service("select-light\n"),
                        "multi_autoexec": False,
                    },
                    {
                        "identifier": "live-hull",
                        "label": _("Live Hull"),
                        "icon": icon_balor_hull,
                        "help": "devicebalor",
                        "action": lambda e: service("hull-light\n"),
                        "multi_autoexec": False,
                    },
                    {
                        "identifier": "hull",
                        "label": _("Trace Hull"),
                        "icon": icon_balor_hull,
                        "help": "devicebalor",
                        "action": lambda e: service("element* geometry hull light\n"),
                        "multi_autoexec": False,
                    },
                    {
                        "identifier": "box",
                        "label": _("Trace Bounds"),
                        "icon": icon_balor_bounds,
                        "help": "devicebalor",
                        "action": lambda e: service("box light\n"),
                        "multi_autoexec": False,
                    },
                    # {
                    #     "identifier": "ants",
                    #     "label": _("Trace Ants"),
                    #     "action": lambda e: service("element* ants light\n"),
                    # },
                    {
                        "identifier": "full",
                        "label": _("Trace Full"),
                        "icon": icon_balor_full,
                        "help": "devicebalor",
                        "action": lambda e: service("element* geometry light\n"),
                        "multi_autoexec": False,
                    },
                ],
                "toggle": {
                    "label": _("Stop Tracing..."),
                    "icon": icons8_light_off,
                    "tip": _("Turn light off"),
                    "help": "devicebalor",
                    "action": lambda v: service("stop\n"),
                    "signal": "light_simulate",
                },
            },
        )
        service.register(
            "button/control/Redlight",
            {
                "label": _("Red Dot On"),
                "icon": icons8_flash_on,
                "tip": _("Turn Redlight On"),
                "help": "devicebalor",
                "action": lambda v: service("red on\n"),
                "toggle": {
                    "label": _("Red Dot Off"),
                    "action": lambda v: service("red off\n"),
                    "icon": icons8_flash_off,
                    "signal": "red_dot",
                },
            },
        )
        service.register(
            "button/basicediting/Center",
            {
                # Between Paste (priority 0) and Grid (priority 1).
                "priority": 0.5,
                "label": _("Center"),
                "icon": icons8_center_of_gravity,
                "tip": _("Center selection on laserbed"),
                "help": "devicebalor",
                "action": lambda v: service("align bed group xy center center\n"),
                "rule_enabled": lambda cond: bool(service.elements.has_emphasis()),
            },
        )

        from .corscene import register_scene

        register_scene(service)

        service.add_service_delegate(BalorGui(service))


class BalorGui:
    # Class stub.
    def __init__(self, context):
        self.context = context
