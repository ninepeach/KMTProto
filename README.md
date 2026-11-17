# KMTProto

**A transport-independent binary protocol for reliable messaging, session recovery and state synchronization.**

**Status: V1 DESIGN DRAFT — NOT FROZEN.** There is one protocol design and no legacy compatibility requirement. The historical JSON design is superseded, not a supported wire version.

## Architecture

```
Go Client + Server            TypeScript Browser Client
        \                         /
            KMTProto Core
    SEND / ACK / Session / Recovery / State
                  |
             Channel Adapter
                  |
    TLS\/TCP · WSS · other reliable Channels
```

- Go: Client and Server, TCP and WebSocket first; reliable UDP later.
- TypeScript: browser WebSocket binary Client only.
- One binary wire protocol shared across all implementations and transports.
- Encryption and authentication mechanisms are supplied by Channel adapters and the hosting application, not mandated by KMTProto Wire.
- Channel adapters deliver reliable ordered complete Frames. Raw UDP is not directly conformant.
- A Protocol Session survives disconnect and Channel changes; every RESUME requires fresh authorization.

## Documents

| Document | Role |
|---|---|
| [spec/protocol.md](spec/protocol.md) | **The single normative specification.** Every rule is a numbered clause (`R<section>.<n>`). |
| [spec/golden-vectors.md](spec/golden-vectors.md) | Byte-exact wire vectors for all 19 Frames, plus variants. |
| [spec/conformance.md](spec/conformance.md) | Normative acceptance plan: expected behavior per fault, each row citing clauses. Not executed test evidence. |
| [spec/secure-channel.md](spec/secure-channel.md) | Informative notes on Channel security options. |
| `tools/` | Informative validators, see below. |

The specification is organised as: 0 conventions, 1 scope, 2 binary encoding, 3 Channel and security, 4 Streams and Sessions, 5 admission, 6 lease and expiry, 7 heartbeat and gaps, 8 reliable SEND, 9 REQUEST/RESPONSE, 10 EVENT delivery and recovery, 11 State, 12 Full Sync, 13 errors and flow control, 14 limits and capabilities.

## Validation

```
python3 tools/check_vectors.py   # golden vectors: encoding, enums, limit and ERROR constraints
python3 tools/check_spec.py      # clause numbers, cross-references, links, registry consistency
```

These checks cover encoding and document consistency only. They do not execute protocol behavior, and no implementation has been verified against the specification yet. Independent SDK interoperability testing is required to claim implementation conformance.

License: Apache-2.0.
