from __future__ import annotations

import base64
from pathlib import Path
from urllib.parse import urljoin, urlparse
import httpx
from .files import ensure_dir, slugify


def normalize_url(base_url: str, maybe_url: str | None) -> str | None:
    if not maybe_url:
        return None
    maybe_url = maybe_url.strip()
    if maybe_url.startswith("data:"):
        return None
    return urljoin(base_url, maybe_url)


def is_likely_image_url(url: str) -> bool:
    lower = url.lower().split("?")[0]
    return lower.endswith((".jpg", ".jpeg", ".png", ".webp", ".gif")) or "image" in lower or "thumb" in lower


def download_image(url: str, out_dir: str | Path, prefix: str = "img", timeout: float = 20.0) -> str | None:
    ensure_dir(out_dir)
    try:
        with httpx.Client(follow_redirects=True, timeout=timeout, headers={"User-Agent": "Mozilla/5.0"}) as client:
            r = client.get(url)
            r.raise_for_status()
            ctype = r.headers.get("content-type", "")
            if "image" not in ctype and not is_likely_image_url(url):
                return None
            ext = ".jpg"
            if "png" in ctype:
                ext = ".png"
            elif "webp" in ctype:
                ext = ".webp"
            elif "gif" in ctype:
                ext = ".gif"
            name = f"{slugify(prefix, 50)}-{abs(hash(url)) % 10_000_000}{ext}"
            path = Path(out_dir) / name
            path.write_bytes(r.content)
            return str(path)
    except Exception:
        return None


def image_file_to_data_url(path: str | Path) -> str:
    p = Path(path)
    ext = p.suffix.lower().replace('.', '') or 'png'
    if ext == 'jpg':
        ext = 'jpeg'
    data = base64.b64encode(p.read_bytes()).decode('utf-8')
    return f"data:image/{ext};base64,{data}"
