# Canonical publication contract

The canonical publication identity is `(issue_id, article_slug)`. The existing build validates
article slugs as unique within an issue. `story_id` is retained as editorial lineage, but the
current code does not enforce it as globally unique.

Structured article content and canonical publication state are independent of presentation
clients. Website, mobile app, newsletter renderer, Slack operations, and future clients must
consume the same article/publication identity rather than maintaining separate publication
records.

Evidence `PASS`, `HOLD`, and `FAIL` describe evidence sufficiency only. They do not create or
change publication state. An `ArticlePackage`, rendered HTML, and discovery/index metadata are
also not publication approval or canonical workflow state.

Allowed transitions are:

| From | To |
| --- | --- |
| `ready_for_review` | `approved`, `held`, `rejected` |
| `held` | `ready_for_review`, `rejected` |
| `approved` | `published`, `held` |
| `rejected` | none |
| `published` | none |

Every transition requires an explicit actor and creates an immutable event. Local development
uses an atomic JSON repository; clients depend on the repository boundary, so hosted storage can
replace it without making Slack, HTML, or another presentation client the source of truth.
