import time
import httpx
from bs4 import BeautifulSoup
from urllib.robotparser import RobotFileParser
from .base import ProviderFailure, ProviderResult
from ..models import ProviderStatus

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
            response.raise_for_status(); text=BeautifulSoup(response.text,"lxml").get_text(" ",strip=True)
            return ProviderResult(ProviderStatus.UP,[{"url":str(response.url),"html":response.text,"text":text}],elapsed_ms=int((time.perf_counter()-start)*1000))
        except ProviderFailure: raise
        except httpx.TimeoutException as exc: raise ProviderFailure("TIMEOUT",ProviderStatus.DEGRADED) from exc
        except Exception as exc: raise ProviderFailure("PROVIDER_FAILED") from exc

