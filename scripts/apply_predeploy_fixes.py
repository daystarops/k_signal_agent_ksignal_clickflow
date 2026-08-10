"""Apply audited fixes to generated Issue 001 artifacts and refresh its zip."""
from pathlib import Path
import zipfile

ISSUE = Path("outputs/issues/001")
OLD = "search.addEventListener('focusin',open)"
NEW = "search.addEventListener('focusin',()=>{if(!mobile())open()})"
HEADERS = """/*
  X-Content-Type-Options: nosniff
  Referrer-Policy: strict-origin-when-cross-origin
  Permissions-Policy: camera=(), microphone=(), geolocation=(), payment=()
  X-Frame-Options: SAMEORIGIN

/*.html
  Content-Type: text/html; charset=utf-8

/articles/*.html
  Content-Type: text/html; charset=utf-8

/search/*.json
  Content-Type: application/json; charset=utf-8

/pagefind/*
  X-Content-Type-Options: nosniff
"""

def patch_html(root: Path) -> int:
    changed = 0
    for path in root.rglob("*.html"):
        text = path.read_text(encoding="utf-8")
        if OLD in text:
            path.write_text(text.replace(OLD, NEW), encoding="utf-8")
            changed += 1
    return changed

if __name__ == "__main__":
    count = patch_html(ISSUE)
    host = ISSUE / "host_package"
    if host.exists():
        (host / "_headers").write_text(HEADERS, encoding="utf-8")
        archive_path = ISSUE / "host_package.zip"
        with zipfile.ZipFile(archive_path, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
            for path in sorted(host.rglob("*")):
                if path.is_file():
                    archive.write(path, path.relative_to(host).as_posix())
    print(f"patched_html={count}; headers={host.exists()}; zip={host.exists()}")
