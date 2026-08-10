# Auto-translation QA

Automated browser translation is not part of the local browser harness, so run this checklist on the deployed package:

- Chrome / Google Translate: translate English to Korean, Japanese, Simplified Chinese, and Traditional Chinese; confirm navigation and search still open and close.
- Edge Translate: repeat the navigation, typeahead, lane, and article-route checks.
- Safari translation (where available): verify homepage and article reading surfaces and route navigation.
- Papago / Naver: copy and translate the English explanation; confirm the Korean original receipt remains separately identifiable.
- DeepL browser translation/copy: confirm brand, Issue 001, card IDs, route slugs, and source platform labels remain stable where marked.
- On every translator, search after visible lane labels are mutated; results must still use Pagefind and stable data attributes.
- Confirm original Korean quotes remain `lang="ko"`, visually identifiable, and unchanged.
- Confirm English explanation remains translatable.
- Confirm K-Signal and machine IDs are not translated.
- Confirm no control depends on the text content of a translated label.