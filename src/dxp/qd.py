import logging
import re
from collections import Counter
from collections.abc import Iterator, Sequence
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta
from functools import partial
from pathlib import Path, PurePosixPath
from urllib.parse import urlparse

import httpx
import pyarrow as pa
import pyarrow.parquet as pq
from pydantic import BaseModel, Field, field_validator

from dxp.fetch import Fetcher, FetchError
from dxp.files import cached_json, write_atomic

log = logging.getLogger(__name__)

BASE_URL = "https://api.queridodiario.org.br"
RESULT_CAP = 10_000
PAGE_SIZE = 100
S3_PREFIX = "s3://okbr-qd-migration//"
PUBLIC_FILES = "https://data.queridodiario.ok.org.br/"
MIN_TEXT_CHARS = 1000
ONLY_URL = re.compile(r"^\s*https?://\S+\s*$")


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
        if url and url.startswith(S3_PREFIX):
            return PUBLIC_FILES + url.removeprefix(S3_PREFIX)
        return url

    @property
    def gazette_id(self) -> str:
        file_hash = PurePosixPath(urlparse(self.url).path).stem
        return f"{self.territory_id}_{self.date.isoformat()}_{file_hash}"


def month_windows(since: date, until: date) -> list[tuple[date, date]]:
    windows = []
    while since <= until:
        next_month = (since.replace(day=1) + timedelta(days=32)).replace(day=1)
        end = min(next_month - timedelta(days=1), until)
        windows.append((since, end))
        since = end + timedelta(days=1)
    return windows


def text_status(text: str) -> str:
    if not text.strip():
        return "vazio"
    if ONLY_URL.match(text):
        return "so_link"
    return "curto" if len(text.strip()) < MIN_TEXT_CHARS else "ok"


class QDClient(Fetcher):
    def __init__(self, http: httpx.Client | None = None, *, page_size: int = PAGE_SIZE, **kw):
        super().__init__(BASE_URL, http, **kw)
        self.page_size = page_size

    def cities(self, level: int = 3) -> list[dict]:
        return self.get("/cities", params={"levels": level}).json()["cities"]

    def search(
        self, territory_ids: Sequence[str], since: date, until: date, *, offset=0, size=None
    ) -> tuple[int, list[Gazette]]:
        params = [("territory_ids", t) for t in territory_ids] + [
            ("published_since", since.isoformat()),
            ("published_until", until.isoformat()),
            ("size", self.page_size if size is None else size),
            ("offset", offset),
            ("sort_by", "ascending_date"),
        ]
        data = self.get("/gazettes", params=params).json()
        return data["total_gazettes"], [Gazette.model_validate(g) for g in data["gazettes"]]

    def iter_gazettes(
        self, territory_ids: Sequence[str], since: date, until: date
    ) -> Iterator[Gazette]:
        seen = set()
        for start, end in month_windows(since, until):
            for g in self._window(territory_ids, start, end):
                if g.gazette_id not in seen:
                    seen.add(g.gazette_id)
                    yield g

    def _window(self, territory_ids: Sequence[str], since: date, until: date) -> Iterator[Gazette]:
        total, page = self.search(territory_ids, since, until)
        if total >= RESULT_CAP:
            if since == until:
                raise FetchError(f"{since}: mais de {RESULT_CAP} diários num único dia")
            mid = since + (until - since) // 2
            yield from self._window(territory_ids, since, mid)
            yield from self._window(territory_ids, mid + timedelta(days=1), until)
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

    def listing(self, territory_ids: Sequence[str], since: date, until: date) -> list[dict]:
        return [g.model_dump(mode="json") for g in self.iter_gazettes(territory_ids, since, until)]

    def fetch_text(self, gazette: Gazette) -> str:
        if not gazette.txt_url:
            raise FetchError(f"{gazette.gazette_id} não tem txt_url")
        return self.get(gazette.txt_url).text


def download(
    client: QDClient,
    territory_ids: Sequence[str],
    since: date,
    until: date,
    data_dir: Path,
    workers=4,
) -> Counter:
    raw = data_dir / "raw" / "qd"
    gazettes = [
        Gazette.model_validate(item)
        for start, end in month_windows(since, until)
        for item in cached_json(
            raw / "gazettes" / f"{start:%Y-%m}.json",
            partial(client.listing, territory_ids, start, end),
        )
    ]

    def text_path(g: Gazette) -> Path:
        return raw / "txt" / g.territory_id / f"{g.gazette_id}.txt"

    def fetch(g: Gazette) -> str | None:
        try:
            write_atomic(text_path(g), client.fetch_text(g))
        except (FetchError, httpx.HTTPError, OSError) as error:
            log.error("%s: %s", g.gazette_id, error)
            return str(error)
        return None

    missing = [g for g in gazettes if g.txt_url and not text_path(g).exists()]
    with ThreadPoolExecutor(workers) as pool:
        errors = {
            g.gazette_id: e for g, e in zip(missing, pool.map(fetch, missing), strict=True) if e
        }

    rows = []
    for g in gazettes:
        error = errors.get(g.gazette_id)
        text = text_path(g).read_text(encoding="utf-8") if g.txt_url and not error else ""
        status = "erro" if error else text_status(text) if g.txt_url else "sem_txt"
        meta = g.model_dump(exclude={"scraped_at", "state_code", "excerpts"})
        rows.append(
            {
                "gazette_id": g.gazette_id,
                **meta,
                "text": text,
                "text_status": status,
                "error": error,
            }
        )

    out = data_dir / "processed" / "qd_gazettes.parquet"
    out.parent.mkdir(parents=True, exist_ok=True)
    pq.write_table(pa.Table.from_pylist(rows), out)
    return Counter(r["text_status"] for r in rows)
