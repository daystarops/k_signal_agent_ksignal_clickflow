# K-Signal Engine V1 Operational Architecture

Pipeline: seed → discover → capture → correlate → score → brief → render.

Public pages are observable signals. Login-only, private, or robots-denied branches terminate as `denied`. Rate limits and partial captures are `degraded`. Captures are append-only timestamped versions. Providers report outcomes; the orchestrator alone selects fallbacks.

The source graph and JSON sidecars are authoritative. Markdown briefs and rendered cards are projections of machine-readable records.

