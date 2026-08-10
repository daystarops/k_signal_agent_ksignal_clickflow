"""Apply small generated-markup accessibility fixes and refresh the host zip."""
from pathlib import Path
import zipfile

issue = Path("outputs/issues/001")
replacements = {
    '<p class="honeypot">': '<p class="honeypot" hidden aria-hidden="true">',
    '<select id="lane-filters">': '<select id="lane-filters" aria-label="Filter search results by lane">',
    '<div class="hero video"><img': '<div class="hero video"><img',
    '</img><i>▶</i>': '</img><i aria-hidden="true">▶</i>',
}
for root in (issue,):
    for path in root.rglob("*.html"):
        text = path.read_text(encoding="utf-8")
        updated = text
        for old, new in replacements.items():
            updated = updated.replace(old, new)
        updated = updated.replace('<i>▶</i></div>', '<i aria-hidden="true">▶</i></div>')
        if updated != text:
            path.write_text(updated, encoding="utf-8")
host = issue / "host_package"
with zipfile.ZipFile(issue / "host_package.zip", "w", zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
    for path in sorted(host.rglob("*")):
        if path.is_file(): archive.write(path, path.relative_to(host).as_posix())
print("accessibility fixes applied; zip refreshed")
