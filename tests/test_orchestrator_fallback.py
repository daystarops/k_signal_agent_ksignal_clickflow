from ksignal.engine.orchestrator import SourceOrchestrator
from ksignal.engine.providers.base import ProviderFailure,ProviderResult
from ksignal.engine.models import ProviderStatus
class A:
    provider_id="apify" 
    def discover_hashtag(self,*a,**k): raise ProviderFailure("AUTH_MISSING")
class B:
    provider_id="browser"
    def capture(self,url): return ProviderResult(ProviderStatus.UP,[{"text":"partial"}])
def test_fallback(tmp_path):
    nodes=SourceOrchestrator(A(),B(),tmp_path).discover_instagram({"issue_id":"2","hashtag":"x"}); assert nodes[0].fallback_provider=="browser"; assert (tmp_path/"issues/2/research/instagram/provider_runs.json").exists()

