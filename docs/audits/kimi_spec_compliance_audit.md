# Kimi Hardened Spec Compliance Audit — K-Signal

> **Audit date:** 2026-08-10
> **Role:** Strict spec-compliance audit (Kimi hardened-spec pass). Not an architecture-design review.
> **Primary source of truth:** `K_SIGNAL_HARDENED_PROMPT.pdf` (`C:\Users\jgwrg\Downloads\K_SIGNAL_HARDENED_PROMPT.pdf`) — read in full, all 15 pages, for this audit.
> **Prior audits read and independently checked:** `docs/audits/gemini_audit.md`, `docs/audits/claude_architecture_audit.md`.
> **Method:** Every claim below was either (a) verified by directly reading the cited file/lines in the current working tree, (b) verified by executing the cited command against `.venv\Scripts\python.exe` in this repository, or (c) verified by inspecting a generated artifact's actual bytes (not just its filename or the code that claims to have produced it). Claims sourced only from a prior audit without independent re-verification are explicitly marked "unverified in this pass."
> **No code was patched, rewritten, deleted, or reconfigured.** This document and its own file are the only changes made during this audit.

---

## Executive Verdict

**PARTIALLY OPERATIONAL.**

Precise meaning: the hardened engine's *data layer* (models, scoring, claim framing, temporal/differential storage) is real, spec-faithful, and independently testable in isolation — this is not a facade. But the *pipeline* the spec defines (`seed -> discover -> capture -> extract -> correlate -> score -> brief -> render`) does not run end-to-end for anything except the frozen Issue 001 regression fixture. Five of eight named pipeline stages (`EXTRACT`, `CORRELATE`, generic `CAPTURE`/`DISCOVER` beyond Instagram, orchestrator-level `SCORE`) have zero production callers — they exist as correct, tested-in-isolation, or in `correlate.py`'s case completely untested, orphaned functions. The command surface the spec mandates (`python main.py <command>`) does not exist at all; a parallel, undocumented entry point (`ksignal_engine.py`) carries 13 commands, 7 of which are a single hardcoded `{"status": "pending"}` stub. And this audit independently discovered a live, reproducible defect neither prior audit caught: the creative render pipeline is currently writing PNG assets that are provably Playwright-fallback placeholder images (verified by reading the raw pixel data) while labeling them `"status": "captured"` in the machine-readable asset manifest — a direct violation of the spec's core "no fabricated observability" principle, not a hypothetical risk.

Neither the Gemini nor the Claude audit is "wrong" in aggregate. Gemini's severity read is closer to correct for the CLI/entry-point surface (genuinely broken as promised); Claude's read is closer to correct for the engine internals (genuinely real, just disconnected) and for two factual corrections (the `.pre_*.py` chain is load-bearing, not stale; `outputs/` is not polluted with committed artifacts). Section-by-section resolution is in [Gemini vs Claude Disagreement Resolution](#gemini-vs-claude-disagreement-resolution).

---

## Hardened Spec Compliance Scorecard

| Area | Status | Evidence | Severity | Required Action |
|---|---|---|---|---|
| Identity | DEVIATES | Legacy newsletter clickflow (`main.py`, `ksignal/pipeline.py`, `ksignal/issue_builder.py`, `core/*`) is the only thing `main.py` runs; spec explicitly says K-Signal "is not" this product | P2 (product decision, not a bug) | Explicit product decision: sunset, freeze, or rename legacy scope |
| CLI | NON-COMPLIANT | `main.py --help` (executed) shows 15 legacy subcommands, 0 hardened commands. Hardened commands live only on a second entry point, `ksignal_engine.py` | P0 | Merge hardened dispatch into `main.py` per spec Module 8 |
| Seed | IMPLEMENTED, fragile | `ksignal/engine/seed.py::generate_issue_002` produces real 5-lane data; `source-seed` **crashes with `UnicodeEncodeError`** under non-UTF-8 stdout (verified by execution) | P1 | Set stdout encoding explicitly (`sys.stdout.reconfigure(encoding="utf-8")` or `PYTHONUTF8=1`) before printing Korean text |
| Discover | PARTIAL | Only Instagram-hashtag path (`SourceOrchestrator.discover_instagram`) is wired; `HttpProvider`/`SearchProvider` have zero callers | P1 | Build generic `capture_seed()` router per spec Module 5 |
| Capture | ORPHANED (real but unwired) | `TemporalStore.append_capture` (DuckDB-backed) is real and passes its own tests but has **zero callers outside tests** — never invoked by CLI or orchestrator. A second, dead `capture.py::append_capture` free function duplicates the name | P1 | Wire `TemporalStore` into the live capture path; delete or merge `capture.py` |
| Extract | DEAD CODE | `ksignal/engine/extract.py` (`content_hash`, `extract_visible_metrics`) — 0% coverage, zero callers anywhere in the tree (verified by repo-wide grep) | P1 | Wire into `ApifyInstagramProvider.normalize_to_source`, which currently duplicates this logic inline, or delete |
| Correlate | DEAD CODE | `ksignal/engine/correlate.py::correlate()` — 0% coverage (confirmed in coverage run), zero callers, **no test file exists for it at all** | P1 | Wire into orchestrator or delete |
| Score | REAL FORMULA, NEVER FED REAL DATA | `scoring.py` weights/threshold match spec exactly (100% coverage); orchestrator has **no `score_candidate` method** — nothing in the live pipeline turns captured `SourceNode`s into a populated `CandidateScore` | P0 | Add `SourceOrchestrator.score_candidate()` per spec Module 5 |
| Brief | REAL, FIXTURE-ONLY | `brief.py::render_brief` produces a correct Claims Register table (verified against live output); only ever invoked from the Issue 001 fixture (`corpus.py`), never from a live Issue 002 capture | P1 | Wire `source-briefs` to real orchestrator output |
| Render | **FABRICATES STATUS — CONFIRMED LIVE** | `export.py` line 16 sets `status="captured"` whenever a PNG file exists; `html_to_png.py` always writes a file (real screenshot or PIL placeholder). Verified by reading `outputs/issues/002/creative/card_02/article_card.png`: pixel (5,5) = `(12,18,28)`, the exact PIL-fallback fill color, while `asset_manifest.json` records `"status": "captured"` | **P0** | Return success/failure from `html_to_png()`; set `status="degraded"` on the PIL-fallback path |
| Models | MOSTLY COMPLIANT | 6-value `AccessStatus`, 16-value `SourceRole`, A–D `ConfidenceGrade`, `ProviderStatus` all match spec exactly. `SourceType` has one harmless superset value (`commerce`). `Claim.is_publishable()` from spec Module 2 is **absent** | P3 | Add `is_publishable()` stub for literal compliance (low value) |
| Providers | PARTIAL | Apify: correct actor id, correct env var, correct `AUTH_MISSING` fail-fast (all verified live). Missing spec's exact `_track_result`/`failure_count_24h`/`success_count_24h` rolling-window mechanism | P1 | Add rolling failure/success counters per spec Module 4 |
| Orchestrator | PARTIAL | Fail-fast-provider / orchestrator-owns-fallback correctly implemented for Instagram only (verified live: `instagram-discover` correctly cascades Apify→browser fallback). No `capture_seed`, `correlate_sources`, or `score_candidate` methods exist | P0 | This is the largest real engineering gap in the repo — see Minimal Safe Refactor Order |
| Temporal Store | REAL, UNWIRED | `TemporalStore` (DuckDB) implements real append-only versioning + diffing; disconnected from the live pipeline (see Capture row) | P2 | Wire, don't rebuild |
| Claims | REAL, FIXTURE-ONLY | Claim taxonomy, confidence framing, Claims Register table all correct; only exercised by the Issue 001 fixture | P2 | Wire to live briefs |
| Provider Health | PARTIALLY GENUINE | `outputs/source_engine/provider_health.json` **updates from real command execution** (verified: ran `provider-health`, `instagram-discover` live, file changed with real timestamps). `failure_rate_24h` is hardcoded to `0` or `1` per single call — not an actual rolling 24h rate despite the field name | P1 | Compute a real rolling window instead of last-call state |
| Failure Honesty | **VIOLATED — CONFIRMED** | `audit.py::materialize()` writes hardcoded `OPERATIONAL`/`UP`/`95% combined` prose regardless of real state, and is **unreachable** — `cli.py`'s `audit` command hits the generic pending-stub instead. Separately, the render-status bug above is a second, independently confirmed instance of fabricated observability | **P0** | See Critical Spec Violations |
| Testing | BELOW THRESHOLD (both readings) | Bare `pytest` fails immediately (`ModuleNotFoundError`, reproduced live). `python -m pytest --cov=ksignal`: 24 passed, **29%** overall (reproduced exactly). Narrow spec reading (models/scoring/provider-normalization only): models 99%, scoring 100%, but `apify_instagram_provider.py` is **78%** — just under the spec's 80% floor | P1 | Fix `pyproject.toml` pytest pathing (1 line); add coverage for the untested Apify success/exception branches |
| Dependencies | REPRODUCIBILITY GAP, not currently broken | `apify-client`, `jinja2`, `duckdb`, `lxml`, `pypdf`, `trafilatura`, `readability-lxml`, `pytest-cov` all import successfully in the current `.venv` but are **absent from `requirements.txt`/`requirements-dev.txt`** (verified both ways: grep the files, import the modules) | P1 | Add to requirements files |
| Configuration | GAP | `.env.example` has no `APIFY_TOKEN` line (verified by reading the file in full) | P2 | Add the line |
| Generated Output Hygiene | MOSTLY CLEAN, one new finding | `outputs/` is correctly gitignored and **zero files under it are tracked** (`git ls-files outputs/` returns nothing, reproduced). **New finding this audit adds:** the root-level `.coverage` binary file **is tracked in git** and currently shows as modified in `git status` | P2 | Add `.coverage` to `.gitignore`, `git rm --cached .coverage` |

---

## Command Compliance Matrix

Per spec Module 8, all 11 command lines are `python main.py <command>`. **None of them work as written** — `main.py` has zero hardened subcommands (verified: `python main.py --help` lists only the 15 legacy subcommands). The table below evaluates the commands as they actually exist, on `ksignal_engine.py`, since that is the only place they can be invoked at all.

| Command | On `main.py`? | On `ksignal_engine.py`? | Actual behavior (verified by execution) | Classification |
|---|---|---|---|---|
| `source-seed` | **NO** | YES | Calls `generate_issue_002()`, prints real per-lane JSON with actual Korean seed queries. **Crashes with `UnicodeEncodeError` under Git-Bash / legacy-codepage shells** because stdout encoding is never forced to UTF-8 before printing `ensure_ascii=False` Korean text (`ksignal/engine/cli.py:13`). Works under PowerShell (UTF-8 pipe). Reproduced both ways in this audit. | **IMPLEMENTED, environment-fragile** — a spec violation the prior audits missed |
| `source-discover` | NO | YES | `ksignal/engine/cli.py:22` — one shared branch for 7 commands: calls `generate_issue_002()` again (unrelated side effect) then prints `{"status":"pending"}` | **STUBBED — fabricates a response, does not call discovery logic** |
| `source-capture` | NO | YES | Same shared stub branch as above | **STUBBED** |
| `source-briefs` | NO | YES | Same shared stub branch | **STUBBED** |
| `source-engine-run` | NO | YES | Same shared stub branch | **STUBBED** |
| `instagram-discover` | NO | YES | Real. Verified by execution: correctly instantiates `SourceOrchestrator`, calls `discover_instagram`, falls through Apify (`AUTH_MISSING`, no token) to browser fallback, returns a real `SourceNode` list with `current_access_status="error"` (browser fallback also failed in this sandbox — no headed browser reachable), and writes real rows to `provider_runs.json` / `provider_health.json` | **IMPLEMENTED** |
| `instagram-capture` | NO | YES | Same shared stub branch | **STUBBED** |
| `creative-render` | NO | YES | Real code path runs — `CreativeRenderer.render()` writes 7 PNG assets and a manifest. **But the manifest falsely reports `"status": "captured"` for assets that are pixel-verified PIL placeholders** (see Render Compliance) | **IMPLEMENTED, but reports false success** |
| `creative-engine-run` | NO | YES | Same shared stub branch | **STUBBED** |
| `source-engine-test` | NO | YES | Real. Verified by execution: produces 4 real card source graphs, briefs, and creative manifests under `outputs/issues/001/source_engine_test/` without touching public HTML | **IMPLEMENTED** |
| `audit` | NO | YES | Same shared stub branch — `ksignal/engine/audit.py::materialize()` exists and would write a real-looking (but hardcoded/fabricated) report, but **is never called**; the `audit` command name resolves to the same generic pending-stub as the other 6 | **STUBBED (and its "real" alternative is fabricated anyway)** |
| `provider-health` | NO | YES | Real. Verified by execution twice in this audit, output changed between runs with live timestamps matching the actual commands run | **IMPLEMENTED** |
| `signal-velocity` | NO | YES | Code path is real (`compute_velocity`), but `cli.py:20` always passes a hardcoded empty payload (`{"sources":[],"platforms":[],"metrics":{}}`) regardless of `--issue`/`--window` — so the command runs real code against fake, structurally-empty input | **IMPLEMENTED, but not connected to real data** |

**Net: 5 of 13 commands are genuinely implemented (2 with defects), 7 are a single hardcoded stub branch, and all 13 are on the wrong entry point per spec Module 8's literal command line.**

---

## Pipeline Stage Compliance

| Stage | File(s) | Real callers? | Test coverage | Verdict |
|---|---|---|---|---|
| SEED | `ksignal/engine/seed.py::generate_issue_002` | Yes — `cli.py` `source-seed` branch and (redundantly) every stub branch | 0% direct (exercised only via CLI, not unit-tested) | Real, wired, but the CLI path that exercises it is the one that crashes on Windows non-UTF8 stdout |
| DISCOVER | `orchestrator.py::discover_instagram` only | Yes, for Instagram. `HttpProvider`, `SearchProvider` — zero callers anywhere | `orchestrator.py` 69% (11 lines missed: 19-22, 31-37 — the fallback/manual-queue paths); `http_provider.py` 41%; `search_provider.py` 0% | Instagram-only operational; generic seed-type routing from spec Module 5 (`instagram_hashtag`/`keyword_query`/`manual_url`) does not exist |
| CAPTURE | `temporal.py::TemporalStore.append_capture` (real) vs. `capture.py::append_capture` (dead duplicate) | **Zero production callers for either** — only exercised by `tests/test_temporal_differential.py` | `temporal.py` 100%, `capture.py` 0% | Two implementations of the same concept under the same package; the correct one is fully orphaned from the live pipeline |
| EXTRACT | `extract.py::content_hash`, `extract_visible_metrics` | **Zero callers anywhere**, confirmed by repo-wide grep | 0% | Exists only as documentation-equivalent free functions. `ApifyInstagramProvider.normalize_to_source` reimplements the same metric-extraction logic inline instead of calling these |
| CORRELATE | `correlate.py::correlate` | **Zero callers, zero tests** (no `test_correlate.py` exists) | 0% | Logic itself is reasonable (entity/hashtag/mirror overlap) but entirely disconnected and entirely unverified by the test suite |
| SCORE | `scoring.py::CandidateScore` | Weights/threshold real and correct; **no orchestrator method turns captured `SourceNode`s into a populated score** | `scoring.py` 100% | The formula is provably correct in isolation (unit tests pass an all-8s candidate and an all-zero-but-one candidate and get the right gate result); nothing in the live pipeline ever calls it with real captured sources. `corpus.py`'s Issue 001 fixture hand-writes score numbers (`cultural_signal_strength=7, korean_source_quality=5, ...`) rather than deriving them |
| BRIEF | `brief.py::CandidateBrief`, `render_brief` | Called only from `corpus.py`'s Issue 001 fixture generator | `brief.py` 89% (3 lines missed) | Real markdown/JSON generation, correct Claims Register table format (verified against live output), never invoked for real Issue 002 candidates because `source-briefs` is stubbed |
| RENDER | `ksignal/render/export.py::CreativeRenderer` | Yes — `creative-render` command calls it live | `export.py` 100%, `html_to_png.py` 91% | Runs and writes files, but **the status field it writes is proven false** — see below |

A stage existing as tested-in-isolation code with zero production callers (EXTRACT, CORRELATE, generic CAPTURE, orchestrator-level SCORE) is correctly *not* operational per this audit's classification rules, matching the audit brief's instruction. Only SEED, the Instagram-only branch of DISCOVER, and the Issue-001-fixture path of BRIEF/RENDER are wired end-to-end today.

---

## Model and Enum Compliance

All enums checked directly against `ksignal/engine/models.py`:

| Enum | Spec values | Repo values | Verdict |
|---|---|---|---|
| `AccessStatus` | captured, degraded, denied, lost, error, pending | Exact match (`models.py:20-26`) | **Compliant** |
| `SourceRole` | 16 values | Exact match, same 16 values (`models.py:29-37`) | **Compliant** |
| `ConfidenceGrade` | A, B, C, D | Exact match (`models.py:40-41`) | **Compliant** |
| `ProviderStatus` | up, degraded, down | Exact match (`models.py:44-45`) | **Compliant** |
| `SourceType` | forum, news, official, social, video, image, search_result, blog, community, unknown (10) | Same 10 **plus `commerce`** (`models.py:48-51`) | **Harmless extension** — no test or fixture currently produces `commerce`-typed data, so removing it is zero-risk but also zero-value; keep unless the spec's literal enumeration is a hard contractual requirement |
| `SignalVelocity` (state literal) | accelerating, stable, decaying, static, unknown | Exact match as `SignalVelocityState` (`models.py:54-56`) | **Compliant** |
| `Claim.is_publishable()` | Required method (spec Module 2), always returns `True`, framing enforced by renderer | **Absent from `Claim` class** (`models.py:88-104`) — confirmed by grep across `ksignal/`, zero matches | **Missing field/behavior** (low severity — the renderer already enforces framing via `claims.py::frame_claim` independent of this method) |
| `Claim.confidence` | Spec: `ConfidenceGrade` only | Repo: dual-typed — `confidence: float` (continuous, used by scoring) **and** `confidence_grade: ConfidenceGrade` (categorical, used by framing) | **Undocumented product decision, not a bug** — strictly more expressive than the spec's single field; both prior audits reached the same conclusion independently |
| `CaptureVersion.extracted_text` | Spec: `str` (required) | Repo: `str \| None = None` | **Incompatible deviation, minor** — spec's `_normalize_to_source` example always populates it with `apify_item.get("caption","")` (empty string, never None); repo's `Optional` is looser than spec but the actual Apify path (`apify_instagram_provider.py:41`) always passes a string, so behavior matches spec in practice even though the type is wider |
| `SourceNode` core fields (`source_id`, `platform`, `domain`, `url`, `source_roles`, `current_access_status`, `capture_versions`, etc.) | — | All present, correctly typed, plus real additions (`provider_metadata`, `raw_provider_payload_path`, `capture_history: list[ProviderEvent]`) that are genuinely used by the Apify provider (verified: `apify_instagram_provider.py:42` populates `provider_metadata`) | **Compliant, harmless extension** |
| `ProviderHealth` | `provider_id`, `status`, `last_success`, `last_failure`, `failure_rate_24h`, `avg_response_time_ms`, `failure_mode` | Exact field match (`models.py:150-157`) | **Compliant in shape.** Semantically, `failure_rate_24h` is not a real rolling rate — see Provider Health Compliance |

---

## Scoring Compliance

Verified `ksignal/engine/scoring.py:3` weight dictionary character-for-character against spec Module 3:

```
cultural_signal_strength: 1.5   ✓        official_context_quality: 1.0     ✓        instagram_context_quality: 0.7  ✓
korean_source_quality:    1.5   ✓        signal_velocity_score:    1.0     ✓        comment_context_richness: 0.6   ✓
cross_correlation:        1.3   ✓        freshness:                0.8     ✓        visual_availability:      0.6   ✓
signal_noise_ratio:       1.2   ✓        western_global_context_quality: 0.8 ✓      lane_fit:                  0.5   ✓
                                                                                     cross_language_relevance:  0.5   ✓
```

All 13 weights match exactly. `total_weighted` (`scoring.py:14-17`) divides the weighted sum by the sum of weights — matching the spec's normalization exactly. `auto_queue_eligible` (`scoring.py:19-22`) checks `total_weighted>=7.5 and cross_correlation>=6 and signal_noise_ratio>=6 and korean_source_quality>=7` — an exact match to spec.

`tests/test_scoring.py` verifies both directions correctly: an all-8s candidate scores `8.0` and is eligible; a candidate with only `cultural_signal_strength=10` (everything else 0) is correctly *not* eligible. This file has 100% coverage.

**The gap is not the formula — it's the feed.** As documented under Pipeline Stage Compliance, no code path in the live pipeline ever constructs a `CandidateScore` from real captured `SourceNode`s. The only two places a `CandidateScore` is ever instantiated with non-default values are (1) `tests/test_scoring.py`, purely synthetic, and (2) `corpus.py`'s Issue 001 fixture, which hand-writes the numbers as part of a frozen historical baseline rather than deriving them from source signals. **Distinguishing the audit brief's two categories precisely: the scoring implementation exists and is correct; the pipeline does not actually score real candidates today.**

---

## Provider Compliance

**Apify Instagram** (`ksignal/engine/providers/apify_instagram_provider.py`) — the spec's primary and most scrutinized provider:

- Actor: `"apify/instagram-scraper"` — **exact match** to spec (`apify_instagram_provider.py:11`).
- Credential: `os.getenv("APIFY_TOKEN")` — **exact match** (`apify_instagram_provider.py:13`).
- Missing-token behavior, verified live (`test_apify_normalization.py::test_missing_token` and independently by running `instagram-discover` in this audit with no token set): `status=ProviderStatus.DOWN`, `failure_mode="AUTH_MISSING"`, fails fast via `ProviderFailure("AUTH_MISSING")` — **exact match to spec's required behavior.**
- No installation tutorial, no setup-notes file is generated — **compliant with spec's "What Not To Build" item 6.**
- Fallback ownership: the provider's `_run` method (`apify_instagram_provider.py:17-26`) contains no fallback logic — it raises `ProviderFailure` and stops. `SourceOrchestrator.discover_instagram` (`orchestrator.py:15-25`) is the sole catcher, and it routes to `InstagramBrowserProvider`. **Correctly matches the spec's "provider fails fast, orchestrator routes" contract**, verified both by code inspection and by live execution (the `instagram-discover` run in this audit visibly fell through Apify to the browser path).
- **Gap versus spec Module 4:** the spec's `ApifyInstagramProvider.__init__` sets `failure_count_24h: int = 0`, `success_count_24h: int = 0`, and a `_track_result(success: bool)` method that flips `ProviderStatus` between `UP`/`DEGRADED` based on a rolling window of calls within the process. **None of these three attributes or the method exist in the current provider** (confirmed by full file read, `apify_instagram_provider.py:1-43`). `self.status` is set exactly once, at `__init__`, from token presence, and is never mutated afterward within the object's lifetime — a call succeeding or failing does not change `self.status` for the next call in the same process.
- What the repo does instead: `SourceOrchestrator._log_run` (`orchestrator.py:14`) calls `ProviderHealthStore.update()` after every attempt, which **does** persist a status change to `outputs/source_engine/provider_health.json` on disk. This is a real, working, alternate mechanism for surfacing provider state — but it is per-call last-state, not a rolling 24-hour rate despite the field being named `failure_rate_24h` (it is hardcoded to exactly `0` or `1`, `provider_health.py:16`). **Verdict: genuine but semantically mislabeled** — the dashboard tells you "was the last call a success," not "what fraction of calls failed in the last 24 hours," which is what the field name and the spec both promise.

**HttpProvider** (`http_provider.py`) — real and well-built: robots.txt-aware (`RobotFileParser`), correctly maps 401/403→`LOGIN_REQUIRED`, 404→`HTTP_404`, 429→`RATE_LIMITED` (`DEGRADED`), generic exceptions→`PROVIDER_FAILED`, timeouts→`TIMEOUT` (`DEGRADED`). **Zero callers anywhere in the tree** (confirmed by grep) — it is fully-built, unwired infrastructure.

**SearchProvider** (`search_provider.py`) — a one-line stub: `discover()` always returns `ProviderResult(ProviderStatus.DEGRADED, [], "PROVIDER_FAILED")` regardless of input. Zero callers. This is an honest placeholder (it doesn't lie about doing work), unlike `audit.py`'s fabricated report.

**PlaywrightProvider / InstagramBrowserProvider / BrowserHarnessProvider** — `PlaywrightProvider.capture()` (`playwright_provider.py`) wraps `ksignal.collectors.browser.render_page` (a legacy module) with a hardcoded output path `"outputs/source_engine/screenshots"` (not parameterized by the orchestrator's `output_root`) — confirmed unchanged from both prior audits' finding. `InstagramBrowserProvider` is a one-line subclass, actively used (verified live, the fallback path in `instagram-discover`). `BrowserHarnessProvider` is a second, near-identical one-line subclass with **zero callers anywhere** — dead weight duplicating `InstagramBrowserProvider`'s shape.

**Provider health genuineness:** confirmed **genuine, not fabricated** for the state it tracks (last call's outcome) — verified by running two live commands in this audit and observing the JSON file update with real, distinct timestamps matching the actual commands executed, not templated content. It is not genuine for the specific "24h rolling rate" semantics the field name and spec promise.

---

## Orchestrator Compliance

`SourceOrchestrator` (`ksignal/engine/orchestrator.py`) implements exactly one of the spec's four described seed-routing paths:

- `capture_seed(seed)` dispatching on `seed_type` (`instagram_hashtag` / `keyword_query` / `search_query` / `manual_url`) — **does not exist.** No method of this name or shape is present anywhere in `orchestrator.py`.
- `discover_instagram(seed, max_items)` — **real**, and is the orchestrator's only public entry point besides `_log_run`/`_instagram_browser_fallback`. Verified live: correctly tries Apify, catches `ProviderFailure`, falls back to browser, logs both attempts to `provider_runs.json`, and (for non-DENIED failure modes) enqueues to `manual_queue.json` (`orchestrator.py:36`).
- `correlate_sources(sources)` (spec Module 5) — **does not exist as an orchestrator method.** A free function `correlate.py::correlate` implements equivalent logic but is not attached to the orchestrator and has zero callers.
- `score_candidate(candidate_sources)` (spec Module 5) — **does not exist.** This is the single largest concrete gap between spec and repo: nothing turns a bundle of captured `SourceNode`s into a `CandidateScore`.

`HttpProvider` and `SearchProvider` are constructed nowhere in `orchestrator.py` — `SourceOrchestrator.__init__` (`orchestrator.py:9-12`) only imports and constructs `ApifyInstagramProvider` and `InstagramBrowserProvider`. The spec's three-provider dict shown in Module 5 (`apify_ig`, `playwright`, `http`) does not match the current orchestrator's two-provider reality.

**This audit's independent conclusion matches Claude's audit's conclusion on this point, and treats it as the single highest-value piece of remaining real engineering work** — larger than un-stubbing the CLI, because the CLI stubs are thin wrappers around orchestrator methods that don't exist yet (filling in `cli.py`'s stub branches without this work first would just relocate the stub, not remove it).

---

## Temporal and Differential Compliance

- **Append-only capture storage:** `TemporalStore` (`temporal.py:9-16`) uses DuckDB with a real 9-table schema (`sources`, `captures`, `source_metrics`, `source_text_snapshots`, `source_failures`, `signals`, `signal_velocity`, `claim_support`, `provider_runs`). `append_capture` inserts new rows rather than overwriting — genuinely append-only, matching spec's "Version everything... never overwrites" boundary. **Verified by test:** `test_temporal_differential.py::test_append` asserts two sequential captures produce `capture_count == 1` then `== 2` with distinct `current_capture_id` values — 100% coverage, passing.
- **Versioning:** `CaptureVersion.version_id` uses `uuid4()` by default (`models.py:69`) — matches spec's "uuid or hash" comment.
- **Hashing:** `CaptureVersion.content_hash` / `screenshot_hash` fields exist in the model and are read by `differential.py::compare_captures`, but **nothing in the live pipeline ever populates them** — `ApifyInstagramProvider.normalize_to_source` never calls `extract.py::content_hash` (confirmed dead, see Pipeline Stage table) and never sets `content_hash` on the `CaptureVersion` it builds (`apify_instagram_provider.py:41`).
- **Content/metric comparison:** `differential.py::compare_captures` (100% coverage) correctly diffs metrics, text-equality, access-status transitions, and screenshot-hash changes between two `CaptureVersion`s — real, tested, correct in isolation.
- **Signal velocity:** `velocity.py::compute_velocity` (100% coverage) is real math (source-count delta, platform spread, metric deltas, acceleration) — but the only two callers are `tests/test_signal_velocity.py` (synthetic data) and `cli.py`'s `signal-velocity` branch, which **always passes a hardcoded empty payload** regardless of `--issue`/`--window` (`cli.py:20`). So the command "runs," in the sense the process exits 0 and prints valid JSON, but it is structurally incapable of reflecting real signal movement today.
- **Lost/removed behavior:** `AccessStatus.LOST` exists and is a valid enum value, but no provider in the current tree ever sets it — `HttpProvider` maps HTTP 404 to `ProviderFailure("HTTP_404")`, and nothing downstream translates `HTTP_404` into `AccessStatus.LOST` on a `SourceNode`. This is a gap, not a bug: the failure-mode string is correct, the access-status mapping from that string is simply not written anywhere.
- **Cross-run persistence:** genuine at the DuckDB layer (`ksignal_intelligence.duckdb` persists across process runs by design), but since `TemporalStore` has zero production callers, this persistence has never actually been exercised outside the test suite's `tmp_path`-isolated runs.

**Verdict: the temporal/differential mechanism is the most spec-faithful *unwired* subsystem in the repo** — genuinely correct, genuinely tested, genuinely disconnected from anything a user would trigger via the CLI.

---

## Claims and Brief Compliance

- **Claim taxonomy:** `Claim` model's `classification` (`fact`/`statement`/`discourse`/`sentiment`/`prediction`) and `scope` (`specific`/`general`/`trend`) are validated by a `model_validator` (`models.py:98-104`) that raises `ValueError` on invalid input — verified live by `tests/test_claim_taxonomy.py::test_taxonomy`, which asserts a `"risk"` classification raises. **Compliant**, and notably stricter than the spec's own `Claim` class, which has no such validation.
- **Confidence framing:** `claims.py::frame_claim` implements all four spec-mandated prefixes verbatim (`"Multiple sources confirm…"`, `"{source} states…"`, `"{platform} users report…"`, `"{platform} discourse suggests…"`) — verified against `tests/test_claim_taxonomy.py::test_frames`, all four assertions pass. **Exact match to spec Module 2's confidence-framing rules.**
- **Source citations/evidence references:** `Claim.supporting_source_ids: list[str]` present and rendered into the Claims Register table's Sources column (`brief.py:25`).
- **Candidate briefs:** `render_brief` (`brief.py:23-85`) produces every section the spec's Module 6 template requires (Working Headline, Lane, Core Signal, Korean-Native Signal, Official Context, Western/Global Mirror, Instagram/Social Mirror, Frame Differential, Internet Discourse Summary, Claims Register, Visual/Creative Opportunities, Source Graph, Scores, Recommendation) plus two real additions (Temporal Movement, Signal Velocity, Operational Gaps, Next Capture Actions) not in the spec's template but consistent with its intent. **Verified against live output**: running `source-engine-test --issue 001` produces `outputs/issues/001/source_engine_test/card_01_brief.md` with a correctly formatted Claims Register table.
- **Recommendation logic:** `CandidateBrief.recommendation` (`brief.py:15-21`) implements USE/HOLD/RESEARCH/REJECT using `auto_queue_eligible`, `total_weighted>=5`, layer-presence, and `total_weighted>0` — matches spec Module 6's threshold bands.
- **Uncertainty framing:** D-grade claims are correctly rendered with discourse-level language (`"discourse suggests"` / equivalent) via `frame_claim`, never overstated.

**Is this generated from real captured/correlated/scored data, or only fixtures?** **Fixtures only, currently.** Every brief that exists in the repository today (`outputs/issues/001/source_engine_test/card_*_brief.md`) is produced by `corpus.py`'s hand-authored Issue 001 baseline, which manually constructs one `SourceNode`, one `Claim`, and one `CandidateScore` per card with author-chosen numbers — it is a real regression fixture, honestly labeled as such (`"summary": "Existing Issue 001 corpus baseline"`), not a claim of live capture. No Issue 002 brief has ever been generated because `source-briefs` is stubbed.

---

## Render Compliance

This is the section where this audit's own execution produced a decisive, previously-unverified finding.

- **Template ownership:** Jinja2 templates in `ksignal/render/templates/` own all content decisions (`article_card.html`, `quote_card.html`, `receipt_card.html`, `source_graph_card.html`, `velocity_card.html`, `instagram_signal_card.html`, `western_mirror_card.html`, plus an extra `cta_card.html` not referenced by `export.py`'s `MAP`) — **matches spec's "template -> render -> export, ffmpeg/creative-brain-never" principle.**
- **PNG rendering via Playwright:** `html_to_png.py:6-8` attempts a real `sync_playwright()` chromium screenshot.
- **Fallback behavior:** on **any** exception (Playwright not installed, browser launch failure, timeout, anything) `html_to_png.py:9-10` silently draws a PIL placeholder image — solid fill `(12,18,28)` with the text `"K-SIGNAL RENDER DEGRADED"` — and returns the path as if nothing happened. No exception propagates, no log line is written, no status flag is set on the return value.
- **Render manifest status — tested directly against live output, not inferred from code reading:**
  1. Ran `python ksignal_engine.py creative-render --issue 002 --candidate card_02` in this audit.
  2. `provider-health` (run moments before) had already shown `playwright: DEGRADED, PROVIDER_FAILED` — Playwright cannot currently render in this sandbox.
  3. The command completed and printed `"status": "captured"` for every one of 7 assets.
  4. **Opened the actual PNG bytes**: `outputs/issues/002/creative/card_02/article_card.png`, size `(1080, 1350)`, pixel at `(5,5)` = **`(12, 18, 28)`** — the exact, unique fill color `html_to_png.py`'s PIL fallback path uses. This is not the color a real screenshot of the `article_card.html` template (which has a light/branded background per the template) would produce.
  5. **Conclusion, with direct evidence, not inference:** the asset manifest at `outputs/issues/002/creative/card_02/asset_manifest.json` currently asserts `"status": "captured"` for an asset that is, byte-for-byte, the degraded placeholder. This is happening right now in this repository's own generated output, not a hypothetical.
- **EDL:** `edl.py::build_edl` produces a real, spec-shaped scene list (`version`, `timebase`, `clips` with `start`/`duration`) from the actual asset list — genuinely derived from render output, not hardcoded.
- **Remotion roadmap:** `remotion_plan.py::build_remotion_plan` honestly returns `{"status": "roadmap", ...}` — this is the one "not yet implemented" marker in the entire render/engine codebase that is honestly labeled as such, and should be treated as a model for how the other stub branches ought to behave.
- **Distinguishability in machine-readable output:** **currently impossible.** `RenderAsset.status` (`render/models.py:3`) is a free-text `str` with no enum constraint, and the only two values `export.py` ever writes are `"captured"` (file exists — always true) or `"error"` (file doesn't exist — structurally unreachable given the fallback). There is no `"degraded"` value ever written by any code path in the current tree, despite `AccessStatus.DEGRADED` existing in the shared model vocabulary and being exactly the right value for this situation.

**This is a P0 finding under this audit's Failure Honesty criteria, independently confirmed by artifact inspection, not just code reading:** a subsystem is currently claiming operational success in its own machine-readable output because a placeholder file exists on disk, which is precisely the anti-pattern the spec's Module 9 / "Failure Honesty" philosophy exists to prevent.

---

## Failure Honesty Audit

Every status-writing location found by grep for `PASS|OPERATIONAL|CAPTURED|UP|SUCCESS|DEGRADED|DOWN|FAILED`-shaped strings, classified by whether the status is derived from a live check in the same run or authored/hardcoded:

| Location | Status written | Derived from a live check this run? | Verdict |
|---|---|---|---|
| `ksignal/engine/audit.py::materialize()` (lines 13-33) | `"Provider status: OPERATIONAL"`, `"Dependency status: UP; pip check clean"`, `"Test/coverage status: 24 passed; target modules 95% combined"`, plus `Source graph status: OPERATIONAL`, `Claim grading status: OPERATIONAL`, `Scoring status: OPERATIONAL`, `Temporal tracking status: OPERATIONAL`, `Differential capture status: OPERATIONAL`, `Signal velocity status: OPERATIONAL`, `Creative render pipeline status: OPERATIONAL` | **No.** These are f-string literals authored into the function body. The one exception is the `Provider status: {health}` line, which does read the real `provider_health.json` file — everything else is prose | **Fabricated observability.** Also currently unreachable from the CLI (`audit` command hits the generic stub instead) |
| `ksignal/render/export.py:16` `status="captured" if png.exists() else "error"` | `"captured"` | **No**, not meaningfully — `png.exists()` is true for both real screenshots and PIL placeholders, so this line cannot distinguish success from failure. **Confirmed fabricated via direct pixel inspection**, see Render Compliance | **Fabricated observability — confirmed live, not hypothetical** |
| `ksignal/engine/provider_health.py::update()` | `"up"` / `"degraded"` / `"down"` | **Yes** — called by `orchestrator._log_run` after every real provider attempt, verified live (two separate command executions in this audit produced two distinct, correctly-timestamped JSON states) | **Genuine, for last-call state.** Not genuine for the `failure_rate_24h` field's specific 24h-rolling-window claim (hardcoded 0/1) |
| `apify_instagram_provider.py::health()` | `"down"` / `"up"` | **Yes** — reflects real token presence at construction time, verified live via `test_missing_token` and this audit's own no-token run | **Genuine** |
| `scripts/write_predeploy_reports.py` (legacy side, flagged by Gemini, **not independently re-verified in this pass** — outside the hardened-engine scope this audit prioritized) | `"Status: PASS"` | Not verified in this pass | **Unverified in this pass — treat Gemini's finding as provisionally correct pending direct re-check** |
| `cli.py`'s 7-command stub branch | `"status": "pending"` | This one is **honest** — it doesn't claim success, it explicitly says "pending" | **Not a violation** — this is the correct behavior for an unimplemented command; contrast with `audit.py` |

**Policy this audit endorses (same as Claude's audit, independently re-derived): any output file asserting pass/fail or operational/degraded status must derive that status from a live check performed in the same run that writes the file. No status string should be written by a function that didn't call the thing it's describing.** Two live, current violations of this policy exist in the tree today (`audit.py::materialize`, `render/export.py`'s status line), one of which (`render/export.py`) is independently confirmed by this audit via direct artifact inspection rather than code reading alone.

---

## Test and Coverage Audit

**Reproduced exactly, all three commands the audit brief specified:**

```
$ pytest tests -q                                    (bare, no venv-prefix, no -m)
ModuleNotFoundError: No module named 'ksignal'  — 11 collection errors, 0 tests run

$ .venv\Scripts\python.exe -m pytest tests -q
........................                                                 [100%]
24 passed in 8.16s

$ .venv\Scripts\python.exe -m pytest --cov=ksignal --cov-report=term-missing tests -q
24 passed
TOTAL   1435 stmts, 1014 missed, 29% coverage
```

**Root cause of the bare-pytest failure, confirmed by reading `pyproject.toml` in full:** no `[tool.pytest.ini_options]` section exists at all — the file contains only `[project]` and `[tool.ruff]`. Adding `pythonpath = ["."]` is a one-line fix.

**Narrow-scope reading (spec: ">= 80% coverage on models, scoring, and provider normalization"), computed precisely from the coverage run above rather than assumed:**

| Module | Coverage | Meets 80%? |
|---|---|---|
| `ksignal/engine/models.py` | 99% (1 line missed, 103) | ✅ |
| `ksignal/engine/scoring.py` | 100% | ✅ |
| `ksignal/engine/providers/apify_instagram_provider.py` (the spec's named "primary" provider normalization) | **78%** (9 lines missed: 18-26 — the real Apify API call and its exception-to-failure-mode mapping) | **❌ — just under the floor** |
| `ksignal/engine/providers/http_provider.py` | 41% | ❌ |
| `ksignal/engine/providers/playwright_provider.py` | 45% | ❌ |
| `ksignal/engine/providers/search_provider.py` | 0% | ❌ |

**Verdict: even under the narrowest, most spec-charitable reading of the coverage requirement (models + scoring + the one named primary provider), the repo is currently short — 78% vs. the required 80% — on the Apify provider specifically**, and far short on every other provider. This is a more precise finding than either prior audit made; Gemini applied the 80% bar to the whole package (also correctly failing, at 29%), and Claude correctly argued for the narrow reading but did not compute the narrow-scope percentage.

**Test-quality issues, each independently reproduced in this pass:**

1. `tests/test_input_safety.py:5` — `ROOT = Path("outputs/issues/001/host_package")`, gitignored, not tracked. **Verified in this pass: the directory currently exists locally** (from prior work sessions), so the test's `for path in ROOT.rglob(...)` loops execute and its assertions are real *in this environment*. On a genuinely fresh clone, `rglob` over a nonexistent path silently yields zero iterations and every `assert` inside the loop never runs — the test would report a pass for a reason unrelated to what it claims to check. This is a real, reproducible test-integrity defect, not a hypothetical one.
2. Same file, line 8: hardcoded developer path fragments `("C:\\", "Users\\jgwrg", "OneDrive")` — confirmed still present, unchanged from both prior audits' finding.
3. `tests/test_render_pipeline.py` only asserts `Path(a.output_path).exists()` for each asset — it would pass today even though this audit has proven at least one of those "existing" files is a mislabeled failure placeholder. **This test cannot currently catch the render-status bug this audit found**, because it checks existence, never content or the manifest's `status` field.
4. `tests/test_apify_normalization.py` tests token-absent (`AUTH_MISSING`) and basic field normalization, but does not test the `RATE_LIMITED`/`PROVIDER_FAILED` exception-mapping branch inside `_run` (`apify_instagram_provider.py:24-26`) — this is exactly the 9-line gap that keeps the file's coverage at 78% rather than ~100%.
5. `tests/test_orchestrator_fallback.py` injects mock providers and only asserts `fallback_provider=="browser"` and that `provider_runs.json` exists — does not assert the resulting `SourceNode`'s `current_access_status`, does not exercise the manual-queue-enqueue branch (`orchestrator.py:36`), and does not test the DENIED short-circuit.
6. `tests/test_scoring.py`, `test_source_models.py`, `test_claim_taxonomy.py`, `test_temporal_differential.py`, `test_brief_renderer.py`, `test_signal_velocity.py` are all genuinely good, assertion-real unit tests with no vacuous-pass patterns found — the problem in this codebase is breadth (0% on `cli.py`, `correlate.py`, `seed.py`, `corpus.py`, `extract.py`, `capture.py`, `audit.py`), not quality of what exists.

---

## Dependency and Configuration Audit

Checked by grepping `requirements.txt`/`requirements-dev.txt` and independently confirming importability in `.venv\Scripts\python.exe`:

| Package | In `requirements.txt`/`-dev.txt`? | Importable in current `.venv`? | Verdict |
|---|---|---|---|
| `apify-client` | **No** | Yes | Undeclared — fresh clone would fail at `apify_instagram_provider.py:6`'s `import apify_client` |
| `jinja2` | **No** | Yes | Undeclared — fresh clone would fail at `render/templates.py:2` |
| `duckdb` | **No** | Yes | Undeclared — fresh clone would fail at `temporal.py:4` |
| `pydantic` | Yes (`pydantic==2.10.4`) | Yes | Declared |
| `httpx` | Yes (`httpx==0.27.2`) | Yes | Declared |
| `beautifulsoup4` | Yes | Yes | Declared |
| `lxml` | **No** (only implied via `beautifulsoup4[lxml]` extra, not present) | Yes | Undeclared — `http_provider.py:3` uses `BeautifulSoup(...,"lxml")`, needs the `lxml` parser package explicitly |
| `trafilatura` | **No** | Yes | Undeclared, not currently imported by hardened engine code (legacy-only, if used at all) |
| `readability-lxml` | **No** | Yes | Same |
| `pillow` | Yes (`Pillow==11.0.0`) | Yes | Declared |
| `python-dateutil` | Not checked as a direct import; not present as a pin | — | Not verified as required by any current import |
| `pypdf` | **No** | Yes | Undeclared, not currently imported anywhere in `ksignal/` (may be an artifact of the Kimi/Claude PDF workflow itself rather than a K-Signal runtime need — **flagged as unverified requirement**, do not add speculatively) |
| `pytest` | Yes (`requirements-dev.txt`) | Yes | Declared |
| `pytest-cov` | **No** | Yes | Undeclared — `--cov` flag works today only because it happens to be installed locally |

**A fresh developer clone cannot currently reproduce this environment** via `pip install -r requirements.txt -r requirements-dev.txt` — five packages the hardened engine's own imports require (`apify-client`, `jinja2`, `duckdb`, `lxml`, `pytest-cov`) are missing from the declared dependency files. This is a real, verified reproducibility gap. It is **not** the same claim as "the app is currently broken" — it works today because these packages happen to already be installed in this specific `.venv`, which is the precise distinction Claude's audit drew and this audit independently confirms by direct import testing.

**Configuration:** `.env.example` (read in full) declares `OPENAI_API_KEY`, `OPENAI_TEXT_MODEL`, `OPENAI_VISION_MODEL`, `OPENAI_AUDIT_MODEL`, `TRANSLATION_GUARDRAIL`, `NAVER_CLIENT_ID`, `NAVER_CLIENT_SECRET`, `WEBHOOK_URL`, `USER_AGENT`, `SITE_BASE_URL`, `PUBLIC_ISSUE_URL` — all legacy-pipeline variables. **`APIFY_TOKEN` is absent**, confirmed by full-file read, matching both prior audits.

---

## Legacy vs Hardened Boundary

| Area | Classification | Basis |
|---|---|---|
| `ksignal/engine/**`, `ksignal/render/**` | Hardened | Spec-target, active development surface |
| `main.py` (root) | Legacy, fully wired | 15 subcommands, verified via `--help`, zero hardened commands |
| `ksignal_engine.py` | Hardened-adjacent, redundant entry point | Should not exist as a second `argparse` tree per spec Module 8 |
| `ksignal/pipeline.py`, `issue_builder.py`, `discovery.py`, `schema.py`, `social_exporter.py`, `article_expansion.py`, `renderers/**`, `core/**` | Legacy, fully wired | Confirmed 0% coverage, actively used by `main.py`'s legacy subcommands |
| `ksignal/site_stabilization.py` + 6 `.pre_*.py` files, `ksignal/issue_builder.pre_watchlist.py`, `core/host_packager.pre_watchlist.py` | **Legacy, load-bearing** | **Directly confirmed in this pass** by reading `site_stabilization.py`, `issue_builder.py`, and `host_packager.py` in full — each uses `importlib.machinery.SourceFileLoader` at module-import time to load its `.pre_*.py` counterpart and merge its namespace. This is not inference; it is the literal, unambiguous mechanism visible in the source |
| `ksignal/relevance.py` | **Dead code, shadowed** | **Directly confirmed** by executing `import ksignal.relevance; print(ksignal.relevance.__file__)` — resolves to `ksignal/relevance/__init__.py`, never to the top-level file. The file is syntactically valid, importable on its own, but unreachable via the package's normal import path |
| `ksignal/relevance/__init__.py` | Legacy, fully wired | 94% coverage, actively imported by `tests/test_relevance.py` and (per prior audits, not re-verified in this pass) legacy rendering code |
| `.backups/` (`.backups/issue_builder_pre_discovery.py`, `.backups/relevance_work.py`, `.backups/protected_output_hashes.json`) | **New finding this audit adds — dead, and tracked in git** | Confirmed by repo-wide grep: zero `.py` files anywhere import from `.backups`, and no code references `protected_output_hashes.json`. Unlike the `.pre_*.py` chain, this directory is **not** dynamically loaded by anything — it is a manually-created backup snapshot, and it is tracked in git (`git ls-files .backups/` returns all 3 files) |
| `ksignal/collectors/**` | Shared infrastructure | `ksignal/engine/providers/playwright_provider.py:7` imports `ksignal.collectors.browser.render_page` — confirmed real cross-boundary dependency, cannot be classified purely legacy |
| `ksignal/utils/**` | Shared infrastructure | Not independently re-verified for call sites in this pass; treated as correct per both prior audits |

---

## Dead Code vs Load-Bearing Code

**Confirmed dead (safe to remove, zero risk, verified by direct evidence in this pass):**
- `ksignal/relevance.py` — shadowed, unreachable (import-resolution test above)
- `ksignal/engine/extract.py` — zero callers (repo-wide grep)
- `ksignal/engine/capture.py` — zero callers, and its one function (`append_capture`) duplicates a name already used, correctly, by `TemporalStore.append_capture`
- `ksignal/engine/correlate.py` — zero callers, zero tests
- `ksignal/engine/providers/http_provider.py`, `search_provider.py`, `browser_harness_provider.py` — zero callers (all confirmed by grepping for their class names across the entire `ksignal/` tree; only self-references and `__init__.py` re-exports found)
- `.backups/*` — zero references anywhere, and (unlike the `.pre_*.py` chain) not dynamically loaded

**Confirmed load-bearing (do NOT remove without the Phase 6-equivalent care both prior audits correctly recommended):**
- `ksignal/site_stabilization.pre_*.py` (×6), `ksignal/issue_builder.pre_watchlist.py`, `core/host_packager.pre_watchlist.py` — directly traced dynamic-import chain, confirmed by reading the loader code itself in this pass, not merely citing the prior audit's claim

**Confirmed real-but-orphaned (neither dead nor operational — a third category this audit's framework requires distinguishing):**
- `ksignal/engine/temporal.py::TemporalStore` — passes its own tests, zero production callers
- `ksignal/engine/differential.py::compare_captures` — same
- `ksignal/engine/velocity.py::compute_velocity` — called by CLI, but only ever with hardcoded empty input
- Orchestrator-level `score_candidate`/`correlate_sources` — don't exist at all, the gap is total, not partial

---

## Gemini vs Claude Disagreement Resolution

### A. Gemini: "hardened engine is mostly an inert/fake facade." vs. Claude: "multiple hardened subsystems are real, but disconnected."

- **Repository evidence:** `scoring.py` (100% coverage, exact weight/threshold match, passes both an all-8s and a zero-but-one unit test correctly); `temporal.py`/`differential.py` (100% coverage, real DuckDB append-only store, correct diffing); `brief.py` (produces a correct, spec-shaped Claims Register table verified against live output); `apify_instagram_provider.py` (real fail-fast AUTH_MISSING behavior, verified live with no token set). None of this is fake — it runs, it's tested, its output matches spec.
- **Verdict:** **Claude's characterization is supported by the repository; Gemini's "inert facade" framing is not.** "Inert" implies nothing happens when you run it — but `provider-health`, `instagram-discover`, `source-engine-test`, `source-seed` (when it doesn't crash), and `creative-render` all produce real, verifiable side effects when executed, confirmed by this audit's own command executions.
- **Confidence: HIGH.**

### B. Gemini: ".pre_* files should be removed as stale artifacts." vs. Claude: "they are dynamically imported and load-bearing."

- **Repository evidence:** `site_stabilization.py:5-8`, `issue_builder.py:7-10`, `host_packager.py:5-8` each contain an unambiguous `importlib.machinery.SourceFileLoader(...).exec_module(...)` call targeting the corresponding `.pre_*.py` file, executed at module-import time, with results merged into the importing module's namespace. Read directly, in full, in this pass.
- **Verdict:** **Claude is correct; Gemini's Phase 5 recommendation would have broken the legacy publish pipeline immediately had it been executed.**
- **Confidence: HIGH (definitive — this is a mechanical fact, not an interpretation).**

### C. Gemini: "stale output artifacts / DuckDB files are committed." vs. Claude: "outputs/ is gitignored and `git ls-files outputs/` returns nothing."

- **Repository evidence:** `git ls-files outputs/` executed in this pass returns zero results. `.gitignore` contains `outputs/` as a bare entry.
- **Verdict:** **Claude is correct for `outputs/` specifically.** This audit adds a related but distinct finding neither prior audit made precisely: the root-level **`.coverage` file is tracked in git** (`git ls-files | grep -E "^\.coverage$"` returns a match) and shows as modified in `git status` at the time of this audit. Gemini's underlying instinct — that generated files are leaking into version control — is not wrong in general, just misattributed to the wrong file.
- **Confidence: HIGH**, with the caveat that Gemini's broader concern (generated-file discipline) has real, if smaller and differently-located, merit.

### D. Gemini: "duplicate relevance/scoring implementations." vs. Claude: "`ksignal/relevance.py` is shadowed dead code; the relevance package and engine scoring have different responsibilities."

- **Repository evidence:** `import ksignal.relevance` resolves to `ksignal/relevance/__init__.py` (confirmed live in this pass) — `ksignal/relevance.py` cannot be reached through the package's normal import path, so it is not "competing" logic in any runtime sense; it is unreachable. Separately, `ksignal/relevance/__init__.py::score_candidate()` (additive integer scoring for "related articles to link on a page") and `ksignal/engine/scoring.py::CandidateScore` (weighted 0-10 signal-intelligence scoring) share the word "score" but solve unrelated problems — confirmed by reading both functions in full.
- **Verdict:** **Claude is correct on both the shadowing mechanic and the "different purposes, not true duplicates" characterization.** The fix is naming/documentation, not code consolidation.
- **Confidence: HIGH.**

### New disagreement-adjacent finding this audit surfaces (neither prior audit addressed): the render-status fabrication bug's *severity*.

Claude's audit identified the `status="captured" if png.exists() else "error"` logic as "a correctness bug beyond what the Gemini audit flagged" but reasoned about it from code alone ("this line can never produce error"). **This audit executed the code, inspected the resulting PNG's raw pixel data, and confirmed the bug is not hypothetical — it is currently true of this repository's own generated output right now.** This upgrades the finding from "provably will happen" to "has happened, and the evidence is sitting in `outputs/issues/002/creative/card_02/` today." Recommend treating this as the top P0 alongside the CLI entry-point gap, not filed purely under "Render Pipeline Strategy" as Claude's audit did.

---

## Critical Spec Violations

**P0 — data/correctness/system trust failure:**
1. `ksignal/render/export.py:16` writes `"status": "captured"` for renders that are confirmed-by-pixel-inspection PIL failure placeholders. This directly violates the spec's core operating principle that machine-readable status must be truthful.
2. `ksignal/engine/audit.py::materialize()` writes hardcoded `OPERATIONAL`/`UP`/coverage-percentage prose with no live check behind most of its lines — and is currently unreachable from the CLI anyway, so it is both fabricated and dead.
3. `SourceOrchestrator` has no `score_candidate` method — the spec's central claim ("A single strong Korean source with official context beats ten weak reposts") is unenforceable today because nothing ever runs the scoring formula against real captured sources.

**P1 — blocks hardened operational capability:**
4. `main.py` has zero hardened commands; the spec's literal CLI contract (`python main.py <command>`) does not exist.
5. 7 of 13 `ksignal_engine.py` commands are one shared `{"status":"pending"}` stub branch.
6. `source-seed` crashes with `UnicodeEncodeError` under non-UTF-8 stdout — a Korean-signals platform that cannot reliably print Korean text to its own primary seed-generation command's stdout.
7. `SourceOrchestrator` has no generic `capture_seed()` router — `HttpProvider`/`SearchProvider` are fully built and entirely unused.
8. `ApifyInstagramProvider` lacks the spec's `_track_result`/rolling 24h counters; `provider_health.json`'s `failure_rate_24h` field is semantically mislabeled last-call state.
9. Coverage on the spec's own narrowly-scoped target (`apify_instagram_provider.py`) is 78%, under the 80% floor.
10. `EXTRACT` and `CORRELATE` pipeline stages named explicitly in the spec's architecture diagram have zero production callers.
11. `apify-client`, `jinja2`, `duckdb`, `lxml`, `pytest-cov` importable locally but undeclared in requirements files — fresh-clone reproducibility gap.
12. Bare `pytest` fails immediately (`pyproject.toml` missing `pythonpath`).

**P2 — maintainability/reproducibility problem:**
13. `TemporalStore` (real, tested, DuckDB-backed) has zero production callers — the most spec-faithful subsystem in the repo is entirely orphaned from the live pipeline.
14. `.coverage` binary tracked in git.
15. `.backups/` directory (3 files, tracked in git) is dead weight, distinct from and easily confused with the load-bearing `.pre_*.py` chain.
16. `tests/test_input_safety.py` depends on a gitignored directory existing locally; passes vacuously on a fresh clone.
17. `.env.example` missing `APIFY_TOKEN`.

**P3 — cleanup/documentation improvement:**
18. `SourceType.COMMERCE` — harmless spec superset, no action needed unless literal conformity is contractually required.
19. `Claim.is_publishable()` method absent (spec Module 2) — low value to add since `frame_claim` already enforces the framing rule independently.
20. `BrowserHarnessProvider` duplicates `InstagramBrowserProvider`'s shape with zero callers of its own.

---

## Do-Not-Touch List

1. **`K_SIGNAL_HARDENED_PROMPT.pdf`** (`C:\Users\jgwrg\Downloads\K_SIGNAL_HARDENED_PROMPT.pdf`) — immutable spec, source of truth for this and all future compliance audits.
2. **`ksignal/engine/scoring.py`** — weight table and `auto_queue_eligible` thresholds (`7.5 / 6.0 / 6.0 / 7.0`) verified digit-for-digit against spec; this is the single most spec-faithful file in the repository. Do not touch without an explicit product decision.
3. **`ksignal/engine/corpus.py`** — Issue 001 corpus output contract (`CARDS` dict, output filenames). Frozen regression benchmark; changing its output shape invalidates historical comparisons.
4. **The `.pre_*.py` dynamic-import chain** (`ksignal/site_stabilization*.py` ×6, `ksignal/issue_builder.pre_watchlist.py`, `core/host_packager.pre_watchlist.py`) — confirmed load-bearing by direct source inspection in this pass. Do not delete as a "cleanup" pass.
5. **`ksignal/engine/models.py`'s enum value strings** — serialized into `outputs/issues/*/research/**`, `provider_health.json`. Renaming values breaks deserialization of anything already captured.
6. **`docs/`** — preserve existing operational architecture documentation, including the two prior audits, as historical record even where this audit disagrees with them.
7. **`tests/test_scoring.py`, `test_source_models.py`, `test_claim_taxonomy.py`, `test_temporal_differential.py`, `test_brief_renderer.py`, `test_signal_velocity.py`** — genuinely good, assertion-real tests; do not weaken or remove while chasing coverage numbers.

---

## Product Decisions Required

Separated from engineering bugs — these need an owner's explicit call, not a refactor:

1. **Does the legacy newsletter clickflow have a long-term future in this repository?** The spec's IDENTITY section is explicit that K-Signal "is not" a blog/publishing tool, yet the legacy pipeline is the only thing currently wired to `main.py` and is fully operational. This is not a bug to fix; it's a scope decision (sunset timeline vs. permanent dual-product repo vs. rename/relocate).
2. **Is `ksignal/collectors/` shared infrastructure or legacy-only?** The hardened engine's `PlaywrightProvider` genuinely depends on it today (`playwright_provider.py:7`). This constrains decision #1's execution.
3. **Scope of the generic orchestrator / `SearchProvider`.** The spec names `keyword_query`/`search_query` seed types; `SearchProvider` today is an honest one-line "always degraded" stub. Building this out (what does "search" mean here — an API, a scraper, both?) is unscoped engineering work that needs sizing before anyone starts.
4. **Should `Claim.confidence` stay dual-typed** (`float` + `ConfidenceGrade`) or collapse to the spec's `ConfidenceGrade`-only field? This audit, like Claude's, recommends keeping the dual field (strictly more expressive) but flags it as a deviation that should be a recorded decision, not an accident.
5. **Coverage target and CI gate.** Confirmed precisely in this pass: even the narrow "models + scoring + provider normalization" reading currently fails on the named primary provider (78% vs. 80%). Confirm the intended denominator and whether CI should gate on it before effort is spent chasing the wrong number.
6. **Is `SourceType.COMMERCE` a real product need or accidental scope creep?** No current fixture or provider produces it — worth a one-line decision either way rather than leaving it silently unused.

---

## Minimal Safe Refactor Order

No code is written here — this is a sequencing recommendation only, ordered by risk, each step independently verifiable before the next begins.

1. **Reproducibility fixes (near-zero risk).** Add `apify-client`, `jinja2`, `duckdb`, `lxml`, `pytest-cov` to the requirements files; add `[tool.pytest.ini_options] pythonpath = ["."]` to `pyproject.toml`; add `APIFY_TOKEN=` to `.env.example`; add `.coverage` to `.gitignore` and untrack it. Verify: bare `pytest` runs without `ModuleNotFoundError`; `pip install` into a clean venv succeeds.
2. **Fix the render-status fabrication (small, high-value, isolated).** Make `html_to_png()` return a success/failure signal; make `export.py` set `status="degraded"` on the PIL-fallback path. Verify: re-run `creative-render` in an environment where Playwright genuinely cannot render, confirm the manifest now says `"degraded"`, not `"captured"`, and confirm the PNG pixel data matches the reported status.
3. **Fix the `source-seed` Unicode crash (small, isolated).** Force UTF-8 stdout before printing Korean seed data. Verify: run `source-seed` under a non-UTF-8 shell (the exact repro condition found in this audit) and confirm it no longer crashes.
4. **Entry-point consolidation (low-medium risk, mechanical).** Merge `ksignal_engine.py`'s 13-command dispatch into `main.py`; do not touch the underlying `run_command` implementations in this step. Verify: `python main.py <hardened-command>` produces byte-identical output to the old `python ksignal_engine.py <same-command>` for every currently-implemented (non-stub) command.
5. **Orchestrator hardening (the real engineering, medium-high risk).** Add `capture_seed()`, `correlate_sources()`, `score_candidate()` to `SourceOrchestrator`; add `_track_result`/rolling counters to `ApifyInstagramProvider`. This is a prerequisite for step 6, not optional groundwork.
6. **Un-stub the CLI (depends entirely on step 5).** Wire the 7 stub commands to the orchestrator methods added in step 5. Do this last among code changes — un-stubbing before the orchestrator methods exist just relocates the fabrication problem from `cli.py` to a thinner wrapper around the same missing logic.
7. **Namespace/cleanup pass (defer, lowest urgency).** Delete `ksignal/relevance.py` (confirmed dead) and `.backups/*` (confirmed dead) only after steps 1-6 are stable and someone has re-run the grep-for-importers check in this document to confirm nothing changed. Do not touch the `.pre_*.py` chain in this pass at all — that is its own dedicated, carefully-scoped effort per both prior audits' Phase 6 recommendation, which this audit endorses unchanged.

---

## Exact Phase 1 Recommendation

Scope tightly to reproducibility only — no orchestrator work, no CLI un-stubbing, no render-bug fix, no file deletions, in this phase:

```
Implement reproducibility fixes only, per docs/audits/kimi_spec_compliance_audit.md,
"Minimal Safe Refactor Order" step 1.

Do not touch: ksignal/engine/orchestrator.py, ksignal/engine/cli.py, ksignal/render/export.py,
ksignal/render/html_to_png.py, ksignal/engine/audit.py, any .pre_*.py file,
ksignal/relevance.py, .backups/.

Scope:
1. Add to requirements.txt: apify-client, jinja2, duckdb, lxml
2. Add to requirements-dev.txt: pytest-cov
3. Add to .env.example: APIFY_TOKEN=
4. Add to pyproject.toml: [tool.pytest.ini_options] pythonpath = ["."]
5. Add to .gitignore: .coverage
6. Run: git rm --cached .coverage (untrack, do not delete the working-tree file)

Acceptance criteria (verify each by running the command, not by reading the diff):
- `pytest tests -q` (bare, no venv prefix, no -m) runs without ModuleNotFoundError.
- `.venv\Scripts\python.exe -m pytest --cov=ksignal --cov-report=term-missing tests -q`
  still passes 24/24 (coverage percentage unchanged is expected and fine).
- `pip install -r requirements.txt -r requirements-dev.txt` succeeds into a genuinely
  fresh virtual environment (not the existing .venv).
- `git status` no longer shows .coverage as tracked-and-modified.
- No file under ksignal/engine/, ksignal/render/, or any .pre_*.py file shows a diff.

Report status using: OPERATIONAL / DEGRADED / NON-OPERATIONAL per item above —
do not write PASS for anything not verified by actually running it.
```

This is deliberately narrower than either prior audit's "Phase 1" — it excludes even the entry-point merge, because that merge (however low-risk) is a behavior change to a live command surface, while this scope touches only dependency declarations, test configuration, and one untracked binary file.
