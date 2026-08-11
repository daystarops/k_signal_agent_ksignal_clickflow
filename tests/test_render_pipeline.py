from pathlib import Path

from PIL import Image

from ksignal.render import CreativeRenderer


def test_html_to_png_fallback_reports_degradation(tmp_path,monkeypatch):
    from playwright import sync_api
    from ksignal.render.html_to_png import html_to_png

    def fail_playwright():
        raise RuntimeError("forced Playwright failure")

    monkeypatch.setattr(sync_api,"sync_playwright",fail_playwright)
    png,render_succeeded=html_to_png(tmp_path/"input.html",tmp_path/"fallback.png")

    assert png.exists()
    assert render_succeeded is False
    with Image.open(png) as image:
        assert image.size==(1080,1350)
        assert image.convert("RGB").getpixel((5,5))==(12,18,28)


def test_render_reports_degraded_when_fallback_exists(tmp_path,monkeypatch):
    from ksignal.render import export

    def degraded_render(html_path,png_path,width=1080,height=1350):
        png_path=Path(png_path)
        Image.new("RGB",(width,height),(12,18,28)).save(png_path)
        return png_path,False

    monkeypatch.setattr(export,"html_to_png",degraded_render)
    m=CreativeRenderer(tmp_path).render("2","c",{"working_headline":"Signal"}); assert len(m.assets)==7; assert (tmp_path/"issues/2/creative/c/asset_manifest.json").exists(); assert all(__import__("pathlib").Path(a.output_path).exists() for a in m.assets)
    assert all(a.status=="degraded" for a in m.assets)
