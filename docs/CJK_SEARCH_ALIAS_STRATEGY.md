# CJK search alias strategy

Issue 001 keeps its public labels and editorial copy unchanged. Search-only aliases are maintained in `ksignal/site_stabilization.py`, added to the four structured indexes during every rebuild, and emitted once per relevant page in a visually hidden, `aria-hidden` Pagefind body block.

Aliases are deliberately curated by card and lane. They cover Korean spacing/transliteration variants, a small set of likely English misspellings, and useful Japanese/Simplified/Traditional Chinese lane terms. They are normalized with Unicode NFKC plus case folding and deduplicated. They are not used as visible article prose and are not expanded into unrelated topics.

Pagefind still does not provide Korean morphological stemming. New concepts should therefore add explicit variants only when editorially relevant. Search excerpts should continue to prefer visible page copy; the alias block is intentionally short and placed after the main content.

