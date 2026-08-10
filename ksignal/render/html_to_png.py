from pathlib import Path
from PIL import Image,ImageDraw
def html_to_png(html_path,png_path,width=1080,height=1350):
    png_path=Path(png_path); png_path.parent.mkdir(parents=True,exist_ok=True)
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            browser=p.chromium.launch(); page=browser.new_page(viewport={"width":width,"height":height}); page.goto(Path(html_path).resolve().as_uri()); page.screenshot(path=str(png_path),full_page=False); browser.close()
    except Exception:
        image=Image.new("RGB",(width,height),(12,18,28)); draw=ImageDraw.Draw(image); draw.text((64,64),"K-SIGNAL\nRENDER DEGRADED",fill=(240,240,240)); image.save(png_path)
    return png_path

