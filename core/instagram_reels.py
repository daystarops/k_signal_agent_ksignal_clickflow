from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
import os
from pathlib import Path

def find_ffmpeg(name: str = "ffmpeg"):
    configured = os.getenv("KSIGNAL_FFMPEG", "").strip()
    if configured:
        candidate = Path(configured)
        if name == "ffprobe":
            candidate = candidate.with_name("ffprobe.exe")
        if candidate.exists():
            return str(candidate)
    found = shutil.which(name)
    if found:
        return found
    root = Path.home() / "AppData/Local/Microsoft/WinGet/Packages"
    matches = sorted(root.glob(f"Gyan.FFmpeg*/ffmpeg-*_build/bin/{name}.exe"))
    return str(matches[-1]) if matches else None
def render_one(folder: Path):
    ffmpeg = find_ffmpeg("ffmpeg")
    output = folder / "reel_01.mp4"
    temp_output = Path(tempfile.gettempdir()) / f"ksignal_{folder.parent.name}_reel.mp4"
    if not ffmpeg:
        return {"success": False, "path": str(output), "error": "ffmpeg not found on PATH"}
    inputs = []
    for index in range(1, 5):
        inputs += ["-i", str(folder / f"frame_{index:02d}.png")]
    filters = []
    for index in range(4):
        zoom = "min(zoom+0.00035,1.04)" if index % 2 == 0 else "if(lte(zoom,1.0),1.04,max(1.0,zoom-0.00035))"
        filters.append(f"[{index}:v]zoompan=z='{zoom}':d=105:s=1080x1920:fps=30[v{index}]")
    graph = ";".join(filters) + ";[v0][v1][v2][v3]concat=n=4:v=1:a=0,format=yuv420p[outv]"
    cmd = [ffmpeg, "-y", *inputs, "-filter_complex", graph, "-map", "[outv]", "-c:v", "libx264",
           "-pix_fmt", "yuv420p", "-preset", "ultrafast", "-crf", "24", "-r", "30", "-movflags", "+faststart", str(temp_output)]
    result = subprocess.run(cmd, capture_output=True, text=True)
    success = result.returncode == 0 and temp_output.exists()
    if success:
        shutil.copy2(temp_output, output)
        temp_output.unlink(missing_ok=True)
    return {"success": success and output.exists(), "path": str(output),
            "error": result.stderr[-1200:] if result.returncode else ""}


def probe(path: str):
    ffprobe = find_ffmpeg("ffprobe")
    if not ffprobe or not Path(path).exists():
        return {}
    result = subprocess.run([ffprobe, "-v", "error", "-show_entries",
        "format=duration:stream=width,height,codec_name,pix_fmt", "-of", "json", path], capture_output=True, text=True)
    return json.loads(result.stdout) if result.returncode == 0 else {}


def render_reels(issue: str, output_root: str | Path = "outputs/issues"):
    root = Path(output_root) / issue / "distribution_pack" / "instagram"
    manifest_path = root / "creative_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8")) if manifest_path.exists() else {"candidates": []}
    folders = sorted(p for p in root.glob("card_*") if p.is_dir() and (p / "reels" / "frame_01.png").exists())
    results = []
    for card_root in folders:
        item = render_one(card_root / "reels")
        canonical = root / card_root.name[:7] / "reels" / "reel_01.mp4"
        if item["success"]:
            canonical.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(item["path"], canonical)
            item["path"] = str(canonical)
        data = probe(item["path"]) if item["success"] else {}
        stream = (data.get("streams") or [{}])[0]
        selected = [c for c in manifest["candidates"] if c["card_id"] == card_root.name[:7] and c.get("selected_for_ig")]
        results.append({"card": card_root.name, **item, "duration": float((data.get("format") or {}).get("duration", 0)),
                        "width": stream.get("width", 0), "height": stream.get("height", 0),
                        "codec": stream.get("codec_name", ""), "pix_fmt": stream.get("pix_fmt", ""), "creatives": selected})
    lines = ["# Reels Ready", "", f"- ffmpeg detected: **{'yes' if shutil.which('ffmpeg') else 'no'}**",
             "- Audio/music: none", "- External source video downloaded or embedded: no", ""]
    for item in results:
        unknown = any(c["card_id"] == item["card"][:7] and c.get("blocked_from_public_ig") and c["rights_status"] == "unknown_rights" for c in manifest["candidates"])
        lines += [f"## {item['card']}", "", f"- Reel: `{item['path']}`",
                  f"- Generation succeeded: **{'yes' if item['success'] else 'no'}**",
                  f"- Duration: {item['duration']:.2f}s", f"- Resolution: {item['width']}x{item['height']}",
                  f"- Codec/pixel format: {item['codec']} / {item['pix_fmt']}",
                  "- Creatives used: " + (", ".join(f"{c['title']} (`{c['rights_status']}`)" for c in item["creatives"]) or "K-Signal frames only"),
                  f"- Unknown-rights media blocked: **{'yes' if unknown else 'no candidates'}**", ""]
        if item["error"]:
            lines += [f"- Error: `{item['error']}`", ""]
    (root / "REELS_READY.md").write_text("\n".join(lines), encoding="utf-8")
    return results
