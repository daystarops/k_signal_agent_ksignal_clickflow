from .base import ProviderResult
from ..models import ProviderStatus
class SearchProvider:
    provider_id="search"
    def discover(self,query,max_items=20): return ProviderResult(ProviderStatus.DEGRADED,[],"PROVIDER_FAILED")

