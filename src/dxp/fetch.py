import logging
import time
from collections.abc import Callable

import httpx

log = logging.getLogger(__name__)

USER_AGENT = "lacuna/0.1 (+https://github.com/juan-barross/lacuna)"
RETRY_STATUS = {429, 500, 502, 503, 504}
RETRY_ERRORS = (httpx.TimeoutException, httpx.NetworkError, httpx.RemoteProtocolError)


class FetchError(RuntimeError):
    pass


class Fetcher:
    def __init__(
        self,
        base_url: str,
        http: httpx.Client | None = None,
        *,
        max_retries: int = 3,
        backoff: float = 2.0,
        rate_limit_wait: float = 30.0,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self.http = http or httpx.Client(
            base_url=base_url,
            headers={"User-Agent": USER_AGENT},
            timeout=120,
            follow_redirects=True,
        )
        self.max_retries = max_retries
        self.backoff = backoff
        self.rate_limit_wait = rate_limit_wait
        self._sleep = sleep

    def __enter__(self):
        return self

    def __exit__(self, *exc: object) -> None:
        self.http.close()

    def _wait(self, attempt: int, resp: httpx.Response | None) -> float:
        if resp is not None and resp.status_code == httpx.codes.TOO_MANY_REQUESTS:
            return float(resp.headers.get("Retry-After", self.rate_limit_wait))
        return self.backoff * 2**attempt

    def get(self, url: str, params: dict | list | None = None) -> httpx.Response:
        for attempt in range(self.max_retries + 1):
            last, resp = attempt == self.max_retries, None
            try:
                resp = self.http.get(url, params=params)
            except httpx.TransportError as e:
                if last or not isinstance(e, RETRY_ERRORS):
                    raise FetchError(f"falha de rede em {url}: {e}") from e
                log.warning("erro de rede em %s (%s), tentativa %d", url, e, attempt + 1)
            else:
                if resp.status_code not in RETRY_STATUS:
                    return resp.raise_for_status()
                if last:
                    raise FetchError(
                        f"{url} respondeu {resp.status_code} após {attempt + 1} tentativas"
                    )
                log.warning("%s respondeu %d, tentativa %d", url, resp.status_code, attempt + 1)
            self._sleep(self._wait(attempt, resp))
        raise AssertionError("inalcançável")
