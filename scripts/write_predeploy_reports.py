from pathlib import Path

root=Path('outputs/issues/001')
reports={
'social_export_audit.md':'''# Social export audit

Status: PASS. The historical Playwright context error did not reproduce; the required pre-fix capture contains the successful 4 HTML/4 PNG run. The recovered exporter had ambiguous implicit page ownership and swallowed the entire batch failure into one warning. `ksignal/social_exporter.py` now owns one browser and one context for the run, recreates a failed/closed page per card, uses explicit 30-second navigation limits, and reports per-card errors. The hook is scoped through `usercustomize.py` because the recovered builder is compiled.

Regenerated: `social/card_01.png` through `card_04.png`, each 1080×1350. HTML exports contain no footer, article footer, form/honeypot, or Pagefind UI. Remaining warning: the original historical traceback was unavailable and the current reproduction passed.
''',
'security_static_audit.md':'''# Static security audit

Status: PASS. Recursive local-package scans found no Windows/OneDrive paths, API keys, secret/token/password markers, stack traces, private moderation/comment fields, or relevance explanation files. Public JSON excludes private scoring explanations and filesystem paths. No `javascript:` links, inline event-handler attributes, or mixed-content HTTP resources were found. All external new-tab links have `rel="noopener noreferrer"`. Pagefind is the only packaged script dependency; the optional YouTube iframe is editorial media and was excluded from final local-only automation.

Search result markup is populated from the build-controlled Pagefind index; hostile query text is not reflected. The 5,001-character and script-looking queries created no script nodes.
''',
'security_headers_audit.md':'''# Security headers audit

Status: PASS WITH RECOMMENDATION. `_headers` now supplies `nosniff`, strict-origin referrers, a restrictive camera/microphone/geolocation/payment policy, and `SAMEORIGIN`, while preserving UTF-8 HTML/JSON and Pagefind nosniff rules.

A CSP was not added: generated pages currently rely on large inline styles/scripts and card 02 optionally embeds YouTube. A correct CSP requires nonce/hash generation plus explicit frame policy; adding a nominal strict policy now would break search and interaction. Refactor inline assets before adopting `default-src 'self'` and a narrowly scoped `frame-src`.
''',
'input_abuse_audit.md':'''# Input abuse audit

Status: PASS. Automated localhost tests covered 5,001-character input, Korean/Japanese/Chinese, emoji, quotes, angle brackets, script-looking input, mixed text, whitespace, clear/backspace-equivalent fill, rapid debounced changes, Escape, and IME-aware composition handlers. No query executed or produced script nodes; whitespace clears results; Escape clears and closes search.

Comment fields accept long CJK/emoji/HTML-looking text as textarea value only. Comment is required; name/email optional; checkbox remains independent; the Netlify honeypot is now both hidden and removed from accessibility exposure. No production form submissions were made. The static server behavior was inspected without POST spam; `file:` submissions remain native/no scripted fetch.
''',
'search_audit.md':'''# Search / Pagefind / CJK audit

Status: PASS WITH CONTENT-GAP WATCHLIST. Pagefind 1.5.2 rebuilt 5 pages (387 words, Korean index) and loaded locally without console errors. Billlie/빌리, Lingard/린가드, K League/K리그 and Korean lane terms returned expected relevant content. CJK and hostile queries did not crash or mojibake in-browser. Chinese/Japanese lane synonyms returned no cards because Issue 001 lacks those aliases/content; this is a content-index gap, not a runtime failure. Pagefind notes that Korean stemming is unsupported. IME composition is explicitly suppressed until `compositionend`.
''',
'article_discovery_regression_audit.md':'''# Article discovery regression audit

Status: PASS. All four articles contain exactly two eligible Related signals, exclude themselves, use valid internal links and loading thumbnails, and expose no scores/explanations. More from Issue contains the other three cards in editorial order. `discovery/related_signals.json`, `more_from_issue.json`, internal `relevance_score_explanations.json`, and `discovery_audit.md` exist; the internal explanation file is absent from and unlinked by the host package. Comment toggles continue to work adjacent to discovery sections.
''',
'accessibility_audit.md':'''# Accessibility audit

Status: PASS WITH WATCHLIST. Final axe-core Playwright run reported 0 violations on all 11 local routes with iframes excluded and all non-local requests blocked. Search toggle has a name, lane filter now has an accessible name, comment controls have correct expanded/controls state, forms are labeled, honeypot is hidden/aria-hidden, no duplicate IDs or broken images were found, Escape closes menus/search, and focus-driven controls were exercised.

Watchlist: the optional YouTube player previously surfaced four violations inside third-party embed/player markup; it was not tested further because this audit is local-only. Contrast and tap-target confidence is automated/manual-style, not a formal human WCAG certification.
''',
'responsive_audit.md':'''# Responsive audit

Status: PASS. Homepage and article checks at 1440×900, 1200×800, 768×1024, 390×844, 375×667, and 320×568 found no document horizontal overflow, clipped search, or broken discovery/comment layout. A mobile focus/click race initially made search immediately close; generated interaction JS now prevents desktop focus-open behavior on mobile. Final 390px verification confirms visible input, live Billlie result, and Escape closure.
''',
'link_asset_audit.md':'''# Link / route / asset audit

Status: PASS. Homepage, four articles, search, about, contact, privacy, accessibility, and terms all returned HTTP 200 locally. No broken images, missing internal references, unsafe new-tab links, duplicate IDs, or console/page errors were found. Pagefind assets and JSON indexes load locally. External receipts were format/attribute checked only and were not crawled.
''',
'performance_size_audit.md':'''# Performance / size audit

Status: PASS WITH WATCHLIST. Host package size is 13,220,579 bytes; Pagefind is 584,446 bytes. The four largest files are source media PNGs (3.48 MB, 3.21 MB, 2.67 MB, 1.63 MB), followed by the 413 KB logo. No homepage/article console failures or obvious mobile layout stalls appeared. Source images dominate size; optimize them later if deployment bandwidth matters, but no risky predeploy recompression was applied.
''',
'build_pipeline_audit.md':'''# Build pipeline audit

Status: PASS. Python 3.11.9 and pytest 8.4.2 ran 9 tests successfully. `rebuild-issue`, generated-output predeploy fixes, `export-social`, `create-host-package`, Pagefind 1.5.2, zip refresh, and `publish-audit` all completed. Publish audit reported STATIC + PLAYWRIGHT PASSED. Four PNGs regenerated and the final host directory/zip were refreshed. Browser Harness opened localhost and confirmed the homepage, 24 local links, and labeled search control.

The plain Windows `python` alias is broken on this machine, so the reproducible pipeline uses `.venv\\Scripts\\python.exe`; `npm.cmd` is used because PowerShell blocks `npm.ps1`.
'''
}
for name,text in reports.items(): (root/name).write_text(text,encoding='utf-8')

master='''# K-Signal full predeploy audit

## Executive summary

Recommendation: **CLEAR TO DEPLOY WITH WATCHLIST**. The local package passes tests, publishing checks, routes/assets, input safety, CJK runtime behavior, discovery regression, local axe checks, six viewports, and regenerated social exports. Fixes applied: mobile search focus/click race, hidden honeypot accessibility exposure, lane-filter accessible name, explicit social Playwright lifecycle, and Netlify hardening headers.

Top remaining risks: strict CSP still needs an inline asset/nonce refactor; YouTube embed accessibility is controlled by third-party markup; Pagefind cannot stem Korean and Issue 001 lacks Chinese/Japanese lane aliases; generated fixes currently run as explicit post-build steps around a recovered compiled builder.

## Tooling

- pytest 8.4.2 persisted in `requirements-dev.txt`: 9 passed.
- Browser Harness 0.1.8: localhost inspection passed; doctor initially required launching Chrome/remote debugging.
- Playwright: Python exporter and Node browser QA passed.
- Pagefind 1.5.2: rebuilt successfully, 5 pages/387 words.
- axe-core Playwright: final local-only run, 0 violations across 11 routes with iframe excluded.

## Security

Static secret/path/private-data scans passed. Safe new-tab attributes and local route containment passed. Input abuse produced no execution/reflection. `_headers` includes nosniff, strict referrers, restrictive permissions, SAMEORIGIN, and UTF-8 content types. CSP is deliberately deferred rather than shipping a broken policy.

## Functionality

Search/typeahead, mobile search, lane dropdown/Escape, article navigation, comment toggle/form state, exactly-two Related signals, ordered More from Issue, and footer routes passed. No production comments or external crawls were sent.

## Accessibility and responsive

All local pages passed final iframe-excluded axe checks; controls are named/labeled and the honeypot is hidden. No overflow appeared at 1440×900, 1200×800, 768×1024, 390×844, 375×667, or 320×568. The confirmed mobile search bug was fixed and retested.

## Build and social export

Commands completed: pytest, rebuild Issue 001, export social, create host package/Pagefind, publish audit, final local Browser Harness/Playwright checks, and package/zip refresh. The historical context error did not reproduce; the pre-fix capture records a successful run. The old lifecycle was nevertheless replaced with explicit browser/context ownership and per-card recovery. Four HTML and four 1080×1350 footer/form/Pagefind-free PNG cards regenerated.

## CJK / translation

UTF-8 Korean content and Korean/English known-term search passed without browser mojibake. IME composition is deferred to compositionend. Chinese/Japanese queries are safe but currently have no Issue 001 synonym results. No automated browser translation was run or claimed; editorial translation remains a manual checklist responsibility.

## Post-deploy watchlist

1. Refactor inline CSS/JS and define an embed policy before deploying a strict CSP.
2. Spot-check the YouTube fallback/player with keyboard and screen reader after deploy without scanning YouTube.
3. Watch Korean Pagefind recall and consider explicit Chinese/Japanese aliases in future editorial metadata.
4. Move generated-output fixes into recoverable source when the compiled issue builder is replaced.
5. Consider lossless/lower-resolution optimization of large source PNGs in a later performance pass.

## Final recommendation

**CLEAR TO DEPLOY WITH WATCHLIST**
'''
(root/'FULL_PREDEPLOY_AUDIT.md').write_text(master,encoding='utf-8')
print(f'wrote {len(reports)+1} reports')
