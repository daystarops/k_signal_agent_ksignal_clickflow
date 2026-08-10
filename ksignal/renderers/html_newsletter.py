from __future__ import annotations

from html import escape
from pathlib import Path
from ksignal.schema import SignalCard
from ksignal.utils.files import ensure_dir


def _rel(path: str) -> str:
    return path.replace("outputs/", "") if path.startswith("outputs/") else path


def _badge(cat: str) -> str:
    return {
        "government": "Government",
        "idols": "Idols",
        "sports": "Sports",
        "local_phenomenon": "Local Phenomenon",
    }.get(cat, cat.replace("_", " ").title())


def render_html(cards: list[SignalCard], out_path: str | Path = "outputs/newsletter.html", title: str = "K Signal") -> str:
    sections = []
    for c in cards:
        visual = ""
        img = (c.image_paths or c.screenshot_paths or [""])[0]
        if img:
            visual = f'<img class="w-full rounded-2xl border border-zinc-200 object-cover max-h-[480px]" src="{escape(_rel(img))}" alt="visual" />'
        audit = ""
        if c.translation_audit:
            q = c.translation_audit.translation_quality
            score = c.translation_audit.quality_score
            issues = "; ".join(c.translation_audit.issues[:3])
            audit = f'<div class="mt-3 text-xs text-zinc-500">Translation guardrail: <b>{escape(q)}</b> / {score}. {escape(issues)}</div>'
        url = f'<a class="text-xs underline text-zinc-500" href="{escape(c.url)}">source</a>' if c.url else ""
        sections.append(f'''
        <article class="rounded-3xl border border-zinc-200 bg-white p-5 shadow-sm">
          <div class="mb-3 flex items-center justify-between gap-3">
            <span class="rounded-full bg-zinc-950 px-3 py-1 text-xs font-semibold text-white">{escape(_badge(c.category))}</span>
            {url}
          </div>
          {visual}
          <h2 class="mt-5 text-2xl font-bold tracking-tight">{escape(c.title_english or c.title_original)}</h2>
          <p class="mt-1 text-sm text-zinc-500">{escape(c.source)} · Confidence: {escape(c.confidence)}</p>
          <div class="mt-4 rounded-2xl bg-zinc-50 p-4 text-sm leading-7 text-zinc-700">
            <div class="font-semibold text-zinc-950">Raw Korean</div>
            <div class="mt-1 whitespace-pre-wrap">{escape(c.raw_korean_excerpt[:900])}</div>
          </div>
          <div class="mt-4 grid gap-4 md:grid-cols-2">
            <section><h3 class="font-bold">Literal translation</h3><p class="mt-1 leading-7 text-zinc-700">{escape(c.literal_translation)}</p></section>
            <section><h3 class="font-bold">Cultural read</h3><p class="mt-1 leading-7 text-zinc-700">{escape(c.cultural_read)}</p></section>
            <section><h3 class="font-bold">Business read</h3><p class="mt-1 leading-7 text-zinc-700">{escape(c.business_read)}</p></section>
            <section><h3 class="font-bold">Visual read</h3><p class="mt-1 leading-7 text-zinc-700">{escape(c.visual_read)}</p></section>
          </div>
          {audit}
        </article>
        ''')
    html = f'''<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>{escape(title)}</title>
  <script src="https://cdn.tailwindcss.com"></script>
  <style>
    body {{ font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", "Noto Sans KR", "Malgun Gothic", sans-serif; }}
  </style>
</head>
<body class="bg-zinc-100 text-zinc-950">
  <main class="mx-auto max-w-4xl px-4 py-8">
    <header class="mb-8 rounded-3xl bg-zinc-950 p-7 text-white">
      <p class="text-sm uppercase tracking-[0.35em] text-zinc-400">Korean-native signal board</p>
      <h1 class="mt-3 text-4xl font-black tracking-tight">{escape(title)}</h1>
      <p class="mt-3 max-w-2xl text-zinc-300">Government, idols, sports, and local phenomena translated with screenshot-aware context. Built for newsletter publishing first; app/dashboard later.</p>
    </header>
    <div class="grid gap-6">
      {''.join(sections)}
    </div>
  </main>
</body>
</html>'''
    p = Path(out_path)
    ensure_dir(p.parent)
    p.write_text(html, encoding="utf-8")
    return html
