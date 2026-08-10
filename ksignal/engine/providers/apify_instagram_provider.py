from __future__ import annotations
import json, os, time
from pathlib import Path
from urllib.parse import urlparse
from uuid import uuid4
from apify_client import ApifyClient
from .base import ProviderFailure, ProviderResult
from ..models import AccessStatus, CaptureVersion, ProviderStatus, SourceNode, SourceRole, SourceType

class ApifyInstagramProvider:
    provider_id="apify_instagram"; actor_id="apify/instagram-scraper"
    def __init__(self, token: str|None=None, output_root: str|Path="outputs"):
        self.token=token or os.getenv("APIFY_TOKEN"); self.output_root=Path(output_root)
        self.status=ProviderStatus.UP if self.token else ProviderStatus.DOWN
        self.failure_mode=None if self.token else "AUTH_MISSING"
    def health(self): return {"provider_id":self.provider_id,"status":self.status.value,"failure_mode":self.failure_mode}
    def _run(self, run_input):
        if not self.token: raise ProviderFailure("AUTH_MISSING")
        start=time.perf_counter()
        try:
            run=ApifyClient(self.token).actor(self.actor_id).call(run_input=run_input)
            items=list(ApifyClient(self.token).dataset(run["defaultDatasetId"]).iterate_items())
            return ProviderResult(ProviderStatus.UP,items,elapsed_ms=int((time.perf_counter()-start)*1000))
        except Exception as exc:
            mode="RATE_LIMITED" if "429" in str(exc) else "PROVIDER_FAILED"
            raise ProviderFailure(mode, ProviderStatus.DEGRADED if mode=="RATE_LIMITED" else ProviderStatus.DOWN) from exc
    def discover_hashtag(self, hashtag,max_items=20): return self._run({"hashtags":[hashtag.lstrip("#")],"resultsLimit":max_items})
    def discover_profile(self, handle,max_items=20): return self._run({"directUrls":[f"https://www.instagram.com/{handle.lstrip('@')}/"],"resultsLimit":max_items})
    def discover_url(self,url): return self._run({"directUrls":[url],"resultsLimit":1})
    def normalize_to_source(self, item, seed):
        issue=str(seed.get("issue_id",seed.get("issue","unknown"))); candidate=str(seed.get("candidate_id","instagram"))
        url=item.get("url") or item.get("shortCode") and f"https://www.instagram.com/p/{item['shortCode']}/" or seed.get("url","")
        caption=item.get("caption") or item.get("text") or ""
        hashtags=item.get("hashtags") or [w[1:] for w in caption.split() if w.startswith("#")]
        mentions=item.get("mentions") or [w[1:].strip(".,") for w in caption.split() if w.startswith("@")]
        metrics={"likesCount":item.get("likesCount"),"commentsCount":item.get("commentsCount"),"videoViewCount":item.get("videoViewCount")}
        raw_dir=self.output_root/"issues"/issue/"research"/"instagram"/"captures"; raw_dir.mkdir(parents=True,exist_ok=True)
        raw_path=raw_dir/f"{uuid4()}.json"; raw_path.write_text(json.dumps(item,ensure_ascii=False,default=str,indent=2),encoding="utf-8")
        roles=[SourceRole.INSTAGRAM_CONTEXT,SourceRole.VISUAL_REFERENCE]
        if hashtags: roles.append(SourceRole.HASHTAG_SIGNAL)
        cap=CaptureVersion(provider=self.provider_id,extracted_text=caption,visible_metrics=metrics,access_status=AccessStatus.CAPTURED,raw_provider_payload_path=str(raw_path))
        return SourceNode(issue_id=issue,candidate_id=candidate,platform="instagram",domain=urlparse(url).netloc,url=url,title=caption[:120] or None,source_roles=roles,source_type=SourceType.SOCIAL,current_access_status=AccessStatus.CAPTURED,last_captured_at=cap.captured_at,capture_versions=[cap],hashtags=list(hashtags),mentions=list(mentions),summary=caption,primary_provider=self.provider_id,raw_provider_payload_path=str(raw_path),provider_metadata={k:v for k,v in item.items() if k not in {"caption","text"}})

