import logging
from collections.abc import Iterator, Sequence
from datetime import date, datetime, timedelta
from pathlib import PurePosixPath
from urllib.parse import urlparse

import httpx
from pydantic import BaseModel, Field, field_validator

from dxp.fetch import Fetcher, FetchError, make_client

log = logging.getLogger(__name__)

BASE_URL = "https://api.queridodiario.org.br"
RESULT_CAP = 10_000
PAGE_SIZE = 100
S3_PREFIX = "s3://okbr-qd-migration//"
PUBLIC_FILES = "https://data.queridodiario.ok.org.br/"


def public_file_url(url: str | None) -> str | None:
    if url and url.startswith(S3_PREFIX):
        return PUBLIC_FILES + url.removeprefix(S3_PREFIX)
    return url


class Gazette(BaseModel):
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

    @field_validator("url", "txt_url")
    @classmethod
    def _public_url(cls, url: str | None) -> str | None:
        return public_file_url(url)

    @property
    def gazette_id(self) -> str:
        file_hash = PurePosixPath(urlparse(self.url).path).stem
        return f"{self.territory_id}_{self.date.isoformat()}_{file_hash}"


def month_windows(since: date, until: date) -> list[tuple[date, date]]:
    windows = []
    start = since
    while start <= until:
        next_month = (start.replace(day=1) + timedelta(days=32)).replace(day=1)
        end = min(next_month - timedelta(days=1), until)
        windows.append((start, end))
        start = end + timedelta(days=1)
    return windows


class QDClient(Fetcher):
    def __init__(self, http: httpx.Client | None = None, *, page_size: int = PAGE_SIZE, **kw):
        super().__init__(http or make_client(BASE_URL), **kw)
        self.page_size = page_size

    def cities(self, level: int = 3) -> list[dict]:
        return self.get("/cities", params={"levels": level}).json()["cities"]

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
        params = [("territory_ids", t) for t in territory_ids] + [
            ("published_since", since.isoformat()),
            ("published_until", until.isoformat()),
            ("size", self.page_size if size is None else size),
            ("offset", offset),
            ("sort_by", "ascending_date"),
        ]
        if querystring:
            params.append(("querystring", querystring))
        data = self.get("/gazettes", params=params).json()
        return data["total_gazettes"], [Gazette.model_validate(g) for g in data["gazettes"]]

    def iter_gazettes(
        self, territory_ids: Sequence[str], since: date, until: date
    ) -> Iterator[Gazette]:
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
                raise FetchError(f"{since}: mais de {RESULT_CAP} diários num único dia")
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
            raise FetchError(f"{gazette.gazette_id} não tem txt_url")
        return self.get(gazette.txt_url).text
