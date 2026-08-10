from __future__ import annotations
import json
from datetime import datetime, timezone
from pathlib import Path
from .models import ProviderHealth, ProviderStatus

class ProviderHealthStore:
    def __init__(self,path="outputs/source_engine/provider_health.json"):
        self.path=Path(path); self.path.parent.mkdir(parents=True,exist_ok=True)
    def load(self):
        if not self.path.exists(): return {}
        return {x["provider_id"]:x for x in json.loads(self.path.read_text(encoding="utf-8"))}
    def update(self,provider_id,status,failure_mode=None,elapsed_ms=0):
        data=self.load(); now=datetime.now(timezone.utc).isoformat(); old=data.get(provider_id,{})
        status=ProviderStatus(status)
        data[provider_id]={"provider_id":provider_id,"status":status.value,"last_success":now if status==ProviderStatus.UP else old.get("last_success"),"last_failure":now if status!=ProviderStatus.UP else old.get("last_failure"),"failure_rate_24h":0 if status==ProviderStatus.UP else 1,"avg_response_time_ms":elapsed_ms or old.get("avg_response_time_ms",0),"failure_mode":failure_mode}
        self.path.write_text(json.dumps(list(data.values()),indent=2),encoding="utf-8"); return ProviderHealth.model_validate(data[provider_id])

