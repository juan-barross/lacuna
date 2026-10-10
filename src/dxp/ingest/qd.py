"""Cliente da API do Querido Diário (https://api.queridodiario.org.br)."""

import logging
import time
from collections.abc import Callable, Iterator, Sequence
from datetime import date, datetime, timedelta
from pathlib import PurePosixPath
from urllib.parse import urlparse

import httpx
from pydantic import BaseModel, Field

log = logging.getLogger(__name__)

# A URL antiga (queridodiario.ok.org.br/api) só redireciona para esta.
BASE_URL = "https://api.queridodiario.org.br"
# A API responde 403 ao User-Agent padrão de algumas bibliotecas.
USER_AGENT = "diario-x-pncp/0.1"
# total_gazettes satura em 10.000 e offset >= 10.000 devolve 500.
RESULT_CAP = 10_000
PAGE_SIZE = 100
RETRY_STATUS = {429, 500, 502, 503, 504}


class QDError(RuntimeError):
    pass


class Gazette(BaseModel):
    """Um diário oficial, como a rota /gazettes devolve."""

    territory_id: str
    territory_name: str
    state_code: str
    date: date
    scraped_at: datetime
    url: str
    txt_url: str | None = None
    edition: str | None = None
    is_extra_edition: bool | None = None
    excerpts: list[str] = Field(default_factory=list)

    @property
    def gazette_id(self) -> str:
        """Identificador estável: município, data e o hash que o QD usa no nome do arquivo."""
        file_hash = PurePosixPath(urlparse(self.url).path).stem
        return f"{self.territory_id}_{self.date.isoformat()}_{file_hash}"


def month_windows(since: date, until: date) -> list[tuple[date, date]]:
    """Divide [since, until] em janelas de um mês do calendário, sem sobreposição."""
    windows = []
    start = since
    while start <= until:
        next_month = (start.replace(day=1) + timedelta(days=32)).replace(day=1)
        end = min(next_month - timedelta(days=1), until)
        windows.append((start, end))
        start = end + timedelta(days=1)
    return windows


class QDClient:
    """Acesso à API do QD com retentativa e paginação que contorna o teto de 10.000."""

    def __init__(
        self,
        http: httpx.Client | None = None,
        *,
        page_size: int = PAGE_SIZE,
        max_retries: int = 3,
        backoff: float = 2.0,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self.http = http or httpx.Client(
            base_url=BASE_URL,
            headers={"User-Agent": USER_AGENT},
            timeout=60,
            follow_redirects=True,
        )
        self.page_size = page_size
        self.max_retries = max_retries
        self.backoff = backoff
        self._sleep = sleep

    def __enter__(self) -> "QDClient":
        return self

    def __exit__(self, *exc: object) -> None:
        self.http.close()

    def _get(self, url: str, params: dict | list | None = None) -> httpx.Response:
        for attempt in range(self.max_retries + 1):
            try:
                resp = self.http.get(url, params=params)
            except httpx.TransportError as e:
                if attempt == self.max_retries:
                    raise QDError(f"falha de rede em {url}: {e}") from e
                log.warning("erro de rede em %s (%s), tentativa %d", url, e, attempt + 1)
            else:
                if resp.status_code not in RETRY_STATUS:
                    resp.raise_for_status()
                    return resp
                if attempt == self.max_retries:
                    raise QDError(
                        f"{url} respondeu {resp.status_code} após {attempt + 1} tentativas"
                    )
                log.warning("%s respondeu %d, tentativa %d", url, resp.status_code, attempt + 1)
            self._sleep(self.backoff * 2**attempt)
        raise AssertionError("inalcançável")

    def cities(self, level: int = 3) -> list[dict]:
        return self._get("/cities", params={"levels": level}).json()["cities"]

    def search(
        self,
        territory_ids: Sequence[str],
        since: date,
        until: date,
        *,
        offset: int = 0,
        size: int | None = None,
        querystring: str = "",
    ) -> tuple[int, list[Gazette]]:
        """Uma página de /gazettes. Devolve (total_gazettes, diários da página)."""
        params = [("territory_ids", t) for t in territory_ids] + [
            ("published_since", since.isoformat()),
            ("published_until", until.isoformat()),
            ("size", size if size is not None else self.page_size),
            ("offset", offset),
            ("sort_by", "ascending_date"),
        ]
        if querystring:
            params.append(("querystring", querystring))
        data = self._get("/gazettes", params=params).json()
        return data["total_gazettes"], [Gazette.model_validate(g) for g in data["gazettes"]]

    def iter_gazettes(
        self, territory_ids: Sequence[str], since: date, until: date
    ) -> Iterator[Gazette]:
        """Todos os diários do período, uma janela mensal por vez, sem repetição."""
        seen: set[str] = set()
        for start, end in month_windows(since, until):
            for g in self._iter_window(territory_ids, start, end):
                if g.gazette_id not in seen:
                    seen.add(g.gazette_id)
                    yield g

    def _iter_window(
        self, territory_ids: Sequence[str], since: date, until: date
    ) -> Iterator[Gazette]:
        total, page = self.search(territory_ids, since, until)
        if total >= RESULT_CAP:
            if since == until:
                raise QDError(f"{since}: mais de {RESULT_CAP} diários num único dia")
            mid = since + (until - since) // 2
            yield from self._iter_window(territory_ids, since, mid)
            yield from self._iter_window(territory_ids, mid + timedelta(days=1), until)
            return

        received = 0
        while page:
            yield from page
            received += len(page)
            if received >= total:
                break
            _, page = self.search(territory_ids, since, until, offset=received)
        if received < total:
            log.warning(
                "%s a %s: API informou %d diários, vieram %d", since, until, total, received
            )

    def fetch_text(self, gazette: Gazette) -> str:
        if not gazette.txt_url:
            raise QDError(f"{gazette.gazette_id} não tem txt_url")
        return self._get(gazette.txt_url).text
