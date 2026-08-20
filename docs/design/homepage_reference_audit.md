# Homepage reference audit

Evidence journal for the homepage / article-view / navigation architecture pass. Everything below
was observed directly; nothing is carried over from memory or from the earlier notes. Prior
principles live in `../EDITORIAL_REFERENCES.md` and `../COMPETITIVE_DESIGN_NOTES.md`; where this
audit contradicts them, they have been corrected and point here.

## 1. Inspection date and method

**2026-08-19.** Google Chrome 151.0.7922.138 launched with `--remote-debugging-port=9222` and a
dedicated profile, driven over CDP through Playwright's `connect_over_cdp`. Both surfaces were
inspected in the same browser session: `https://www.nytimes.com/` and the local build served from
`outputs/site` at `http://localhost:8000/`. Measurements are computed styles and bounding boxes
from the live DOM, plus real clicks and real URL transitions. Screenshots were not used as
evidence.

One harness caveat worth recording: Python's `http.server` sends `Last-Modified`, and Chrome
served stale homepage HTML after a rebuild until `Network.setCacheDisabled` was set over CDP. An
early validation run reported the old page and had to be discarded.

## 2. NYT homepage tree (desktop 1440px, main content column 1200px)

```
div#app
├── div[data-testid=StandardAd]                     ad slot, above everything
├── div[data-testid=masthead-container]             masthead, 165px tall
│   └── header
│       ├── section  edition menu + account/utility links
│       ├── div[data-testid=masthead-desktop-logo]  wordmark, 64px band
│       ├── div .floatingMiniNavContainer           sticky condensed nav (offscreen at rest)
│       └── div[data-testid=masthead-nested-nav]    section nav, 284 links / 32 images
└── main#site-content
    └── div[data-testid=programming-node]
        ├── div .gridContainer     ← first editorial region, 6477px tall, 82 links, 27 images
        ├── div                    briefing / promo band
        ├── div[data-testid=programming-node]   section package
        └── div[data-testid=programming-node]   section package
```

Masthead, navigation and content are three separate regions; the section nav is a distinct
`data-testid=masthead-nested-nav` sibling of the logo, not part of it.

### Column model by viewport

| Viewport | main width | Dominant block geometry (left:width) |
|---|---:|---|
| 1440 | 1425 | `113:830` and `113:291` (main), `976:337` (right rail), `421:522` (lead image) |
| 1024 | 1009 | `30:948`, `30:334`, `731:247` — still three columns |
| 760 | 745 | `22:700`, `22:245`, `546:177` — **still multi-column** |
| 390 | 375 | `20:335` for 24 of 26 blocks — single column |

The collapse to one column happens between 760px and 390px, not at 760.

### Hierarchy levels above and near the fold

Measured headline roles, in document order from the top of the grid:

| Role | Type | Block | Media |
|---|---|---|---|
| Lead | 22px/700 serif | left col, 291w | 522px image alongside, block spans 830 |
| Package-mate | 18px/700 serif | 291w or 399w | none |
| Full-width feature | 18px/700 serif | `section.story-wrapper`, 830w | 522px image |
| Rail feature | **24px/300** serif | 337w | — |
| Rail row | 16px/700 serif | 337w | 90px thumbnail |
| Rail grid cell | 16px/700 serif | 151w | 151px image |
| Opinion item | 11px/700 small-caps serif (author) + headline | 337w or 152w | occasional 152px |
| Package label | 14px/700 **sans** | e.g. `<h2>Opinion</h2>` → `/section/opinion` | — |
| Utility nav inside a package | 13px/500 sans | e.g. "Key Race Results" | — |

**The first editorial package is a themed cluster, not a lead plus a second story.** The lead
("U.S. Debt Hits $40 Trillion", 22px) is followed by "Markets Rally After U.S. Treasury Eases Bond
Investor Stress", "How the $32 Trillion Treasury Market Influences the Economy" and "More Fed
Officials Lose Patience About Elevated Inflation" — three stories at one shared 18px/700 weight,
all on the same subject, inside one block.

**Which stories get images:** image presence tracks block width, not rank. Every 830px-wide
`story-wrapper` carries a 522px image; every 291px-column story is headline-only regardless of
importance. Labels such as `Analysis` and `BREAKING` sit on structurally identical 830px blocks.

**Rules and dividers are sparse.** In the top 3600px of `main` there are exactly **7** bordered
elements, all `border-top: 1px rgb(223,223,223)` `<hr>`; five are inside the right rail
(left=976) and two span the 830px main column. No full-width rule, no vertical column dividers.
Separation in the main column is done with whitespace and column geometry.

### Mobile (390px) — the same page, re-projected

First 16 editorial items in document order at 390px versus 1440px:

- Levels collapse from ~7 to **3**: 30px/700 (one lead), 26px/700 (package leads), 20px/700
  (everything else), plus 16px/500 sans utility links.
- Type gets **larger**, not smaller (lead 22px → 30px).
- The entire right rail is gone from the top of the page: the 24px/300 travel feature, the
  four-cell lifestyle grid, and the whole Opinion package do not appear in the first 16 items.
- **Story order is not preserved.** Desktop items 4, 6, 7, 8, 10, 13 and 15 are absent from the
  mobile sequence; the main column is promoted into one ranked list.

## 3. NYT click map

Every interaction below was a real click in the debug browser. All navigations were same-tab.

| # | Element | From | To | Destination type |
|---|---|---|---|---|
| C1 | Lead headline | `/` | `/2026/08/19/business/economy/us-debt-40-trillion.html` | article |
| C2 | **Image** of the lead story | `/` | same URL as C1 | article |
| C3 | Supporting headline, no image | `/` | `/2026/08/19/business/iran-hormuz-oman-us-navy.html` | article |
| C4 | `<h2>Opinion</h2>` package label | `/` | `/section/opinion` | section (`PT=collection`) |
| C5 | Opinion item (columnist kicker) | `/` | `/2026/08/19/opinion/trumps-revenge.html` | article |
| C6 | Masthead logo | an article page | `/` | homepage (`PT=Homepage`, own canonical) |
| C7 | Section nav "World" | `/` | — | link present but only visible in a hover dropdown |
| C8 | Search control | `/` | `/` unchanged | in-page overlay, not a route |
| C9 | Byline on an article | article | `/by/jamelle-bouie` | author page, own canonical |
| C10 | Timestamp | article | — | `<time datetime=…>`, **not inside a link** |
| C11 | Live coverage | direct | `/live/2026/us/times-election-results-explained` | live page; posts addressable as `#slug` anchors within the one canonical URL |

Headline, image and dek of one story share one destination. Metadata does not: the byline has its
own surface, and the timestamp has no destination at all.

Section-page cross-check: from `/section/world`, the first story link resolved to
`/2026/08/19/world/europe/iran-trump-economic-sanctions-leverage.html` — **the destination URL
contains no `/section/` segment.**

## 4. NYT URL patterns

Every editorial href on the homepage, reduced to its pattern (142 links in `main`):

| Count | Pattern |
|---:|---|
| ~45 | `/{YYYY}/{MM}/{DD}/{section}/{slug}.html` |
| ~12 | `/{YYYY}/{MM}/{DD}/{section}/{subsection}/{slug}.html` |
| 11 | `/interactive/{YYYY}/{MM}/{DD}/{section}/{slug}.html` and `/interactive/polls/{slug}.html` |
| 11 | `/athletic/{numeric-id}/{YYYY}/{MM}/{DD}/{slug}/` |
| 8 | `/wirecutter/reviews/{slug}/` |
| 8 | `https://cooking.nytimes.com/recipes/{slug}` |
| 2 | `/live/{YYYY}/{section}/{slug}`, `/live/{YYYY}/{MM}/{DD}/{section}/{slug}` |
| 1 | `/section/opinion` |
| 1 | `/news-event/{slug}` |

Header nav: `/section/{name}`, `/section/{name}/{sub}`, `/spotlight/{slug}`,
`/topic/organization/{slug}`, `/news-event/{slug}`, `/newsletters/{slug}`, `/column/{slug}`.

**Query strings: 1 of 142 links carries one, and it is a games A/B flag.** Homepage placement,
module, rank and package are encoded nowhere in the link.

## 5. NYT canonical metadata

| Surface | canonical | og:url | internal id | page type |
|---|---|---|---|---|
| news article | = landed URL | = canonical | `nyt://article/ce1295c7-b8f2-5f58-891c-a1dd1d49cfc3` | `PT=article PST=News` |
| opinion | = landed URL | = canonical | `nyt://article/f908839b-…` | `PT=article PST=Op-Ed` |
| culture | = landed URL | = canonical | `nyt://article/b4fd4967-…` | `CG=arts SCG=music` |
| interactive | = landed URL | = canonical | `nyt://interactive/4cb983d1-…` | — |
| live | = landed URL | = canonical | `nyt://legacycollection/bba3aede-…` | — |
| sports (Athletic) | = landed URL | = canonical | the URL itself | — |
| section page | = landed URL | = canonical | `nyt://legacycollection/dadd4177-…` | `PT=collection` |
| author page | `/by/jamelle-bouie` | absent | absent | — |
| search | **absent** | absent | absent | — |
| homepage | `https://www.nytimes.com/` | — | — | `PT=Homepage` |

JSON-LD on articles carries `@type: NewsArticle` with `@id`, `url` and `mainEntityOfPage` all
equal to the canonical URL, plus `datePublished` / `dateModified`.

Two conclusions that matter for KSGNL:

1. **Identity is an opaque UUID; the readable path is a projection of it.** The URL can carry
   date and section for humans without those segments being the identity.
2. **Section membership appears in both the URL and the metadata, but section pages do not own
   the story.** `iran-hormuz-oman-us-navy` is filed `CG=business`, sits in a Middle-East-themed
   homepage cluster, and is reachable from `/section/world` — one canonical URL throughout.

## 6. KSGNL tree before this pass

```
main.home-shell
├── header.section-heading
│   ├── p       "From Issue 002"
│   ├── h1      "Four signals from this week."
│   └── p.issue-date  "Sunday, August 23, 2026"
├── section.front-page
│   ├── article.story-preview.lead        kicker "From Issue 002"
│   ├── article.story-preview.secondary   kicker "From Issue 002"
│   └── div.supporting-stack
│       ├── article.story-preview.supporting  kicker "From Issue 002"
│       └── article.story-preview.supporting  kicker "From Issue 002"
├── form (correction capture)
└── div.search-aliases[data-pagefind-body]
```

`/` and `/issues/002/` were the **same document**. A normalised diff of the two files produced 62
differing lines, every one of them a relative-path prefix (`./` vs `../../`). The homepage `<h1>`
was the edition's headline and all four cards were kickered with the edition.

## 7. KSGNL click map before this pass

| # | Element | Observed URL | Notes |
|---|---|---|---|
| K1 | lead headline | `/articles/im-ji-min-stadium-response/` | ok |
| K3 | secondary headline | `/articles/bigbang-20th-anniversary-trio/` | ok |
| K4 | supporting headline | `/articles/samjeon-nix-samsung-hynix/` | ok |
| K5 | "Read the signal →" | same as K1 | headline and CTA agree |
| K2 | hero media | — | hero is not a link (differs from NYT, where the image is) |
| K6 | lane label on a card | — | not a link |
| K7 | footer Archive | `/archive/` | ok |
| K8 | logo | `/` | ok, but `/` was the edition |
| K9 | lane dropdown | `/search/?lane=Beauty` | lanes are search queries, not lane pages |

`<link rel="canonical">` was **absent on every page of the site**.

## 8. KSGNL URL ownership before this pass

| Surface | Clicked element | Observed URL | Code that authored it | Canonical data source |
|---|---|---|---|---|
| homepage | headline | `articles/{slug}/` | `site_assembler._rewrite_issue_page(latest=True)` | `outputs/issues/002/newsletter.html` preview |
| homepage | — | `/` served the edition | `site_assembler.assemble_site` — `shutil.copy2(latest_dir/"newsletter.html", staged/"index.html")` | latest issue newsletter |
| issue page | headline | `../../articles/{slug}/` | `_rewrite_issue_page(latest=False)` with `elif issue != "001"` | same |
| article | — | `/articles/{slug}/index.html` | promotion loop over `latest_slugs` only | `outputs/issues/002/article_packages/card_NN.json` → `article_slug` |
| issue 001 article | — | `/issues/001/articles/card_NN.html` | `if issue == "001": copytree(...)` | no packages exist; slot names only |
| archive | list row | `../issues/{id}/` | `_archive_from_shell` | `ISSUE_METADATA` |
| lane nav | popover link | `/search/?lane={Lane}` | issue_builder markup | Pagefind `lane` filter |

**The defect, proven by re-running the builder rather than by reading it:**

```
assemble_site(("001",))        -> /articles/card_01/ … /articles/card_04/
assemble_site(("001","002"))   -> /articles/im-ji-min-stadium-response/ … (card_01..04 gone)
```

`/articles/<slug>/` was a lease held by whichever issue was newest. Every release deleted the
previous issue's article URLs. Cause: the promotion loop iterated `latest_slugs`, and
`_rewrite_issue_page` hardcoded `elif issue != "001"`.

Secondary finding: `main.article-shell[data-route]` claimed `articles/{slug}.html` while the
served route was `articles/{slug}/`.

## 9. Why `/` read as "the current issue" — cause, not theory

Ruled in: **literal route aliasing plus identical data projection, DOM template and hierarchy.**
`/` was produced by copying `outputs/issues/<latest>/newsletter.html` to `index.html` and
rewriting link depth. Ruled out: CSS was not making structurally different pages look alike, and
there was no separate homepage assembler reading only latest-issue data — there was no homepage
assembler at all.

## 10. Old assumptions, checked against the live site

| Assumption (source) | Verdict | Evidence |
|---|---|---|
| "One lead, a clearly subordinate second story, then compact supporting stories" (`COMPETITIVE_DESIGN_NOTES.md`, `EDITORIAL_REFERENCES.md` #1–2) | **Rejected as stated** | No distinct "secondary" role exists. The lead is followed by three package-mates at one shared 18px/700 weight. Our 4-rank ladder over 4 stories was finer than NYT uses over 100+. |
| "On mobile, preserve story order and hierarchy" (`EDITORIAL_REFERENCES.md` #5) | **Contradicted** | At 390px the right rail vanishes from the top and the main column is re-sequenced; 7 desktop items in the first 16 are absent. |
| "Use rules and whitespace to create cadence" (#3) | **Partially confirmed** | Whitespace does nearly all of it; only 7 hairline rules exist in the top 3600px, 5 of them rail-scoped. |
| "Keep navigation compact and utility-driven so the front page carries the voice" (#4) | **Confirmed** | Masthead is 165px against a 6477px first editorial region. |
| "Group stories by importance and relationship, not by making every card equal" (`COMPETITIVE_DESIGN_NOTES.md`) | **Confirmed, and stronger than journaled** | Relationship grouping is the primary structure, not a refinement of it. |
| "Keep date and issue context quiet but findable" | **Confirmed by analogy** | NYT shows no edition at all; dates appear on articles as non-interactive `<time>`. |
| "Do not copy the masthead, grids, typography or newspaper ornament" | **Unchanged** | Still the rule. Nothing visual was taken. |

Nothing in the repo previously recorded a URL-architecture or canonical-ownership decision. The
only prior statement of identity is `docs/PUBLICATION_CONTRACT.md`: canonical publication identity
is `(issue_id, article_slug)`, with slugs unique **within** an issue.

## 11. Architecture decision

| Concept | Route | Owns |
|---|---|---|
| HOME | `/` | nothing — presentation over canonical stories |
| ARTICLE | `/articles/<slug>/` | **canonical identity** |
| ISSUE | `/issues/<id>/` | package membership and edition date |
| ARCHIVE | `/archive/` | discovery |
| SEARCH / LANE | `/search/`, `/search/?lane=` | discovery |

**Article ownership: the publication root.** Lane and issue are attributes, never path segments,
so a story's identity cannot change when it is promoted, demoted or re-laned.

**Discovery ownership:** home, issue page, archive, search and lane filter all point at the same
canonical article URL. This mirrors the observed NYT split between `PT=collection` surfaces and
article identity, and it is what the assembler now enforces.

**No URL migration was performed, and none was needed.** The existing `/articles/<slug>/` form
already satisfies every stated priority — stable, human-readable, independent of homepage position,
independent of lane. Only the minting rule was wrong. The route inventory before and after this
pass is byte-identical in membership; what changed is that future issues now *add* article routes
instead of revoking the previous issue's.

Assumption, labelled as such: issue 001 keeps `/issues/001/articles/card_NN.html`. It has no
`article_packages`, so no editorial slug exists for its stories; minting `/articles/card_01/`
would publish a slot number as a story identity, and inventing slugs is an editorial decision, not
an assembler one. Tied to evidence: `outputs/issues/001/` contains no `article_packages` directory,
and its four articles are named by slot.

**Homepage hierarchy: three levels, reduced from four**, following the mobile-collapse evidence in
§2 — one lead, a package at one shared weight, then headline-only rows for earlier editions.

## 12. Implementation

All changes are in `core/site_assembler.py` unless noted.

1. **`_is_globally_routable(issue_dir)`** — an issue earns publication-root article URLs by having
   an `article_packages/*.json` that names a real `article_slug`. Replaces `issue != "001"`.
2. **Promotion loop** now iterates every routable issue, not `latest_slugs`. A slug claimed by two
   issues raises rather than silently overwriting.
3. **`_project_home_page` / `_collect_home_stories` / `_home_card`** — `<main>` on `index.html` is
   rebuilt as `main.home-shell` containing `.home-masthead`, `.home-front` (one `.home-story.is-lead`
   plus a `.home-package` of the rest) and `.home-earlier` (`.home-rows`). The shell — header,
   footer, styles, search wiring — is retained, so the header work is untouched.
   Stories are read from the assembled issue pages' own previews, which already carry approved
   hero media, public headline, dek, lane label and the canonical article route. **No homepage
   content file was added and no story record is duplicated.** Homepage order is the editorial
   order the pipeline already encodes in `.lead` / `.secondary` / `.supporting`; no new ranking
   layer was introduced.
4. **`_canonical_route` / `_project_discovery`** — every page emits
   `<link rel="canonical">`. Absolute, because the package is deliberately relative and
   `validate_host_package` rejects root-relative hrefs; origin from `SITE_BASE_URL`, defaulting to
   `DEFAULT_SITE_BASE_URL` (mirrors `DEFAULT_PUBLIC_ISSUE_URL` in `core/distribution_pack.py`).
   `main.article-shell[data-route]` is corrected to the served route.
5. **Search index scoped to articles.** Non-article documents lose `data-pagefind-body` and gain
   `body[data-pagefind-ignore]`. Index went from 13 documents to 8.
6. **Subscribe** — flat black rectangle, white letters, `border-radius:0`, still
   `aria-disabled="true"` with no destination. Search remains the only rounded control.
7. **`.internet-read`** — `border-radius:0`, `border:0`, padding `20px 22px` → `14px 16px`, tint
   lowered to `#16305e0a`, heading given the article's existing red indent
   (`border-left:3px solid var(--red); padding-left:12px`) at the same 21px Georgia scale as other
   article headings.
8. **Head safety** — a document without `<head>` now gets one, so it cannot silently ship
   unstyled and uncanonicalised.
9. `tests/test_site_assembler.py` — two existing tests re-pointed at the homepage's new structure
   (same guarantees, new selectors), seven new tests added.

### Search-index change, measured

`data-pagefind-body` before: `/`, `/issues/001/`, `/issues/002/`, `/archive/`, `/search/`, four
`/articles/*/`, four `/issues/001/articles/*` = 13 documents.
After: the 8 article documents only.

Root cause of the reported noise, traced rather than blacklisted: on `/` and the issue pages the
only `data-pagefind-body` was the `.search-aliases` div, and Pagefind titled those results from
the page `<h1>` — "Four signals from this week." `/archive/` was indexed because
`_archive_from_shell` set `data-pagefind-body` on the archive `<main>`. No literal-title blacklist
was used. Every article page already carries its own `.search-aliases` block, so removing the
aggregate blocks lost no Korean alias coverage — verified by query.

Measured results after the change:

| Query | Before | After |
|---|---|---|
| `signals` | 4 (`/`, both issues, `/search/`) | **0** |
| `archive` | 1 (`/archive/`) | **0** |
| `week` | 3 (`/`, both issues) | **0** |
| `samjeon` | 3 (article + `/` + issue) | **1** — `/articles/samjeon-nix-samsung-hynix/` |
| `korea` | 5 | **3**, all articles |
| `BigBang` | 3 | **1** — `/articles/bigbang-20th-anniversary-trio/` |

Lane filter unchanged and still correct: `{Fandom: 3, Society: 2, Sports: 3}`.

## 13. Post-change browser validation

Same Chrome session, cache disabled over CDP, real clicks.

| Check | Result |
|---|---|
| `/` lead headline | → `/articles/im-ji-min-stadium-response/`, canonical matches |
| `/` package story | → `/articles/bigbang-20th-anniversary-trio/`, canonical matches |
| `/` earlier-issue row | → `/issues/001/articles/card_02.html`, canonical matches |
| Archive | → `/archive/` |
| Logo from an article | → `/`, h1 `What the Internet Is Really Saying` |
| Edition link | → `/issues/002/`, h1 `Four signals from this week.` |
| Lane navigation | → `/search/?lane=Beauty` |

Layout, three widths:

| Width | Lead | Package | Rows | Horizontal overflow |
|---|---|---|---|---|
| 1440 | 34px/700, 1156w | 19px/700, three columns at 368w | 17px | none |
| 1024 | 34px/700, 965w | 19px/700, two columns at 471w | 17px | none |
| 390 | 27px/700, 335w | 20px/700, stacked | 17px | none |

Header geometry preserved at every width — brand at the far left (135), Subscribe then Search to
its right (1118–1231, 1243–1291), lane nav on its own row below (top 94). Subscribe computes
`border-radius: 0px`, `background: rgb(0,0,0)`, `color: rgb(255,255,255)`; `.site-search` remains
`999px`. `.internet-read` computes `border-radius: 0px`, `border: 0px`, `padding: 14px 16px`,
heading `border-left: 3px rgb(217,54,50)`, `padding-left: 12px`.

Tests: `tests/test_site_assembler.py` 28 passed; full suite 444 passed.

## 14. Open findings, not changed in this pass

- **Two of five header lanes resolve to nothing.** The Pagefind lane filter contains only
  `Fandom`, `Society` and `Sports`; clicking Beauty or Food reaches `/search/?lane=…` with zero
  results. NYT's nav items all resolve to populated surfaces. Fixing this means either removing
  lanes from the header or giving lane routes an empty state — both editorial calls.
- **Hero media on homepage cards is not a link.** On NYT the image and the headline share a
  destination. Ours has the image inert. Low risk to change; left alone as it was not part of the
  reported problem.
- **Lane disagreement on one story.** `outputs/issues/002/article_packages/card_03.json` records
  `lane: "culture"` while the rendered page shows `Society / 사회`. Editorial data question, not an
  assembler one.
- **Issue 002's edition date is 2026-08-23**, four days after this inspection. Taken from
  `ISSUE_METADATA` as configured; not adjusted.
