from __future__ import annotations

import shutil
import stat
import subprocess
import tempfile
import zipfile
from pathlib import Path
from urllib.parse import unquote, urlparse

from bs4 import BeautifulSoup


PUBLIC_DIRS = ("articles", "media", "assets", "search")
PUBLIC_FILES = ("about.html", "contact.html", "privacy.html", "accessibility.html", "terms.html")
NETLIFY_HEADERS = """/*.html
  Content-Type: text/html; charset=utf-8

/articles/*.html
  Content-Type: text/html; charset=utf-8

/search/*.json
  Content-Type: application/json; charset=utf-8
"""


def _remove_readonly_tree(path: Path) -> None:
    def unlock_and_retry(function, target, _error):
        Path(target).chmod(stat.S_IWRITE)
        function(target)
    shutil.rmtree(path, onerror=unlock_and_retry)
LOCAL_ATTRS = (("a", "href"), ("img", "src"), ("script", "src"), ("link", "href"), ("iframe", "src"))


def _is_external(value: str) -> bool:
    parsed = urlparse(value)
    return parsed.scheme in ("http", "https", "mailto", "tel") or value.startswith("//")


def validate_host_package(package_dir: Path) -> list[str]:
    errors: list[str] = []
    root = package_dir.resolve()
    html_files = sorted(package_dir.rglob("*.html"))
    if not (package_dir / "index.html").exists():
        errors.append("index.html is missing")

    for html_path in html_files:
        soup = BeautifulSoup(html_path.read_text(encoding="utf-8"), "html.parser")
        for selector, attribute in LOCAL_ATTRS:
            for node in soup.select(f"{selector}[{attribute}]"):
                value = (node.get(attribute) or "").strip()
                if not value or value.startswith(("#", "data:", "javascript:")):
                    continue
                if _is_external(value):
                    if selector == "a":
                        rel = set(node.get("rel", []))
                        if node.get("target") != "_blank" or not {"noopener", "noreferrer"}.issubset(rel):
                            errors.append(f"{html_path.relative_to(package_dir)}: external link lacks safe new-tab attributes: {value}")
                    continue
                local_value = unquote(urlparse(value).path)
                target = (html_path.parent / local_value).resolve()
                try:
                    target.relative_to(root)
                except ValueError:
                    errors.append(f"{html_path.relative_to(package_dir)}: local path escapes package: {value}")
                    continue
                if not target.exists():
                    errors.append(f"{html_path.relative_to(package_dir)}: broken local {attribute}: {value}")
    return errors


def create_host_package(issue: str, output_root: str | Path = "outputs/issues") -> tuple[Path, Path, int]:
    issue_dir = Path(output_root) / issue
    newsletter = issue_dir / "newsletter.html"
    if not newsletter.exists():
        raise FileNotFoundError(f"Build Issue {issue} before creating its host package.")

    package_dir = issue_dir / "host_package"
    zip_path = issue_dir / "host_package.zip"
    with tempfile.TemporaryDirectory(prefix=f"ksignal-{issue}-") as temp_name:
        staged = Path(temp_name) / "host_package"
        staged.mkdir(parents=True)
        shutil.copy2(newsletter, staged / "index.html")
        search_page = issue_dir / "search.html"
        if search_page.exists():
            shutil.copy2(search_page, staged / "search.html")
        for filename in PUBLIC_FILES:
            source = issue_dir / filename
            if not source.exists():
                raise FileNotFoundError(f"Required publication page is missing: {source}")
            shutil.copy2(source, staged / filename)
        for dirname in PUBLIC_DIRS:
            source = issue_dir / dirname
            if not source.exists():
                raise FileNotFoundError(f"Required issue directory is missing: {source}")
            shutil.copytree(source, staged / dirname)

        # Article back-links target newsletter.html in issue output. Netlify serves
        # that same page as index.html inside the package.
        for article_path in (staged / "articles").glob("*.html"):
            html = article_path.read_text(encoding="utf-8")
            article_path.write_text(html.replace("../newsletter.html", "../index.html"), encoding="utf-8")
        staged_search = staged / "search.html"
        if staged_search.exists():
            html = staged_search.read_text(encoding="utf-8")
            staged_search.write_text(html.replace('href="newsletter.html"', 'href="index.html"'), encoding="utf-8")
        for page_name in PUBLIC_FILES:
            staged_page = staged / page_name
            html = staged_page.read_text(encoding="utf-8")
            staged_page.write_text(html.replace('href="newsletter.html"', 'href="index.html"'), encoding="utf-8")
        (staged / "_headers").write_text(NETLIFY_HEADERS, encoding="utf-8")
        pagefind = Path("node_modules/.bin/pagefind.cmd")
        if not pagefind.exists():
            raise FileNotFoundError("Pagefind is not installed. Run npm install first.")
        subprocess.run(
            [str(pagefind.resolve()), "--site", str(staged.resolve()), "--output-subdir", "pagefind", "--force-language", "ko"],
            check=True,
        )

        errors = validate_host_package(staged)
        if errors:
            raise ValueError("Host package validation failed:\n- " + "\n- ".join(errors))

        if package_dir.exists():
            _remove_readonly_tree(package_dir)
        shutil.copytree(staged, package_dir)

    if zip_path.exists():
        zip_path.unlink()
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for path in sorted(package_dir.rglob("*")):
            if path.is_file():
                archive.write(path, path.relative_to(package_dir).as_posix())

    errors = validate_host_package(package_dir)
    if errors:
        raise ValueError("Final host package validation failed:\n- " + "\n- ".join(errors))
    return package_dir, zip_path, len(list(package_dir.rglob("*")))

