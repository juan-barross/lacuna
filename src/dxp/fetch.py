import logging
import time
from collections.abc import Callable
from dataclasses import dataclass

import httpx

log = logging.getLogger(__name__)

DEFAULT_TIMEOUT = 120.0
RATE_LIMIT_WAIT = 30.0
USER_AGENT = "lacuna/0.1 (+https://github.com/juan-barross/lacuna)"
RETRY_STATUS = {429, 500, 502, 503, 504}
RETRY_ERRORS = (httpx.TimeoutException, httpx.NetworkError, httpx.RemoteProtocolError)


class FetchError(RuntimeError):
    pass


@dataclass(frozen=True)
class RetryPolicy:
    max_retries: int = 3
    backoff: float = 2.0
    sleep: Callable[[float], None] = time.sleep

    def wait_after(self, attempt: int, resp: httpx.Response | None) -> float:
        if resp is not None and resp.status_code == httpx.codes.TOO_MANY_REQUESTS:
            return float(resp.headers.get("Retry-After", RATE_LIMIT_WAIT))
        return self.backoff * 2 ** (attempt - 1)


DEFAULT_RETRY = RetryPolicy()


def new_client(
    base_url: str = "", *, headers: dict[str, str] | None = None, timeout: float = DEFAULT_TIMEOUT
) -> httpx.Client:
    return httpx.Client(
        base_url=base_url,
        headers={"User-Agent": USER_AGENT, **(headers or {})},
        timeout=timeout,
        follow_redirects=True,
    )


class Fetcher:
    def __init__(self, http: httpx.Client, retry: RetryPolicy = DEFAULT_RETRY) -> None:
        self.http = http
        self.retry = retry

    def __enter__(self):
        return self

    def __exit__(self, *_: object) -> None:
        self.http.close()

    def get(self, url: str, params: dict | list | None = None) -> httpx.Response:
        return self.request("GET", url, params=params)

    def post(self, url: str, json: dict) -> httpx.Response:
        return self.request("POST", url, json=json)

    def request(
        self, method: str, url: str, *, params: dict | list | None = None, json: dict | None = None
    ) -> httpx.Response:
        attempt = 1
        while True:
            outcome = self._attempt(method, url, attempt, params, json)
            if isinstance(outcome, httpx.Response):
                return outcome
            self.retry.sleep(outcome)
            attempt += 1

    def _attempt(
        self, method: str, url: str, attempt: int, params: dict | list | None, json: dict | None
    ) -> httpx.Response | float:
        last = attempt > self.retry.max_retries
        try:
            resp = self.http.request(method, url, params=params, json=json)
        except httpx.TransportError as error:
            if last or not isinstance(error, RETRY_ERRORS):
                raise FetchError(f"falha de rede em {url}: {error}") from error
            log.warning("erro de rede em %s (%s), tentativa %d", url, error, attempt)
            return self.retry.wait_after(attempt, None)
        if resp.status_code not in RETRY_STATUS:
            return resp.raise_for_status()
        if last:
            raise FetchError(f"{url} respondeu {resp.status_code} após {attempt} tentativas")
        log.warning("%s respondeu %d, tentativa %d", url, resp.status_code, attempt)
        return self.retry.wait_after(attempt, resp)
