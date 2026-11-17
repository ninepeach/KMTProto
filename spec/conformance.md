# KMTProto V1 — Normative Conformance Matrix

**Status: review checklist, not executed test results.** Each row cites the clauses of [protocol.md](protocol.md) that it exercises. Independent implementations MUST satisfy each applicable expected behavior. Each case should be exercised with distinct Channels and, where applicable, different server nodes.

| ID | Input / fault | Expected observable behavior | Clauses |
|---|---|---|---|
| W01 | Truncated Frame, bad length, trailing bytes or reserved flags | Reject before application effects | R2.5, R2.6 |
| W02 | Wrong direction or unknown Frame code | Protocol error, no application effect | R2.5, R2.9 |
| W03 | Unknown capability offered | Ignore and do not echo | R2.10, R14.6 |
| W04 | QUICK_ACK not negotiated but emitted | Protocol-state failure | R14.6, R5.9 |
| A01 | Unauthorized RESUME with valid Session ID | No takeover; no existence disclosure | R5.1, R5.2, R3.10 |
| A02 | Two concurrent RESUMEs | One current Generation; old owner fenced | R5.21, R4.10, R4.11 |
| A03 | Cursor beyond Stream head or wrong Stream | Reject without takeover | R5.5, R5.17 |
| R01 | Pruning concurrent with replay admission | Pin complete range or reject before takeover | R5.5, R10.12 |
| R02 | Disconnect after durable EVENT apply but before marker | Retry from durable Cursor; no double apply | R10.6, R10.8 |
| R03 | Missing EVENT during replay | Abort; never skip sequence | R7.4, R10.8 |
| R04 | Live EVENT arrives during replay | Do not interleave before RECOVERY_COMPLETE | R10.4, R7.6 |
| F01 | Full Sync interrupted during pages | Old baseline/Cursor remain | R12.8, R12.10 |
| F02 | Full Sync committed, response lost | Resume from committed baseline Cursor | R12.10 |
| F03 | SYNC_COMMIT from stale Generation | Reject; no READY transition | R12.9 |
| F04 | Duplicate, missing, out-of-order SYNC_PAGE | Abort; no baseline commit | R12.6 |
| F05 | Snapshot scope cannot share EVENT logical cut | Reject Full Sync before takeover | R12.1, R12.3, R12.5 |
| F06 | SYNC_COMMIT with a wrong sync_id or baseline_seq, or forged | Reject; recovery not advanced; no READY transition | R12.9 |
| S01 | Duplicate SEND same ID/bytes | At most one effect; identical final ACK | R8.2, R8.9 |
| S02 | Duplicate SEND same ID/different bytes | SEND_CONFLICT; no second effect | R8.2, R8.9 |
| S03 | Crash after effect but before ACK | Stored result or SEND_INDETERMINATE; never blind re-execution | R8.10, R8.13 |
| S04 | Old Generation commits during takeover | Fenced or idempotently reconciled; never duplicate effect | R8.15, R8.16, R4.11 |
| S05 | Expired Session pending SEND | No automatic migration to new Session | R6.12, R8.17 |
| S06 | Crash before claim persistence | Operation never invoked; a retry may claim normally | R8.3 |
| S07 | Crash after claim persistence but before the effect | Claim recovered and a safe continuation determined; never assume no effect solely from a missing ACK | R8.10 |
| S08 | Crash after the effect but before outcome persistence | An atomic transaction recovers both, or the operation is INDETERMINATE | R8.5, R8.13 |
| S09 | Crash after durable outcome but before ACK | Duplicate SEND returns the same ACK | R8.6, R8.9 |
| S10 | Two simultaneous SENDs with the same ID and different bytes | At most one claim; the conflicting SEND never executes | R8.2, R8.3 |
| Q01 | Point query A,B,C with B missing | Exactly three ordered results; B=MISSING | R11.5 |
| Q02 | Deleted key | Versioned DELETED tombstone, not MISSING | R11.5, R2.11 |
| Q03 | Concurrent mutation between pages | One consistent read view or whole query fails | R11.6 |
| Q04 | Wrong or duplicate page index, wrong result key, wrong total count, premature final_page or partial auth | Reject entire query; no partial visible result | R11.4, R11.7, R11.8 |
| Q05 | Disconnect before final page | No partial query result committed | R11.9 |
| Q06 | Duplicate keys in STATE_QUERY, or an unauthorized key | Whole query fails without partial results | R11.3, R11.4 |
| L01 | Frame/list/inflight above limit | Reject without effect | R2.5, R13.8, R13.9 |
| L02 | Session absolute TTL elapsed despite PINGs | RESUME fails; no takeover | R6.1, R6.6 |
| L03 | HELLO NEW without sync | READY at WELCOME | R5.11, R5.13 |
| L04 | SEND before recovery completion | Reject without effect | R5.8, R5.11 |
| P01 | Due PING with valid reauthorization | Durable lease renewal before matching PONG | R6.7 |
| P02 | Due PING with revoked authorization | No matching PONG; Channel closed | R6.8 |
| P03 | NEW selected existing Stream | Cursor begins at authorized Stream head | R5.12, R5.13 |
| P04 | RESUME sync flag=1 | Full Sync or reject; preserve Session and SEND dedup | R5.17, R5.19 |
| P05 | Replay exceeds per-attempt bound | Contiguous progress, REPLAY_PARTIAL, close; next RESUME continues | R10.9, R10.10, R10.11 |
| P06 | EVENT gap or duplicate | Close Channel and RESUME from last durable Cursor | R7.4 |
| P07 | RATE_LIMITED SEND | No effect; retry_after_ms>0; same msg_id on retry | R13.3, R13.8, R8.18 |
| P08 | Full Sync skips EVENT-only history | Notify Application before READY | R12.13 |
| P09 | WELCOME carries absolute_remaining_seconds | Client estimates the absolute deadline early, drains SENDs and rotates Session before it | R6.5, R6.11 |
| P10 | PING sent before renewal_due | PONG carries no lease information; lease_deadline does not move | R6.9 |
| P11 | EVENT n+1 accepted before EVENT n is durable | No violation; Cursor lags; reconnect replays from the Cursor | R7.5 |
| P12 | In-flight count exceeded | RATE_LIMITED with retry_after_ms>0 before any effect, never LIMIT_EXCEEDED | R13.8 |
| P13 | WELCOME with heartbeat_ms above session_ttl_seconds*1000/8, or absolute_remaining_seconds=0 | Client closes the Connection | R14.2 |
| P14 | SEND the Principal may not perform | Final ACK with outcome=APPLICATION_ERROR; not UNAUTHORIZED | R8.19 |
| P15 | ERROR sent by either peer while RECOVERING | Accepted; connection state unchanged unless the code requires closing | R5.10, R13.6 |
| P16 | HELLO NEW, HELLO ATTACH and RESUME with each state_sync_requested value | Exactly the admission or rejection in the R5.19 table; RESUME keeps SEND dedup | R5.19, R5.17 |
| P17 | REQUEST outstanding when a newer Generation takes over | Logically cancelled; a late RESPONSE is not delivered on the new Channel | R5.22, R9.2 |
| P18 | Full Sync commits baseline_seq=B while the Client's old Cursor was C < B | Client accepts live EVENT B+1 after RECOVERY_COMPLETE; no gap detected | R7.4, R12.11 |
| P19 | HELLO NEW with WELCOME replay_to=H | Client accepts live EVENT H+1 as the first EVENT | R7.4, R5.13 |
| P20 | RESUME with state_sync_requested=1 when replay is possible | FULL_SYNC (or reject if no baseline), never RESUMED | R5.18, R5.19 |
| P21 | RESUME with state_sync_requested=0, Cursor no longer retained, Full Sync not chosen | REPLAY_UNAVAILABLE, no takeover; a retry with state_sync_requested=1 is admissible | R5.18, R13.10 |
| P22 | RESUME after Session deadline passed | SESSION_EXPIRED, not ADMISSION_REJECTED or REPLAY_UNAVAILABLE | R13.10, R6.3 |
| P23 | Two STATE_QUERYs outstanding, one fails | ERROR carries ErrorRef kind=2 with that query_id; the other query completes | R11.15, R13.4 |
| P24 | STATE_QUERY above max_inflight_query | RATE_LIMITED with kind=2 ref, before any read | R11.15, R13.8 |
| P25 | RESUME of a Session whose first WELCOME had max_frame_bytes=M | Later WELCOME carries max_frame_bytes >= M, or the RESUME is rejected without takeover | R14.4, R8.20 |
| P26 | Application submits a SEND larger than the effective max_frame_bytes | Rejected locally, never stored in the outbox or sent | R8.20 |
| P27 | Full Sync whose total_entries exceeds the Client's max_sync_entries | Server rejects with LIMIT_EXCEEDED before takeover; a Client receiving such SYNC_BEGIN aborts | R14.8 |
| P28 | WELCOME max_frame_bytes above the Client's ClientLimits value | Client closes the Connection | R14.8, R2.7 |
| P29 | Frame with header version 2 sent to a Server in CHANNEL_READY | Body not parsed; optional ERROR UNSUPPORTED_VERSION; Channel closed | R2.23 |
| P30 | Renewal PING outstanding while a later ordinary PING is answered first | Ordinary PONG accepted by nonce; lease moves only on the renewal PONG | R7.2, R6.9 |
| P31 | Session ID unknown vs. Session ID owned by another Principal | Both UNAUTHORIZED, indistinguishable | R5.2, R13.7 |

## Implementation interoperability artifacts

[Golden vectors](golden-vectors.md) provide one valid byte-level example for each of the 19 Frame types. For each Frame type, additionally publish exhaustive malformed-field cases and malformed-vector cases (truncation, overflow, enum and length errors). For Full Sync, publish empty and multipage baselines; for STATE_SNAPSHOT, publish MISSING/PRESENT/DELETED examples. Run the matrix against independent implementations and capture pass/fail evidence for **implementation conformance**; this is not a prerequisite for freezing the specification. This file documents expected outcomes only; it is **not** evidence that any implementation passed.

## Review caveats

Full Sync requires a deployment-defined scope and a provable State/EVENT cut. Reliable SEND requires atomic effect/outcome persistence or equivalent idempotency; neither property is created by a wire codec. If these contracts cannot be satisfied, the implementation MUST reject the corresponding operation rather than claim stronger guarantees.
