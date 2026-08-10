from __future__ import annotations
import json
from pathlib import Path
LANES={
"beauty":{"ko":["한국 뷰티 신제품 반응","올리브영 화제 제품"],"official":["브랜드 공식 계정","식약처"],"western":["K-beauty trend review"],"hashtags":["kbeauty","한국화장품"],"profiles":["oliveyoung_official"],"locations":["Seoul","Seongsu"]},
"food":{"ko":["한국 음식 커뮤니티 화제","편의점 신제품 반응"],"official":["식품 브랜드 공식 계정"],"western":["Korean food trend"],"hashtags":["kfood","먹스타그램"],"profiles":[],"locations":["Seoul"]},
"society":{"ko":["한국 온라인 커뮤니티 사회 이슈"],"official":["정부 공식 발표","통계청"],"western":["South Korea social trend"],"hashtags":["한국사회"],"profiles":[],"locations":["Seoul"]},
"fandom":{"ko":["한국 팬덤 커뮤니티 화제","아이돌 팬 반응"],"official":["아티스트 공식 계정","소속사 공지"],"western":["K-pop fandom discussion"],"hashtags":["kpop","케이팝"],"profiles":[],"locations":[]},
"sports":{"ko":["K리그 커뮤니티 화제","한국 스포츠 팬 반응"],"official":["kleague","대한축구협회"],"western":["K League global fans"],"hashtags":["kleague","K리그"],"profiles":["kleague"],"locations":["Seoul World Cup Stadium"]}}
def generate_issue_002(output_root="outputs"):
    root=Path(output_root)/"issues"/"002"/"research"; root.mkdir(parents=True,exist_ok=True); source=[]; instagram=[]
    for lane,v in LANES.items():
        source.append({"lane":lane,"seed_types":["keyword_query","official_site","western_search_query"],"korean_native_seed_queries":v["ko"],"official_context_targets":v["official"],"western_global_mirror_queries":v["western"],"creative_reference_capture_targets":["public page screenshot","official media"],"temporal_tracking_plan":"24h baseline; 72h recapture; 7d decay check","operational_gaps":[]})
        instagram.append({"lane":lane,"hashtags":v["hashtags"],"profiles":v["profiles"],"locations":v["locations"],"provider_chain":["apify","browser","manual_url_queue"]})
    (root/"source_seed_queue.json").write_text(json.dumps(source,ensure_ascii=False,indent=2),encoding="utf-8"); (root/"instagram_seed_queue.json").write_text(json.dumps(instagram,ensure_ascii=False,indent=2),encoding="utf-8"); (root.parent/"issue_intelligence_plan.md").write_text("# Issue 002 Intelligence Plan\n\n"+"\n".join(f"## {x.title()}\nSeed → discover → capture → correlate → score → brief → render.\n" for x in LANES),encoding="utf-8"); return source,instagram

