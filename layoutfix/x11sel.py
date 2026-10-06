"""Minimal X11 selection client, standard library only.

Why this exists: GNOME's Wayland compositor offers no data-control protocol, so wl-clipboard has to open
a real (focused) window for every call. Those windows make the dock relayout ("vibrate"), the shell lag,
and in one case crash. mutter bridges CLIPBOARD and PRIMARY between Wayland and X11 (XWayland) in both
directions, and an X11 window that is never *mapped* has no Wayland surface at all. So on Wayland we talk
to XWayland with a tiny X11 client. The same code serves plain X11 sessions (no xclip needed).

Only the handful of requests a selection owner/requestor needs is implemented (ICCCM 2, with INCR for
large data). Nothing here ever maps a window or sends input.
"""
import glob
import os
import select
import socket
import struct
import time

# Predefined atoms
XA_PRIMARY, XA_ATOM, XA_INTEGER, XA_STRING = 1, 4, 19, 31
INCR_CHUNK = 200_000                 # bytes per INCR chunk; smaller data goes in one property
_PROPERTY_CHANGE_MASK = 1 << 22
_CW_EVENT_MASK = 1 << 11

# Event codes
PROPERTY_NOTIFY, SELECTION_CLEAR, SELECTION_REQUEST, SELECTION_NOTIFY = 28, 29, 30, 31

TEXT_TARGETS = ("UTF8_STRING", "text/plain;charset=utf-8", "text/plain", "STRING", "TEXT")
META_TARGETS = {"TARGETS", "TIMESTAMP", "MULTIPLE", "SAVE_TARGETS", "DELETE", "INCR"}


class X11Error(Exception):
    pass


def _pad(n):
    return (-n) % 4


def read_xauth_cookie(display_number, paths=None):
    """MIT-MAGIC-COOKIE-1 for the display, from $XAUTHORITY / ~/.Xauthority / mutter's auth file."""
    if paths is None:
        paths = [os.environ.get("XAUTHORITY"), os.path.expanduser("~/.Xauthority")]
        paths += glob.glob(f"/run/user/{os.getuid()}/.mutter-Xwaylandauth.*")
    wanted = str(display_number).encode()
    for path in paths:
        if not path or not os.path.isfile(path):
            continue
        try:
            with open(path, "rb") as f:
                data = f.read()
        except OSError:
            continue
        pos = 0
        while pos + 2 <= len(data):
            fields = []
            pos += 2                                            # family
            for _ in range(4):                                  # address, number, name, data
                if pos + 2 > len(data):
                    return None
                n = struct.unpack_from(">H", data, pos)[0]
                fields.append(data[pos + 2:pos + 2 + n])
                pos += 2 + n
            _addr, number, name, cookie = fields
            if name == b"MIT-MAGIC-COOKIE-1" and number in (wanted, b""):
                return cookie
    return None


def parse_display(display):
    """':0', ':0.1', 'unix:0' -> 0. Raises ValueError for TCP displays we do not speak to."""
    host, _, rest = display.rpartition(":")
    if host not in ("", "unix"):
        raise ValueError(f"only local displays are supported, not {display!r}")
    return int(rest.split(".")[0])


class Connection:
    """One X11 connection with a queue of unsolicited events."""

    def __init__(self, display=None, sock=None, cookie=None):
        self.events = []
        self.atoms = {}
        self.names = {}
        self._seq = 0
        self._next_id = 0
        if sock is None:
            number = parse_display(display or os.environ.get("DISPLAY", ""))
            cookie = cookie if cookie is not None else (read_xauth_cookie(number) or b"")
            sock = self._connect(number)
        self.sock = sock
        self._setup(cookie)

    @staticmethod
    def _connect(number):
        last = None
        for addr in (f"/tmp/.X11-unix/X{number}", f"\0/tmp/.X11-unix/X{number}"):
            s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            try:
                s.connect(addr)
                return s
            except OSError as exc:
                last = exc
                s.close()
        raise X11Error(f"cannot connect to display :{number}: {last}")

    def _setup(self, cookie):
        name = b"MIT-MAGIC-COOKIE-1" if cookie else b""
        msg = struct.pack("<BxHHHHxx", ord("l"), 11, 0, len(name), len(cookie))
        msg += name + b"\0" * _pad(len(name)) + cookie + b"\0" * _pad(len(cookie))
        self.sock.sendall(msg)
        head = self._recv(8)
        status, _reason_len, _major, _minor, length = struct.unpack("<BBHHH", head)
        body = self._recv(length * 4)
        if status != 1:
            raise X11Error("X server refused the connection: " + body[:head[1]].decode("latin-1").strip())
        (_release, self.id_base, id_mask, _motion, vendor_len, self.max_request_len,
         _nscreens, nformats) = struct.unpack_from("<IIIIHHBB", body)
        self._id_shift = (id_mask & -id_mask).bit_length() - 1
        self._id_max = id_mask >> self._id_shift
        pos = 32 + vendor_len + _pad(vendor_len) + 8 * nformats
        self.root = struct.unpack_from("<I", body, pos)[0]
        self.max_data = min(INCR_CHUNK, (self.max_request_len * 4 - 24) // 4 * 4)

    # ------------------------------------------------------------ wire helpers
    def _recv(self, n):
        buf = b""
        while len(buf) < n:
            chunk = self.sock.recv(n - len(buf))
            if not chunk:
                raise X11Error("X connection closed")
            buf += chunk
        return buf

    def new_id(self):
        self._next_id += 1
        if self._next_id > self._id_max:
            raise X11Error("out of X resource ids")
        return self.id_base | (self._next_id << self._id_shift)

    def _send(self, opcode, data_byte, body):
        """Send one request; returns its sequence number."""
        assert len(body) % 4 == 0
        self._seq = (self._seq + 1) & 0xFFFF
        self.sock.sendall(struct.pack("<BBH", opcode, data_byte, 1 + len(body) // 4) + body)
        return self._seq

    def _read_packet(self):
        pkt = self._recv(32)
        if pkt[0] == 1:                                         # reply: may carry extra data
            extra = struct.unpack_from("<I", pkt, 4)[0]
            pkt += self._recv(extra * 4)
        return pkt

    def _dispatch(self, pkt, waiting_for):
        kind = pkt[0] & 0x7F
        seq = struct.unpack_from("<H", pkt, 2)[0]
        if kind == 1:
            return pkt if seq == waiting_for else None
        if kind == 0:
            if seq == waiting_for:
                raise X11Error(f"X error {pkt[1]} (sequence {seq})")
            return None
        self.events.append(pkt)
        return None

    def _reply(self, seq):
        while True:
            pkt = self._dispatch(self._read_packet(), seq)
            if pkt is not None:
                return pkt

    def next_event(self, timeout):
        """One queued/incoming event packet, or None after `timeout` seconds."""
        if self.events:
            return self.events.pop(0)
        deadline = time.monotonic() + timeout
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return None
            ready, _, _ = select.select([self.sock], [], [], remaining)
            if not ready:
                return None
            self._dispatch(self._read_packet(), None)
            if self.events:
                return self.events.pop(0)

    def wait_event(self, timeout, match):
        """First event packet for which match(code, pkt) is true, keeping the others queued."""
        deadline = time.monotonic() + timeout
        skipped = []
        try:
            while True:
                pkt = self.next_event(max(0.0, deadline - time.monotonic()))
                if pkt is None:
                    return None
                if match(pkt[0] & 0x7F, pkt):
                    return pkt
                skipped.append(pkt)
        finally:
            self.events[:0] = skipped

    # ----------------------------------------------------------------- requests
    def create_window(self):
        """An InputOnly child of the root that is never mapped: no surface, no focus, invisible."""
        wid = self.new_id()
        body = struct.pack("<IIhhHHHHIII", wid, self.root, -1, -1, 1, 1, 0, 2, 0,
                           _CW_EVENT_MASK, _PROPERTY_CHANGE_MASK)
        self._send(1, 0, body)
        return wid

    def destroy_window(self, wid):
        self._send(4, 0, struct.pack("<I", wid))

    def select_property_events(self, wid, enable):
        self._send(2, 0, struct.pack("<III", wid, _CW_EVENT_MASK, _PROPERTY_CHANGE_MASK if enable else 0))

    def atom(self, name):
        if name not in self.atoms:
            raw = name.encode("latin-1")
            seq = self._send(16, 0, struct.pack("<Hxx", len(raw)) + raw + b"\0" * _pad(len(raw)))
            self.atoms[name] = struct.unpack_from("<I", self._reply(seq), 8)[0]
            self.names[self.atoms[name]] = name
        return self.atoms[name]

    def atom_name(self, atom):
        if atom not in self.names:
            seq = self._send(17, 0, struct.pack("<I", atom))
            reply = self._reply(seq)
            n = struct.unpack_from("<H", reply, 8)[0]
            self.names[atom] = reply[32:32 + n].decode("latin-1")
            self.atoms[self.names[atom]] = atom
        return self.names[atom]

    def change_property(self, wid, prop, type_atom, fmt, data, mode=0):
        unit = fmt // 8
        body = struct.pack("<IIIBxxxI", wid, prop, type_atom, fmt, len(data) // unit) + data + b"\0" * _pad(len(data))
        self._send(18, mode, body)

    def delete_property(self, wid, prop):
        self._send(19, 0, struct.pack("<II", wid, prop))

    def get_property(self, wid, prop, delete=True):
        """(type_atom, format, bytes) of a whole property, or None when it does not exist."""
        seq = self._send(20, 1 if delete else 0, struct.pack("<IIIII", wid, prop, 0, 0, 0xFFFFFFFF))
        reply = self._reply(seq)
        fmt = reply[1]
        type_atom, _after, n = struct.unpack_from("<III", reply, 8)
        if type_atom == 0:
            return None
        return type_atom, fmt, reply[32:32 + n * (fmt // 8)]

    def set_selection_owner(self, selection, wid, timestamp):
        self._send(22, 0, struct.pack("<III", wid, selection, timestamp))

    def get_selection_owner(self, selection):
        seq = self._send(23, 0, struct.pack("<I", selection))
        return struct.unpack_from("<I", self._reply(seq), 8)[0]

    def convert_selection(self, requestor, selection, target, prop, timestamp):
        self._send(24, 0, struct.pack("<IIIII", requestor, selection, target, prop, timestamp))

    def send_event(self, destination, event):
        assert len(event) == 32
        self._send(25, 0, struct.pack("<II", destination, 0) + event)

    def server_time(self, wid):
        """A fresh server timestamp (ICCCM: never pass CurrentTime for selections)."""
        prop = self.atom("LAYOUTFIX_TIME")
        self.change_property(wid, prop, XA_INTEGER, 32, b"", mode=2)   # append nothing -> PropertyNotify
        pkt = self.wait_event(0.5, lambda code, p: code == PROPERTY_NOTIFY
                              and struct.unpack_from("<II", p, 4) == (wid, prop))
        return struct.unpack_from("<I", pkt, 12)[0] if pkt else 0      # 0 = CurrentTime as a last resort

    def close(self):
        try:
            self.sock.close()
        except OSError:
            pass


# ------------------------------------------------------------------ high level
def _event_fields(pkt, count):
    return struct.unpack_from("<" + "I" * count, pkt, 4)


class Selections:
    """Read selections and own them (serving requests) through one X11 connection."""

    def __init__(self, conn):
        self.conn = conn
        self.window = conn.create_window()                     # requestor window
        self.prop = conn.atom("LAYOUTFIX_SEL")
        self.owned = {}                                         # selection atom -> (window, {target atom: bytes})
        self._incr = {}                                         # (requestor, prop) -> [data, offset]
        self.served = []                                        # (monotonic time, selection name, target name)

    # ---------------------------------------------------------------- reading
    def targets(self, selection, timeout=2.0):
        res = self.read(selection, "TARGETS", timeout)
        if not res or res[1] != 32:
            return []
        atoms = struct.unpack("<%dI" % (len(res[2]) // 4), res[2])
        return [self.conn.atom_name(a) for a in atoms if a]

    def read(self, selection, target, timeout=2.0):
        """(type_atom, format, bytes) or None when nobody owns the selection / target refused."""
        conn = self.conn
        sel, tgt = conn.atom(selection), conn.atom(target)
        conn.convert_selection(self.window, sel, tgt, self.prop, conn.server_time(self.window))
        deadline = time.monotonic() + timeout
        pkt = conn.wait_event(timeout, lambda code, p: code == SELECTION_NOTIFY
                              and _event_fields(p, 3)[1:] == (self.window, sel))
        if pkt is None or _event_fields(pkt, 5)[4] == 0:
            return None
        res = conn.get_property(self.window, self.prop)
        if res is None:
            return None
        type_atom, fmt, data = res
        if type_atom != conn.atom("INCR"):
            return type_atom, fmt, data
        chunks = []                                             # INCR: owner sends the data in pieces
        while True:
            pkt = conn.wait_event(max(0.0, deadline - time.monotonic()),
                                  lambda code, p: code == PROPERTY_NOTIFY and p[16] == 0
                                  and _event_fields(p, 2) == (self.window, self.prop))
            if pkt is None:
                return None
            res = conn.get_property(self.window, self.prop)
            if res is None or not res[2]:
                return (res[0], res[1], b"".join(chunks)) if res else None
            chunks.append(res[2])

    def read_text(self, selection, timeout=2.0):
        res = self.read(selection, "UTF8_STRING", timeout)
        return res[2].decode("utf-8", "replace") if res else ""

    # ----------------------------------------------------------------- owning
    def own(self, selection, offers):
        """Take `selection` offering {target name: bytes}. Text should be offered as all TEXT_TARGETS."""
        conn = self.conn
        sel = conn.atom(selection)
        wid = conn.create_window()                              # a new owner window: mutter re-reads TARGETS
        conn.set_selection_owner(sel, wid, conn.server_time(self.window))
        ok = conn.get_selection_owner(sel) == wid
        old = self.owned.pop(sel, None)
        if ok:
            self.owned[sel] = (wid, {conn.atom(t): d for t, d in offers.items()})
        if old:
            conn.destroy_window(old[0])
        return ok

    def own_text(self, selection, text):
        data = text.encode("utf-8")
        return self.own(selection, {t: data for t in TEXT_TARGETS})

    def clear(self, selection):
        conn = self.conn
        sel = conn.atom(selection)
        conn.set_selection_owner(sel, 0, conn.server_time(self.window))
        old = self.owned.pop(sel, None)
        if old:
            conn.destroy_window(old[0])

    def serve(self, seconds, until=None):
        """Answer requests for up to `seconds`; stop early when until() becomes true."""
        deadline = time.monotonic() + seconds
        while True:
            if until and until():
                return
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return
            pkt = self.conn.next_event(remaining)
            if pkt is not None:
                self.handle(pkt)

    def handle(self, pkt):
        code = pkt[0] & 0x7F
        if code == SELECTION_REQUEST:
            self._answer(pkt)
        elif code == SELECTION_CLEAR:
            _t, owner, sel = _event_fields(pkt, 3)
            if sel in self.owned and self.owned[sel][0] == owner:
                del self.owned[sel]
        elif code == PROPERTY_NOTIFY and pkt[16] == 1:         # requestor deleted a chunk: send the next
            self._incr_continue(_event_fields(pkt, 2))

    def _answer(self, pkt):
        conn = self.conn
        timestamp, owner, requestor, sel, target, prop = _event_fields(pkt, 6)
        prop = prop or target
        entry = self.owned.get(sel)
        answered = 0
        if entry and entry[0] == owner:
            offers = entry[1]
            if target == conn.atom("TARGETS"):
                atoms = [conn.atom("TARGETS"), conn.atom("TIMESTAMP"), *offers]
                conn.change_property(requestor, prop, XA_ATOM, 32, struct.pack("<%dI" % len(atoms), *atoms))
                answered = prop
            elif target == conn.atom("TIMESTAMP"):
                conn.change_property(requestor, prop, XA_INTEGER, 32, struct.pack("<I", timestamp))
                answered = prop
            elif target in offers:
                data = offers[target]
                if len(data) > conn.max_data:
                    conn.select_property_events(requestor, True)
                    conn.change_property(requestor, prop, conn.atom("INCR"), 32, struct.pack("<I", len(data)))
                    self._incr[(requestor, prop)] = [data, 0, target]
                else:
                    conn.change_property(requestor, prop, target, 8, data)
                answered = prop
                self.served.append((time.monotonic(), conn.atom_name(sel), conn.atom_name(target)))
        notify = struct.pack("<BxHIIIII", SELECTION_NOTIFY, 0, timestamp, requestor, sel, target, answered)
        conn.send_event(requestor, notify + b"\0" * (32 - len(notify)))

    def _incr_continue(self, key):
        state = self._incr.get(key)
        if state is None:
            return
        data, offset, target = state
        requestor, prop = key
        chunk = data[offset:offset + self.conn.max_data]
        self.conn.change_property(requestor, prop, target, 8, chunk)
        if chunk:
            state[1] = offset + len(chunk)
        else:                                                   # zero-length chunk ends the transfer
            del self._incr[key]
            self.conn.select_property_events(requestor, False)

    def data_requests_since(self, t):
        return [(when, sel, tgt) for when, sel, tgt in self.served if when >= t]


def connect(display=None):
    return Selections(Connection(display))
