import json
from pathlib import Path
from bs4 import BeautifulSoup

ROOT = Path("outputs/issues/001/host_package")

def test_public_json_has_no_private_fields_or_paths():
    banned = ("relevance_score_explanations", "moderation_data", "comments_read", "C:\\", "Users\\jgwrg", "OneDrive")
    for path in ROOT.rglob("*.json"):
        text = path.read_text(encoding="utf-8")
        assert not any(term in text for term in banned), path

def test_html_has_no_javascript_links_or_unsafe_blank_targets():
    for path in ROOT.rglob("*.html"):
        soup = BeautifulSoup(path.read_text(encoding="utf-8"), "html.parser")
        assert not soup.select('a[href^="javascript:"]'), path
        for link in soup.select('a[target="_blank"]'):
            assert {"noopener", "noreferrer"}.issubset(set(link.get("rel", []))), (path, link.get("href"))

def test_comment_forms_and_honeypots_are_controlled():
    for path in (ROOT / "articles").glob("card_*.html"):
        soup = BeautifulSoup(path.read_text(encoding="utf-8"), "html.parser")
        form = soup.select_one('form[name="ksignal-comment"]')
        assert form and form.select_one('textarea[name="comment"][required]')
        assert form.select_one('[data-netlify-honeypot="bot-field"]') is None
        assert form.get("data-netlify-honeypot") == "bot-field"
        assert form.select_one('.honeypot input[name="bot-field"]')

def test_discovery_public_markup_excludes_scores_and_current_card():
    for path in (ROOT / "articles").glob("card_*.html"):
        card_id = path.stem
        soup = BeautifulSoup(path.read_text(encoding="utf-8"), "html.parser")
        discovery = soup.select_one('.discovery')
        assert discovery and len(discovery.select('.related-signal-card')) == 2
        assert not discovery.select(f'[data-related-card-id="{card_id}"], [data-issue-card-id="{card_id}"]')
        assert "score" not in discovery.get_text(" ").lower()
