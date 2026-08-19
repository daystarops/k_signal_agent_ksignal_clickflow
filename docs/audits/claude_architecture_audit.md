# Claude Architecture Audit — K-Signal

> **Audit date:** 2026-08-10
> **Primary source of truth:** `K_SIGNAL_HARDENED_PROMPT.pdf` (K-Signal Engine V1 Operational Spec)
> **Prior audit incorporated:** `docs/audits/gemini_audit.md`
> **Scope:** Architecture and maintainability only. No code was patched, rewritten, or added as part of this audit.
> **Method:** Every claim below was checked directly against the current working tree (`git ls-files`, `pytest`/`pytest --cov`, module imports run in `.venv`) rather than taken on faith from the prior audit. Where this audit disagrees with the Gemini audit, the disagreement is called out explicitly with evidence.

---

## Executive Architecture Diagnosis

K-Signal is currently **two products sharing one repository**, and the repository does not admit that to a reader.

**Product A — the legacy newsletter clickflow** (`main.py`, `ksignal/pipeline.py`, `ksignal/issue_builder.py` + its dynamic-import chain, `ksignal/site_stabilization*.py` chain, `ksignal/relevance/`, `ksignal/discovery.py`, `ksignal/schema.py`, all of `core/`, `ksignal/renderers/`) is a Windows-first, click-to-run tool that scrapes a handful of Korean sources, runs them through a vision model, and publishes a branded static newsletter site (Netlify package, Instagram carousel/reels export, link-checking, Pagefind search). It is fully wired, has a README, a Makefile, and is the only thing `main.py` knows how to run. It is also **explicitly the thing the hardened spec says not to build** ("This is not a blog tool... not a WordPress-style content workflow").

**Product B — the hardened operational intelligence engine** (`ksignal/engine/`, `ksignal/render/`) implements the spec's `seed -> discover -> capture -> correlate -> score -> brief -> render` pipeline. Contrary to the Gemini audit's characterization of this as "an inert façade," direct inspection shows real, working logic: `CandidateScore.total_weighted`/`auto_queue_eligible` reproduce the spec's weighting formula exactly; `SourceOrchestrator` implements fail-fast-provider + orchestrator-owned-fallback correctly for the Instagram path; `TemporalStore`/`compare_captures` implement real append-only versioning and diffing over DuckDB; `CandidateBrief`/`render_brief` produce the spec's markdown sections including a real Claims Register. This is a genuine, if partial, implementation — not a stub farm.

What is real is narrower than what the CLI advertises:

- `ksignal_engine.py` exposes all 13 spec commands, but `ksignal/engine/cli.py` still lumps **7 of them** (`source-discover`, `source-capture`, `source-briefs`, `source-engine-run`, `instagram-capture`, `creative-engine-run`, `audit`) into one branch that regenerates the Issue 002 seed queue and prints `{"status": "pending"}`. **Verified current, not stale** — re-reading `ksignal/engine/cli.py` today shows this branch unchanged.
- The general-purpose orchestrator routing the spec describes (`capture_seed()` dispatching `instagram_hashtag` / `keyword_query` / `search_query` / `manual_url` seeds to Apify/Playwright/HTTP providers) does not exist. `SourceOrchestrator` only implements the Instagram-hashtag path (`discover_instagram`). `HttpProvider`, `BrowserHarnessProvider`, and `SearchProvider` all exist as classes but are **never imported or called by the orchestrator** — they are unwired leaf nodes.
- `main.py` (root) is 100% the legacy CLI. It has zero hardened commands. `ksignal_engine.py` is a second, separate `argparse` entry point. A developer has no way to discover the hardened engine exists without already knowing the filename.
- The EXTRACT stage named explicitly in the spec's architecture diagram (`CAPTURE -> EXTRACT -> CORRELATE`) has two orphaned pure functions in `ksignal/engine/extract.py` (`content_hash`, `extract_visible_metrics`) that **nothing calls**. `ApifyInstagramProvider.normalize_to_source` builds its own metrics dict inline instead of reusing `extract_visible_metrics`. EXTRACT is a pipeline stage that exists in documentation only.
- `ksignal/render/html_to_png.py` silently degrades to a PIL-drawn placeholder image on any Playwright failure (confirmed unchanged from the Gemini audit's finding), **and** `CreativeRenderer.render()` in `ksignal/render/export.py` sets `RenderAsset.status = "captured"` whenever the output file exists on disk — which is *always true*, because the PIL fallback always writes a file. **This means the asset manifest can never report a degraded or failed render.** This is a correctness bug beyond what the Gemini audit flagged (it noted the silent fallback; it did not note that the status field is provably always wrong for the fallback path).
- `ksignal/relevance.py` (149 lines, legacy scoring for "related articles") and the `ksignal/relevance/` package (`__init__.py`, 62 lines) both exist with the same import path. **Verified by import**: `import ksignal.relevance` resolves to `ksignal/relevance/__init__.py`. `ksignal/relevance.py` is not "competing" logic as the Gemini audit framed it — it is **unreachable dead code**. Coverage confirms this: the package shows 94% coverage under the existing test suite; the shadowed file shows 0%.
- The `.pre_*.py` files the Gemini audit recommended deleting in Phase 5 are **not stale backups**. `ksignal/site_stabilization.py`, `ksignal/issue_builder.py`, and `core/host_packager.py` each dynamically load their `.pre_*.py` counterpart at import time via `importlib.machinery.SourceFileLoader`, forming a five-file dependency chain (`site_stabilization.py -> pre_metadata_presence_fix -> pre_dom_click_fix -> pre_pagefind_fix`, with `pre_lane_pagefind_fix` and `pre_combined_fix -> pre_android_tap_fix` as parallel branches that also terminate at `pre_pagefind_fix.py`). **Deleting these files as the Gemini audit's Phase 5 recommends would break the legacy publish pipeline immediately.** This is the single most important correction this audit makes to the prior audit.
- Bare `pytest` still fails with `ModuleNotFoundError: No module named 'ksignal'` (`pyproject.toml` has no `[tool.pytest.ini_options] pythonpath`). `python -m pytest --cov=ksignal` passes 24/24 and reports **29%** coverage — both numbers reproduced exactly against the current tree, confirming the Gemini audit's figures are still accurate today, not stale.
- `outputs/` **is correctly gitignored and zero files under it are tracked** (`git ls-files outputs/` returns nothing). The Gemini audit's claim of a committed DuckDB file and committed stale screenshots does not hold against the current tree — either it was fixed since, or it described local untracked state. This audit corrects that finding downward.
- `apify-client`, `jinja2`, and `duckdb` are all missing from `requirements.txt` but are all importable in the current `.venv` (verified directly). The risk is real but is a **fresh-environment reproducibility gap**, not a currently-broken environment — worth stating precisely rather than implying the app is broken today.
- There is no CI (`.github/` does not exist). Nothing enforces coverage, the pytest pathing fix, or dependency completeness on any change.

Net assessment: the hardened engine is a real, partially-built system with good bones (Pydantic-first models, a genuinely weighted scorer, correct provider-fails-fast/orchestrator-routes separation) wearing an entry point and CLI that don't tell the truth about what's implemented, sitting next to a fragile-but-functional legacy publishing tool that the spec says shouldn't exist in this identity, connected by one piece of accidental dead code and one accidental live landmine (the `.pre_*` chain) that a future developer could trip on in opposite directions — deleting something load-bearing, or editing something inert and wondering why nothing changes.

---

## Proposed Canonical Architecture

Target end-state, not a description of today:

```
k_signal/
  main.py                      # SINGLE entry point. Hardened commands are top-level.
                                #   Legacy commands live under `main.py legacy <cmd>`.
  ksignal/
    engine/                    # HARDENED — the product. seed/discover/capture/correlate/score/brief
      models.py                # canonical schema for anything issue-scoped or signal-scoped
      scoring.py                # DO NOT TOUCH weights/threshold without a product decision
      orchestrator.py           # owns ALL provider routing + fallback, for every seed_type
      providers/                # one file per provider, all fail-fast, no fallback logic inside
      brief.py / claims.py / roles.py
      corpus.py / seed.py       # Issue 001 / Issue 002 fixtures
      velocity.py / temporal.py / differential.py / correlate.py
      cli.py                    # every command real; no {"status": "pending"} branches
    render/                     # HARDENED — creative render pipeline (template -> png -> manifest -> EDL)
    legacy/                     # RENAMED from core/ + assorted ksignal/*.py — frozen, isolated
      pipeline.py, issue_builder.py, site_stabilization/ (collapsed chain, see Refactor Phases),
      relevance/, discovery.py, schema.py, renderers/, instagram_pack.py, instagram_reels.py,
      link_checker.py, distribution_pack.py, host_packager.py, creative_scout.py, media_collector.py,
      web_searcher.py, collectors/, models/openai_client.py, exporters/webhook.py, social_exporter.py,
      article_expansion.py
    shared/                     # utils/files.py, utils/images.py — genuinely used by both products
  tests/
    engine/                     # mirrors ksignal/engine/
    render/
    legacy/                     # mirrors ksignal/legacy/
  docs/
```

The organizing principle: **a directory boundary should tell you whether code is under active spec development or frozen-but-load-bearing.** Right now that information exists only in a developer's head (or in this audit). `ksignal/legacy/` makes it explicit, and nothing about moving files there changes behavior — it's a namespace move, not a rewrite, and is safe to do mechanically with import-path updates plus a test run.

---

## Module Ownership Map

| Area | Owner / Domain | Status | Notes |
|---|---|---|---|
| `ksignal/engine/models.py`, `scoring.py`, `roles.py`, `claims.py` | Source Engine — schema & scoring | **Real, tested, spec-compliant** | Keep as the single schema for hardened work |
| `ksignal/engine/orchestrator.py`, `providers/` | Source Engine — capture routing | **Partially real** | Instagram path only; generic `capture_seed()` router from spec missing |
| `ksignal/engine/brief.py`, `corpus.py`, `seed.py`, `velocity.py`, `temporal.py`, `differential.py`, `correlate.py` | Source Engine — pipeline stages | **Real, narrow test coverage** | Each function works in isolation; none are wired end-to-end by `cli.py` |
| `ksignal/engine/extract.py`, `capture.py` | Source Engine — EXTRACT/CAPTURE stage | **Dead code** | Two free functions, zero callers |
| `ksignal/engine/audit.py` | Source Engine — status reporting | **Fabricated output, unwired** | `materialize()` writes hardcoded "OPERATIONAL" prose regardless of real state, and isn't even called by the `audit` CLI command (which hits the generic `pending` stub instead) |
| `ksignal/engine/cli.py`, `ksignal_engine.py` | Source Engine — CLI | **7/13 commands stubbed** | See Legacy/Hardened Boundary Table |
| `ksignal/render/` (all files) | Creative Render Pipeline | **Real, spec-compliant shape, one status bug** | `export.py` render-status logic is wrong (see Render Pipeline Strategy) |
| `main.py` (root) | Legacy CLI | **Fully wired, legacy-only** | 15 subcommands, all newsletter-clickflow, zero engine commands |
| `ksignal/pipeline.py`, `ksignal/discovery.py`, `ksignal/schema.py` | Legacy — collection & article discovery | **Fully wired** | `schema.py`'s `SignalCard`/`RawItem` are legacy-only; do not extend for engine work |
| `ksignal/issue_builder.py` + `.pre_watchlist.py` | Legacy — issue assembly | **Fully wired, dynamic-import chain** | See Legacy/Hardened Boundary Table |
| `ksignal/site_stabilization.py` + 6 `.pre_*.py` files | Legacy — HTML/search stabilization | **Fully wired, 5-deep dynamic-import chain** | Load-bearing; do not delete |
| `ksignal/relevance.py` | — | **Dead code (shadowed)** | Delete; `ksignal/relevance/__init__.py` is what actually runs |
| `ksignal/relevance/__init__.py` | Legacy — related-article scoring | **Fully wired** | Naming collision with `engine/scoring.py`'s `CandidateScore`; different purpose, same word "score" |
| `ksignal/renderers/`, `ksignal/social_exporter.py`, `ksignal/article_expansion.py` | Legacy — newsletter/social rendering | **Fully wired** | |
| `core/*.py` (8 files) + `host_packager.pre_watchlist.py` | Legacy — packaging, link-checking, Instagram export, media collection | **Fully wired** | `host_packager.py` has its own dynamic-import chain to `host_packager.pre_watchlist.py` |
| `ksignal/collectors/` | Legacy — HTML/Naver/browser collection | **Fully wired** | Reused indirectly by `PlaywrightProvider.capture()` in the engine — one genuine cross-boundary dependency, see below |
| `ksignal/models/openai_client.py` | Legacy — vision/LLM card creation | **Fully wired** | Legacy-only; engine doesn't use an LLM step anywhere yet |
| `ksignal/exporters/webhook.py`, `ksignal/utils/` | Shared / legacy | `utils/` is genuinely shared (used by both) | `exporters/webhook.py` is legacy-only |
| `tests/` (12 files) | Both | **29% line coverage** | See Testing Strategy |

**One real cross-boundary coupling worth flagging on its own:** `ksignal/engine/providers/playwright_provider.py` imports `ksignal.collectors.browser.render_page` — i.e., the hardened engine's browser-fallback provider is implemented on top of a legacy collector module. This is not necessarily wrong (no need to duplicate a working Playwright wrapper), but it means `ksignal/collectors/` cannot be moved into `legacy/` without updating the engine, so it should be classified as **shared infrastructure**, not legacy, despite being written for and mostly used by the legacy pipeline.

---

## Legacy/Hardened Boundary Table

| Item | Classification | Action |
|---|---|---|
| `ksignal/engine/**` | Hardened | Active development target |
| `ksignal/render/**` | Hardened | Active development target |
| `main.py` (root) | Legacy | Repurpose as unified entry point (see below); keep legacy commands as a subgroup |
| `ksignal_engine.py` | Hardened-adjacent, redundant | Fold into `main.py`; do not maintain two argparse trees |
| `ksignal/pipeline.py`, `issue_builder.py`, `discovery.py`, `schema.py`, `social_exporter.py`, `article_expansion.py`, `renderers/**` | Legacy | Freeze feature growth; move under `ksignal/legacy/` |
| `ksignal/site_stabilization.py` + 6 `.pre_*.py` files | Legacy, **load-bearing dynamic-import chain** | Do not delete. Collapse into one file only via the phased plan below, with tests green before and after each step |
| `ksignal/issue_builder.pre_watchlist.py` | Legacy, **load-bearing** | Same — loaded at import time by `issue_builder.py`, not dead |
| `core/host_packager.pre_watchlist.py` | Legacy, **load-bearing** | Same — loaded at import time by `core/host_packager.py` |
| `ksignal/relevance.py` | Dead code | Delete outright — shadowed, unreachable, zero risk |
| `ksignal/relevance/` | Legacy | Keep; this is the module that actually runs |
| `core/**` (all other files) | Legacy | Move under `ksignal/legacy/` |
| `ksignal/collectors/**` | Shared infrastructure | Keep at current path or move to `ksignal/shared/`; both legacy pipeline and engine's `PlaywrightProvider` depend on it |
| `ksignal/utils/**` | Shared infrastructure | Same treatment |
| `ksignal/models/openai_client.py` | Legacy | Move under `ksignal/legacy/`; engine has no LLM dependency today |
| `ksignal/exporters/webhook.py` | Legacy | Move under `ksignal/legacy/` |

---

## Entry Point Recommendation

Collapse to **one** `main.py`. Concretely:

1. Add an `argparse` subparser group for the 13 hardened commands, delegating to `ksignal/engine/cli.py::run_command` exactly as `ksignal_engine.py` does today — copy that dispatch table into `main.py`, don't invent a new one.
2. Keep the 15 existing legacy subcommands in `main.py`, but nest them under a `legacy` subcommand (`python main.py legacy build-from-inspect ...`) so `python main.py --help` makes the product split visible instead of hiding it.
3. Turn `ksignal_engine.py` into a 4-line deprecated shim that prints a warning and calls `main.py`'s engine dispatch, or delete it once nothing references it (check `Makefile`, `README*.md`, `scripts/`, CI if added). Do not maintain two independent `argparse` trees pointed at the same underlying commands — that's exactly how `main.py` and `ksignal_engine.py` diverged in the first place.
4. Do not merge the *implementations* — only the entry point. The legacy pipeline and the hardened engine should remain separate code paths under one CLI, not one merged pipeline.

This directly reverses the current failure mode the Gemini audit named "Entry Point Confusion" without requiring the CLI-command implementation work (Phase 3 in the plan below) to happen first — the namespacing is safe to do immediately.

---

## Schema/Model Strategy

- `ksignal/engine/models.py` is the **only** schema for anything issue-scoped, candidate-scoped, or signal-scoped. It already matches the spec closely: correct six-value `AccessStatus`, correct 16-value `SourceRole`, correct A–D `ConfidenceGrade`, `SourceNode`/`CaptureVersion`/`Claim` all present with sensible field-level deviations from the spec (e.g., `Claim` carries both a `float confidence` *and* a `ConfidenceGrade confidence_grade` — a reasonable hardening beyond the spec, not a bug, since it lets scoring stay continuous while framing stays categorical; document this choice rather than "fixing" it to match the PDF literally).
- `ksignal/schema.py` (`SignalCard`, `RawItem`, `VisionLayout`, `TranslationAudit`) is legacy-only. It is not a competitor to `engine/models.py` in practice — nothing in the engine imports it, and nothing in the legacy pipeline imports `engine/models.py`. The two schemas don't actually collide at runtime today; they collide conceptually because a reader doesn't know that. Fix by moving `schema.py` under `ksignal/legacy/` and adding a one-line module docstring: `"Legacy SignalCard schema for the newsletter clickflow. Do not use for engine/render work; see ksignal.engine.models."`
- Delete `ksignal/relevance.py`. It is dead. Verify with `git grep "from ksignal.relevance import\|from ksignal import relevance"` before deleting to confirm nothing imports the top-level module path expecting the file rather than the package (expected: nothing does, since Python already resolves to the package).
- Do not add a `COMMERCE` removal or any other spec-literalism pass to `SourceType`/enums. The current enums are supersets of the spec, not violations of it; removing values is churn with no behavioral benefit and risks breaking anything that already produced `COMMERCE`-typed data.

---

## Scoring Strategy

- `ksignal/engine/scoring.py` reproduces the spec's weight table and `auto_queue_eligible` gate exactly (verified line-by-line against Module 3, and by the passing `test_scoring.py` assertions: an all-8s candidate scores `8.0` and is eligible; a candidate with only `cultural_signal_strength=10` and everything else 0 is correctly *not* eligible). **This is the single most spec-faithful module in the repo. Do not touch the weights or the `7.5 / 6.0 / 6.0 / 7.0` threshold without a deliberate product decision** — this is the mechanism the spec calls out as most sacred ("A single strong Korean source with official context beats ten weak reposts").
- `ksignal/relevance/__init__.py::score_candidate()` is a completely different function solving a completely different problem (which *other published articles* to link as "related signals" on a rendered page) that happens to share the word "score" with the engine's `CandidateScore`. This is not duplicate logic to consolidate — consolidating it would be wrong, since one is signal-intelligence weighting and the other is content-recommendation similarity. The fix is naming and documentation, not code merging: rename the legacy function's concept in developer-facing docs to "relevance ranking" and never call it "scoring" in prose to avoid the false-duplicate read the Gemini audit gave it.
- The orchestrator's inline `score_candidate` sketch shown in the spec PDF (Module 5, computing `korean_source_quality`, `official_context_quality`, etc. from a list of `SourceNode`s) has **no equivalent in the current codebase** — `SourceOrchestrator` has no `score_candidate` method at all. This is a real gap, not a duplicate: nothing currently turns a bundle of captured `SourceNode`s into a populated `CandidateScore`. `CandidateBrief.recommendation` assumes `self.scores` is already populated by something external, but that something doesn't exist yet.

---

## Render Pipeline Strategy

- `ksignal/render/` is the canonical creative pipeline (`CreativeRenderer.render()` → `templates.render_template` → `html_to_png` → `AssetManifest` → `edl.json` + `remotion_scene_plan.json`), matching spec Module 7's shape well, including the "ffmpeg/Remotion is encoder only, never the creative brain" principle (Jinja2 templates own all content decisions).
- **Fix the status bug before building anything more on top of this module.** In `ksignal/render/export.py`:
  ```python
  status="captured" if png.exists() else "error"
  ```
  `html_to_png()` in `ksignal/render/html_to_png.py` *always* writes a PNG — either a real Playwright screenshot or a PIL "K-SIGNAL RENDER DEGRADED" placeholder — so `png.exists()` is unconditionally `True` and this line can never produce `"error"`. Combined with the silent PIL fallback itself, this means **the asset manifest has no way to ever report a degraded creative render**, even though the spec's `AccessStatus`/render-status philosophy depends on failures being visible, not swallowed. The correct fix (for a future patch pass, not this audit) is for `html_to_png()` to return a success/failure signal alongside the path, and for `export.py` to set `status="degraded"` on the PIL-fallback path rather than inferring status from file existence.
- Legacy render surfaces (`core/instagram_pack.py`, `core/instagram_reels.py`, `ksignal/issue_builder.py`'s `export_social`, `ksignal/social_exporter.py`) are a **separate, legitimate pipeline** for the newsletter clickflow's social exports (1080×1350 carousel cards, Instagram reels via ffmpeg). Do not attempt to unify these with `CreativeRenderer` — they serve different products with different asset shapes (carousel/story/reel vs. article/quote/receipt/velocity cards) and different rights-handling logic (`allow_unknown_rights`, `safe_public` vs `creator_mode`) that has no equivalent concept in the hardened spec. Consolidation here would be scope creep, not cleanup.
- Template strategy is correctly staged per spec ("v1: static HTML + Jinja2, v2: Remotion") — `remotion_plan.py` already returns `{"status": "roadmap", ...}` rather than pretending to be implemented. Keep this pattern; it's an honest stub, unlike `cli.py`'s and `audit.py`'s stubs, which claim more than they deliver.

---

## Provider/Orchestrator Strategy

- The fail-fast-provider / orchestrator-owns-fallback separation from spec Module 4/5 is implemented correctly for the one path that's wired: `ApifyInstagramProvider` raises `ProviderFailure` and contains no fallback logic; `SourceOrchestrator.discover_instagram` catches it and routes to `InstagramBrowserProvider`. This is the right shape — extend it, don't redesign it.
- Gap 1 — **no generic seed router.** The spec's `SourceOrchestrator.capture_seed()` dispatches on `seed_type` (`instagram_hashtag`, `keyword_query`/`search_query`, `manual_url`) to different provider chains. The current orchestrator has only the Instagram-hashtag path. `HttpProvider` (real, robots.txt-aware, correctly maps 401/403→`LOGIN_REQUIRED`, 429→`RATE_LIMITED`/`DEGRADED`, 404→`LOST`-equivalent) and `SearchProvider` (a one-line stub that always returns `DEGRADED`/`PROVIDER_FAILED`) exist but have zero callers. This is exactly the gap that keeps `source-discover`/`source-capture`/`source-briefs` stubbed in `cli.py` — there's no orchestrator method for them to call yet.
- Gap 2 — **no 24h failure counters.** Spec Module 4 specifies `failure_count_24h`, `success_count_24h`, and a `_track_result()` method that flips `ProviderStatus` between `UP`/`DEGRADED` based on a rolling window. `ApifyInstagramProvider` in the current code has none of this — `self.status` is set once at `__init__` based on token presence and never updated after a call succeeds or fails. `ProviderHealthStore.update()` similarly hardcodes `failure_rate_24h` to `0` or `1` per call rather than computing an actual rolling rate. This means `provider-health` output is accurate for "is a token configured" but not for "is this provider currently degraded from repeated failures," which is the actual point of the spec's health dashboard.
- Gap 3 — the spec's orchestrator-level `score_candidate` and `correlate_sources` (Module 5) exist as standalone functions elsewhere (`ksignal/engine/correlate.py::correlate`, no scoring equivalent) but are not orchestrator methods and are not called from anywhere in the capture flow. `correlate()` itself is real and reasonable (entity/hashtag/mention overlap, cross-platform mirror detection) — it's simply disconnected from `SourceOrchestrator`.
- Recommendation: treat "wire the generic seed router + failure counters + candidate scoring into the orchestrator" as the single largest remaining chunk of real engineering work in this codebase — larger than the CLI stub-filling, because the CLI stubs are thin wrappers around orchestrator methods that don't exist yet. Filling in `cli.py`'s `source-discover`/`source-capture`/`source-briefs` branches without this orchestrator work first would just relocate the stubs, not remove them.

---

## Generated Output Policy

- `outputs/` is correctly gitignored and **zero files under it are currently tracked** — verified via `git ls-files outputs/`. This is a clean state; no action needed here, and this audit explicitly downgrades the Gemini audit's R-10 ("committed stale artifacts... DuckDB binaries committed") — that is not true of the tree as it exists now.
- The one real generated-output problem is **fabricated status reporting**, and it exists in two places with the same shape:
  1. `ksignal/engine/audit.py::materialize()` writes a hardcoded Markdown block asserting `Provider status: OPERATIONAL`, `Dependency status: UP; pip check clean`, `Test/coverage status: 24 passed; target modules 95% combined` — none of which is computed from anything; it's authored prose masquerading as a generated report. It is also currently **not even reachable from the `audit` CLI command** (`cli.py`'s `audit` branch hits the generic pending-stub, not `materialize()`), so today it's inert as well as fabricated.
  2. `scripts/write_predeploy_reports.py` (legacy side, flagged by the Gemini audit) does the same thing for predeploy reports.
- Policy going forward: **any file under `outputs/` that asserts a pass/fail or operational/degraded status must derive that status from a live check performed in the same run that writes the file.** No status string should ever be written by a function that didn't call the thing it's describing. This is a spec-alignment issue too — the spec's own philosophy ("Provider health is machine-readable... the log says DOWN: AUTH_MISSING. Fix the token. Rerun.") only works if the machine-readable output is actually machine-generated from real state, not templated.
- `data/editorial_overrides.json`, `configs/sources.yaml`, `examples/example_signal_card.json` are legitimate committed config/fixtures, not generated output — no action needed.

---

## Testing Strategy

Current state, reproduced directly against the tree today:

- `pytest` (bare): fails immediately, 11 collection errors, `ModuleNotFoundError: No module named 'ksignal'`.
- `python -m pytest --cov=ksignal`: 24 passed, **29% line coverage** (1014/1435 lines missing) — both numbers match the Gemini audit exactly, confirming this is a stable, current problem, not a stale one.
- Zero-coverage modules include the entire legacy collection/rendering stack (`collectors/`, `pipeline.py`, `discovery.py`, `models/openai_client.py`, `renderers/`, `exporters/webhook.py`, `issue_builder.py`, `site_stabilization.py`), and, more importantly, large parts of the **hardened** engine: `cli.py` (0%, meaning no test exercises a single CLI command end-to-end), `seed.py`, `corpus.py`, `correlate.py`, `audit.py`, `search_provider.py`, and most of `http_provider.py` and `playwright_provider.py`.
- Where tests exist for the engine, they are genuinely good unit tests — `test_scoring.py`, `test_source_models.py`, `test_claim_taxonomy.py`, `test_temporal_differential.py` all assert real behavior with `tmp_path` isolation, not smoke tests. The problem is breadth, not quality.
- **Two structural test-integrity issues beyond what the Gemini audit found:**
  1. `tests/test_input_safety.py` iterates `ROOT.rglob(...)` over `outputs/issues/001/host_package`, a directory that only exists after running the legacy publish pipeline locally and is gitignored. On a fresh clone, `rglob` over a nonexistent directory silently yields zero paths, every `assert` inside the loop never executes, and the test **passes vacuously**. It currently passes in this environment only because `outputs/issues/001/host_package` happens to already exist locally from prior work — a fresh CI runner would report a false pass, not a failure, for a completely different reason than "the safety check ran and found no problems."
  2. The same hardcoded developer path the Gemini audit flagged (`"C:\\", "Users\\jgwrg", "OneDrive"` in `test_input_safety.py`) is real and unchanged.
- Recommendation, in priority order:
  1. Fix `pyproject.toml` (`[tool.pytest.ini_options]` `pythonpath = ["."]`) — one line, unblocks bare `pytest` and any future CI immediately.
  2. Convert `test_input_safety.py` to fail loudly (`assert ROOT.exists(), "run the publish pipeline fixture first"`) or, better, generate its own minimal fixture in a `tmp_path` instead of depending on `outputs/`. A safety test that can pass without ever running is worse than no test.
  3. Add coverage for `ksignal/engine/cli.py` — even a smoke test per command (assert the real branches return real data and the stub branches are visibly labeled `pending`) would catch regressions in the CLI-to-orchestrator wiring described above.
  4. Do not chase 80% coverage by testing legacy modules — chase it by testing the *hardened* modules that currently sit at 0% (`seed.py`, `corpus.py`, `correlate.py`) first, since those are the active-development surface.
  5. Add CI (currently absent) running `python -m pytest --cov=ksignal --cov-fail-under=<agreed threshold>` on every PR, once the pathing fix lands — otherwise this audit's findings recur silently.

---

## Refactor Phases

Six phases, ordered by risk. Each phase should land as its own PR with tests green before moving to the next. This plan supersedes the Gemini audit's six-phase plan primarily on **Phase 5** (do not delete the `.pre_*.py` chain outright) and reorders provider/orchestrator work ahead of CLI-stub-filling, since the stubs can't be honestly filled until the orchestrator methods they'd call exist.

### Phase 1 — Make the build reproducible (LOW risk)
- Add `apify-client`, `jinja2`, `duckdb`, `lxml` to `requirements.txt`; add `pytest-cov` to `requirements-dev.txt`.
- Add `APIFY_TOKEN=` to `.env.example`.
- Add `[tool.pytest.ini_options] pythonpath = ["."]` to `pyproject.toml`.
- Delete `ksignal/relevance.py` (dead, shadowed).
- Acceptance: bare `pytest` runs without `ModuleNotFoundError`; `pip install -r requirements.txt` into a clean venv succeeds; `import ksignal.relevance` still resolves correctly (to the package).

### Phase 2 — Entry point consolidation (LOW-MEDIUM risk)
- Merge `ksignal_engine.py`'s 13-command dispatch into `main.py` under top-level names; nest the 15 legacy commands under `main.py legacy <cmd>`.
- Turn `ksignal_engine.py` into a deprecation shim or remove it once nothing references it.
- Acceptance: `python main.py source-seed --issue 002 --lane fandom` and `python main.py legacy build-from-inspect --issue 001` both work; `python main.py --help` shows both groups clearly.

### Phase 3 — Namespace the legacy/hardened split (LOW risk, mechanical)
- Move `core/**`, `ksignal/pipeline.py`, `issue_builder.py`(+chain), `site_stabilization*.py`(+chain), `discovery.py`, `schema.py`, `renderers/`, `social_exporter.py`, `article_expansion.py`, `models/openai_client.py`, `exporters/webhook.py` under `ksignal/legacy/`. Update imports.
- Do **not** touch the `.pre_*.py` dynamic-import chain's internal structure in this phase — move the files as a unit, keep their relative `Path(__file__).with_name(...)` relationships intact, and re-run the full legacy publish flow (`main.py legacy build-from-inspect` → `publish-audit`) once to confirm the chain still resolves after the move.
- Acceptance: full test suite green; a manual legacy publish run (`build-from-inspect` → `rebuild-issue` → `publish-audit`) completes without import errors.

### Phase 4 — Orchestrator hardening (MEDIUM risk — this is the real engineering)
- Add `SourceOrchestrator.capture_seed()` dispatching `instagram_hashtag` / `keyword_query` / `manual_url` to the appropriate provider (`ApifyInstagramProvider`, `HttpProvider`, wiring in `SearchProvider` or explicitly deferring it with a labeled `NotImplementedError`, not a silent `DEGRADED` return).
- Add `_track_result`/24h failure-window tracking to `ApifyInstagramProvider` (and ideally `HttpProvider`), and make `ProviderHealthStore.update()` compute a real rolling `failure_rate_24h` instead of hardcoding 0/1.
- Add an orchestrator-level `score_candidate(sources) -> CandidateScore` so `CandidateBrief.scores` can be populated from real captured sources instead of assumed pre-populated.
- Acceptance: `tests/test_orchestrator_fallback.py`-style tests extended to cover the new seed types; `provider-health` output changes visibly after a sequence of forced failures in a test.

### Phase 5 — Un-stub the CLI (MEDIUM risk, depends on Phase 4)
- Wire `source-discover`, `source-capture`, `source-briefs`, `source-engine-run`, `instagram-capture`, `creative-engine-run`, `audit` to the orchestrator methods added in Phase 4, `CreativeRenderer`, and a rewritten `audit.py::materialize()` that derives every status line from a live check (real provider health, real test run result, real file-existence checks against the current issue's output tree) instead of authored prose.
- Acceptance: each of the 13 commands in `python ksignal_engine.py --help` / `python main.py --help` returns real, issue-specific data — no command returns a literal `{"status": "pending"}`.

### Phase 6 — Collapse the legacy dynamic-import chains (LOW-MEDIUM risk, do last, do carefully)
- Only after Phases 1–5 are stable: collapse `site_stabilization.py` + its 6 `.pre_*.py` files into a single `ksignal/legacy/site_stabilization.py`, and similarly fold `issue_builder.pre_watchlist.py` into `issue_builder.py` and `host_packager.pre_watchlist.py` into `host_packager.py`. This is a real simplification (five files of layered monkey-patching become one readable file) but it is **not urgent** and carries real regression risk against a publish pipeline with weak test coverage — do it as its own isolated PR, with a full manual publish-and-visually-diff pass (the existing browser QA scripts in `tools/` and `scripts/` are the right harness for this), not bundled with unrelated changes.
- Acceptance: identical HTML/PNG output for a known Issue before and after the collapse (diff the rendered artifacts, not just "tests still pass," since coverage here is thin).

---

## Do-Not-Touch List

1. **`K_SIGNAL_HARDENED_PROMPT.pdf`** — immutable spec; source of truth for all engine work.
2. **`ksignal/engine/scoring.py`** — weight table and `auto_queue_eligible` thresholds (`7.5 / 6.0 / 6.0 / 7.0`). Changing these is a product decision, not a refactor.
3. **`ksignal/engine/corpus.py`** — Issue 001 corpus output contract (`CARDS` dict, output file names). This is a fixed regression benchmark; changing its output shape invalidates historical comparisons.
4. **The `.pre_*.py` dynamic-import chain** (`ksignal/site_stabilization*.py` ×6, `ksignal/issue_builder.pre_watchlist.py`, `core/host_packager.pre_watchlist.py`) — until Phase 6 is executed deliberately with visual-diff verification. Do not delete any of these files as a "cleanup" pass; they are runtime dependencies, confirmed by direct import trace.
5. **`ksignal/engine/models.py`'s enum value strings** (`AccessStatus`, `SourceRole`, `ConfidenceGrade` values) — these are serialized into JSON on disk (`outputs/issues/*/research/**`, `provider_health.json`). Renaming values breaks deserialization of anything already captured.
6. **`docs/`** (existing operational architecture docs) — preserve as historical record even where this audit disagrees with them; don't silently overwrite.

---

## Highest-Risk Decisions

These require a product/owner decision before more code gets written — none of them are "obviously correct" refactors:

1. **Does the legacy newsletter clickflow have a long-term future in this repository, or is it being sunset?** The hardened spec's IDENTITY section is explicit that K-Signal "is not" that product. If the legacy pipeline is staying (e.g., because it's the current revenue/publishing path while the engine matures), the namespacing in Phase 3 is the right call. If it's being sunset, a harder decision (deletion timeline, migration of any still-needed utilities like `collectors/`) should be made explicitly rather than left to accrete indefinitely under `legacy/`.
2. **Is `ksignal/collectors/` shared infrastructure or legacy-only?** Today the engine's `PlaywrightProvider` depends on it. If the legacy pipeline is sunset per decision #1, this dependency needs a home that isn't `legacy/`.
3. **Scope of the generic orchestrator (Phase 4).** The spec describes `keyword_query`/`search_query`/`manual_url` seed types beyond Instagram, but `SearchProvider` today is a one-line "always degraded" placeholder. Building this out is real, unscoped engineering work (what does "search" mean here — a search API, a scraper, both?) that should be sized and owned explicitly, not inferred from the stub's shape.
4. **Whether `Claim.confidence` should stay dual-typed** (`float` + `ConfidenceGrade`) or collapse to match the spec's `ConfidenceGrade`-only field. This audit recommends keeping the current dual-field design (documented, not silently deviating) because it's strictly more expressive, but it's a deviation from the literal PDF and should be a recorded decision, not an accident.
5. **Coverage target and CI gate.** The spec's acceptance criteria say ">= 80% on models, scoring, and provider normalization" — a narrower target than "80% of `ksignal` overall." Confirm which reading is intended before anyone burns effort writing tests against the wrong denominator.

---

## Exact Next Phase Prompt Recommendation

Give the next AI builder session **only Phase 1 + Phase 2** from the plan above, scoped tightly, with this framing:

```
Implement Phase 1 and Phase 2 of docs/audits/claude_architecture_audit.md only.
Do not touch ksignal/engine/orchestrator.py, ksignal/engine/cli.py's stub branches,
ksignal/render/export.py, or any .pre_*.py file. Do not attempt to un-stub any
CLI command. Do not move any files into a legacy/ namespace yet.

Scope:
1. Add apify-client, jinja2, duckdb, lxml to requirements.txt; pytest-cov to
   requirements-dev.txt; APIFY_TOKEN= to .env.example.
2. Add [tool.pytest.ini_options] pythonpath = ["."] to pyproject.toml.
3. Delete ksignal/relevance.py (confirm first with:
   git grep -n "relevance" -- '*.py' to verify nothing imports it by file path
   rather than package path; ksignal/relevance/__init__.py is the live module).
4. Merge ksignal_engine.py's 13-command argparse dispatch into main.py as
   top-level subcommands. Nest main.py's existing 15 legacy subcommands under
   a new `legacy` subcommand group (main.py legacy <existing-command-name>).
   Turn ksignal_engine.py into a 5-line deprecated shim that prints a warning
   and re-invokes main.py's engine dispatch — do not delete it outright in case
   scripts/tooling still shell out to it directly.

Acceptance criteria:
- Bare `pytest` (no `-m`) runs without ModuleNotFoundError.
- `python -m pytest --cov=ksignal` still passes 24/24 (coverage percentage may
  be unchanged — that's expected and fine for this phase).
- `pip install -r requirements.txt` succeeds into a fresh venv.
- `python main.py --help` shows both hardened top-level commands and a
  `legacy` subcommand group.
- `python main.py source-seed --issue 002 --lane fandom` produces the same
  output as `python ksignal_engine.py source-seed --issue 002 --lane fandom`
  did before this change.
- `python main.py legacy build-from-inspect --issue 001` runs identically to
  the old `python main.py build-from-inspect --issue 001`.
- No file under ksignal/engine/, ksignal/render/, or any .pre_*.py file is
  modified.

Report status using: OPERATIONAL / DEGRADED / NON-OPERATIONAL per area, and
list exact capability gaps remaining — do not write "PASS" for anything you
did not verify by running it.
```

This is deliberately the smallest possible next step: it fixes the two things blocking *every* future contributor (broken bare `pytest`, two competing entry points) without touching any of the higher-risk surfaces (orchestrator, CLI stubs, render status bug, the `.pre_*.py` chain) that need their own dedicated, carefully-scoped passes per the phases above.
