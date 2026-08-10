# K-Signal Design Recommendations V2

## Executive Recommendation

Approve an article-discovery and data-architecture pass next, not a homepage redesign. Preserve the existing compact logo header, bilingual lane navigation, four-story editorial hierarchy, Pagefind, receipts, comment/correction toggle, footer, public headlines, and CJK hardening. Replace the single conceptual “related” bucket later with two separate systems: exactly two archive-wide **Related signals**, followed by editorial-order **More from Issue 001** navigation.

## What K-Signal Should Borrow

### From NYT

Editorial priority that survives mobile, stable typographic roles, read-time/byline/date conventions, structured search filters, corrections visibility, and a mature but proportionate site index.

### From BuzzFeed

Immediate format/category recognition, one clear payoff per card, explicit trending rank, and legible reaction/comment cues. Borrow the clarity, not the content-commerce volume.

### From Vice

Specific nouns, tension-led headlines, prominent author/date/tags, compact category navigation, and confident recirculation after an article.

### From FMKorea

Board ancestry, clear separation of popular and recent lists, dense but consistent time/recommendation/comment metadata, and quick movement from list to post to comments.

### From Naver

Search-first discovery, source/publisher identity, typed category destinations, mobile prioritization, and visible corrections/fact-check/algorithm accountability.

### From TheQoo

Stable `HOT`/`전체`/`스퀘어` paths, compact mobile lists, direct comment anchors, and source-board context around a post.

## What K-Signal Should Avoid

- NYT-scale density, copied newspaper ornament, or account/paywall infrastructure.
- BuzzFeed's equal-weight feed, commerce collisions, emoji decoration, and engagement bait.
- Vice's subscription interruption, sensational edge, and oversized recirculation wall.
- FMKorea's ad density, taxonomy sprawl, and recommendation count as credibility.
- Naver's portal clutter, personalization dependency, and opaque blended rankings.
- TheQoo's anonymous-volume-as-consensus, weak integrated search, and context-light post walls.
- Translated labels as selectors or canonical metadata.
- Any statement that one thread represents “what Koreans think.”

## Homepage Recommendations

Hold off on redesign. The current lead/secondary/supporting hierarchy is proportionate to four stories and works at desktop/mobile sizes. When issue volume grows, add named archive/lane packages and compact rows before adding more card walls. Ensure every lane label eventually routes to a useful archive; do not add inactive navigation promises.

## Article Page Recommendations

- Add **Related signals**: exactly two strongest published archive matches, with lane, issue, summary, optional thumbnail, and `Read the signal →`.
- Keep **More from Issue 001** separate and ordered by issue editorial order; use a compact desktop strip and accessible mobile swipe/stack pattern.
- Retain the correction/comment toggle; distinguish correction submissions from public discussion and never boost relevance from unverified volume.
- Keep original Korean, English interpretation, “What the Internet Is Really Saying,” source receipts, media credit, platform/board, and capture context visible.
- Turn lane/topic/entity/source labels into search/archive hooks as destinations become real.

## Search / Archive Recommendations

Keep Pagefind as public full-text search and structured JSON as the cultural data layer. Add normalized canonical IDs and aliases for topics, entities, lanes, platforms, and boards. Later build lane, topic, entity, platform, cluster, and issue pages with result-type/filter controls. Preserve CJK segmentation, IME handling, original text, and stable untranslated machine attributes.

## Korean-Native Platform Lessons

Korean community interfaces are fast because they expose where a post lives, how fresh it is, and how much visible activity it has. K-Signal should make those facts legible as provenance without importing chaotic UI or implying that views, recommendations, or anonymous replies establish truth. Source platform, board/category, timestamp, observed metrics, permalink, translation status, and capture time should be first-class metadata.

## Korean Source Navigation Memory

The click journal should become a versioned research artifact and backend navigation-memory layer. Each safe public path records canonical URL patterns, Korean labels, English interpretations, page type, rough selector/location, login/translation/access status, visible metadata, comment anchors, and cautions. Future agents should consult it before browsing, append only verified actions, and record breakage rather than guessing.

In a later backend, convert journal entries into platform adapters or navigation recipes separate from content ingestion. That memory can guide source discovery and RAG provenance while enforcing low-volume public access, no login bypass, no personal-data collection, canonical Korean preservation, and explicit confidence/access fields.

## Approval Checklist

1. Approve the separate **Related signals** section with exactly two archive-wide results.
2. Approve the separate **More from Issue 001** module in editorial order.
3. Approve deterministic relevance scoring v1 and explainable score output.
4. Approve topic/entity/platform/board normalization and editorial overrides.
5. Approve below-article placement; permit a non-sticky desktop rail experiment later.
6. Approve compact Korean-platform-informed lane/topic/entity archive pages later.
7. Approve click-journal navigation memory as a maintained research/backend artifact.
8. Approve provenance fields for original label, board, capture time, observed metrics, translation/access status.
9. Hold off on homepage redesign.
10. Hold public headlines and all UI implementation until a separate implementation approval.
