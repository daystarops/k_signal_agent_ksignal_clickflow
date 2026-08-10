"""Deterministic, explainable article discovery for K-Signal."""
from __future__ import annotations
from datetime import datetime, timezone
import unicodedata
from typing import Any, Iterable

DEFAULT_ALIASES = {"k\ub9ac\uadf8":"k league","\ube4c\ub9ac":"billlie","\ub9b0\uac00\ub4dc":"lingard","\ud32c\ub364":"fandom","\uc2a4\ud3ec\uce20":"sports","fc\uc11c\uc6b8":"fc seoul"}

def _plain(value: Any) -> str:
    return " ".join(unicodedata.normalize("NFKC", str(value or "")).casefold().split())

def normalize(value: Any, aliases: dict[str,str] | None=None) -> str:
    mapping = DEFAULT_ALIASES if aliases is None else aliases
    return {_plain(k):_plain(v) for k,v in mapping.items()}.get(_plain(value), _plain(value))

def normalized_ids(values: Iterable[Any] | None, aliases=None) -> list[str]:
    return sorted({item for value in (values or []) if (item:=normalize(value, aliases))})

def enrich_card(card: dict[str,Any], editorial_order: int|None=None, aliases=None) -> dict[str,Any]:
    result=dict(card)
    if editorial_order is not None: result.setdefault("editorial_order",editorial_order)
    result.setdefault("status","published"); result.setdefault("lane",result.get("lane_label","").split(" / ")[0]); result.setdefault("lane_label",result.get("lane","")); result.setdefault("lane_slug",normalize(result.get("lane","")).replace(" ","-")); result.setdefault("public_summary",result.get("dek","")); result.setdefault("dek",result.get("public_summary","")); result.setdefault("thumbnail",result.get("hero_image",""))
    result["normalized_topic_ids"]=normalized_ids(result.get("topic_tags"),aliases); result["normalized_entity_ids"]=normalized_ids(result.get("entity_tags"),aliases); result["normalized_keyword_ids"]=normalized_ids(result.get("search_keywords"),aliases); result["source_platform_id"]=normalize(result.get("source_platform"),aliases); result["source_type_id"]=normalize(result.get("source_type"),aliases)
    return result

def is_eligible(card: dict[str,Any], current_card_id: str) -> bool:
    return card.get("card_id") != current_card_id and normalize(card.get("status")) == "published" and bool(str(card.get("article_path") or "").strip())

def score_candidate(current: dict[str,Any], candidate: dict[str,Any], aliases=None) -> dict[str,Any]:
    current,candidate=enrich_card(current,aliases=aliases),enrich_card(candidate,aliases=aliases); score=0; reasons=[]
    def add(points,reason):
        nonlocal score
        score+=points; reasons.append(f"{reason} +{points}")
    same_lane=normalize(current.get("lane_slug") or current.get("lane"),aliases)==normalize(candidate.get("lane_slug") or candidate.get("lane"),aliases)
    if same_lane:add(25,"same lane")
    for item in sorted(set(current["normalized_topic_ids"])&set(candidate["normalized_topic_ids"])):add(12,f"shared topic {item}")
    for item in sorted(set(current["normalized_entity_ids"])&set(candidate["normalized_entity_ids"])):add(18,f"shared entity {item}")
    if current["source_platform_id"] and current["source_platform_id"]==candidate["source_platform_id"]:add(6,"shared source platform")
    if current["source_type_id"] and current["source_type_id"]==candidate["source_type_id"]:add(4,"shared source type")
    if str(current.get("issue_id"))==str(candidate.get("issue_id")):add(3,"same issue")
    for item in sorted(set(current["normalized_keyword_ids"])&set(candidate["normalized_keyword_ids"])):add(5,f"shared keyword {item}")
    return {"current_card":current.get("card_id"),"candidate_card":candidate.get("card_id"),"score":score,"reasons":reasons,"same_lane":same_lane}

def _date_rank(value):
    try:return datetime.fromisoformat(str(value).replace("Z","+00:00")).replace(tzinfo=timezone.utc).timestamp()
    except (TypeError,ValueError):return float("-inf")

def related_signals(current,cards,limit=2,aliases=None,overrides=None):
    current_id=str(current.get("card_id")); rules=(overrides or {}).get(current_id,{}); excluded=set(rules.get("pinned_exclude",[])); pinned=list(rules.get("pinned_include",[])); scored=[]
    for position,card in enumerate(cards):
        if not is_eligible(card,current_id):continue
        detail=score_candidate(current,card,aliases); detail["editorial_override"]=card.get("card_id") in pinned; detail["excluded_by_override"]=card.get("card_id") in excluded; detail["tie_break"]={"published_at":card.get("published_at"),"same_lane":detail["same_lane"],"editorial_override":detail["editorial_override"]}; scored.append((card,detail,position))
    allowed=[row for row in scored if row[0].get("card_id") not in excluded]; allowed.sort(key=lambda row:(-row[1]["score"],-_date_rank(row[0].get("published_at")),-int(row[1]["same_lane"]),-int(row[1]["editorial_override"]),row[2])); pinned_rows=sorted((row for row in allowed if row[0].get("card_id") in pinned),key=lambda row:pinned.index(row[0].get("card_id"))); ordered=pinned_rows+[row for row in allowed if row not in pinned_rows]
    public=[]
    for card,detail,_ in ordered[:limit]:
        item={key:card.get(key) for key in ("card_id","article_path","lane","lane_label","issue_id","headline","dek","public_summary","hero_image","thumbnail")}; item["score"]=detail["score"]; public.append(item)
    return public,[row[1] for row in scored]

def more_from_issue(current,cards):
    eligible=[c for c in cards if is_eligible(c,str(current.get("card_id"))) and str(c.get("issue_id"))==str(current.get("issue_id"))]; eligible.sort(key=lambda c:(int(c.get("editorial_order",10**9)),str(c.get("card_id",""))))
    return [{key:c.get(key) for key in ("card_id","article_path","editorial_order","lane","lane_label","issue_id","headline","hero_image","thumbnail")} for c in eligible]
