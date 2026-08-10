# Generator stabilization plan

## Safely moved into normal source

`ksignal/site_stabilization.py` now owns repeatable CJK alias enrichment, Pagefind metadata, interaction-script extraction, embed attributes/fallback labeling, and the prior honeypot/lane-filter accessibility fixes. `ksignal/issue_builder.py` applies those steps on every rebuild and carries restrained mobile CSS. `core/host_packager.py` now generates the audited Netlify security headers. Footer, search/header, comments, discovery, forms, and social cleanup remain in their existing source wrappers/exporters.

## Remaining generated-output behavior

The recovered compiled builder still emits the main templates and large inline CSS. The source wrapper normalizes its output before packaging, but it is not a replacement template system. The preserved pre-watchlist wrappers document the exact previous boundary.

## Risks and next step before Issue 002

Large inline CSS prevents a genuinely strict CSP without hashes or extraction. Before Issue 002, recover or replace the compiled templates behind snapshot tests, split shared CSS into `assets/ksignal.css`, then remove the compatibility wrappers. Keep Pagefind, Netlify form detection, discovery ordering, and social-export exclusion tests as migration gates.

