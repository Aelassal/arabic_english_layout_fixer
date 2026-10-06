"""A tiny fake X server for tests: speaks the subset of the protocol layoutfix.x11sel uses, over a
socketpair, in a thread. It stores properties, selection owners and the events the client sends."""
import socket
import struct
import threading

PROPERTY_CHANGE_MASK = 1 << 22


def _pad(n):
    return (-n) % 4


class FakeXServer:
    def __init__(self):
        self.sock, self.client = socket.socketpair()
        self.atoms = {"PRIMARY": 1, "ATOM": 4, "INTEGER": 19, "STRING": 31}
        self.props = {}                     # (window, atom) -> (type, fmt, bytes)
        self.owners = {}                    # selection atom -> window
        self.windows = set()
        self.listening = set()              # windows the client wants PropertyNotify for
        self.sent_events = []               # (destination, 32-byte event) via SendEvent
        self.on_convert = None              # hook(server, requestor, selection, target, prop, time)
        self.seq = 0
        self.lock = threading.Lock()
        self.thread = threading.Thread(target=self._serve, daemon=True)
        self.thread.start()

    # ------------------------------------------------------------- utilities
    def atom(self, name):
        if name not in self.atoms:
            self.atoms[name] = 100 + len(self.atoms)
        return self.atoms[name]

    def atom_name(self, atom):
        return next(n for n, a in self.atoms.items() if a == atom)

    def _recv(self, n):
        buf = b""
        while len(buf) < n:
            chunk = self.sock.recv(n - len(buf))
            if not chunk:
                raise ConnectionError
            buf += chunk
        return buf

    def _reply(self, seq, body32=b"", extra=b""):
        """body32: the 24 bytes after the 8-byte header; extra: data after the 32-byte reply."""
        body32 = body32.ljust(24, b"\0")
        extra += b"\0" * _pad(len(extra))
        self.sock.sendall(struct.pack("<BxHI", 1, seq, len(extra) // 4) + body32 + extra)

    def emit(self, event):
        """Deliver a 32-byte event to the client (as another client / the server would)."""
        with self.lock:
            self.sock.sendall(event.ljust(32, b"\0"))

    def property_notify(self, window, atom, state, time=1000):
        self.emit(struct.pack("<BxHIIIB", 28, self.seq, window, atom, time, state))

    def selection_request(self, owner, requestor, selection, target, prop, time=1234):
        self.emit(struct.pack("<BxHIIIIII", 30, 0, time, owner, requestor, selection, target, prop))

    # ------------------------------------------------------------- main loop
    def _serve(self):
        try:
            self._setup()
            while True:
                head = self._recv(4)
                opcode, data, length = struct.unpack("<BBH", head)
                body = self._recv(length * 4 - 4)
                self.seq = (self.seq + 1) & 0xFFFF
                self._handle(opcode, data, body)
        except (ConnectionError, OSError):
            pass

    def _setup(self):
        head = self._recv(12)
        _, _, _, nlen, dlen = struct.unpack("<BxHHHHxx", head)
        self._recv(nlen + _pad(nlen) + dlen + _pad(dlen))
        screen = struct.pack("<IIIIIHHHHHHIBBBB", 0x400, 0x20, 0xFFFFFF, 0, 0, 800, 600, 200, 150, 1, 1,
                             0x21, 0, 0, 24, 0)
        body = struct.pack("<IIIIHHBBBBBBBBxxxx", 12345, 0x200000, 0x1FFFFF, 256, 0, 65535, 1, 0,
                           0, 0, 32, 32, 8, 255) + screen
        self.sock.sendall(struct.pack("<BBHHH", 1, 0, 11, 0, len(body) // 4) + body)

    def _handle(self, opcode, data, body):
        with self.lock:
            if opcode == 1:                                     # CreateWindow
                wid, parent, *_ = struct.unpack_from("<II", body)
                self.windows.add(wid)
                mask = struct.unpack_from("<I", body, 24)[0]
                if mask & (1 << 11) and struct.unpack_from("<I", body, 28)[0] & PROPERTY_CHANGE_MASK:
                    self.listening.add(wid)
            elif opcode == 2:                                   # ChangeWindowAttributes
                wid, _mask, value = struct.unpack_from("<III", body)
                (self.listening.add if value & PROPERTY_CHANGE_MASK else self.listening.discard)(wid)
            elif opcode == 4:                                   # DestroyWindow
                self.windows.discard(struct.unpack_from("<I", body)[0])
            elif opcode == 16:                                  # InternAtom
                n = struct.unpack_from("<H", body)[0]
                self._reply(self.seq, struct.pack("<I", self.atom(body[4:4 + n].decode())))
            elif opcode == 17:                                  # GetAtomName
                name = self.atom_name(struct.unpack_from("<I", body)[0]).encode()
                self._reply(self.seq, struct.pack("<H", len(name)), name)
            elif opcode == 18:                                  # ChangeProperty
                wid, prop, typ, fmt, n = struct.unpack_from("<IIIBxxxI", body)
                new = body[20:20 + n * (fmt // 8)]
                if data == 2 and (wid, prop) in self.props:     # append
                    new = self.props[(wid, prop)][2] + new
                self.props[(wid, prop)] = (typ, fmt, new)
                if wid in self.listening:
                    self.sock.sendall(struct.pack("<BxHIIIB", 28, self.seq, wid, prop, 5000 + self.seq, 0).ljust(32, b"\0"))
            elif opcode == 19:                                  # DeleteProperty
                wid, prop = struct.unpack_from("<II", body)
                self._delete(wid, prop)
            elif opcode == 20:                                  # GetProperty
                wid, prop, _typ, _off, _len = struct.unpack_from("<IIIII", body)
                entry = self.props.get((wid, prop))
                if entry is None:
                    self._reply(self.seq, b"")
                else:
                    typ, fmt, value = entry
                    self.sock.sendall(struct.pack("<BBHIIII", 1, fmt, self.seq, (len(value) + _pad(len(value))) // 4,
                                                  typ, 0, len(value) // (fmt // 8)).ljust(32, b"\0")
                                      + value + b"\0" * _pad(len(value)))
                    if data == 1:
                        self._delete(wid, prop)
            elif opcode == 22:                                  # SetSelectionOwner
                wid, sel, _t = struct.unpack_from("<III", body)
                old = self.owners.get(sel)
                if wid:
                    self.owners[sel] = wid
                else:
                    self.owners.pop(sel, None)
                if old and old != wid and old in self.windows:
                    self.sock.sendall(struct.pack("<BxHIII", 29, self.seq, _t, old, sel).ljust(32, b"\0"))
            elif opcode == 23:                                  # GetSelectionOwner
                self._reply(self.seq, struct.pack("<I", self.owners.get(struct.unpack_from("<I", body)[0], 0)))
            elif opcode == 24:                                  # ConvertSelection
                requestor, sel, target, prop, t = struct.unpack_from("<IIIII", body)
                if self.on_convert:
                    self.on_convert(self, requestor, sel, target, prop, t)
                else:                                           # nobody owns it
                    self.sock.sendall(struct.pack("<BxHIIIII", 31, self.seq, t, requestor, sel, target, 0).ljust(32, b"\0"))
            elif opcode == 25:                                  # SendEvent
                dest = struct.unpack_from("<I", body)[0]
                self.sent_events.append((dest, body[8:40]))

    def _delete(self, wid, prop):
        if self.props.pop((wid, prop), None) is not None and wid in self.listening:
            self.sock.sendall(struct.pack("<BxHIIIB", 28, self.seq, wid, prop, 6000 + self.seq, 1).ljust(32, b"\0"))

    # helpers for scripted foreign owners -----------------------------------
    def answer_convert(self, requestor, sel, target, prop, t, typ, fmt, value):
        """Behave like a foreign owner: put the data on the requestor and send SelectionNotify."""
        self.props[(requestor, prop)] = (typ, fmt, value)
        self.sock.sendall(struct.pack("<BxHIIIII", 31, self.seq, t, requestor, sel, target, prop).ljust(32, b"\0"))

    def close(self):
        self.sock.close()
