"""The X11 selection client against a fake X server (real wire encoding over a socketpair)."""
import os
import struct
import tempfile
import threading
import time
import unittest

from layoutfix import x11sel
from fake_xserver import FakeXServer


class XauthTests(unittest.TestCase):
    def test_reads_the_cookie_for_the_display(self):
        def entry(family, addr, number, name, data):
            out = struct.pack(">H", family)
            for field in (addr, number, name, data):
                out += struct.pack(">H", len(field)) + field
            return out
        with tempfile.NamedTemporaryFile(delete=False) as f:
            f.write(entry(256, b"host", b"1", b"MIT-MAGIC-COOKIE-1", b"\x01" * 16))
            f.write(entry(256, b"host", b"0", b"MIT-MAGIC-COOKIE-1", b"\xab" * 16))
        try:
            self.assertEqual(x11sel.read_xauth_cookie(0, [f.name]), b"\xab" * 16)
            self.assertEqual(x11sel.read_xauth_cookie(1, [f.name]), b"\x01" * 16)
            self.assertIsNone(x11sel.read_xauth_cookie(7, [f.name]))
            self.assertIsNone(x11sel.read_xauth_cookie(0, ["/nonexistent", None]))
        finally:
            os.unlink(f.name)

    def test_parse_display(self):
        self.assertEqual(x11sel.parse_display(":0"), 0)
        self.assertEqual(x11sel.parse_display(":1.0"), 1)
        self.assertEqual(x11sel.parse_display("unix:2"), 2)
        with self.assertRaises(ValueError):
            x11sel.parse_display("remote:0")


class ServerTests(unittest.TestCase):
    def setUp(self):
        self.server = FakeXServer()
        self.conn = x11sel.Connection(sock=self.client_sock(), cookie=b"")
        self.sel = x11sel.Selections(self.conn)

    def client_sock(self):
        return self.server.client

    def tearDown(self):
        self.conn.close()
        self.server.close()

    def wait(self, predicate, timeout=2.0):
        deadline = time.time() + timeout
        while time.time() < deadline:
            if predicate():
                return True
            time.sleep(0.005)
        return False

    def test_setup_parsed_and_window_created_unmapped(self):
        self.assertEqual(self.conn.root, 0x400)
        self.assertEqual(self.conn.id_base, 0x200000)
        self.assertTrue(self.wait(lambda: self.sel.window in self.server.windows))
        self.assertTrue(self.sel.window & 0x200000)

    def test_atoms_round_trip(self):
        a = self.conn.atom("CLIPBOARD")
        self.assertEqual(self.conn.atom("CLIPBOARD"), a)          # cached
        self.assertEqual(self.conn.atom_name(a), "CLIPBOARD")
        self.assertEqual(self.conn.atom("PRIMARY"), 1)

    def test_read_from_nobody_is_none_and_text_is_read(self):
        self.assertIsNone(self.sel.read("CLIPBOARD", "UTF8_STRING", timeout=0.5))
        self.assertEqual(self.sel.read_text("CLIPBOARD", timeout=0.5), "")

        def owner(server, requestor, sel, target, prop, t):
            server.answer_convert(requestor, sel, target, prop, t, server.atom("UTF8_STRING"), 8, "héllo".encode())
        self.server.on_convert = owner
        self.assertEqual(self.sel.read_text("CLIPBOARD"), "héllo")

    def test_targets_are_names(self):
        def owner(server, requestor, sel, target, prop, t):
            atoms = struct.pack("<3I", server.atom("UTF8_STRING"), server.atom("image/png"), server.atom("TARGETS"))
            server.answer_convert(requestor, sel, target, prop, t, 4, 32, atoms)
        self.server.on_convert = owner
        self.assertEqual(self.sel.targets("CLIPBOARD"), ["UTF8_STRING", "image/png", "TARGETS"])

    def test_incr_read_reassembles_chunks(self):
        big = bytes(range(256)) * 1000                             # 256 KB

        def owner(server, requestor, sel, target, prop, t):
            server.answer_convert(requestor, sel, target, prop, t, server.atom("INCR"), 32, struct.pack("<I", len(big)))

            def feed():
                for i in range(0, len(big) + 100_000, 100_000):      # last chunk is empty -> end
                    self.wait(lambda: (requestor, prop) not in server.props)
                    with server.lock:
                        server.props[(requestor, prop)] = (server.atom("image/png"), 8, big[i:i + 100_000])
                        server.sock.sendall(struct.pack("<BxHIIIB", 28, 0, requestor, prop, 1, 0).ljust(32, b"\0"))
            threading.Thread(target=feed, daemon=True).start()
        self.server.on_convert = owner
        res = self.sel.read("CLIPBOARD", "image/png")
        self.assertEqual(res[2], big)

    def test_owning_answers_targets_data_and_refuses_unknown(self):
        self.assertTrue(self.sel.own_text("CLIPBOARD", "abc"))
        clipboard = self.conn.atom("CLIPBOARD")
        owner = self.sel.owned[clipboard][0]
        self.assertEqual(self.server.owners[clipboard], owner)
        requestor, prop = 0x900001, self.server.atom("THEIR_PROP")

        # TARGETS
        self.server.selection_request(owner, requestor, clipboard, self.server.atom("TARGETS"), prop)
        self.sel.serve(0.2, until=lambda: self.server.sent_events)
        self.assertTrue(self.wait(lambda: (requestor, prop) in self.server.props))
        typ, fmt, value = self.server.props[(requestor, prop)]
        names = {self.server.atom_name(a) for a in struct.unpack("<%dI" % (len(value) // 4), value)}
        self.assertEqual((typ, fmt), (4, 32))
        self.assertTrue({"TARGETS", "TIMESTAMP", "UTF8_STRING", "text/plain", "STRING"} <= names)
        self.assertEqual(self.sel.data_requests_since(0), [])      # TARGETS is not a paste

        # data
        self.server.sent_events.clear()
        self.server.selection_request(owner, requestor, clipboard, self.server.atom("UTF8_STRING"), prop)
        self.sel.serve(0.2, until=lambda: self.server.sent_events)
        self.assertEqual(self.server.props[(requestor, prop)][2], b"abc")
        dest, notify = self.server.sent_events[-1]
        self.assertEqual(dest, requestor)
        self.assertEqual(struct.unpack_from("<I", notify, 20)[0], prop)     # property set = success
        self.assertEqual(self.sel.data_requests_since(0)[0][1:], ("CLIPBOARD", "UTF8_STRING"))

        # unknown target -> property None
        self.server.sent_events.clear()
        self.server.selection_request(owner, requestor, clipboard, self.server.atom("image/png"), prop)
        self.sel.serve(0.2, until=lambda: self.server.sent_events)
        self.assertEqual(struct.unpack_from("<I", self.server.sent_events[-1][1], 20)[0], 0)

    def test_incr_write_for_large_data(self):
        self.conn.max_data = 1000
        data = b"x" * 2500
        self.assertTrue(self.sel.own("CLIPBOARD", {"image/png": data}))
        clipboard = self.conn.atom("CLIPBOARD")
        owner = self.sel.owned[clipboard][0]
        requestor, prop = 0x900002, self.server.atom("P")
        self.server.selection_request(owner, requestor, clipboard, self.server.atom("image/png"), prop)
        self.sel.serve(0.2, until=lambda: self.server.sent_events)
        typ, fmt, value = self.server.props[(requestor, prop)]
        self.assertEqual(typ, self.server.atom("INCR"))
        self.assertEqual(struct.unpack("<I", value)[0], 2500)
        received = b""
        for _ in range(4):                                           # 3 chunks + the empty end marker
            with self.server.lock:
                self.server._delete(requestor, prop)                 # requestor consumed the chunk
            self.sel.serve(0.3, until=lambda: (requestor, prop) in self.server.props)
            chunk = self.server.props[(requestor, prop)][2]
            received += chunk
            if not chunk:
                break
        self.assertEqual(received, data)
        self.assertFalse(self.sel._incr)

    def test_new_owner_window_per_write_and_clear(self):
        self.sel.own_text("PRIMARY", "one")
        first = self.sel.owned[1][0]
        self.sel.own_text("PRIMARY", "two")
        second = self.sel.owned[1][0]
        self.assertNotEqual(first, second)                           # mutter re-reads TARGETS for a new owner
        self.sel.serve(0.05)                                         # the stale SelectionClear is ignored
        self.assertIn(1, self.sel.owned)
        self.sel.clear("PRIMARY")
        self.assertNotIn(1, self.sel.owned)
        self.assertTrue(self.wait(lambda: 1 not in self.server.owners))

    def test_selection_clear_from_another_client_drops_ownership(self):
        self.sel.own_text("CLIPBOARD", "mine")
        clipboard = self.conn.atom("CLIPBOARD")
        owner = self.sel.owned[clipboard][0]
        self.server.emit(struct.pack("<BxHIII", 29, 0, 99, owner, clipboard))
        self.sel.serve(0.1, until=lambda: not self.sel.owned)
        self.assertEqual(self.sel.owned, {})


if __name__ == "__main__":
    unittest.main()
