"""
USB flight recorder for the galvo (LMC) connection.

Enabled by setting MK_USB_TRACE to a file path. Every transfer is kept in an
in-memory ring buffer; errors, opens, closes and resets are written to the file
immediately (with the calling stack), and the ring buffer is dumped on the
first error of each burst so the lead-up is preserved.
"""

import collections
import os
import threading
import time
import traceback

PATH = os.environ.get("MK_USB_TRACE")
RING_SIZE = int(os.environ.get("MK_USB_TRACE_RING", "4000"))

_lock = threading.Lock()
_ring = collections.deque(maxlen=RING_SIZE)
_file = None
_last_dump = 0.0


def enabled():
    return bool(PATH)


def _out():
    global _file
    if _file is None:
        _file = open(PATH, "a", buffering=1)
        _file.write(f"\n===== trace start pid={os.getpid()} {time.strftime('%F %T')}\n")
    return _file


def _stamp():
    t = time.time()
    return (
        time.strftime("%H:%M:%S", time.localtime(t)) + f".{int(t * 1e6) % 1000000:06d}"
    )


def _fmt(kind, detail):
    return f"{_stamp()} [{threading.current_thread().name}] {kind} {detail}"


def transfer(op, data, dt, result=None):
    """Record a successful transfer (ring buffer only)."""
    if not PATH:
        return
    head = bytes(data[:12]).hex(" ") if data is not None else ""
    n = len(data) if data is not None else 0
    extra = f" -> {bytes(result).hex(' ')}" if result is not None else ""
    with _lock:
        _ring.append(_fmt(op, f"len={n} {dt * 1000:.1f}ms {head}{extra}"))


def event(kind, detail="", stack=False):
    """Record an event (ring buffer + file)."""
    if not PATH:
        return
    line = _fmt(kind, detail)
    with _lock:
        _ring.append(line)
        f = _out()
        f.write(line + "\n")
        if stack:
            f.write("".join("    " + s for s in traceback.format_stack(limit=12)[:-1]))


def error(op, exc, data=None, dt=0.0, attempt=0):
    """Record a USB error; dump the ring buffer if this starts a new burst."""
    if not PATH:
        return
    global _last_dump
    head = bytes(data[:12]).hex(" ") if data is not None else ""
    detail = (
        f"{op} attempt={attempt} after {dt * 1000:.1f}ms "
        f"errno={getattr(exc, 'errno', None)} "
        f"backend={getattr(exc, 'backend_error_code', None)} "
        f"'{exc}' data={head}"
    )
    with _lock:
        f = _out()
        now = time.time()
        if now - _last_dump > 5.0:
            f.write(f"----- ring buffer ({len(_ring)} entries) before error -----\n")
            for line in _ring:
                f.write(line + "\n")
            f.write("----- end ring buffer -----\n")
            _ring.clear()
        _last_dump = now
        line = _fmt("ERROR", detail)
        _ring.append(line)
        f.write(line + "\n")
        f.write("".join("    " + s for s in traceback.format_stack(limit=12)[:-1]))
