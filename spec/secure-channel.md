# Optional Channel Security Implementations — Non-normative

This document is **informative only**. KMTProto V1 does not require Noise or TLS as part of its binary wire protocol.

The normative abstraction is the [Channel contract](protocol.md) (section 3 of the specification). A deployment chooses a Channel security mechanism and policy independently of KMTProto Core. Candidate implementations include TLS 1.3 over TCP, WSS, or a Noise-based adapter. This document does not select a Noise handshake pattern, define cryptographic records or mandate any particular library.

For sensitive remote Sessions, a deployment MUST provide confidentiality, integrity and server endpoint authentication, and MUST separately authenticate and authorize the client Principal. Verified Channel security attributes are local trusted context, not remotely declared KMTProto fields.

A Channel implementation is responsible for its own handshake, cryptographic key validation, record framing, replay protection, limits, error handling and key lifecycle. Failures MUST NOT deliver unauthenticated Frame data to Core.

Security of a Channel does not imply permission to RESUME. A Session ID is not a bearer credential; Core admission requires a fresh authorization decision before generation fencing.

Any future Noise profile is an independent adapter specification, not a KMTProto Wire version.
