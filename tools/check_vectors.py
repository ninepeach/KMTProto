#!/usr/bin/env python3
"""Validate KMTProto V1 golden Frames (including P0/P1 RESUME/ERROR changes)."""
import pathlib
import re
import struct

ROOT = pathlib.Path(__file__).resolve().parents[1]
SOURCE = ROOT / "spec" / "golden-vectors.md"

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
        if self.num(1) not in (0, 1):
            raise ValueError("boolean")
    def ident(self):
        if not any(self.take(16)):
            raise ValueError("zero identifier")
    def text(self, allow_empty=False):
        n = self.num(2)
        if n == 0 and not allow_empty:
            raise ValueError("empty text")
        x = self.take(n).decode("utf-8")
        if "\x00" in x:
            raise ValueError("NUL text")
    def blob(self):
        self.take(self.num(4))
    def caps(self):
        count, prev = self.num(2), 0
        if count > 64:
            raise ValueError("cap count")
        for _ in range(count):
            code = self.num(2)
            if code <= prev:
                raise ValueError("cap order")
            prev = code
    def cursor(self):
        self.text()
        self.num(8)
    def key(self):
        self.text()
        self.text()
    def entry(self):
        self.key()
        if not self.num(8):
            raise ValueError("version")
        deleted = self.num(1)
        if deleted not in (0, 1):
            raise ValueError("deleted")
        length = self.num(4)
        if deleted and length:
            raise ValueError("tombstone")
        self.take(length)

ERROR_RETRYABLE = {1: 0, 2: 0, 3: 0, 4: 0, 5: 0, 6: 0, 7: 0, 8: 1, 9: 0, 10: 1, 11: 0, 12: 0, 13: 1, 14: 1, 15: 0, 1001: 0}

def limits(r):
    max_frame, _inflight_send, _inflight_request, _replay, _items = r.num(4), r.num(2), r.num(2), r.num(4), r.num(2)
    heartbeat, idle, ttl, absolute = r.num(4), r.num(4), r.num(4), r.num(4)
    if not 8 <= max_frame <= 1048576: raise ValueError("max_frame_bytes")
    if 0 in (_inflight_send, _inflight_request, _replay, _items, heartbeat, idle, ttl, absolute): raise ValueError("zero limit")
    if idle <= heartbeat: raise ValueError("idle timeout")
    if heartbeat > ttl * 1000 // 8: raise ValueError("heartbeat exceeds ttl/8")

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
        r.caps()
        flag = r.num(1)
        if flag not in (0, 1): raise ValueError("presence")
        if flag: r.cursor()
        r.boolean()
    elif typ == 2:
        r.ident(); r.text()
        if r.num(1) > 3: raise ValueError("admission")
        r.num(8); r.num(8)
        limits(r); r.caps()
    elif typ == 3:
        r.ident(); r.cursor(); r.caps(); r.boolean()
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
        for _ in range(r.num(2)): r.key()
    elif typ == 12:
        r.ident(); r.num(4); r.boolean()
        for _ in range(r.num(2)):
            status = r.num(1)
            if status in (1, 2): r.entry()
            elif status != 0: raise ValueError("snapshot status")
    elif typ == 13: r.ident(); r.entry()
    elif typ in (14, 15): r.num(8)
    elif typ == 16:
        code = r.num(2)
        retryable = r.num(1)
        if retryable not in (0, 1): raise ValueError("boolean")
        kind = r.num(1)
        if kind not in (0, 1): raise ValueError("error kind")
        ref = r.take(16)
        if (kind == 0) != (not any(ref)): raise ValueError("error ref")
        retry_after = r.num(4)
        if code in ERROR_RETRYABLE and ERROR_RETRYABLE[code] != retryable: raise ValueError("retryable registry")
        if code in (9, 10, 14, 1001) and kind != 1 and code != 14: raise ValueError("send error needs ref")
        if (code == 14) != (retry_after > 0) and code != 10: raise ValueError("retry_after rule")
        r.text(allow_empty=True)
    elif typ == 17: r.ident(); r.num(8); r.text(); r.num(4)
    elif typ == 18:
        r.ident(); r.num(4); r.boolean()
        for _ in range(r.num(2)): r.entry()
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
    # limits start at body offset 16+3+1+8+8 = 36, i.e. frame offset 44; heartbeat/idle/ttl/absolute are at +14, +18, +22, +26
    semantic = []
    def put(frame, off, size, value):
        x = bytearray(frame); x[off:off + size] = value.to_bytes(size, "big"); return bytes(x)
    roomy = put(welcome, 62, 4, 20000)  # idle timeout large enough that only the heartbeat/ttl rule can fail
    semantic += [("heartbeat above ttl/8", put(roomy, 58, 4, 60 * 1000 // 8 + 1)),
                 ("idle not above heartbeat", put(welcome, 62, 4, 1000)),
                 ("zero absolute remaining", put(welcome, 70, 4, 0)),
                 ("zero ttl", put(welcome, 66, 4, 0))]
    rl = by["ERROR_RATE_LIMITED"]; rp = by["ERROR_REPLAY_PARTIAL"]
    semantic += [("RATE_LIMITED retry_after 0", put(rl, 8 + 2 + 1 + 1 + 16, 4, 0)),
                 ("REPLAY_PARTIAL retry_after>0", put(rp, 8 + 2 + 1 + 1 + 16, 4, 5)),
                 ("RATE_LIMITED retryable 0", put(rl, 10, 1, 0)),
                 ("REPLAY_PARTIAL retryable 0", put(rp, 10, 1, 0))]
    for label, raw in (("heartbeat exactly ttl/8", put(roomy, 58, 4, 60 * 1000 // 8)), ("absolute remaining 1", put(welcome, 70, 4, 1))):
        assert parse(raw) == 2, f"rejected a boundary value: {label}"
    for label, raw in semantic:
        try: parse(raw)
        except ValueError: rejected += 1
        else: raise AssertionError(f"accepted: {label}")
    print(f"PASS: {len(base)} base + {len(variants)} variant golden vectors, {rejected} malformed or constraint-violating variants rejected")

if __name__ == "__main__":
    main()
