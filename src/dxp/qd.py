import logging
import re
from collections import Counter
from collections.abc import Iterator, Sequence
from concurrent.futures import ThreadPoolExecutor
from datetime import date
from functools import partial
from pathlib import Path, PurePosixPath
from typing import Self
from urllib.parse import urlparse

import httpx
from pydantic import BaseModel, field_validator, model_validator

from dxp.fetch import DEFAULT_RETRY, Fetcher, FetchError, RetryPolicy, new_client
from dxp.files import cached_json, path_inside, short_hash, write_atomic, write_parquet
from dxp.ids import ALPHANUMERIC_ID, TERRITORY_ID, checked_id
from dxp.period import Period

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
    date: date
    url: str
    txt_url: str | None = None

    @field_validator("territory_id")
    @classmethod
    def _valid_territory_id(cls, territory_id: str) -> str:
        return checked_id(TERRITORY_ID, territory_id, "territory_id")

    @field_validator("url", "txt_url")
    @classmethod
    def _public_url(cls, url: str | None) -> str | None:
        if url and url.startswith(S3_PREFIX):
            return PUBLIC_FILES + url.removeprefix(S3_PREFIX)
        return url

    @model_validator(mode="after")
    def _valid_file_hash(self) -> Self:
        checked_id(ALPHANUMERIC_ID, self.file_hash, "hash do arquivo do diário")
        return self

    @property
    def file_hash(self) -> str:
        return PurePosixPath(urlparse(self.url).path).stem

    @property
    def gazette_id(self) -> str:
        return f"{self.territory_id}_{self.date.isoformat()}_{self.file_hash}"


def text_status(text: str) -> str:
    if not text.strip():
        return "vazio"
    if ONLY_URL.match(text):
        return "so_link"
    return "curto" if len(text.strip()) < MIN_TEXT_CHARS else "ok"


class QDClient(Fetcher):
    def __init__(
        self,
        http: httpx.Client | None = None,
        *,
        page_size: int = PAGE_SIZE,
        retry: RetryPolicy = DEFAULT_RETRY,
    ) -> None:
        super().__init__(http or new_client(BASE_URL), retry)
        self.page_size = page_size

    def cities(self) -> list[dict]:
        return self.get("/cities", params={"levels": 3}).json()["cities"]

    def search(
        self, territory_ids: Sequence[str], period: Period, *, offset: int = 0, size: int | None = None
    ) -> tuple[int, list[Gazette]]:
        params = [("territory_ids", t) for t in territory_ids] + [
            ("published_since", period.since.isoformat()),
            ("published_until", period.until.isoformat()),
            ("size", self.page_size if size is None else size),
            ("offset", offset),
            ("sort_by", "ascending_date"),
        ]
        data = self.get("/gazettes", params=params).json()
        return data["total_gazettes"], [Gazette.model_validate(g) for g in data["gazettes"]]

    def iter_gazettes(self, territory_ids: Sequence[str], period: Period) -> Iterator[Gazette]:
        seen = set()
        for month in period.monthly():
            for gazette in self._window(territory_ids, month):
                if gazette.gazette_id not in seen:
                    seen.add(gazette.gazette_id)
                    yield gazette

    def _window(self, territory_ids: Sequence[str], period: Period) -> Iterator[Gazette]:
        total, page = self.search(territory_ids, period)
        if total >= RESULT_CAP:
            if period.is_single_day:
                raise FetchError(f"{period.since}: mais de {RESULT_CAP} diários num único dia")
            for half in period.halves():
                yield from self._window(territory_ids, half)
            return
        received = 0
        while page:
            yield from page
            received += len(page)
            if received >= total:
                break
            _, page = self.search(territory_ids, period, offset=received)
        if received < total:
            raise FetchError(
                f"{period.since} a {period.until}: API informou {total} diários, vieram {received}"
            )

    def listing(self, territory_ids: Sequence[str], period: Period) -> list[dict]:
        return [g.model_dump(mode="json") for g in self.iter_gazettes(territory_ids, period)]

    def fetch_text(self, gazette: Gazette) -> str:
        if not gazette.txt_url:
            raise FetchError(f"{gazette.gazette_id} não tem txt_url")
        return self.get(gazette.txt_url).text


def text_path(raw: Path, gazette: Gazette) -> Path:
    return path_inside(raw / "txt", gazette.territory_id, f"{gazette.gazette_id}.txt")


def listing_path(raw: Path, territory_ids: Sequence[str], month: Period) -> Path:
    key = short_hash(*sorted(territory_ids), month.since, month.until)
    return raw / "gazettes" / f"{month.since:%Y-%m}_{key}.json"


def load_gazettes(client: QDClient, territory_ids: Sequence[str], period: Period, raw: Path) -> list[Gazette]:
    return [
        Gazette.model_validate(item)
        for month in period.monthly()
        for item in cached_json(
            listing_path(raw, territory_ids, month), partial(client.listing, territory_ids, month)
        )
    ]


def fetch_text(client: QDClient, raw: Path, gazette: Gazette) -> tuple[str, str | None]:
    try:
        write_atomic(text_path(raw, gazette), client.fetch_text(gazette))
    except (FetchError, httpx.HTTPError, OSError) as error:
        log.warning("%s: %r", gazette.gazette_id, error)
        return gazette.gazette_id, repr(error)
    return gazette.gazette_id, None


def fetch_missing_texts(client: QDClient, raw: Path, gazettes: list[Gazette], workers: int) -> dict[str, str]:
    missing = [g for g in gazettes if g.txt_url and not text_path(raw, g).exists()]
    with ThreadPoolExecutor(workers) as pool:
        results = pool.map(partial(fetch_text, client, raw), missing)
        return {gazette_id: error for gazette_id, error in results if error}


def status_of(gazette: Gazette, error: str | None, text: str) -> str:
    if error:
        return "erro"
    if not gazette.txt_url:
        return "sem_txt"
    return text_status(text)


def build_row(raw: Path, gazette: Gazette, error: str | None) -> dict:
    has_text = gazette.txt_url and not error
    text = text_path(raw, gazette).read_text(encoding="utf-8") if has_text else ""
    return {
        "gazette_id": gazette.gazette_id,
        **gazette.model_dump(),
        "text": text,
        "text_status": status_of(gazette, error, text),
        "error": error,
    }


def download(
    client: QDClient, territory_ids: Sequence[str], period: Period, data_dir: Path, workers: int = 4
) -> Counter:
    raw = data_dir / "raw" / "qd"
    gazettes = load_gazettes(client, territory_ids, period, raw)
    errors = fetch_missing_texts(client, raw, gazettes, workers)
    rows = [build_row(raw, g, errors.get(g.gazette_id)) for g in gazettes]
    write_parquet(rows, data_dir / "processed" / "qd_gazettes.parquet")
    return Counter(r["text_status"] for r in rows)
