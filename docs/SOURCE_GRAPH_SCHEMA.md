# Source Graph Schema

`SourceNode` identifies a canonical URL, roles, type, current six-state access status, claims, provider routing, and append-only `CaptureVersion` records. `capture_history` records provider, status, failure mode, timestamp, fallback use, and elapsed time. Unknown provider fields remain in `provider_metadata`; raw payloads are persisted by path.

