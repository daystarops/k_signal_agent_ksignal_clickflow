from .base import ProviderFailure, ProviderResult
from ..models import ProviderStatus
class PlaywrightProvider:
    provider_id="playwright"
    def capture(self,url):
        try:
            from ksignal.collectors.browser import render_page
            return ProviderResult(ProviderStatus.UP,[render_page(url,"outputs/source_engine/screenshots")])
        except Exception as exc:
            mode="LOGIN_REQUIRED" if "login" in str(exc).lower() else "TIMEOUT" if "timeout" in str(exc).lower() else "PROVIDER_FAILED"
            raise ProviderFailure(mode,ProviderStatus.DEGRADED if mode=="TIMEOUT" else ProviderStatus.DOWN) from exc

