from __future__ import annotations
import json,time
from pathlib import Path
from .models import AccessStatus, ProviderEvent, ProviderStatus, SourceNode, SourceType
from .provider_health import ProviderHealthStore
from .providers.base import ProviderFailure

class SourceOrchestrator:
    def __init__(self,apify_provider=None,browser_provider=None,output_root="outputs"):
        from .providers.apify_instagram_provider import ApifyInstagramProvider
        from .providers.instagram_browser_provider import InstagramBrowserProvider
        self.output_root=Path(output_root); self.apify=apify_provider or ApifyInstagramProvider(output_root=output_root); self.browser=browser_provider or InstagramBrowserProvider(); self.health=ProviderHealthStore(self.output_root/"source_engine"/"provider_health.json")
    def _log_run(self,issue,provider,status,failure_mode=None,elapsed_ms=0,fallback=False):
        root=self.output_root/"issues"/str(issue)/"research"/"instagram"; root.mkdir(parents=True,exist_ok=True); path=root/"provider_runs.json"; rows=json.loads(path.read_text()) if path.exists() else []; row={"provider":provider,"status":status.value if hasattr(status,"value") else status,"failure_mode":failure_mode,"timestamp":__import__("datetime").datetime.now(__import__("datetime").timezone.utc).isoformat(),"fallback_used":fallback,"elapsed_ms":elapsed_ms}; rows.append(row); path.write_text(json.dumps(rows,indent=2),encoding="utf-8"); self.health.update(provider,ProviderStatus.UP if row["status"] in {"up","captured"} else ProviderStatus.DEGRADED if row["status"]=="degraded" else ProviderStatus.DOWN,failure_mode,elapsed_ms); return row
    def discover_instagram(self,seed,max_items=20):
        issue=seed.get("issue_id",seed.get("issue","unknown")); start=time.perf_counter()
        try:
            if seed.get("hashtag"): result=self.apify.discover_hashtag(seed["hashtag"],max_items)
            elif seed.get("handle"): result=self.apify.discover_profile(seed["handle"],max_items)
            else: result=self.apify.discover_url(seed["url"])
            self._log_run(issue,self.apify.provider_id,result.status,None,result.elapsed_ms)
            return [self.apify.normalize_to_source(item,seed) for item in result.items]
        except ProviderFailure as exc:
            self._log_run(issue,self.apify.provider_id,exc.status,exc.failure_mode,int((time.perf_counter()-start)*1000),True)
            return self._instagram_browser_fallback(seed)
    def _instagram_browser_fallback(self,seed):
        issue=seed.get("issue_id",seed.get("issue","unknown")); url=seed.get("url") or (f"https://www.instagram.com/explore/tags/{seed['hashtag'].lstrip('#')}/" if seed.get("hashtag") else f"https://www.instagram.com/{seed.get('handle','')}/")
        try:
            result=self.browser.capture(url); self._log_run(issue,self.browser.provider_id,result.status,None,result.elapsed_ms)
            return [SourceNode(issue_id=str(issue),candidate_id=seed.get("candidate_id","instagram"),platform="instagram",url=url,source_type=SourceType.SOCIAL,current_access_status=AccessStatus.DEGRADED,primary_provider=self.apify.provider_id,fallback_provider=self.browser.provider_id,summary=str(result.items[0])[:1000])]
        except ProviderFailure as exc:
            access=AccessStatus.DENIED if exc.failure_mode in {"LOGIN_REQUIRED","PRIVATE_ACCOUNT","ROBOTS_DENIED"} else AccessStatus.DEGRADED if exc.failure_mode=="TIMEOUT" else AccessStatus.ERROR
            self._log_run(issue,self.browser.provider_id,exc.status,exc.failure_mode,0,True)
            node=SourceNode(issue_id=str(issue),candidate_id=seed.get("candidate_id","instagram"),platform="instagram",url=url,source_type=SourceType.SOCIAL,current_access_status=access,failure_mode=exc.failure_mode,primary_provider=self.apify.provider_id,fallback_provider=self.browser.provider_id)
            if access!=AccessStatus.DENIED:
                q=self.output_root/"issues"/str(issue)/"research"/"instagram"/"manual_queue.json"; q.parent.mkdir(parents=True,exist_ok=True); rows=json.loads(q.read_text()) if q.exists() else []; rows.append({"url":url,"status":"pending","failure_mode":exc.failure_mode}); q.write_text(json.dumps(rows,indent=2),encoding="utf-8")
            return [node]

