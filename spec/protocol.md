# KMTProto V1 — Protocol Specification

**Status: V1 DESIGN DRAFT — P0/P1 revision, consolidated.** This is the single normative specification of KMTProto V1. The wire format is binary; its inner header carries version 1. There is no legacy wire compatibility; the earlier JSON design is superseded.

KMTProto is a transport-independent binary protocol for reliable messaging, session recovery and state synchronization.

## 0. Document conventions

### 0.1 Authority

- **R0.1** This document is the only normative specification of KMTProto V1. [golden-vectors.md](golden-vectors.md) supplies byte-exact vectors for the encoding; [conformance.md](conformance.md) is the normative acceptance plan, a list of expected behaviors that is not evidence that any implementation passed; [secure-channel.md](secure-channel.md) and the programs in `tools/` are informative.
- **R0.2** If this document is found to contradict itself, or a vector, plan or tool contradicts it, the contradiction is a defect to be corrected. No clause overrides another by precedence.
- **R0.3** Specification Frozen requires fixed Frame layouts and registries, internally consistent MUST-level semantics, and deterministic byte-level examples. It does not require independent Go/TS implementations. This draft is not frozen.

### 0.2 Requirement language

- **R0.4** **MUST**, **MUST NOT**, **SHOULD**, **SHOULD NOT** and **MAY** are interpreted as in RFC 2119 and RFC 8174 when written in bold or upper case. Numbered clauses such as `R5.3` are stable references for the conformance plan, vectors and reviews: a clause keeps its number, a new clause takes the next unused number of its section, and a removed clause leaves its number unused.

### 0.3 Terminology

| Term | Meaning |
|---|---|
| Client, Server | The two roles. A component that decodes and re-encodes Frames, such as a gateway, is an Endpoint and is bound by this specification. |
| Application | Caller code that executes SEND and REQUEST operations and produces EVENT and State content. |
| Auth Provider | Application-provided component that authenticates a Principal. |
| Principal | Identity authenticated by the hosting Application/Auth Provider, never inferred from a Session ID. |
| Channel | One reliable, ordered connection carrying complete Frames, with locally verified security properties (section 3). |
| Stream | Server-owned, durable, ordered EVENT log identified by `stream_id` (section 4). |
| Session | Durable logical identity of one authorized Client's messaging and recovery context, identified by `session_id` (section 4). |
| Generation | Monotonically increasing fencing epoch for the current Session owner. |
| Cursor | Highest contiguous EVENT sequence whose effects the Client has durably applied. |
| next_expected | The Client's in-memory sequence of the next EVENT it will accept (section 7). |
| Replay barrier | Immutable Stream sequence `replay_to` captured for one recovery attempt. |
| Lease | The Session's current deadline, `expires_at`, bounded by the immutable `absolute_expires_at` (section 6). |

## 1. Scope and architecture

```
Application / Auth Provider → KMTProto Core → Channel Adapter
```

- **R1.1** KMTProto specifies binary Frames, Session, SEND/ACK, ordered EVENT recovery and State synchronization. It does **not** specify TLS, Noise, cipher suites, key management or an encryption wire format.
- **R1.2** Channel implementations provide bounded, reliable, ordered, complete Frame delivery; a Channel may compose encryption and transport mechanisms. Different Channel implementations MUST NOT change KMTProto Core semantics.
- **R1.3** Application payloads are opaque bytes. No plaintext/encrypted distinction is encoded in the KMTProto Frame itself.
- **R1.4** Delivery guarantees depend on application-side atomic commit/idempotency, not transport alone.
- **R1.5** Implementation targets: Go for Client and Server, with shared codecs and state machine, TCP and WebSocket adapters first; TypeScript for the browser WebSocket Client only, with the same bytes and semantics. Reliable UDP follows only after its Channel binding is specified.

## 2. Binary encoding

### 2.1 Primitives

- **R2.1** All integers are unsigned and big-endian: `u8`, `u16`, `u32`, `u64`.
- **R2.2** `id128` is exactly 16 bytes; all-zero identifiers are forbidden except the explicitly defined null ErrorRef. `id128` is opaque and not a UUID textual encoding.
- **R2.3** `bytes` is `u32 length || length raw octets`. `text` is `u16 byte_length || UTF-8 octets`, nonempty unless a field explicitly allows empty (HELLO NEW `stream_id` and ERROR `detail`). A receiver MUST reject malformed UTF-8, NUL, overlong encodings and unassigned lengths. There is no implicit normalization or trimming: `text` values are compared as exact octets after UTF-8 validation, and names are case-sensitive.
- **R2.4** Optional fields use the explicit presence byte defined by the owning frame; no implicit sentinels. There are no varints, implicit padding or trailing bytes. All booleans are `u8` with only 0 or 1 accepted. Nonzero undefined enum values MUST be rejected.
- **R2.5** A receiver MUST reject truncation, trailing bytes, unknown frame codes, reserved flag bits, lengths above effective limits, invalid UTF-8, and malformed presence bytes before executing any application effect. Implementations MUST check arithmetic overflow before allocating or adding lengths.

### 2.2 Inner Frame

| Offset | Size | Field |
|---|---:|---|
| 0 | 1 | version = 1 |
| 1 | 1 | type |
| 2 | 2 | flags = 0 (reserved) |
| 4 | 4 | body_length |
| 8 | body_length | body |

- **R2.6** Exact inner length MUST equal `8 + body_length`.
- **R2.7** Maximum inner frame size is 1,048,576 bytes including the 8-byte header unless a lower negotiated limit applies. Before WELCOME, this default is mandatory. Any later advertised limit can only lower the effective maximum for this connection. Channel adapters enforce their own bounds including any framing or protection overhead.
- **R2.8** The Channel Adapter transports each complete Frame and applies deployment-specific protection. The inner header and body are protocol data, not a cryptographic record; KMTProto does not mandate a particular encryption method.

### 2.3 Frame type registry

| Code | Name | Direction |
|---:|---|---|
| 1 | HELLO | C→S |
| 2 | WELCOME | S→C |
| 3 | RESUME | C→S |
| 4 | SEND | C→S |
| 5 | ACK | S→C |
| 6 | QUICK_ACK | S→C |
| 7 | REQUEST | C→S |
| 8 | RESPONSE | S→C |
| 9 | EVENT | S→C |
| 10 | RECOVERY_COMPLETE | S→C |
| 11 | STATE_QUERY | C→S |
| 12 | STATE_SNAPSHOT | S→C |
| 13 | STATE_UPDATE | S→C |
| 14 | PING | both |
| 15 | PONG | both |
| 16 | ERROR | both |
| 17 | SYNC_BEGIN | S→C |
| 18 | SYNC_PAGE | S→C |
| 19 | SYNC_COMMIT | C→S |

- **R2.9** A Frame received in the wrong direction is a protocol error (MALFORMED_FRAME). Unknown Frame types, flags and invalid enum values are protocol errors.

### 2.4 Common structures

- `Cursor`: `text stream_id, u64 last_seq`. A zero `last_seq` means no EVENT committed.
- `Limits`: `u32 max_frame_bytes, u16 max_inflight_send, u16 max_inflight_request, u32 max_replay_events, u16 max_state_items, u32 heartbeat_ms, u32 idle_timeout_ms, u32 session_ttl_seconds, u32 absolute_remaining_seconds`. Value constraints are in section 14.
- `Capabilities`: `u16 count, count × u16 capability_code`.
- `StateEntry`: `text namespace, text object_id, u64 version, u8 deleted, bytes data`.
- `StateKey`: `text namespace, text object_id`.
- `ErrorRef`: `u8 kind, id128 ref_id`.
- `SnapshotResult`: `u8 status, [StateEntry]`; status 0=MISSING (no entry), 1=PRESENT (entry deleted=0), 2=DELETED (entry deleted=1). Presence is determined by status, without an additional presence byte.
- `SnapshotPage`: `id128 query_id, u32 page_index, u8 final_page, u16 count, count × SnapshotResult`.

- **R2.10** Capability codes MUST be strictly ascending and unique. Unknown optional capability codes are ignored, not echoed.
- **R2.11** Deleted StateEntry values MUST carry zero-length `data`. State versions start at 1; a version-0 StateEntry is never valid.
- **R2.12** ErrorRef kind 0 means no reference and MUST use the all-zero `ref_id`; kind 1 refers to a Message/Request ID.
- **R2.13** `absolute_remaining_seconds` is the time from WELCOME emission to the Session's immutable absolute deadline; it is never zero.

### 2.5 Frame bodies

| Frame | Exact body fields |
|---|---|
| HELLO | `u8 mode, text stream_id, Capabilities, u8 cursor_present, [Cursor], u8 state_sync_requested` |
| WELCOME | `id128 session_id, text stream_id, u8 admission, u64 generation, u64 replay_to, Limits, Capabilities` |
| RESUME | `id128 session_id, Cursor, Capabilities, u8 state_sync_requested` |
| SEND | `id128 msg_id, bytes content` |
| ACK | `id128 msg_id, u8 outcome, bytes result` |
| QUICK_ACK | `id128 msg_id` |
| REQUEST | `id128 request_id, text method, bytes params` |
| RESPONSE | `id128 request_id, u8 outcome, bytes result` |
| EVENT | `id128 event_id, u64 seq, bytes content` |
| RECOVERY_COMPLETE | `u64 replay_to` |
| STATE_QUERY | `id128 query_id, u16 count, count × StateKey` |
| STATE_SNAPSHOT | `SnapshotPage` |
| STATE_UPDATE | `id128 update_id, StateEntry` |
| PING | `u64 nonce` |
| PONG | `u64 nonce` |
| ERROR | `u16 code, u8 retryable, ErrorRef, u32 retry_after_ms, text detail` |
| SYNC_BEGIN | `id128 sync_id, u64 baseline_seq, text scope_id, u32 total_entries` |
| SYNC_PAGE | `id128 sync_id, u32 page_index, u8 final_page, u16 count, count × StateEntry` |
| SYNC_COMMIT | `id128 sync_id, u64 baseline_seq` |

All fields are serialized in the listed order. Fields in brackets are present only if the preceding presence flag equals 1.

- **R2.14** HELLO `mode`: 0 = create a new Session, 1 = attach to an existing authorized Stream. Mode 0 requires empty `stream_id` and `cursor_present`=0; the Application selects an authorized existing Stream or creates a new Stream (R5.12). Mode 1 requires nonempty `stream_id` and `cursor_present`=1. The Cursor `stream_id` MUST equal the HELLO `stream_id`.
- **R2.15** WELCOME `admission`: 0 NEW, 1 ATTACHED, 2 RESUMED, 3 FULL_SYNC (uses SYNC_BEGIN/SYNC_PAGE/SYNC_COMMIT). `generation` starts at 1 and increases on takeover. `replay_to` may be zero only for an empty Stream.
- **R2.16** `outcome` in ACK and RESPONSE: 0 SUCCESS, 1 APPLICATION_ERROR.
- **R2.17** `state_sync_requested` in HELLO and RESUME MUST be 0 or 1; its meaning is the table in R5.19.
- **R2.18** ERROR `detail` MAY be empty. STATE_QUERY MUST have at least one key.
- **R2.19** A Session ID is only carried by WELCOME and RESUME; after admission, a Connection is bound to exactly one Session. All frames are scoped to that Session without repeating the ID. An EVENT `seq` belongs to the admitted Stream.
- **R2.20** SEND deduplication compares the exact bytes of `content` and any future semantically relevant SEND fields. It MUST NOT compare a hash alone without collision-safe byte verification. Application content may be JSON, Protobuf or arbitrary bytes; KMTProto does not interpret it.
- **R2.21** For State equality, the protocol compares raw `data` octets, the `deleted` flag, namespace and object ID. The same version with different octets is STATE_CONFLICT, even if application-level JSON would be semantically equivalent. Applications requiring semantic equality MUST canonicalize before submission. This removes cross-language JSON equality ambiguity.
- **R2.22** All Frames MUST be fully parsed and checked for correct direction, negotiated size, exact field length, enum values, authorization and current state before triggering application effects. A malformed frame closes the Channel without executing effects.

## 3. Channel and security

### 3.1 Channel contract

- **R3.1** A Channel delivers a reliable, ordered, bidirectional sequence of complete bounded KMTProto binary Frames. It provides cancellation, backpressure, close/error propagation and bounded memory use. It MUST NOT interpret Session, SEND/ACK, EVENT, State or application payload semantics.
- **R3.2** A Channel may compose transport and security, for example TLS/TCP, WSS, Noise/TCP, or a reliable UDP adapter. KMTProto Core does not know the encryption mechanism and does not negotiate ciphers in its Frame protocol.
- **R3.3** A Channel implementation is responsible for its own handshake, cryptographic key validation, record framing, replay protection, limits, error handling and key lifecycle. Failures MUST NOT deliver unauthenticated Frame data to Core.

### 3.2 Trusted security context

- **R3.4** A Channel MAY provide locally verified properties: confidentiality, integrity, endpoint authentication, peer cryptographic identity and optional channel-binding evidence. These are local, non-wire metadata. Properties MUST originate from the trusted local adapter; untrusted remote claims MUST NOT set them, and a remote peer MUST NOT self-assert them. Endpoint authentication direction MUST be explicit: a client validating a WSS server does not authenticate that client to the server.
- **R3.5** A Server MUST apply its deployment Channel Security Policy before accepting credentials, Session identifiers or sensitive application Frames, and MUST reject Channels with insufficient protection before processing credentials or sensitive Session metadata. For remotely accessible Sessions the default policy MUST require a Channel with authenticated server endpoint, confidentiality and integrity. Plaintext or unverified Channels MUST NOT be used for sensitive Sessions by default. A deployable product MUST configure an acceptable secure Channel and an authentication and authorization policy; the Core itself has no mandatory encryption adapter and no Noise-specific dependency.
- **R3.6** A Channel rejected by security policy MUST be closed before reading credentials or sensitive KMTProto Frames.
- **R3.7** Client Principal authentication and per-Session authorization remain mandatory and separate from Channel security. Server authentication of a TLS/WSS endpoint does NOT imply authentication of the client user. The Core MUST NOT equate a connected Channel or a known Session ID with authorization.
- **R3.8** Channel security does not imply permission to RESUME. A Session ID is not a bearer credential.

### 3.3 Auth Provider

- **R3.9** An Application-provided Auth Provider authenticates a Principal using trusted out-of-band connection context or explicitly authenticated credentials. The credential format, authentication exchange and mechanism (cookie, token, mTLS, etc.) are outside the protocol; a deployment MUST define a concrete mechanism and credential transport before admitting a Session. No authentication mechanism is implied by the binary Frames. Deployments MUST satisfy the Channel security and Auth Provider contracts of this section; no particular transport or authentication credential format is mandated by this specification.
- **R3.10** The Core MUST require authorization for Session creation, Stream attachment and RESUME before binding a Connection. Authentication and authorization failures MUST NOT mutate Session state, increment its generation, or fence an existing Connection.
- **R3.11** An optional deployment profile MAY specify cookie, token or mTLS binding without changing these Frames.

### 3.4 TCP binding

- **R3.12** A TCP Channel MAY use a four-byte unsigned big-endian Frame length followed by exactly that many bytes. Length zero, truncation and lengths above the configured bound are fatal. If security is composed underneath or above this framing, the Channel implementation defines its own protected record boundaries; the four-byte prefix is not a universal encrypted-record format.

### 3.5 WebSocket binding

- **R3.13** Each WebSocket binary message carries one complete KMTProto Frame at the Core boundary. Text messages are invalid. WSS is the recommended browser deployment. The WebSocket subprotocol token is `kmtproto.v1`.
- **R3.14** A Channel that wraps Frame bytes in its own protected records MUST perform the unwrap before presenting the Frame to Core. Message and decompression size limits MUST be enforced.

### 3.6 Reliable UDP (future)

- **R3.15** A raw UDP socket does not satisfy the Channel contract. A UDP Channel must independently implement bounded fragmentation/reassembly, retransmission, in-order delivery, flow/congestion control, path authentication and anti-amplification as applicable. Transport ACKs are distinct from KMTProto application ACKs. UDP is not conformant until its Channel binding is specified.

### 3.7 Reconnect

- **R3.16** A new Channel connection may request RESUME for a preexisting Protocol Session. Session authorization MUST succeed before generation takeover. Channel security and cryptographic key lifetimes do not define Protocol Session lifetimes.

## 4. Streams, Sessions and identities

- **R4.1** A Stream is a server-owned, durable, ordered EVENT log, identified by `stream_id`. It has a contiguous `u64 seq` starting at 1, with no wraparound. A Stream is not a connection, authentication principal, deduplication domain or Session owner.
- **R4.2** A Stream can be shared by multiple authorized Sessions, each with its own independently persisted Client Cursor. A shared Stream distributes the same ordered EVENT sequence to authorized Sessions. Delivery or commit of an EVENT to one Session MUST NOT advance another Session's Cursor.
- **R4.3** A Stream may outlive any individual Session. Stream retention and access control are server/application policy; retention MUST be checked against a Cursor before replay admission.
- **R4.4** A Session is one authorized Client's durable messaging and recovery context, identified by `session_id`. It is bound to exactly one Stream and its authorization scope for its lifetime, and a Session MUST NOT change Stream during RESUME. It owns SEND deduplication and a connection Generation, and it can outlive Channels and move between them. A Client MUST NOT substitute another Stream's Cursor.
- **R4.5** Session IDs are correlation identifiers, not credentials. A Session ID MUST never be recycled.
- **R4.6** SEND deduplication is Session-scoped, never Stream-scoped.
- **R4.7** A Generation is never reused within a Session.
- **R4.8** EVENT ordering is total within its Stream. EVENT is the only replayable, cursor-tracked server-to-client change stream. Only a durably applied, contiguous EVENT advances the Client Cursor.
- **R4.9** `event_id` identifies an EVENT; the same `seq` MUST denote the same `event_id` and identical content for the lifetime of its retained history. A conflicting replay is a fatal consistency error.
- **R4.10** The Server MUST serialize ownership changes per Session, including across server instances. Only the current generation may emit new Session-scoped output or begin new application effects. Persisted outcomes of effects already committed remain valid after fencing.
- **R4.11** A RESUME takeover atomically persists the next Generation and new owner. All Session-scoped output MUST verify the active Generation at emission. An old Channel MUST NOT send further ACK, RESPONSE, EVENT or STATE_UPDATE after fencing.

## 5. Admission and connection state machine

### 5.1 Admission preconditions

- **R5.1** The Server MUST validate Channel policy, authenticate the Principal and authorize the target Session/Stream before accepting HELLO or RESUME as an admission request. Authentication may occur in the hosting application or Channel establishment, but the credential acquisition and verification mechanism MUST be defined by the deployment.
- **R5.2** An authorization failure MUST NOT change Session ownership, generation, cursor or dedup state. An unauthorized caller MUST NOT learn whether a Session ID exists; admission authorization failures SHOULD be reported with a generic failure and closed, without a distinguishable unknown-Session response.
- **R5.3** Admission MUST first authenticate and authorize the Principal, validate Session/Stream/Cursor, and establish replay feasibility or Full Sync availability. The Server MUST authorize before allocating or fencing. Only then may a RESUME atomically change the owner Generation.
- **R5.4** A failed admission MUST NOT fence an existing owner or create a visible partial Session. The Server MUST NOT expose a newly allocated Session before its durable record is committed.
- **R5.5** The feasibility check and ownership commit MUST serialize with relevant retention/pruning decisions: replay records needed by the admitted attempt MUST be pinned until its replay completes or the attempt is aborted. If pinning fails, admission fails without takeover. A cursor beyond the current Stream head, a mismatched Stream or an unrecognized Cursor MUST NOT be silently clamped.

### 5.2 Connection states

| State | Accepted inbound Frames | Transition |
|---|---|---|
| CHANNEL_READY | HELLO or RESUME only | successful authorization and admission → RECOVERING or READY; failure → CLOSED |
| RECOVERING | PING, PONG, and SYNC_COMMIT only for an active Full Sync; no SEND/REQUEST/STATE_QUERY | replay or baseline completion → READY; disconnect/fence → CLOSED |
| READY | SEND, REQUEST, STATE_QUERY, PING, PONG | disconnect/fence/expiry → CLOSED |
| CLOSED | none | terminal for this Channel |

- **R5.6** WELCOME is emitted once after successful admission and before EVENT replay. The Server MUST NOT send EVENT, STATE_SNAPSHOT or STATE_UPDATE before WELCOME.
- **R5.7** No second HELLO or RESUME is permitted on the same Channel.
- **R5.8** The Client MUST NOT send application Frames before WELCOME and READY; if recovery is required it MUST await RECOVERY_COMPLETE.
- **R5.9** A Server receiving an inadmissible Frame MUST reject it without application side effects and MAY close the Channel. PING/PONG are not authorization or admission substitutes.
- **R5.10** ERROR may be sent by either peer in any state other than CLOSED. Receiving an ERROR does not by itself change the connection state, except where section 13 requires the Channel to close.
- **R5.11** For HELLO NEW without Full Sync, WELCOME itself marks READY with the initial Cursor at the Application-selected Stream head. For ATTACH/RESUME replay, WELCOME enters RECOVERING and matching RECOVERY_COMPLETE marks READY only after durable application through `replay_to`. For FULL_SYNC, WELCOME enters RECOVERING, SYNC_COMMIT follows durable baseline commit, and matching RECOVERY_COMPLETE marks READY. During RECOVERING only PING/PONG and, for Full Sync, SYNC_COMMIT are valid client inbound Frames. The Server MUST NOT accept SEND, REQUEST or STATE_QUERY before READY. The Server's READY transition is defined by completion of recovery output, not by proof that the Client has durably applied replayed EVENTs; the Client independently enters READY only after verifying and durably applying the replay barrier. A Channel may close at any time; reconnection always requires authorization.

### 5.3 HELLO NEW

- **R5.12** HELLO mode NEW always creates a new Session, not necessarily a new Stream. After authorization to create a Session, the Application/Auth Provider MUST atomically choose an existing authorized Stream or create a new Stream, based on the authenticated Principal and deployment-defined account binding. The Server MUST reject a selection it cannot authorize. A new device need not know `stream_id`; WELCOME returns the selected `stream_id`.
- **R5.13** The Server allocates a fresh Session ID, persists the Session/Stream binding and generation=1, then sends WELCOME with admission=NEW. For NEW without State baseline, the Session Cursor starts at the selected Stream's atomic admission head and WELCOME `replay_to` carries that head; no historical EVENT is sent. Prior EVENTs are deliberately not replayed, and the Application MUST NOT assume that this NEW path has reconstructed historical State. The Session starts READY on WELCOME only if no State baseline is requested.
- **R5.14** If the Server supports an authorized complete State scope and atomic baseline cut, it MAY use WELCOME admission=FULL_SYNC and the SYNC_BEGIN/SYNC_PAGE/SYNC_COMMIT transaction. Otherwise it MUST reject the baseline request before creating the Session. A HELLO NEW that requests a baseline MUST use a deployment-defined scope that is stable for the Application-selected Stream, which MAY already exist.

### 5.4 HELLO ATTACH

- **R5.15** ATTACH requires a Client-supplied existing `stream_id`, Cursor and `state_sync_requested` flag, and creates a separate Session. The Server authenticates and authorizes access to that Stream, creates a new Session with generation=1 and sends WELCOME admission=ATTACHED only after proving and pinning the complete replay interval. If the Cursor cannot be replayed, it MAY use FULL_SYNC only when a complete consistent baseline is available; otherwise admission MUST be rejected before creating the Session.
- **R5.16** Stream attachment MUST NOT take over another Session or fence its Connection. Each Session has its own deduplication scope.

### 5.5 RESUME

- **R5.17** RESUME requires an existing Session ID and preserves its SEND dedup/outbox identity. The Client supplies `session_id`, Cursor, Capabilities and a mandatory `state_sync_requested` boolean. The Server verifies the Session is unexpired, authorizes the authenticated Principal for both the Session and its bound Stream, and verifies the Cursor `stream_id` matches the Session Stream. Only after those checks and a serialized choice of either a pinned replay interval or a provably complete consistent Full Sync baseline does it persist generation+1 and the new owner, fencing the old owner. It then sends WELCOME admission=RESUMED for replay or admission=FULL_SYNC for a verified complete baseline. WELCOME MUST carry the new generation.
- **R5.18** If replay is impossible, the Server MUST choose FULL_SYNC when `state_sync_requested`=1, and otherwise MAY choose FULL_SYNC only after verifying its baseline feasibility before takeover; otherwise it MUST reject RESUME without changing Generation or owner. The retention decision MUST serialize with pruning. A failed RESUME MUST NOT fence the old owner.

### 5.6 State synchronization admission

- **R5.19** The Server admits each request according to this table.

| Request | `state_sync_requested` | Admission |
|---|---:|---|
| HELLO NEW | 0 | Bind Application-selected Stream at head; WELCOME NEW, READY |
| HELLO NEW | 1 | Full Sync of selected Stream at a proven cut, or reject |
| HELLO ATTACH | 0 | Replay from supplied Cursor; safe Full Sync fallback or reject |
| HELLO ATTACH | 1 | Full Sync of specified Stream or reject; supplied Cursor used only to validate Stream identity |
| RESUME | 0 | Replay from durable Cursor; safe Full Sync fallback or reject |
| RESUME | 1 | Full Sync of bound Stream or reject; preserve Session ID and SEND dedup |

For all requests, the Server MUST authorize before allocating or fencing and MUST reject Full Sync if no complete consistent projection is available. An empty new Stream MAY have an empty baseline at baseline_seq=0; State from a different Stream MUST NOT be imported as its projection.

- **R5.20** NEW, ATTACH and RESUME are not interchangeable.

### 5.7 Concurrent takeover

- **R5.21** Two concurrent authorized RESUMEs are serialized. Each successful takeover increments generation; the last committed takeover is the only owner. A superseded Channel MUST stop producing new Session output or starting new effects.
- **R5.22** A superseded Channel's outstanding non-durable REQUESTs are logically cancelled and MUST NOT be replayed on the replacement Channel.
- **R5.23** If a WELCOME is lost, the Client may establish another Channel and RESUME again; the Server MUST treat this as a new authorized takeover, not assume the earlier Channel is still owned.

## 6. Session lease and expiry

### 6.1 Deadlines

- **R6.1** A Session expires at the earlier of durable `expires_at` and immutable `absolute_expires_at` in authoritative Session storage. Admission and expiry decisions are serialized across nodes using that store's clock; Server wall-clock authority MUST be shared and consistent enough for the store's decision. Node-local monotonic clocks MAY schedule wakeups but MUST NOT independently decide durable cross-node expiry. After process restart, the persisted deadline is authoritative; restart MUST NOT reset TTL. The authoritative Session store MUST serialize successful admission, expiry and Generation takeover across nodes.
- **R6.2** The authoritative store persists `expires_at`, `absolute_expires_at`, `last_renewal_at`, Principal binding and Generation. A deployment MUST choose and document a positive absolute Session lifetime of at least `4 * session_ttl_seconds`, so that rotation (R6.11) has time to complete. `absolute_expires_at` is fixed on Session creation and MUST NOT be extended by RESUME or PING.
- **R6.3** At admission the store atomically checks that neither deadline has been reached, validates authorization and replay/baseline feasibility, then commits the new Generation and `expires_at = min(now + session_ttl_seconds, absolute_expires_at)`. HELLO NEW and HELLO ATTACH create Sessions with a persisted deadline and the immutable absolute cap; RESUME before expiry refreshes the deadline within that cap; after expiry RESUME MUST fail without takeover. New Session creation is required after absolute expiry, and an old SEND outbox MUST NOT be silently migrated.
- **R6.4** Expiry fences the owner and stops new effects, including when a Channel remains connected. A commit racing expiry MUST be serialized with the same ownership/fencing decision or be durably idempotent. Committed outcomes remain available for reconciliation according to retention policy, and expiration cleanup MUST NOT erase records required to reconcile indeterminate external effects. Session expiry, auth revocation and Channel closure MUST stop further Session-scoped operations.

### 6.2 Renewal on a healthy connection

- **R6.5** WELCOME carries `session_ttl_seconds` and `absolute_remaining_seconds`. The Client keeps three estimates on its monotonic clock, each deliberately early. They are safe because the Server's reading of its clock lies between the moment the Client sent HELLO/RESUME and the moment it received WELCOME.
  - `absolute_deadline` = (time the Client sent HELLO or RESUME) + `absolute_remaining_seconds`. Nothing moves it.
  - `lease_deadline` = `min(` (time the Client sent HELLO or RESUME) + `session_ttl_seconds`, `absolute_deadline` `)`.
  - `renewal_due` = (time the Client received WELCOME) + `session_ttl_seconds / 4`, plus a small drift allowance (for example 1%).
- **R6.6** Ordinary PING/PONG, SEND, REQUEST and Channel activity do NOT extend the lease. A due, reauthorized renewal PING is the only in-Channel lease renewal mechanism.
- **R6.7** The Server MUST reauthorize the Principal through the Auth Provider before renewing an existing lease. Renewals are throttled: a PING received at or after `last_renewal_at + session_ttl_seconds/4` is a renewal PING; earlier PINGs are ordinary liveness probes and force no write. For a renewal PING, the Server MUST first reauthorize and durably persist `expires_at = min(now + ttl, absolute_expires_at)` and `last_renewal_at = now` before sending the matching PONG. A matching PONG for a renewal PING proves persisted renewal, not merely connectivity.
- **R6.8** If renewal fails, the Server MUST NOT send a matching PONG: it MUST close the Channel, using AUTH_REVOKED when authorization was revoked or SESSION_EXPIRED when a deadline has elapsed. A PING arriving after expiry cannot revive the Session. Authorization revocation MUST be checked at effect boundaries independently of heartbeat cadence.
- **R6.9** The Client sends a renewal PING at or after `renewal_due`, and ordinary liveness PINGs (R7.1) otherwise. Because `renewal_due` is never earlier than the Server's due time, the Server classifies every PING the Client treats as a renewal PING as one. When the matching PONG of a renewal PING arrives, the Client sets `lease_deadline = min(` (time it sent that PING) + `session_ttl_seconds`, `absolute_deadline` `)` and `renewal_due` = (time it received that PONG) + `session_ttl_seconds / 4`. A PONG for any PING sent before `renewal_due` carries no lease information and MUST NOT move `lease_deadline`.
- **R6.10** If `lease_deadline`, less a safety margin of at least `2 * heartbeat_ms`, is reached without a confirmation, the Client MUST stop new effects and reconnect with RESUME; it MUST NOT silently continue on the old Channel.
- **R6.11** When `absolute_deadline` minus the current time falls below `2 * session_ttl_seconds`, the Client SHOULD stop starting new SENDs on this Session, wait for outstanding SENDs to reach a final ACK, and continue on a new Session (HELLO NEW, or ATTACH with its Cursor). SENDs still unresolved at the deadline are handled by R6.12. At absolute expiry the Server SHOULD send SESSION_EXPIRED before closing.

### 6.3 After expiry

- **R6.12** If RESUME fails because Session state is expired, missing or cannot be safely recovered, the Client MUST NOT replay the old Session's pending SENDs into a newly created Session automatically. It MUST expose unresolved operations to the Application for reconciliation; the Application may choose new operation IDs only with an independent idempotency/reconciliation policy.
- **R6.13** A transient Channel loss does not itself expire a Session. Transport reconnection, authentication and authorization are repeated on every RESUME.

## 7. Heartbeat, idle timeout and gaps

- **R7.1** Heartbeat is application-level and does not substitute for transport liveness or cryptographic freshness. Either peer MAY send PING, but the Client MUST originate liveness PINGs at intervals no greater than `heartbeat_ms` while an admitted Channel is active.
- **R7.2** A receiver MUST send a matching PONG for an authorized, nonexpired Session unless the renewal-PING failure rule (R6.8) applies. The PONG nonce MUST match the outstanding PING; an unsolicited PONG MUST be ignored.
- **R7.3** Any complete valid inbound Frame resets the local inbound-idle timer; invalid frames never do. If no valid inbound Frame arrives for `idle_timeout_ms`, the peer MUST close the Channel. A Client MAY close sooner after one unanswered heartbeat interval, but MUST NOT infer successful lease renewal from silence.
- **R7.4** The Client tracks `next_expected`, an in-memory sequence initialized to `Cursor + 1` when WELCOME is received and advanced for every EVENT it accepts. An EVENT whose `seq` is not `next_expected`, in replay or READY, is a gap or duplicate violation: the Client MUST NOT accept it, MUST close the Channel, and MUST initiate RESUME on a new Channel using its durable Cursor.
- **R7.5** The durable Cursor is separate from `next_expected`. It advances only to a sequence whose effects are durable, and the Client MAY commit in batches, so the Cursor may lag `next_expected - 1` by any number of accepted EVENTs. After a reconnect those EVENTs are replayed and applied again, which is safe because applying an EVENT is atomic with the Cursor or idempotent by `event_id`. The Client MUST NOT discard an accepted EVENT before its effects are durable, and it MUST have committed through `replay_to` before it treats recovery as complete.
- **R7.6** During recovery the Client MUST reject premature live EVENTs, including EVENTs arriving after a partial-replay ERROR on that Channel. On auth revocation or expiry, the Client MUST stop retries on that Session.

## 8. Reliable SEND

### 8.1 Outbox and deduplication

- **R8.1** Before its first SEND, the Client MUST durably store `(session_id, msg_id, exact content)`. The same Session retry MUST use the same ID and bytes. The Client removes an outbox item only after durably storing its final ACK.
- **R8.2** The Server dedup key is `(session_id, msg_id)`; the same key with different content MUST fail without invoking the Application (SEND_CONFLICT). Completed outcomes MUST survive reconnect and be returned identically on duplicate SEND.
- **R8.3** The Server MUST atomically and durably claim a dedup key before invoking the Application. Concurrent duplicates MUST observe one in-flight operation, not start parallel effects. The claim, content identity, terminal result and retention lifecycle MUST be crash-recoverable. An in-flight claim without a proven outcome MUST NOT be treated as an unprocessed command.

### 8.2 Commit contract

- **R8.4** A final ACK means that the Application's terminal outcome and the corresponding dedup record are durable. The Server MUST NOT emit a final ACK before both are committed. ACK confirms Application completion, not transport delivery.
- **R8.5** To guarantee at-most-once effects across crashes, the Application MUST either (a) commit the business effect and dedup outcome in one atomic transaction, or (b) provide an equivalent durable idempotency/reconciliation mechanism keyed by a stable operation identity. KMTProto alone cannot make non-transactional external effects exactly once.
- **R8.6** ACK loss does not erase a committed outcome: a same-Session retry returns the persisted ACK.
- **R8.7** QUICK_ACK, if negotiated (capability 1), proves only that the Server has durably admitted the SEND and its dedup claim. It does not prove application execution or success, and it is never a substitute for final ACK. Loss of QUICK_ACK cannot authorize duplicate execution.

### 8.3 Pending-state machine

- **R8.8** For each `(session_id, msg_id)`, the durable dedup state is ABSENT → CLAIMED → COMMITTED or INDETERMINATE. CLAIMED is not terminal and MUST NOT be removed while the Session accepts retries.
- **R8.9** A duplicate CLAIMED SEND with identical bytes receives ERROR SEND_PENDING (code 10, retryable=1, ErrorRef msg_id), without starting another effect. A duplicate COMMITTED SEND receives the byte-identical final ACK. A duplicate INDETERMINATE SEND receives ERROR SEND_INDETERMINATE (1001, retryable=0) and MUST NOT re-execute. Different bytes for any existing claim yield SEND_CONFLICT (9).
- **R8.10** After crash/restart, a CLAIMED operation MUST be reconciled against durable application evidence before progressing. If provably not started, it MAY resume under the current Generation using the original claim; if provably committed, persist COMMITTED and return ACK; if neither can be proved, persist INDETERMINATE.
- **R8.11** A CLAIMED operation MUST NOT remain indefinitely unresolved solely because its original Channel disappeared: the Server MUST run recovery/reconciliation on restart or on the next duplicate; if resolution is impossible, transition to INDETERMINATE.
- **R8.12** A Client MAY retry only an identical SEND on SEND_PENDING while its Session remains valid; no fixed retry delay or automatic retry frequency is guaranteed by the protocol. Session expiry terminates the retry window, not the duty to retain evidence needed for external reconciliation.

### 8.4 Indeterminate outcomes and fencing

- **R8.13** If the Server cannot prove whether a business effect committed, it MUST mark the operation INDETERMINATE, MUST NOT automatically invoke it again, and MUST expose this state for application reconciliation. INDETERMINATE is not an application failure and MUST NOT be encoded as an ACK with outcome=APPLICATION_ERROR.
- **R8.14** ERROR code 1001 SEND_INDETERMINATE has retryable=0 and ErrorRef kind=1 referring to the SEND `msg_id`; `detail` MAY be empty. It means the Server cannot prove whether the operation committed. The Client MUST retain the unresolved outbox item for application reconciliation and MUST NOT automatically re-execute it. It is not a final ACK and does not imply failure of the business effect.
- **R8.15** A generation check only at handler start is insufficient. Before starting an application effect and at its irreversible commit boundary, the Server MUST enforce either a transactional fencing check against the current Generation or an application-level idempotent commit protocol that prevents duplicate or contradictory effects. An effect committed before takeover remains valid and its durable result MUST be available to the new Generation. An effect that cannot be fenced or reconciled MUST be reported as INDETERMINATE; it MUST NOT be retried blindly.
- **R8.16** A generation takeover MUST NOT erase completed results or re-run an already committed effect. An in-flight operation started under an older generation may finish only if its application commit is safely fenced or idempotent; otherwise the Server MUST fail it as indeterminate rather than claiming exactly-once.

### 8.5 Retention and flow control

- **R8.17** The Server MUST retain dedup claims and terminal outcomes for the entire interval in which it accepts retries for that Session, which MUST cover the advertised Session lifetime. It MUST NOT accept a retry if the corresponding dedup history has been pruned. Session expiry forbids further retries and RESUME; an old outbox MUST NOT be automatically migrated into a new Session, and the Client MUST surface unresolved operations for application reconciliation.
- **R8.18** `max_inflight_send` bounds outstanding SENDs (section 13.3). RATE_LIMITED on SEND MUST carry ErrorRef to `msg_id` and MUST NOT imply a durable claim was made; if a claim already exists, use SEND_PENDING or the existing terminal result instead. SEND retries always reuse the original `msg_id` and exact bytes, never assume RATE_LIMITED is a final ACK, and stop at Session expiry.
- **R8.19** A SEND that the admitted Principal is not permitted to perform is a business outcome, not a protocol failure: the Server answers it with a final ACK whose outcome is APPLICATION_ERROR after the normal claim and commit.

## 9. REQUEST and RESPONSE

- **R9.1** REQUEST/RESPONSE is a non-durable, single-connection query exchange. A REQUEST MUST be safe to repeat: the application method MUST NOT create externally visible non-idempotent effects. Applications MUST use SEND for commands that require durable effect/retry guarantees.
- **R9.2** REQUEST IDs correlate Responses only within the current Session generation; the Server does not durably deduplicate or replay them. A disconnect or generation takeover cancels outstanding REQUESTs logically; late Responses from a fenced generation MUST NOT be delivered on a new Channel. A Client MAY retry a query as a new REQUEST after READY, with a fresh `request_id`.
- **R9.3** REQUEST results are observations, not recovery cursors or State baselines. REQUEST does not change EVENT ordering or State versions.
- **R9.4** `max_inflight_request` bounds outstanding REQUESTs (section 13.3). RATE_LIMITED on a REQUEST carries ErrorRef to `request_id`. A REQUEST that the admitted Principal is not permitted to perform is answered with a RESPONSE whose outcome is APPLICATION_ERROR.

## 10. EVENT delivery and incremental recovery

### 10.1 Invariants

- **R10.1** An EVENT sequence number is unique, contiguous and immutable. An admission attempt has one immutable `replay_to` barrier. The Server MUST NOT acknowledge recovery as completed on the Client's behalf.

### 10.2 Incremental replay

- **R10.2** For ATTACH and RESUME with a replayable Cursor, the Server captures the Stream head as `replay_to` while establishing the retention pin, then admits the connection. WELCOME has admission ATTACHED or RESUMED and carries this barrier.
- **R10.3** The Server sends EVENTs with strictly contiguous sequence numbers from `last_seq+1` through `replay_to`, in order, then RECOVERY_COMPLETE with the same barrier, when the complete barrier fits the admitted replay chunk (R10.9). Empty replay still ends with RECOVERY_COMPLETE if recovery mode was entered; REPLAY_PARTIAL MUST never be used for an empty chunk.
- **R10.4** Events beyond the barrier and live STATE_UPDATE MUST NOT interleave into the recovery output lane before RECOVERY_COMPLETE. STATE_UPDATE is non-durable cache data, never a substitute for EVENT replay.
- **R10.5** The Client verifies contiguity and immutable event identity, advances its Cursor only over durably applied EVENTs, and enters READY only after receiving the marker and durably applying through `replay_to`. Receiving the marker is not an acknowledgement of Client persistence to the Server.
- **R10.6** The Client applies each EVENT atomically with its Cursor, or idempotently by `event_id`, and advances the Cursor only to a sequence whose effects are durable; it MAY commit in batches (R7.5). On disconnect it resumes from its durable Cursor, never the last merely received sequence.
- **R10.7** The Client MUST NOT accept a gap or a duplicate (R7.4). Replay always starts at Cursor+1, so a correct Server never repeats a sequence on one Channel; conflicting content for a sequence the Client already holds is a fatal Stream consistency error.
- **R10.8** If the Channel fails mid-replay, the Client retries RESUME from its last durable Cursor. The Server may choose a newer barrier on the new attempt. If the pin cannot be maintained or data is lost, the Server aborts the attempt, never skips an EVENT.

### 10.3 Bounded replay

- **R10.9** The Server MAY choose a contiguous replay chunk of at most `max_replay_events`. If `replay_to` is beyond the end of the chunk, it MUST send exactly the chunk EVENTs followed by ERROR REPLAY_PARTIAL (code 13, retryable=1, ErrorRef kind=0, retry_after_ms=0) and close the Channel; it MUST NOT send RECOVERY_COMPLETE or READY.
- **R10.10** The Client MUST durably commit the received contiguous EVENTs before starting a new authorized RESUME using its updated Cursor. The next RESUME obtains a fresh barrier and Generation; all replay and retention checks repeat.
- **R10.11** The Server MUST NOT emit REPLAY_PARTIAL before sending at least one EVENT of progress, and MUST reject admission if no progress can be guaranteed. A replay requiring more than `max_replay_events` MUST use bounded replay chunks, choose a safe Full Sync, or reject admission; it MUST NOT silently truncate or claim recovery complete. A Stream whose production rate exceeds catch-up rate MAY require indefinite rounds; deployments SHOULD use Full Sync where supported or apply application backpressure. Chunking is never a guarantee of eventual catch-up under unbounded writes.

### 10.4 Retention

- **R10.12** The Server MUST NOT prune any EVENT pinned by an active replay. Pins MUST be bounded and released on completion, failure, timeout or fencing. The Server MUST NOT promise a replay window that it cannot preserve.
- **R10.13** The Client MUST distinguish a recoverable Channel failure from a rejected or expired Session; a new Session MUST NOT silently inherit unresolved SENDs from an old one.

## 11. State

### 11.1 Model

- **R11.1** State is a versioned, current-value projection, not a second reliable log. A State Object is keyed by `(namespace, object_id)`; its version increases strictly on each change. Deleted entries are tombstones. Equal versions are identical only when the raw StateEntry identity, deleted flag and data octets match (R2.21). An older version MUST NOT replace a newer locally applied version.
- **R11.2** Snapshots are current-state reads, not an EVENT history substitute. Missing objects do not imply deletion. Absence from a point query is not a deletion notification; only an explicit tombstone is.

### 11.2 STATE_QUERY and STATE_SNAPSHOT

- **R11.3** STATE_QUERY MUST contain 1..`max_state_items` distinct StateKeys. Keys are matched byte-for-byte (UTF-8 without normalization), and duplicates MUST be rejected.
- **R11.4** The Server MUST authorize every requested key before producing any page; a partially authorized query MUST fail as a whole, without leaking unauthorized values or key existence.
- **R11.5** For each requested key, the Server returns exactly one result in the same order as the query: PRESENT with a StateEntry, DELETED with a tombstone StateEntry, or MISSING. MISSING means that the key has no retained object/tombstone at the query's read view; it MUST NOT be interpreted as a deletion EVENT or an instruction to erase an existing local cache. DELETED is an explicit versioned tombstone, and may replace an older cached version.
- **R11.6** All results of a query MUST derive from one consistent logical read view, even when paginated; changes during pagination MUST NOT cause mixed-version pages. The Server MUST retain that view for the lifetime of the query, or terminate the query with an error; it MUST NOT silently switch to a newer view mid-query. State versions are monotonic per key; equal-version content conflicts are errors (STATE_CONFLICT).
- **R11.7** Pages MUST be contiguous with `page_index` starting at 0. The concatenation of results MUST have exactly the number of requested keys, in request order, and each PRESENT/DELETED entry's key MUST match the corresponding requested key. There MUST be exactly one `final_page`=1, including for a one-page response. Empty nonfinal pages MUST NOT be sent. The total number of results MUST NOT exceed the requested key count. Each page MUST fit the negotiated Frame limit. A Server that cannot encode a single result in one Frame MUST fail the query, not truncate it.
- **R11.8** Any malformed page index, inconsistent result key, incomplete response or partial authorization MUST fail the entire query.
- **R11.9** A Client MUST stage all pages until `final_page`, validate counts, order and identity, then apply the query result atomically as a read result. A failed or interrupted query MUST NOT partially update the application-visible result. The query is scoped to the current Session Generation; late pages from a fenced connection MUST be discarded. A new query after reconnect MUST use a fresh `query_id`.
- **R11.10** STATE_QUERY is a bounded, point-in-time read. It is not a Full Sync baseline, never advances an EVENT Cursor, does not imply an EVENT/State cut, and MUST NOT be used as a recovery baseline.

### 11.3 STATE_UPDATE

- **R11.11** STATE_UPDATE is an opportunistic versioned cache update on a READY Channel. It is not replayed, not acknowledged, has no Stream `seq`, and MUST NOT advance a Cursor or establish a recovery baseline. It may be lost on disconnect.
- **R11.12** Receivers MAY apply a STATE_UPDATE only if the object version is newer and the application permits speculative cache freshness; otherwise they MAY discard it and issue STATE_QUERY. If it conflicts with an equal local version, the receiver MUST reject the update and reconcile via STATE_QUERY.
- **R11.13** Applications needing durable ordered changes MUST encode them in EVENT, not rely on STATE_UPDATE.
- **R11.14** No causal or atomic ordering between an EVENT and a STATE_UPDATE is implied by their arrival order. In particular, receiving STATE_UPDATE version N does not prove that the EVENT describing that change has been applied. If the application requires EVENT-to-State causality, it MUST encode the relevant State identity/version in the opaque EVENT payload and reconcile through STATE_QUERY. The Core MUST NOT fabricate an EVENT-to-State relationship.

## 12. Full Sync

### 12.1 Consistent cut

- **R12.1** A Full Sync scope MUST be a deterministic, complete projection of the Stream EVENT prefix through `baseline_seq`. The Server MUST create the snapshot and capture the Stream head at one serializable commit boundary (or an equivalent MVCC transaction that proves the same cut). It MUST NOT combine an independently read State snapshot with a later sampled Stream head. State changes whose recovery semantics depend on EVENT MUST commit their EVENT and projection mutation atomically or under a replayable, causally ordered projection checkpoint. A projection lagging the chosen head is not eligible. Non-EVENT-backed, opportunistic STATE_UPDATE data MUST NOT be represented as authoritative Full Sync State.
- **R12.2** A Full Sync baseline replaces the entire authorized scope. Scope identity and its membership rules MUST remain stable for a Session; an authorization or scope change requires a fresh explicitly authorized baseline, not a silent merge. A Server unable to enumerate the scope completely or maintain an atomic cut MUST reject Full Sync.
- **R12.3** Full Sync is needed if the Client cannot replay from its Cursor, or a newly admitted Session explicitly requests a complete baseline. The Server MUST establish a point-in-time, authorized, complete State baseline for a precisely declared scope, and an EVENT barrier `baseline_seq` representing the same serializable commit cut. Every State mutation that needs ordered recovery MUST have a corresponding EVENT relationship within this cut. A deployment unable to produce such a consistent cut MUST reject Full Sync rather than fabricate one. FULL_SYNC is conformant only for a deployment that can prove a complete, authorized State projection and an atomic EVENT/State logical cut.
- **R12.4** SYNC_PAGE contains complete StateEntry values and tombstones for a declared scope, not point-query SnapshotResults. Missing keys in the Full Sync scope are removed by the atomic scope replacement, while missing point-query keys are merely reported MISSING.

### 12.2 Transaction

- **R12.5** The Full Sync exchange uses WELCOME(admission=FULL_SYNC, `replay_to`=`baseline_seq`), SYNC_BEGIN, one or more SYNC_PAGE, SYNC_COMMIT and RECOVERY_COMPLETE. `sync_id` MUST be unique and unpredictable for each attempt and MUST be bound to the admitted Session Generation. `scope_id` is a nonempty, server-defined stable identifier of the complete authorized State scope; the Client MUST NOT merge a baseline with a different scope into an existing State store. The Server MUST send a complete snapshot of that scope at the logical cut `baseline_seq`, including tombstones retained by that scope's consistency policy, and MUST guarantee that State and EVENT share this cut; otherwise it MUST reject Full Sync before admission.
- **R12.6** SYNC_BEGIN MUST immediately follow WELCOME for FULL_SYNC and precede all SYNC_PAGE frames. All pages MUST be from the same immutable view and have contiguous `page_index` starting at 0, exactly one `final_page`=1, and a total StateEntry count equal to `total_entries`. Even an empty snapshot MUST send one final page with count=0. Duplicate State keys in a baseline, page index gaps, mismatched sync IDs, exceeding advertised bounds or an incorrect total count are fatal for that attempt.
- **R12.7** The Server MUST NOT send EVENT or STATE_UPDATE during baseline transfer.
- **R12.8** The Client MUST stage the complete baseline without replacing its active State. It MUST atomically and durably replace the scope's baseline State plus Cursor=`baseline_seq` before sending SYNC_COMMIT; if atomic commit is impossible, it MUST retain the old durable baseline/Cursor and abort. It MUST NOT send SYNC_COMMIT for partial, unverified or uncommitted pages.
- **R12.9** The Server MUST accept SYNC_COMMIT only after the complete page sequence was emitted, only on the same live Generation, and only with matching `sync_id` and `baseline_seq`; otherwise it closes the attempt without releasing live events. It then sends RECOVERY_COMPLETE(`baseline_seq`), releases subsequent live EVENTs in sequence and transitions to READY. The Client transitions to READY only upon matching RECOVERY_COMPLETE after its durable baseline commit. No old Generation's SYNC_COMMIT may complete a new attempt, and a forged or stale baseline acknowledgement MUST be rejected without advancing recovery. Baseline acknowledgements MUST NOT be accepted as application SEND acknowledgements.
- **R12.10** A lost response or Channel failure after Client commit is safe: a subsequent RESUME starts at its durable Cursor. A reconnect before baseline commit MUST discard or safely resume staged pages without ever advancing the durable Cursor. Full Sync page failures leave the prior durable baseline/Cursor untouched.

### 12.3 Retention and scope

- **R12.11** The Server MUST establish a retention pin for all EVENTs with `seq` > `baseline_seq` produced while baseline pages are transmitted, before admitting Full Sync. It MUST retain that pin through SYNC_COMMIT and the transition to live delivery; if the pin cannot be guaranteed, it MUST reject admission before Generation takeover. On SYNC_COMMIT, the Server sends RECOVERY_COMPLETE(`baseline_seq`) and then EVENTs strictly in sequence from `baseline_seq`+1, without gaps, and MUST NOT skip events generated during baseline transfer. The Client MUST NOT accept live EVENTs until RECOVERY_COMPLETE and MUST durably apply contiguous EVENTs. The Server MAY release the pin only after the connection's queued delivery has a durable source for subsequent RESUME; it MUST never discard events solely because they were written to a Channel.
- **R12.12** This protocol does not define cross-application scope identity semantics; deployments MUST document `scope_id` and the corresponding projection before enabling Full Sync.

### 12.4 Data-loss boundary

- **R12.13** Full Sync replaces State with the complete projection at `baseline_seq`. Any information that existed only as EVENTs before that cut and is not represented in the State projection is irretrievably unavailable through this recovery path. The Client MUST emit an Application-visible full-sync notification containing `scope_id` and `baseline_seq` after the baseline commit and before reporting recovery READY; the Application is responsible for restoring any EVENT-only derived data by separate means.

## 13. Errors and flow control

### 13.1 ERROR registry

- **R13.1** ERROR has `code:u16, retryable:u8, ErrorRef, retry_after_ms:u32, detail:text`. The `retryable` byte MUST equal the fixed value in this registry, not a server-selected hint.
- **R13.2** Error details are diagnostic only and MUST NOT reveal protected Session existence or credentials. Unrecognized error codes MUST be treated as nonretryable protocol failures; the receiver MUST NOT infer safe replay of SEND.

| Code | Symbol | retryable | Meaning |
|---:|---|---:|---|
| 1 | MALFORMED_FRAME | 0 | Invalid encoding or frame direction |
| 2 | PROTOCOL_STATE | 0 | Frame illegal in current connection state |
| 3 | UNAUTHORIZED | 0 | Authentication/authorization denied, indistinguishable from unknown protected Session |
| 4 | ADMISSION_REJECTED | 0 | Cursor invalid, expired or replay/full-sync unavailable |
| 5 | LIMIT_EXCEEDED | 0 | Frame, field, list or State-item size bound violated; retrying the same operation cannot succeed |
| 6 | UNSUPPORTED_CAPABILITY | 0 | Required local feature not available; no negotiation fallback implied |
| 7 | STATE_CONFLICT | 0 | Same key/version with different data |
| 8 | STATE_QUERY_FAILED | 1 | Consistent read could not complete; retry as new query after READY |
| 9 | SEND_CONFLICT | 0 | Reused msg_id with different bytes |
| 10 | SEND_PENDING | 1 | Same SEND is durably claimed but has no terminal outcome; retry identical SEND only |
| 11 | SESSION_EXPIRED | 0 | Authorized Session no longer resumable |
| 12 | SYNC_ABORTED | 0 | Baseline transaction cannot complete safely |
| 13 | REPLAY_PARTIAL | 1 | A bounded replay chunk was delivered; reconnect using the last durably applied Cursor |
| 14 | RATE_LIMITED | 1 | Operation rejected before effects, including an in-flight SEND or REQUEST count above the advertised limit; retry no sooner than retry_after_ms |
| 15 | AUTH_REVOKED | 0 | Previously admitted Principal authorization revoked; close Channel, no further effects |
| 1001 | SEND_INDETERMINATE | 0 | Business effect cannot be proved committed or absent; application reconciliation required |

### 13.2 Rules

- **R13.3** RATE_LIMITED MUST carry `retry_after_ms` > 0, and is the only code used for in-flight count limits. Other errors MUST carry `retry_after_ms`=0 except SEND_PENDING, which MAY carry a positive retry delay. A retryable error does not override SEND identity, expiry or authorization constraints. The Client MUST wait at least `retry_after_ms` before retrying the referenced operation. `retry_after_ms` is advisory to load management but a mandatory minimum when nonzero; zero means no server-specified minimum, not immediate guaranteed availability.
- **R13.4** For SEND errors, ErrorRef kind=1 refers to `msg_id`; for REQUEST errors, kind=1 refers to `request_id`. For admission, State and Sync errors without a Message/Request identifier, ErrorRef kind=0 MUST carry the all-zero ID.
- **R13.5** SEND_PENDING is nonterminal and permits only an identical SEND retry. A CLAIMED operation MUST be reconciled after a crash; an unprovable outcome becomes SEND_INDETERMINATE, never automatic re-execution. SEND_INDETERMINATE MUST NOT trigger automatic replay.
- **R13.6** A fatal framing or state error closes the Channel. An operation-scoped error terminates only that operation unless the Session is no longer safe; SYNC_ABORTED closes the Channel. REPLAY_PARTIAL is recovery-scoped (ErrorRef kind=0) and closes the Channel after delivering a contiguous chunk.
- **R13.7** UNAUTHORIZED is used only for failed admission and MUST NOT distinguish an absent Session from an unauthorized one. AUTH_REVOKED is used only for an already authenticated Session whose authorization is subsequently withdrawn, and MUST close the Channel. AUTH_REVOKED and SESSION_EXPIRED close the Channel and prohibit further effects.

### 13.3 Backpressure

- **R13.8** `max_inflight_send` and `max_inflight_request` bound outstanding operations. The Client MUST NOT exceed the advertised inflight limits, and the Server MUST NOT invoke an application operation beyond them. When the Server rejects an operation for exceeding an in-flight count it MUST do so before any effect with RATE_LIMITED, never LIMIT_EXCEEDED.
- **R13.9** LIMIT_EXCEEDED (code 5, retryable=0) is reserved for size and shape bounds (Frame, field, list, State items) where retrying the same operation cannot succeed. An operation rejected with it was not claimed, and the Client MUST NOT retry it unchanged.

## 14. Limits and capabilities

### 14.1 Limits

- **R14.1** WELCOME Limits values MUST be nonzero. `max_frame_bytes` MUST be in [8,1048576], but a deployment MUST set it large enough for its mandatory control frames. `max_inflight_send` and `max_inflight_request` are positive u16 counts of uncompleted operations; `max_replay_events` is a positive u32 bound on events transmitted in one replay attempt; `max_state_items` is a positive u16 bound on State keys in one query and State entries in one page.
- **R14.2** `heartbeat_ms`, `idle_timeout_ms`, `session_ttl_seconds` and `absolute_remaining_seconds` MUST be positive. `idle_timeout_ms` MUST be greater than `heartbeat_ms`. `heartbeat_ms` MUST NOT exceed `session_ttl_seconds * 1000 / 8` (integer division), so that several renewal opportunities exist between the first renewal due time (`session_ttl_seconds / 4`) and the end of the lease. `absolute_remaining_seconds` MAY be smaller than `session_ttl_seconds` near the end of a Session's life. A Client MUST close a Connection whose WELCOME violates these bounds.
- **R14.3** Implementations MUST reject multiplication/addition overflow and oversized fields before allocation.
- **R14.4** All pages and Frames MUST respect `max_frame_bytes`. WELCOME `max_frame_bytes` MUST be large enough to encode WELCOME itself, ERROR and mandatory recovery control Frames; otherwise admission fails. An oversized individual EVENT or StateEntry cannot be silently split: reject the originating application payload or fail admission/query/sync safely. Limits apply to the admitted Connection and are not renegotiated mid-Generation.
- **R14.5** Text bounds: `stream_id`, `namespace`, `object_id`, `method` and `scope_id` are 1..255 UTF-8 bytes; ERROR `detail` is 0..1024 bytes. HELLO mode NEW alone permits an empty `stream_id`. The Cursor `stream_id` follows the same bound. The capability list count MUST be at most 64. Zero IDs are forbidden except the null ErrorRef.

### 14.2 Capabilities

- **R14.6** V1 capability codes: 1=QUICK_ACK. All other codes are unassigned. Client HELLO/RESUME advertises supported optional capabilities; WELCOME lists the intersection of the Client offer and Server support, sorted and unique. Unrecognized offers are ignored, never echoed. Neither peer may use an optional capability unless it appears in WELCOME. The absence of QUICK_ACK disables Frame 6, without affecting final ACK.
- **R14.7** Full Sync, EVENT replay and STATE_QUERY are base protocol features, not optional capabilities. A Server unable to support a required base feature for an admission MUST reject it.

## Appendix A. Where the former documents went (informative)

This specification replaces the former documents of the P0/P1 draft. The mapping is kept so that earlier reviews can be followed.

| Former document | Now in |
|---|---|
| protocol.md, core.md, transport.md | sections 1, 3 and 4 |
| binary-wire.md | section 2, plus R5.19, section 11 and section 12 for the rules it carried |
| session.md, semantics.md | sections 4 to 6 and 9 |
| p0-p1.md | sections 5 to 7, 10, 12 and 13 |
| reliability.md, freeze-closure.md | sections 6, 8 and 12 |
| recovery.md | sections 10 and 12 |
| state.md | section 11 |
| control.md | sections 13 and 14 |
| freeze-record.md | removed; it recorded a freeze decision that no longer applies, and remains in the repository history |
