# Article Discovery Architecture

## Decision

Article endings need two visibly separate discovery systems:

1. **Related signals** answers: “What else in the full archive helps me understand this?”
2. **More from Issue 001** answers: “What else was packaged in this edition?”

The current generated articles use one three-card `More from Issue 001` grid. It is useful issue navigation, but it is not archive relevance and should not be relabeled as such.

## Related signals

Place **Related signals** near the bottom of every published article and show exactly two cards drawn from all published issues.

### Eligibility

- Exclude the current card.
- Include only `status: published` cards with a public route.
- Exclude unpublished, draft, held, withdrawn, or route-less records.

### Deterministic score v1

| Factor | Points |
|---|---:|
| Same lane | +25 |
| Each shared normalized topic tag | +12 |
| Each shared normalized entity tag | +18 |
| Shared source platform | +6 |
| Shared source type | +4 |
| Shared issue | +3 |
| Each shared normalized search keyword | +5 |

Normalize case, Unicode (NFKC), whitespace, aliases, and bilingual equivalents before comparison. Cap repeated keyword/tag contribution later if broad tags begin to dominate.

Future inputs are embedding similarity over `internet_read` and `public_summary`, reader correction/comment links, and a small recency adjustment. Recency must not outrank topical or entity relevance.

Tie-breakers, in order:

1. Higher score.
2. Newer `published_at`.
3. Same lane.
4. Editorial override.

Editorial overrides should support pinned inclusions and exclusions with a reason and audit timestamp. The output is the top two cards after overrides.

### Result card

Each compact preview contains headline, lane label, issue label, short dek/public summary, optional tiny thumbnail, and **Read the signal →**. The title is exactly **Related signals**, never “Related stories,” “You may also like,” or “More from K-Signal.”

## More from this issue

This module is package navigation, not a ranking algorithm.

- Title: **More from Issue 001** (dynamic issue ID).
- Include other published cards in the same issue.
- Exclude the current card.
- Preserve issue editorial order.
- Use a tiny image, lane label, headline, and optional issue label.
- Place after Related signals, unless a tested desktop rail is later approved.
- Desktop: horizontal compact strip.
- Mobile: swipeable strip with an accessible stacked fallback; never trap horizontal page scrolling.

## Placement options score

Scores are out of 10 and balance reading comfort, mobile simplicity, clutter, editorial feel, and archive scalability.

| Option | Score | Assessment |
|---|---:|---|
| Below article | **9.0** | Best default. Preserves reading flow, works on all widths, and keeps both systems comparable. |
| Right-side rail on desktop | **7.2** | Magazine-like and useful on wide screens, but competes with receipts/body and disappears on mobile. |
| Sticky side module | **5.1** | Persistent discovery, but highest distraction and collision risk; weak fit for calm reading. |
| Mobile carousel | **8.0** | Space-efficient when secondary to the article; needs clear scroll affordance and accessibility fallback. |

**Recommendation:** approve below-article placement for both modules; allow a non-sticky desktop rail experiment only after the archive has enough issue depth. Use a mobile swipe strip for issue navigation, while Related signals remains two stacked cards.

## Data contract

Add or guarantee stable fields: `issue_id`, `card_id`, `article_path`, `status`, `published_at`, `editorial_order`, `lane_slug`, normalized topic/entity/keyword IDs, source platform/type IDs, `public_summary`, thumbnail, and optional override records. Compute relationships during build initially, emit score reasons for QA, and keep public output free of private moderation/comment data.
