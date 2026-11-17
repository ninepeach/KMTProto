# KMTProto V1 — Golden Wire Vectors

**Status: illustrative byte-exact normative vectors.** Hex octets are network-order. Frame header is version=01, type, flags=0000, u32 body length. These examples validate encoding, not authorization or application effects. IDs are 15 zero bytes followed by the shown nonzero suffix. UTF-8 text uses u16 length. Example ClientLimits in HELLO/RESUME: max_frame=1048576, max_sync_entries=65536. Example WELCOME limits: max_frame=4096, inflight SEND/REQUEST/query=2, max_replay=100, max_state_items=10, heartbeat=1000ms, idle=3000ms, TTL=60s, absolute remaining=3600s. QUICK_ACK requires negotiated capability 1 in a real connection.

| Frame | Type | Complete frame (hex) |
|---|---:|---|
| HELLO | 1 | `010100000000000e0000000000001000000001000000` |
| WELCOME | 2 | `01020000000000460000000000000000000000000000000100017300000000000000000100000000000000000000100000020002000200000064000a000003e800000bb80000003c00000e100000` |
| RESUME | 3 | `01030000000000260000000000000000000000000000000100017300000000000000000000001000000001000000` |
| SEND | 4 | `0104000000000015000000000000000000000000000000020000000141` |
| ACK | 5 | `0105000000000015000000000000000000000000000000020000000000` |
| QUICK_ACK | 6 | `010600000000001000000000000000000000000000000002` |
| REQUEST | 7 | `01070000000000170000000000000000000000000000000300017100000000` |
| RESPONSE | 8 | `0108000000000015000000000000000000000000000000030000000000` |
| EVENT | 9 | `010900000000001d0000000000000000000000000000000400000000000000010000000141` |
| RECOVERY_COMPLETE | 10 | `010a0000000000080000000000000001` |
| STATE_QUERY | 11 | `010b00000000001800000000000000000000000000000005000100016e00016b` |
| STATE_SNAPSHOT | 12 | `010c00000000002c00000000000000000000000000000005000000000100010100016e00016b0000000000000001000000000141` |
| STATE_UPDATE | 13 | `010d0000000000240000000000000000000000000000000600016e00016b0000000000000001000000000141` |
| PING | 14 | `010e000000000009000000000000000700` |
| PONG | 15 | `010f0000000000080000000000000007` |
| ERROR | 16 | `011000000000001a0002000000000000000000000000000000000000000000000000` |
| SYNC_BEGIN | 17 | `011100000000001f00000000000000000000000000000007000000000000000100017300000001` |
| SYNC_PAGE | 18 | `011200000000002b000000000000000000000000000000070000000001000100016e00016b0000000000000001000000000141` |
| SYNC_COMMIT | 19 | `0113000000000018000000000000000000000000000000070000000000000001` |

## Variant vectors

One more example each for behavior that the 19 base vectors do not show: RESUME with `state_sync_requested=1`, an ERROR with a positive `retry_after_ms`, the recovery-scoped REPLAY_PARTIAL, a Full Sync WELCOME (admission=3, generation=2, replay_to=5), a STATE_QUERY_FAILED that references its `query_id` with ErrorRef kind=2, a REPLAY_UNAVAILABLE admission rejection, a renewal PING (`renew`=1), and HELLO ATTACH with `cursor_last_seq`=5 and `state_sync_requested=1`. These rows are validated like the base vectors, with the same type column.

| Variant | Type | Complete frame (hex) |
|---|---:|---|
| RESUME_FULL_SYNC | 3 | `01030000000000260000000000000000000000000000000100017300000000000000000000001000000001000001` |
| ERROR_RATE_LIMITED | 16 | `011000000000001a000e010100000000000000000000000000000002000001f40000` |
| ERROR_REPLAY_PARTIAL | 16 | `011000000000001a000d010000000000000000000000000000000000000000000000` |
| WELCOME_FULL_SYNC | 2 | `01020000000000460000000000000000000000000000000100017303000000000000000200000000000000050000100000020002000200000064000a000003e800000bb80000003c00000e100000` |
| ERROR_QUERY_FAILED | 16 | `011000000000001a0008010200000000000000000000000000000005000000000000` |
| ERROR_REPLAY_UNAVAILABLE | 16 | `011000000000001a0011000000000000000000000000000000000000000000000000` |
| PING_RENEW | 14 | `010e000000000009000000000000000801` |
| HELLO_ATTACH | 1 | `01010000000000170100017300000010000000010000000000000000000501` |

## Negative vectors and checks

- Change header version from `01` to `02`: reject unsupported version.
- Change reserved flags from `0000` to `0001`: reject.
- Increase body_length by 1 without adding bytes: reject truncation.
- Append one trailing octet without changing body_length: reject Frame length mismatch.
- Change any boolean field from `00`/`01` to `02`, including PING `renew`: reject enum.
- A Server-originated PING with `renew`=1, or a renewal PING arriving before `last_renewal_at + renewal_interval_ms`: close with PROTOCOL_STATE (stateful; not checked by the vector tool).
- WELCOME with `max_frame_bytes` below 4096, with `heartbeat_ms` above `session_ttl_seconds * 125`, with `idle_timeout_ms` not above `heartbeat_ms`, or with `absolute_remaining_seconds` of 0: reject.
- ERROR RATE_LIMITED with `retry_after_ms` 0, or any other code except SEND_PENDING with a positive `retry_after_ms`: reject.
- ERROR whose `retryable` byte differs from the registry value for its code, or with a code not in the registry: reject.
- ERROR with ErrorRef kind 3, or kind 1/2 with an all-zero `ref_id`: reject.
- HELLO mode 0 with a nonempty `stream_id`, or mode 1 with an empty `stream_id`: reject.
- STATE_QUERY with count 0, or any text field longer than its R14.5 bound: reject.
- WELCOME with generation 0, or ClientLimits `max_frame_bytes` below 4096: reject.
- Replace the final octet of an id128 with zero when all prior bytes are zero: reject forbidden zero ID.
- Send QUICK_ACK without capability 1 in WELCOME: reject.
- Send SYNC_COMMIT on a replay-only Session: reject protocol state.
- Send STATE_SNAPSHOT page index 1 as first page: reject entire query.
- Change STATE_SNAPSHOT status to MISSING while leaving StateEntry bytes: reject trailing bytes.

## Scope

RESUME includes the mandatory trailing state_sync_requested=0 byte. ERROR includes retry_after_ms=0 after ErrorRef. HELLO and RESUME carry ClientLimits after Capabilities; HELLO carries `cursor_last_seq` only in mode 1, with no presence byte; Limits carries `max_inflight_query`; PING carries a trailing `renew` byte (PONG is unchanged). These are draft-breaking changes; the layouts are in [protocol.md](protocol.md) section 2.5.

These vectors cover the 19 Frame bodies with one compact example each, plus eight variants for behavior the base examples do not show. They do not establish full malformed-field coverage, multi-page interop or independent implementation conformance. The complete acceptance plan is in [conformance.md](conformance.md).
