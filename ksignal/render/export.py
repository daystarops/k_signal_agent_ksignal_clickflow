from __future__ import annotations
import json
from pathlib import Path
from .models import AssetManifest,RenderAsset
from .templates import render_template
from .html_to_png import html_to_png
from .asset_manifest import write_manifest
from .edl import build_edl
from .remotion_plan import build_remotion_plan
MAP={"article_card.png":"article_card.html","quote_0.png":"quote_card.html","receipt.png":"receipt_card.html","source_graph_card.png":"source_graph_card.html","velocity_card.png":"velocity_card.html","instagram_signal_card.png":"instagram_signal_card.html","western_mirror_card.png":"western_mirror_card.html"}
class CreativeRenderer:
    def __init__(self,output_root="outputs"): self.output_root=Path(output_root)
    def render(self,issue_id,candidate_id,data):
        root=self.output_root/"issues"/str(issue_id)/"creative"/candidate_id; root.mkdir(parents=True,exist_ok=True); assets=[]
        for filename,template in MAP.items():
            html=root/(filename+".html"); html.write_text(render_template(template,data),encoding="utf-8"); png=html_to_png(html,root/filename); assets.append(RenderAsset(asset_id=filename[:-4],render_target=filename[:-4],template=template,html_path=str(html),output_path=str(png),status="captured" if png.exists() else "error"))
        manifest=AssetManifest(issue_id=str(issue_id),candidate_id=candidate_id,assets=assets); write_manifest(manifest,root/"asset_manifest.json"); (root/"edl.json").write_text(json.dumps(build_edl(assets),indent=2),encoding="utf-8"); (root/"remotion_scene_plan.json").write_text(json.dumps(build_remotion_plan(assets),indent=2),encoding="utf-8"); return manifest

