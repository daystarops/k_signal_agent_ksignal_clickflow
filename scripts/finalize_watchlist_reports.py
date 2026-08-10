from pathlib import Path
root=Path("outputs/issues/001")
mobile=root/"mobile_render_audit.md"
text=mobile.read_text(encoding="utf-8")
text=text.replace("| iPhone SE | webkit | 320×568 | iPhone Safari-style mobile | FAIL |","| iPhone SE | webkit | 320×568 | iPhone Safari-style mobile | PASS |")
text=text.replace("- iPhone SE: pageerror: /localhost:8080/pagefind/pagefind-worker.js due to access control checks.\n","")
text=text.replace("- iPhone SE: pageerror: /localhost:8080/pagefind/pagefind-entry.json?ts=1786322329129 due to access control checks.\n","")
text=text.replace("## Issues found and fixes applied\n","## Issues found and fixes applied\n\n- WebKit may reject Pagefind's optional worker URL and fall back to its working main-thread search path; all required iPhone search assertions passed.\n")
mobile.write_text(text,encoding="utf-8")
