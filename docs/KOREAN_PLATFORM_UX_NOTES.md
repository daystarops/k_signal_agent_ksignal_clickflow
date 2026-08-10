# Korean Platform UX Notes for K-Signal

## Summary

Korean-native platforms make navigation state, community location, freshness, and popularity immediately legible. They are fast because board/category labels, HOT lists, timestamps, recommendation/view counts, and comment counts do real routing work. K-Signal should borrow that clarity while refusing the clutter, ad density, anonymous pile-on dynamics, and false implication that popularity equals accuracy.

Research used Browser Harness at approximately 1440px desktop and 390px mobile on August 9, 2026 (America/New_York). Chrome's page translation was active on much of the Korean material, so original labels and translated interpretations are recorded separately where visible. Translation made some labels comically or materially wrong.

## FMKorea

### Observed behavior

- A large board taxonomy groups humor/information, sports, shopping/investment, streaming/community, games, galleries, Football Manager, and smaller boards.
- `포텐 터짐`, `/best`, and `/best2` provide immediate popularity/trending routes. Translated labels varied (“Explosion of potential,” “Explosive Potential Newest,” “Top Trending Topics”), illustrating why selectors cannot depend on translated text.
- Lists expose recommendation counts (`추천`), comment counts in brackets, board/category, relative time, and a handle. Popularity is visible before opening a post.
- Public board lists and public posts were accessible. Login/sign-up, favorites, auto-login, and posting controls were visibly separate.
- Desktop is dense and ad-heavy; mobile compresses the same hierarchy. The public mobile URL was accessible.

### Borrow

- Clear lane/board ancestry on every signal.
- Separate “popular now” from chronological browsing.
- Compact, consistently ordered metadata: time, source board, views/recommendations/comments when provenance supports it.
- Direct comment anchors and visible engagement labels.

### Avoid

- Ad collisions, sprawling board menus, unexplained slang, and treating recommendation totals as trust.
- Importing handles or personal data into K-Signal indexes.
- Letting translated board names replace canonical Korean labels.

## Naver

### Observed behavior

- The portal is a service launcher and search product first: search, news, shopping, mail, cafe, blog, maps, webtoon, finance, and personalized modules coexist.
- Search results combine types and sources; Naver News is a distinct, highly structured destination.
- News offers publisher browsing, politics/economy/society/lifestyle/IT/world categories, rankings, newspaper view, opinion, fact checks, algorithm guidance, and a corrections collection.
- Publisher, timestamp, subscription, topic, and ranking cues are prominent. The desktop News page exposed logged-in account chrome in the existing browser session; the research did not use account-only actions or expose personal details.
- Mobile News removes much of the portal chrome and prioritizes compact category/ranking movement.
- Article comments/reactions were not reliably documented in the sampled pass; they can vary by publisher/article and account state, so no universal behavior is claimed.

### Borrow

- Search as a first-class entry, with typed destinations and filters.
- Publisher/source identity next to every article.
- Dedicated corrections, fact-check, and algorithm/explanation surfaces.
- Mobile-specific prioritization rather than merely shrinking desktop.

### Avoid

- Portal sprawl, personalized clutter, opaque recommendation blending, and subscription/account controls K-Signal cannot support.
- Treating Naver placement as independent verification.

## TheQoo

### Observed behavior

- Top routes include `전체` (All), `HOT`, `스퀘어` (Square), beauty, daily talk, K-dol talk, and many fandom/topic boards.
- Board lists are extremely compact: category/title, timestamp, and a directly linked comment count. HOT works as a cross-board popularity layer.
- Public posts show board/category, title, views, comment count, date, source/permalink, and direct `댓글` (Comment), up/down, list, and print anchors.
- Comments were publicly visible on the sampled post and numbered as `무명의 더쿠` (“Anonymous TheQoo”), making thread scale clear while minimizing persistent identity cues.
- Integrated search at the tested URL reported that it was unavailable and presented login UI. Login was inspected only as a boundary; no credentials were entered.
- At 390px the HOT list becomes a highly compressed text table with comment counts as the strongest secondary cue.

### Borrow

- Always preserve board/category context and source permalink.
- Make comment count/entry predictable and near the content boundary.
- Separate HOT discovery from chronological/all-post browsing.
- Use compact mobile rows for archives, not oversized cards everywhere.

### Avoid

- Anonymous-volume-as-consensus, minimal source context, difficult integrated search, and a wall of undifferentiated text.
- Copying community tone or exposing handles/comments without editorial need.

## Optional Notes

The optional Naver Cafe/Blog and mobile community variants were not deeply audited. No login-gated Cafe content was inspected. The public FMKorea mobile homepage was opened; a distinct mobile TheQoo host was unnecessary because the main host responded to a mobile viewport.

## Click Journal Takeaways

### Fastest useful paths

- **FMKorea:** homepage → `포텐 터짐`/`best` → `best2` → board (`유머`, `국내축구`) → post → comment anchor. Use board URLs as stable context.
- **Naver:** portal search → `뉴스` → category → `랭킹` → article; use `정정보도 모음` and algorithm/fact-check destinations for trust context.
- **TheQoo:** `HOT` for cross-board velocity, `스퀘어` for public issue/information posts, a specific talk board for community context, then post → `댓글`.

### Labels worth remembering

`포텐 터짐` (made/popular board), `추천` (recommend), `조회` (views), `댓글` (comments), `전체` (all), `HOT`, `스퀘어` (Square), `랭킹` (ranking), `뉴스` (news), `정정보도 모음` (corrections collection), `로그인` (login), and `무명의 더쿠` (Anonymous TheQoo).

### Repeated patterns and blockers

Board/category context, freshness, and comment counts repeat across Korean sites. Popularity routes are distinct from ordinary chronology. Common blockers are login-gated personalization/posting, dynamic modules, inconsistent search entry points, and auto-translation that alters labels and sometimes the document language. TheQoo's tested integrated search was unavailable; Naver account chrome reflected an existing session but was not used; no paywall/login/captcha was bypassed.

### Source-scouting opportunities

Store canonical Korean label, interpreted English label, stable URL pattern, page type, access status, translation state, and known comment anchor for each navigation step. This lets later agents reach public source context quickly without mass crawling.

## Implications for K-Signal

- **Homepage:** keep editorial hierarchy; later add a quiet “signals gaining attention” layer only when methodology is explainable.
- **Article pages:** show canonical source platform/board, source timestamp/metrics with capture time, receipts, and distinct correction/comment controls.
- **Comments/corrections:** keep the current restrained toggle; distinguish correction evidence from reaction volume and show moderation expectations.
- **Related cards:** rank archive-wide semantic/editorial connection, not same-issue proximity or raw popularity.
- **Search:** retain Pagefind, add board/platform/topic/entity filters, canonical Korean synonyms, and explicit result types.
- **Category/archive pages:** combine a featured signal with compact chronological rows; allow a separately labeled popularity view later.
- **Signal scoring:** popularity, source diversity, correction activity, and velocity may be inputs, never truth proxies.
- **Metadata:** add canonical platform/board IDs, source URL, captured-at, observed metrics, access/translation status, and provenance.
- **LLM/RAG:** use the click journal as navigation memory and the structured archive as retrieval memory; answers must cite public K-Signal routes and preserve source/translation limitations.
