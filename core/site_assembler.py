"""Assemble immutable issue outputs into one persistent static publication."""

from __future__ import annotations

import shutil
import stat
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

from bs4 import BeautifulSoup

from core.host_packager import NETLIFY_HEADERS, validate_host_package


PUBLIC_PAGES = ("about.html", "contact.html", "privacy.html", "accessibility.html", "terms.html")
PUBLIC_DIRS = ("assets", "media")


@dataclass(frozen=True)
class SiteBuild:
    site_dir: Path
    issue_routes: tuple[str, ...]
    article_routes: tuple[str, ...]
    pagefind_entry_count: int


def _remove_tree(path: Path) -> None:
    def retry(function, target, _error):
        Path(target).chmod(stat.S_IWRITE)
        function(target)

    shutil.rmtree(path, onerror=retry)


def _write_soup(path: Path, soup: BeautifulSoup) -> None:
    for link in soup.select("a[href]"):
        parsed = urlparse(str(link.get("href", "")))
        if parsed.scheme in {"http", "https"}:
            link["target"] = "_blank"
            link["rel"] = "noopener noreferrer"
    path.write_text(str(soup), encoding="utf-8")


def _replace_attr(soup: BeautifulSoup, selector: str, attr: str, old: str, new: str) -> None:
    for node in soup.select(selector):
        value = node.get(attr)
        if isinstance(value, str) and value.startswith(old):
            node[attr] = new + value[len(old):]


def _rewrite_issue_page(path: Path, issue: str, *, latest: bool) -> tuple[str, ...]:
    soup = BeautifulSoup(path.read_text(encoding="utf-8"), "html.parser")
    slugs: list[str] = []
    for link in soup.select('a[href^="articles/"]'):
        href = str(link.get("href", ""))
        slug = Path(href.split("?", 1)[0].split("#", 1)[0]).stem
        if slug and slug not in slugs:
            slugs.append(slug)
        if latest:
            link["href"] = f"articles/{slug}/"
        elif issue != "001":
            link["href"] = f"../../articles/{slug}/"
    home = "index.html" if latest else "index.html"
    _replace_attr(soup, 'a[href^="newsletter.html"]', "href", "newsletter.html", home)
    search = "search/" if latest else "../../search/"
    _replace_attr(soup, 'a[href^="search.html"]', "href", "search.html", search.rstrip("/"))
    for form in soup.select('form[action="search.html"]'):
        form["action"] = search
    pagefind = "./pagefind/pagefind.js" if latest else "../../pagefind/pagefind.js"
    for node in soup.select("[data-pagefind-url]"):
        node["data-pagefind-url"] = pagefind
    if not latest:
        for link in soup.select("a[href]"):
            href = str(link["href"])
            for page in PUBLIC_PAGES:
                if href.startswith(page):
                    link["href"] = "../../" + href
    _write_soup(path, soup)
    return tuple(slugs)


def _rewrite_scoped_html(path: Path, issue: str, depth: int) -> None:
    soup = BeautifulSoup(path.read_text(encoding="utf-8"), "html.parser")
    prefix = "../" * depth
    _replace_attr(soup, 'a[href^="newsletter.html"]', "href", "newsletter.html", "index.html")
    for form in soup.select('form[action$="search.html"]'):
        form["action"] = prefix + "search/"
    for link in soup.select('a[href*="search.html"]'):
        value = str(link.get("href", ""))
        query = value.split("?", 1)[1] if "?" in value else ""
        link["href"] = prefix + "search/" + (f"?{query}" if query else "")
    for link in soup.select("a[href]"):
        value = str(link["href"])
        for page in PUBLIC_PAGES:
            if value.startswith("../" + page):
                link["href"] = prefix + value[3:]
            elif value.startswith(page):
                link["href"] = prefix + value
    for node in soup.select("[data-pagefind-url]"):
        node["data-pagefind-url"] = prefix + "pagefind/pagefind.js"
    _write_soup(path, soup)


def _rewrite_global_article(path: Path, issue: str, slugs: set[str]) -> None:
    soup = BeautifulSoup(path.read_text(encoding="utf-8"), "html.parser")
    for tag, attr in (("img", "src"), ("script", "src"), ("link", "href")):
        _replace_attr(soup, f'{tag}[{attr}^="../assets/"]', attr, "../assets/", f"../../issues/{issue}/assets/")
        _replace_attr(soup, f'{tag}[{attr}^="../media/"]', attr, "../media/", f"../../issues/{issue}/media/")
    for node in soup.select("[style]"):
        node["style"] = str(node["style"]).replace("../assets/", f"../../issues/{issue}/assets/")
    for link in soup.select("a[href]"):
        href = str(link["href"])
        bare, marker, suffix = href.partition("?")
        stem = Path(bare).stem
        if "/" not in bare and stem in slugs and bare.endswith(".html"):
            link["href"] = f"../{stem}/" + (f"?{suffix}" if marker else "")
        elif bare == "../newsletter.html":
            link["href"] = f"../../issues/{issue}/"
        elif bare == "../search.html":
            link["href"] = "../../search/" + (f"?{suffix}" if marker else "")
        else:
            for page in PUBLIC_PAGES:
                if href.startswith("../" + page):
                    link["href"] = "../../" + href[3:]
    for form in soup.select('form[action="../search.html"]'):
        form["action"] = "../../search/"
    for node in soup.select("[data-pagefind-url]"):
        node["data-pagefind-url"] = "../../pagefind/pagefind.js"
    _write_soup(path, soup)


def _archive_html(issues: tuple[str, ...]) -> str:
    rows = "".join(
        f'<li><a href="../issues/{issue}/">Issue {issue}</a></li>' for issue in reversed(issues)
    )
    return (
        '<!doctype html><html lang="en"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        '<title>Archive · K-Signal</title><style>body{font:18px/1.6 Arial,sans-serif;max-width:760px;margin:48px auto;padding:0 20px}a{color:#9b1c1c}li{margin:16px 0}</style>'
        '</head><body><main data-pagefind-body><a class="article-back" '
        'href="../">← K-Signal home</a><header><p class="policy-kicker">K-Signal</p>'
        f'<h1>Archive</h1></header><ol class="archive-list">{rows}</ol></main>'
        '<script src="../assets/ksignal.js" defer></script></body></html>'
    )


def assemble_site(
    issues: tuple[str, ...] = ("001", "002"),
    *,
    issues_root: str | Path = "outputs/issues",
    site_dir: str | Path = "outputs/site",
    run_pagefind: bool = True,
) -> SiteBuild:
    if not issues:
        raise ValueError("At least one issue is required")
    source_root = Path(issues_root).resolve()
    destination = Path(site_dir)
    latest = issues[-1]
    for issue in issues:
        source = source_root / issue
        if not (source / "newsletter.html").is_file():
            raise FileNotFoundError(f"Issue {issue} is missing newsletter.html")

    with tempfile.TemporaryDirectory(prefix="ksignal-site-") as temp_name:
        staged = Path(temp_name) / "site"
        staged.mkdir()
        latest_dir = source_root / latest
        shutil.copy2(latest_dir / "newsletter.html", staged / "index.html")
        latest_slugs = _rewrite_issue_page(staged / "index.html", latest, latest=True)
        for name in PUBLIC_PAGES:
            shutil.copy2(latest_dir / name, staged / name)
        if (latest_dir / "search.html").exists():
            shutil.copy2(latest_dir / "search.html", staged / "search.html")
        for dirname in PUBLIC_DIRS:
            shutil.copytree(latest_dir / dirname, staged / dirname)

        for issue in issues:
            source = source_root / issue
            scoped = staged / "issues" / issue
            scoped.mkdir(parents=True)
            shutil.copy2(source / "newsletter.html", scoped / "index.html")
            _rewrite_issue_page(scoped / "index.html", issue, latest=False)
            for dirname in PUBLIC_DIRS:
                shutil.copytree(source / dirname, scoped / dirname)
            if issue == "001":
                shutil.copytree(source / "articles", scoped / "articles")
                for article in (scoped / "articles").glob("*.html"):
                    html = article.read_text(encoding="utf-8").replace("../newsletter.html", "../index.html")
                    article.write_text(html, encoding="utf-8")
                    _rewrite_scoped_html(article, issue, 3)

        slug_set = set(latest_slugs)
        for slug in latest_slugs:
            source = latest_dir / "articles" / f"{slug}.html"
            if not source.exists():
                raise FileNotFoundError(f"Readable article source is missing: {source}")
            target = staged / "articles" / slug / "index.html"
            target.parent.mkdir(parents=True)
            shutil.copy2(source, target)
            _rewrite_global_article(target, latest, slug_set)

        archive = staged / "archive" / "index.html"
        archive.parent.mkdir()
        archive.write_text(_archive_html(issues), encoding="utf-8")

        search_dir = staged / "search"
        search_dir.mkdir(exist_ok=True)
        if (staged / "search.html").exists():
            shutil.move(staged / "search.html", search_dir / "index.html")
            soup = BeautifulSoup((search_dir / "index.html").read_text(encoding="utf-8"), "html.parser")
            _replace_attr(soup, 'a[href="newsletter.html"]', "href", "newsletter.html", "../")
            _replace_attr(soup, 'a[href^="assets/"]', "href", "assets/", "../assets/")
            _replace_attr(soup, 'img[src^="assets/"]', "src", "assets/", "../assets/")
            _replace_attr(soup, 'script[src^="assets/"]', "src", "assets/", "../assets/")
            for node in soup.select("[data-pagefind-url]"):
                node["data-pagefind-url"] = "../pagefind/pagefind.js"
            for form in soup.select('form[action="search.html"]'):
                form["action"] = "./"
            for node in soup.select("[style]"):
                node["style"] = str(node["style"]).replace("url('assets/", "url('../assets/")
            for script in soup.select('script[type="module"]'):
                script.string = (script.string or "").replace("'./pagefind/pagefind.js'", "'../pagefind/pagefind.js'")
            for link in soup.select('a[href^="search.html"]'):
                value = str(link["href"])
                link["href"] = "./" + ("?" + value.split("?", 1)[1] if "?" in value else "")
            for link in soup.select("a[href]"):
                value = str(link["href"])
                for page in PUBLIC_PAGES:
                    if value.startswith(page):
                        link["href"] = "../" + value
            _write_soup(search_dir / "index.html", soup)

        for name in PUBLIC_PAGES:
            _rewrite_scoped_html(staged / name, latest, 0)
        (staged / "_headers").write_text(NETLIFY_HEADERS, encoding="utf-8")

        pagefind_count = 0
        if run_pagefind:
            executable = Path("node_modules/.bin/pagefind.cmd")
            if not executable.exists():
                raise FileNotFoundError("Pagefind is not installed. Run npm install first.")
            result = subprocess.run(
                [str(executable.resolve()), "--site", str(staged.resolve()), "--output-subdir", "pagefind", "--force-language", "ko"],
                check=True, capture_output=True, text=True,
            )
            pagefind_count = result.stdout.count("Indexed")

        errors = validate_host_package(staged)
        if errors:
            raise ValueError("Persistent site validation failed:\n- " + "\n- ".join(errors))
        if destination.exists():
            _remove_tree(destination)
        shutil.copytree(staged, destination)

    return SiteBuild(
        site_dir=destination,
        issue_routes=tuple(f"/issues/{issue}/" for issue in issues),
        article_routes=tuple(f"/articles/{slug}/" for slug in latest_slugs),
        pagefind_entry_count=pagefind_count,
    )
