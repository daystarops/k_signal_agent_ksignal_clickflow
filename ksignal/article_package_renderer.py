"""Render validated ArticlePackage long-form content as an HTML fragment."""

from __future__ import annotations

import re
from html import escape
from urllib.parse import urlsplit

from .article_package import ArticlePackage, MediaRef


def _safe_link(url: str) -> str:
    """Return an escaped web URL, or an inert target for unsafe schemes."""
    if url and urlsplit(url).scheme.lower() in {"http", "https"}:
        return escape(url, quote=True)
    return "#"


def _media(media: MediaRef) -> str:
    details: list[str] = []
    if media.caption:
        details.append(f'<span class="media-caption">{escape(media.caption)}</span>')
    credit = escape(media.credit)
    if media.source_url:
        credit = f'<a href="{_safe_link(media.source_url)}">{credit or "Source"}</a>'
    if credit:
        details.append(f'<span class="media-credit">{credit}</span>')
    figcaption = f"<figcaption>{' · '.join(details)}</figcaption>" if details else ""
    return (
        f'<figure class="supporting-media"><img src="{escape(media.path, quote=True)}" '
        f'alt="{escape(media.caption, quote=True)}">{figcaption}</figure>'
    )


def _paragraphs(body: str) -> str:
    return "".join(
        f"<p>{escape(part).replace(chr(10), '<br>')}</p>"
        for part in re.split(r"\n\s*\n", body)
        if part
    )


def render_article_package(package: ArticlePackage) -> str:
    """Render only the depth content inserted into an existing legacy article."""
    sections: list[str] = []
    for index, section in enumerate(package.sections):
        media = "".join(_media(item) for item in section.supporting_media)
        sections.append(
            f'<section class="article-section" data-section-index="{index}">'
            f"<h2>{escape(section.heading)}</h2>"
            f"{_paragraphs(section.body)}{media}</section>"
        )

    sources = "".join(
        f'<li><a href="{_safe_link(source.url)}">{escape(source.label)}</a></li>'
        for source in package.sources
    )
    return (
        f'<div class="article-package-depth">{"".join(sections)}'
        f'<section class="article-sources"><h2>Sources used in this article</h2>'
        f"<ul>{sources}</ul></section></div>"
    )
