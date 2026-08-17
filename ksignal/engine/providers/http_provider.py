import time
import httpx
from urllib.robotparser import RobotFileParser
from .base import ProviderFailure, ProviderResult
from ..models import ProviderStatus
from ksignal.collectors.html_collector import extract_page_text, response_id

class HttpProvider:
    provider_id="http"
    def capture(self,url):
        start=time.perf_counter(); robots=RobotFileParser(); robots.set_url(url.rstrip("/")+"/robots.txt")
        try:
            robots.read()
            if not robots.can_fetch("KSignal/1.0",url): raise ProviderFailure("ROBOTS_DENIED")
            response=httpx.get(url,follow_redirects=True,timeout=20,headers={"User-Agent":"KSignal/1.0"})
            if response.status_code==404: raise ProviderFailure("HTTP_404")
            if response.status_code in {401,403}: raise ProviderFailure("LOGIN_REQUIRED")
            if response.status_code==429: raise ProviderFailure("RATE_LIMITED",ProviderStatus.DEGRADED)
            response.raise_for_status()
            page_url = str(response.url)
            title, text, _ = extract_page_text(response.text, page_url)
            if not title or not text:
                raise ProviderFailure("SOURCE_TEXT_INCOMPLETE")
            return ProviderResult(ProviderStatus.UP,[{
                "url": page_url, "html": response.text, "title": title, "text": text,
                "title_source_url": page_url, "snippet_source_url": page_url,
                "title_response_id": response_id(response.text),
                "snippet_response_id": response_id(response.text),
            }],elapsed_ms=int((time.perf_counter()-start)*1000))
        except ProviderFailure: raise
        except httpx.TimeoutException as exc: raise ProviderFailure("TIMEOUT",ProviderStatus.DEGRADED) from exc
        except Exception as exc: raise ProviderFailure("PROVIDER_FAILED") from exc
