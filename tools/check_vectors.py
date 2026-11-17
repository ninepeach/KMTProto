#!/usr/bin/env python3
"""Validate KMTProto V1 golden Frames (including P0/P1 RESUME/ERROR changes)."""
import pathlib
import re
import struct

ROOT = pathlib.Path(__file__).resolve().parents[1]
SOURCE = ROOT / "spec" / "golden-vectors.md"

TEXT_MAX = 255
DETAIL_MAX = 1024
FRAME_MIN, FRAME_MAX = 4096, 1048576

class Reader:
    def __init__(self, raw):
        self.raw, self.pos = raw, 0
    def take(self, n):
        if n < 0 or self.pos + n > len(self.raw):
            raise ValueError("truncated")
        x = self.raw[self.pos:self.pos+n]
        self.pos += n
        return x
    def num(self, n):
        return int.from_bytes(self.take(n), "big")
    def boolean(self):
        v = self.num(1)
        if v not in (0, 1):
            raise ValueError("boolean")
        return v
    def ident(self):
        if not any(self.take(16)):
            raise ValueError("zero identifier")
    def text(self, allow_empty=False, limit=TEXT_MAX):
        n = self.num(2)
        if n == 0 and not allow_empty:
            raise ValueError("empty text")
        if n > limit:
            raise ValueError("text too long")
        x = self.take(n).decode("utf-8")  # strict: rejects overlong forms and surrogates
        if "\x00" in x:
            raise ValueError("NUL text")
        return x
    def blob(self):
        self.take(self.num(4))
    def caps(self):
        count, prev = self.num(2), 0
        if count > 64:
            raise ValueError("cap count")
        for _ in range(count):
            code = self.num(2)
            if code <= prev:  # also rejects code 0
                raise ValueError("cap order")
            prev = code
    def client_limits(self):
        max_frame, max_sync = self.num(4), self.num(4)
        if not FRAME_MIN <= max_frame <= FRAME_MAX: raise ValueError("client max_frame_bytes")
        if not max_sync: raise ValueError("client max_sync_entries")
    def cursor(self):
        self.text()
        self.num(8)
    def key(self):
        return (self.text(), self.text())
    def entry(self):
        k = self.key()
        if not self.num(8):
            raise ValueError("version")
        deleted = self.num(1)
        if deleted not in (0, 1):
            raise ValueError("deleted")
        length = self.num(4)
        if deleted and length:
            raise ValueError("tombstone")
        self.take(length)
        return k, deleted
    def page_header(self):
        self.ident(); self.num(4)
        final = self.boolean()
        count = self.num(2)
        if not final and not count:
            raise ValueError("empty nonfinal page")
        return count

ERROR_RETRYABLE = {1: 0, 2: 0, 3: 0, 4: 0, 5: 0, 6: 0, 7: 0, 8: 1, 9: 0, 10: 1, 11: 0, 12: 0, 13: 1, 14: 1, 15: 0, 16: 0, 17: 0, 1001: 0}
REF_SEND = {9, 10, 1001}              # kind 1 (msg_id), R8.9, R8.14
REF_QUERY = {8}                       # kind 2 (query_id), R11.15
REF_NONE = {3, 4, 11, 12, 13, 15, 16, 17}  # admission, recovery and connection errors, R13.4
REF_OPERATION = {14}                  # RATE_LIMITED always names its SEND, REQUEST or query

def limits(r):
    max_frame, *counts = r.num(4), r.num(2), r.num(2), r.num(2), r.num(4), r.num(2)
    heartbeat, idle, ttl, absolute = r.num(4), r.num(4), r.num(4), r.num(4)
    if not FRAME_MIN <= max_frame <= FRAME_MAX: raise ValueError("max_frame_bytes")
    if 0 in counts or 0 in (heartbeat, idle, ttl, absolute): raise ValueError("zero limit")
    if idle <= heartbeat: raise ValueError("idle timeout")
    if heartbeat > ttl * 125: raise ValueError("heartbeat exceeds ttl/8")

def parse(raw):
    r = Reader(raw)
    if r.num(1) != 1:
        raise ValueError("version")
    typ = r.num(1)
    if not 1 <= typ <= 19:
        raise ValueError("type")
    if r.num(2):
        raise ValueError("flags")
    if r.num(4) != len(raw) - 8:
        raise ValueError("length")
    if typ == 1:
        mode = r.num(1)
        if mode not in (0, 1): raise ValueError("mode")
        r.text(allow_empty=mode == 0)
        if mode == 0 and r.raw[r.pos-2:r.pos] != b"\x00\x00": raise ValueError("NEW with stream_id")
        r.caps(); r.client_limits()
        if mode == 1: r.num(8)
        r.boolean()
    elif typ == 2:
        r.ident(); r.text()
        if r.num(1) > 3: raise ValueError("admission")
        if not r.num(8): raise ValueError("generation 0")
        r.num(8)
        limits(r); r.caps()
    elif typ == 3:
        r.ident(); r.cursor(); r.caps(); r.client_limits(); r.boolean()
    elif typ == 4:
        r.ident(); r.blob()
    elif typ == 5:
        r.ident()
        if r.num(1) > 1: raise ValueError("outcome")
        r.blob()
    elif typ == 6: r.ident()
    elif typ == 7: r.ident(); r.text(); r.blob()
    elif typ == 8:
        r.ident()
        if r.num(1) > 1: raise ValueError("outcome")
        r.blob()
    elif typ == 9: r.ident(); r.num(8); r.blob()
    elif typ == 10: r.num(8)
    elif typ == 11:
        r.ident()
        count = r.num(2)
        if not count: raise ValueError("empty query")
        keys = [r.key() for _ in range(count)]
        if len(set(keys)) != count: raise ValueError("duplicate query key")
    elif typ == 12:
        for _ in range(r.page_header()):
            status = r.num(1)
            if status in (1, 2):
                _key, deleted = r.entry()
                if deleted != status - 1: raise ValueError("snapshot status/deleted mismatch")
            elif status != 0: raise ValueError("snapshot status")
    elif typ == 13: r.ident(); r.entry()
    elif typ in (14, 15): r.num(8)
    elif typ == 16:
        code = r.num(2)
        if code not in ERROR_RETRYABLE: raise ValueError("unregistered error code")
        retryable = r.boolean()
        kind = r.num(1)
        if kind not in (0, 1, 2): raise ValueError("error kind")
        ref = r.take(16)
        if (kind == 0) != (not any(ref)): raise ValueError("error ref")
        retry_after = r.num(4)
        if ERROR_RETRYABLE[code] != retryable: raise ValueError("retryable registry")
        if code in REF_SEND and kind != 1: raise ValueError("send error needs msg_id ref")
        if code in REF_QUERY and kind != 2: raise ValueError("query error needs query_id ref")
        if code in REF_NONE and kind != 0: raise ValueError("connection error must not carry a ref")
        if code in REF_OPERATION and kind == 0: raise ValueError("RATE_LIMITED needs a ref")
        if (code == 14) != (retry_after > 0) and code != 10: raise ValueError("retry_after rule")
        r.text(allow_empty=True, limit=DETAIL_MAX)
    elif typ == 17: r.ident(); r.num(8); r.text(); r.num(4)
    elif typ == 18:
        keys = [r.entry()[0] for _ in range(r.page_header())]
        if len(set(keys)) != len(keys): raise ValueError("duplicate baseline key")
    elif typ == 19: r.ident(); r.num(8)
    if r.pos != len(raw):
        raise ValueError("trailing bytes")
    return typ

def main():
    text = SOURCE.read_text()
    base_text, _, variant_text = text.partition("## Variant vectors")
    row = r"^\| ([A-Z_]+) \| (\d+) \| `([0-9a-f]+)` \|$"
    base = re.findall(row, base_text, re.M)
    variants = re.findall(row, variant_text.partition("## Negative vectors")[0], re.M)
    assert len(base) == 19 and sorted(int(n) for _, n, _ in base) == list(range(1, 20)), "base table must hold frame types 1..19 once each"
    assert variants, "variant table missing"
    rejected = 0
    for name, number, value in base + variants:
        raw = bytes.fromhex(value)
        assert parse(raw) == int(number), name
        for invalid in (raw[:-1], raw + b"\x00", bytes([2]) + raw[1:],
                        raw[:2] + b"\x00\x01" + raw[4:]):
            try: parse(invalid)
            except ValueError: rejected += 1
            else: raise AssertionError(f"{name}: accepted malformed vector")
    by = {n: bytes.fromhex(v) for n, _, v in base + variants}
    welcome = by["WELCOME"]
    # WELCOME: generation at frame offset 28; Limits start at 44 (8 header + 16 id + 3 text + 1 admission + 8 + 8):
    # max_frame 44, heartbeat 60, idle 64, ttl 68, absolute 72
    semantic = []
    def put(frame, off, size, value):
        x = bytearray(frame); x[off:off + size] = value.to_bytes(size, "big"); return bytes(x)
    def build(typ, body):
        return bytes([1, typ, 0, 0]) + len(body).to_bytes(4, "big") + body
    def text(s):
        return len(s).to_bytes(2, "big") + s
    ident = bytes(15) + b"\x05"
    client_limits = (1048576).to_bytes(4, "big") + (65536).to_bytes(4, "big")
    roomy = put(welcome, 64, 4, 20000)  # idle timeout large enough that only the heartbeat/ttl rule can fail
    semantic += [("heartbeat above ttl/8", put(roomy, 60, 4, 60 * 125 + 1)),
                 ("idle not above heartbeat", put(welcome, 64, 4, 1000)),
                 ("zero absolute remaining", put(welcome, 72, 4, 0)),
                 ("zero ttl", put(welcome, 68, 4, 0)),
                 ("max_frame below 4096", put(welcome, 44, 4, 4095)),
                 ("generation 0", put(welcome, 28, 8, 0)),
                 ("HELLO NEW with stream_id", build(1, b"\x00" + text(b"s") + b"\x00\x00" + client_limits + b"\x00")),
                 ("HELLO ATTACH with empty stream_id", build(1, b"\x01" + text(b"") + b"\x00\x00" + client_limits + bytes(8) + b"\x00")),
                 ("HELLO client max_frame below 4096", build(1, b"\x00" + text(b"") + b"\x00\x00" + (4095).to_bytes(4, "big") + (1).to_bytes(4, "big") + b"\x00")),
                 ("stream_id of 256 bytes", build(1, b"\x01" + text(b"s" * 256) + b"\x00\x00" + client_limits + bytes(8) + b"\x00")),
                 ("capability code 0", build(1, b"\x00" + text(b"") + b"\x00\x01\x00\x00" + client_limits + b"\x00")),
                 ("STATE_QUERY count 0", build(11, ident + b"\x00\x00")),
                 ("STATE_QUERY duplicate key", build(11, ident + b"\x00\x02" + (text(b"n") + text(b"k")) * 2)),
                 ("SNAPSHOT empty nonfinal page", build(12, ident + bytes(4) + b"\x00\x00\x00")),
                 ("ERROR unregistered code", build(16, (99).to_bytes(2, "big") + b"\x00\x00" + bytes(16) + bytes(4) + text(b""))),
                 ("ERROR ref kind 3", build(16, (2).to_bytes(2, "big") + b"\x00\x03" + ident + bytes(4) + text(b""))),
                 ("STATE_QUERY_FAILED without query ref", build(16, (8).to_bytes(2, "big") + b"\x01\x00" + bytes(16) + bytes(4) + text(b""))),
                 ("REPLAY_UNAVAILABLE with a ref", build(16, (17).to_bytes(2, "big") + b"\x00\x01" + ident + bytes(4) + text(b""))),
                 ("ERROR detail of 1025 bytes", build(16, (2).to_bytes(2, "big") + b"\x00\x00" + bytes(16) + bytes(4) + text(b"x" * 1025)))]
    rl = by["ERROR_RATE_LIMITED"]; rp = by["ERROR_REPLAY_PARTIAL"]
    semantic += [("RATE_LIMITED retry_after 0", put(rl, 8 + 2 + 1 + 1 + 16, 4, 0)),
                 ("REPLAY_PARTIAL retry_after>0", put(rp, 8 + 2 + 1 + 1 + 16, 4, 5)),
                 ("RATE_LIMITED retryable 0", put(rl, 10, 1, 0)),
                 ("REPLAY_PARTIAL retryable 0", put(rp, 10, 1, 0)),
                 ("RATE_LIMITED without ref", put(put(rl, 11, 1, 0), 12, 16, 0))]
    for label, raw in (("heartbeat exactly ttl/8", put(roomy, 60, 4, 60 * 125)), ("absolute remaining 1", put(welcome, 72, 4, 1)),
                       ("max_frame exactly 4096", put(welcome, 44, 4, 4096)),
                       ("stream_id of 255 bytes", build(1, b"\x01" + text(b"s" * 255) + b"\x00\x00" + client_limits + bytes(8) + b"\x00"))):
        assert parse(raw) in (1, 2), f"rejected a boundary value: {label}"
    for label, raw in semantic:
        try: parse(raw)
        except ValueError: rejected += 1
        else: raise AssertionError(f"accepted: {label}")
    print(f"PASS: {len(base)} base + {len(variants)} variant golden vectors, {rejected} malformed or constraint-violating variants rejected")

if __name__ == "__main__":
    main()
