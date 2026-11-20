"""
Galvo USB Connection

Performs the required interactions with the Galvo backend through pyusb and libusb.
"""

import time

import usb.core
import usb.util
from usb.backend.libusb1 import LIBUSB_ERROR_ACCESS, LIBUSB_ERROR_NOT_FOUND

from meerk40t.balormk import usbtrace

USB_LOCK_VENDOR = 0x9588
USB_LOCK_PRODUCT = 0x9899

WRITE_ENDPOINT = 0x02  # usb.util.ENDPOINT_OUT|usb.util.ENDPOINT_TYPE_BULK
READ_ENDPOINT = 0x88

# Retry policy (see USBConnection.write / transact).
RESENDS = 3  # extra sends of a 12-byte command whose write or reply timed out
LATE_REPLY_TIMEOUT_MS = 500  # second wait for a reply before resending
LIST_WRITE_TIMEOUT_MS = 1000  # 0xC00 list packets are never resent

# DEBUG CODE FOR POINTING TO CH341A chip.
# USB_LOCK_VENDOR = 0x1A86  # Dev : (1a86) QinHeng Electronics
# USB_LOCK_PRODUCT = 0x5512  # (5512) CH341A
# WRITE_ENDPOINT = 0x02  # usb.util.ENDPOINT_OUT|usb.util.ENDPOINT_TYPE_BULK
# READ_ENDPOINT = 0x82


class ReplyTimeout(ConnectionError):
    """No reply arrived within the read timeout; the device is still open."""


class USBConnection:
    def __init__(self, channel):
        self.channel = channel
        self.devices = {}
        self.interface = {}
        self.backend_error_code = None
        self.timeout = 100

    def find_device(self, index=0):
        _ = self.channel._
        self.channel(_("Using LibUSB to connect."))
        self.channel(_("Finding devices."))
        try:
            devices = list(
                usb.core.find(
                    idVendor=USB_LOCK_VENDOR, idProduct=USB_LOCK_PRODUCT, find_all=True
                )
            )
        except usb.core.USBError as e:
            self.backend_error_code = e.backend_error_code

            self.channel(str(e))
            raise ConnectionRefusedError
        if len(devices) == 0:
            self.channel(_("Devices Not Found."))
            raise ConnectionRefusedError
        for d in devices:
            self.channel(_("Galvo device detected:"))
            string = str(d)
            string = string.replace("\n", "\n\t")
            self.channel(string)
        try:
            device = devices[index]
        except IndexError:
            if self.backend_error_code == LIBUSB_ERROR_ACCESS:
                self.channel(_("Your OS does not give you permissions to access USB."))
                raise PermissionError
            elif self.backend_error_code == LIBUSB_ERROR_NOT_FOUND:
                self.channel(
                    _(
                        "Galvo devices were found. But something else was connected to them."
                    )
                )
            else:
                self.channel(
                    _(
                        "Galvo devices were found but they were rejected by device criteria in Controller."
                    )
                )
            raise ConnectionRefusedError
        return device

    def detach_kernel(self, device, interface):
        _ = self.channel._
        try:
            if device.is_kernel_driver_active(interface.bInterfaceNumber):
                # TODO: This can raise USBError on entity not found.
                try:
                    self.channel(_("Attempting to detach kernel."))
                    device.detach_kernel_driver(interface.bInterfaceNumber)
                    self.channel(_("Kernel detach: Success."))
                except usb.core.USBError as e:
                    self.backend_error_code = e.backend_error_code

                    self.channel(str(e))
                    self.channel(_("Kernel detach: Failed."))
                    raise ConnectionRefusedError
        except NotImplementedError:
            self.channel(
                _("Kernel detach: Not Implemented.")
            )  # Driver does not permit kernel detaching.
            # Non-fatal error.

    def get_active_config(self, device):
        _ = self.channel._
        self.channel(_("Getting Active Config"))
        try:
            interface = device.get_active_configuration()[(0, 0)]
            self.channel(_("Active Config: Success."))
            return interface
        except usb.core.USBError as e:
            self.backend_error_code = e.backend_error_code

            self.channel(str(e))
            self.channel(_("Active Config: Failed."))
            raise ConnectionRefusedError

    def set_config(self, device):
        _ = self.channel._
        self.channel(_("Config Set"))
        try:
            device.set_configuration()
            self.channel(_("Config Set: Success"))
        except usb.core.USBError as e:
            self.backend_error_code = e.backend_error_code

            self.channel(str(e))
            self.channel(
                _(
                    "Config Set: Fail\n(Hint: may recover if you change where the USB is plugged in.)"
                )
            )
            # raise ConnectionRefusedError

    def claim_interface(self, device, interface):
        _ = self.channel._
        try:
            self.channel(_("Attempting to claim interface."))
            usb.util.claim_interface(device, interface)
            self.channel(_("Interface claim: Success"))
        except usb.core.USBError as e:
            self.backend_error_code = e.backend_error_code

            self.channel(str(e))
            self.channel(_("Interface claim: Failed. (Interface is in use.)"))
            raise ConnectionRefusedError
            # Already in use. This is critical.

    def disconnect_detach(self, device, interface):
        _ = self.channel._
        try:
            self.channel(_("Attempting kernel attach"))
            device.attach_kernel_driver(interface.bInterfaceNumber)
            self.channel(_("Kernel attach: Success."))
        except usb.core.USBError as e:
            self.backend_error_code = e.backend_error_code

            self.channel(str(e))
            self.channel(_("Kernel attach: Fail."))
            # Continue and hope it is non-critical.
        except NotImplementedError:
            self.channel(_("Kernel attach: Fail."))

    def unclaim_interface(self, device, interface):
        _ = self.channel._
        try:
            self.channel(_("Attempting to release interface."))
            usb.util.release_interface(device, interface)
            self.channel(_("Interface released."))
        except usb.core.USBError as e:
            self.backend_error_code = e.backend_error_code

            self.channel(str(e))
            self.channel(_("Interface did not exist."))

    def disconnect_dispose(self, device):
        _ = self.channel._
        try:
            self.channel(_("Attempting to dispose resources."))
            usb.util.dispose_resources(device)
            self.channel(_("Dispose Resources: Success"))
        except usb.core.USBError as e:
            self.backend_error_code = e.backend_error_code

            self.channel(str(e))
            self.channel(_("Dispose Resources: Fail"))

    def disconnect_reset(self, device):
        _ = self.channel._
        try:
            self.channel(_("Attempting USB reset."))
            usbtrace.event(
                "RESET", f"bus={device.bus} addr={device.address}", stack=True
            )
            device.reset()
            self.channel(_("USB connection reset."))
        except usb.core.USBError as e:
            self.backend_error_code = e.backend_error_code

            self.channel(str(e))
            self.channel(_("USB connection did not exist."))

    def bus(self, index):
        return self.devices[index].bus

    def address(self, index):
        return self.devices[index].address

    def is_open(self, index=0):
        try:
            dev = self.devices[index]
            if dev:
                return True
        except KeyError:
            pass
        return False

    def open(self, index=0):
        """Opens device, returns index."""
        _ = self.channel._
        usbtrace.event("OPEN", f"index={index}", stack=True)
        self.channel(_("Attempting connection to USB."))
        try:
            device = self.find_device(index)
            self.devices[index] = device
            self.set_config(device)
            try:
                interface = self.get_active_config(device)
                self.interface[index] = interface
                self.detach_kernel(device, interface)
                try:
                    self.claim_interface(device, interface)
                except ConnectionRefusedError:
                    # Attempting interface cycle.
                    self.unclaim_interface(device, interface)
                    self.claim_interface(device, interface)
            except usb.core.USBError:
                self.channel(_("Device failed during detach and claim"))
            self.channel(_("USB Connected."))
            usbtrace.event("OPENED", f"index={index}")
            return index
        except usb.core.NoBackendError as e:
            self.channel(str(e))
            from platform import system

            osname = system()
            if osname == "Windows":
                self.channel(
                    _(
                        "Did you install the libusb driver via Zadig (https://zadig.akeo.ie/)?"
                    )
                )
                self.channel(
                    _(
                        "Consult the wiki: https://github.com/meerk40t/meerk40t/wiki/Install%3A-Windows"
                    )
                )
            self.channel(_("PyUsb detected no backend LibUSB driver."))
            return -2
        except ConnectionRefusedError:
            self.channel(_("Connection to USB failed.\n"))
            usbtrace.event(
                "OPEN_FAILED", f"index={index} backend={self.backend_error_code}"
            )
            return -1

    def close(self, index=0):
        """Closes device."""
        _ = self.channel._
        usbtrace.event("CLOSE", f"index={index}", stack=True)
        device = self.devices.get(index)
        self.channel(_("Attempting disconnection from USB."))
        if device is not None:
            interface = self.interface.get(index)
            try:
                if interface is not None:
                    self.disconnect_detach(device, interface)
                    self.unclaim_interface(device, interface)
                self.disconnect_dispose(device)
                self.disconnect_reset(device)
                self.channel(_("USB Disconnection Successful.\n"))
            except ConnectionError:
                pass
            finally:
                self.devices.pop(index, None)
                self.interface.pop(index, None)

    def _device(self, index):
        try:
            return self.devices[index]
        except KeyError:
            raise ConnectionError("Not Connected.")

    def _fail(self, index, reason):
        """
        Unrecoverable at this layer: drop the device so the controller reconnects
        and re-initialises the board (with its own bounded retry count).
        """
        self.backend_error_code = getattr(reason, "backend_error_code", None)
        self.channel(str(reason))
        usbtrace.event("FAIL", f"index={index} {reason!r}")
        self.close(index)
        raise ConnectionError(str(reason))

    def write(self, index=0, packet=None):
        """
        Write one packet. A 12-byte command that times out (not accepted by the
        board) is resent as-is. A list packet is not resent: a timed-out bulk
        transfer may have been partly accepted, and a resend would duplicate list
        data. Any other error drops the device.
        """
        packet_length = len(packet)
        assert packet_length == 0xC or packet_length == 0xC00
        device = self._device(index)
        if packet_length == 0xC00:
            timeout, attempts = LIST_WRITE_TIMEOUT_MS, 1
        else:
            timeout, attempts = self.timeout, 1 + RESENDS
        last = None
        for attempt in range(attempts):
            t0 = time.perf_counter()
            try:
                device.write(endpoint=WRITE_ENDPOINT, data=packet, timeout=timeout)
                usbtrace.transfer("W", packet, time.perf_counter() - t0)
                return
            except usb.core.USBTimeoutError as e:
                usbtrace.error("write", e, packet, time.perf_counter() - t0, attempt)
                last = e
            except usb.core.USBError as e:
                usbtrace.error("write", e, packet, time.perf_counter() - t0, attempt)
                self._fail(index, e)
        self._fail(index, last)

    def read(self, index=0, timeout=None):
        """
        Read one 8-byte reply. Raises ReplyTimeout if nothing arrives in time
        (the device is kept); any other error drops the device.
        """
        device = self._device(index)
        if timeout is None:
            timeout = self.timeout
        t0 = time.perf_counter()
        try:
            r = device.read(endpoint=READ_ENDPOINT, size_or_buffer=8, timeout=timeout)
            usbtrace.transfer("R", b"", time.perf_counter() - t0, r)
            return r
        except usb.core.USBTimeoutError as e:
            usbtrace.error("read", e, None, time.perf_counter() - t0)
            raise ReplyTimeout(str(e)) from e
        except usb.core.USBError as e:
            usbtrace.error("read", e, None, time.perf_counter() - t0)
            self._fail(index, e)

    def transact(self, index=0, packet=None):
        """
        Send a 12-byte command and return its reply. A missing reply is waited
        for a second time (it may be late) before the command is resent, so a
        late reply is never left queued to be mistaken for the next command's.
        """
        for attempt in range(1 + RESENDS):
            if attempt:
                usbtrace.event("RESEND", f"attempt={attempt}")
            self.write(index, packet)
            try:
                return self.read(index)
            except ReplyTimeout:
                pass
            try:
                return self.read(index, timeout=LATE_REPLY_TIMEOUT_MS)
            except ReplyTimeout:
                pass
        self._fail(index, ReplyTimeout(f"No reply after {1 + RESENDS} sends"))
