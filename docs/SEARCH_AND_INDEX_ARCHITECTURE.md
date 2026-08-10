# Search and index architecture

K-Signal is designed as four compatible layers:

1. **Media network UI** — the editorial homepage, article routes, receipts, and correction capture.
2. **Static full-text search** — Pagefind indexes the generated public host package and ships its JavaScript, WASM, and index shards locally in `host_package/pagefind/`.
3. **Structured cultural archive** — UTF-8 JSON in `outputs/search/` is the master data layer; each host package gets a public-safe snapshot in `search/`.
4. **Future backend LLM / RAG system** — not implemented in this pass. A future service can retrieve structured cards, topics, entities, and lanes, then cite public article routes.

Pagefind is the public search engine. The header typeahead and `search.html` use Pagefind's browser API; they do not implement a second substring engine. `python main.py create-host-package --issue 001` indexes the staged package before validation and ZIP creation.

The structured indexes remain separate because they model editorial meaning rather than a browser search implementation. `cards_index.json` preserves display text, original receipts, translations, NFKC-normalized search text, language metadata, stable IDs, routes, topics, entities, provenance, and future summarization seeds. Topic, entity, and lane indexes map concepts to stable card IDs.

## CJK and Auto-Translation Strategy

CJK tokenization matters because Korean, Japanese, and Chinese cannot be treated as English text split only on spaces. The host package uses Pagefind Extended and a single forced `ko` index so its specialized no-whitespace segmenter is active across bilingual Korean/English article documents; this avoids splitting one bilingual archive into browser-selected language silos. Article documents are English, while original receipts are explicitly `lang="ko"`; future Japanese and Chinese blocks should use `ja`, `zh-Hans`, or `zh-Hant`.

Original and display values are separate. `original_text` and `original_quote` remain unchanged, while `normalized_text` and `normalized_search_text` use Unicode NFKC plus case folding. This supports full-width/half-width equivalence without mutating the receipt. Language mix and translation language are explicit machine fields.

Browser translation may rewrite visible labels. Interaction logic therefore uses stable classes, IDs, `data-card-id`, `data-issue-id`, `data-lane`, `data-route`, and JSON—not translated label text. Brand names and machine identifiers use `translate="no"`; the whole page never does. Original receipt blocks use their source language and `translate="no"`, while English explanations remain translatable.

IME input is composition-aware: searches wait through `compositionstart`, ignore composing input events, and run after `compositionend`. Ordinary input is lightly debounced and NFKC-normalized before Pagefind search.

All required CSS, SVG icons, Pagefind files, images, and scripts are local and use relative paths. External source/video links are optional receipts with readable surrounding context.