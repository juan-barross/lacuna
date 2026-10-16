import json
import logging
import re
from collections import Counter
from collections.abc import Sequence
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

import httpx
import pyarrow as pa
import pyarrow.parquet as pq

from dxp.fetch import FetchError
from dxp.qd import Gazette, QDClient, month_windows

log = logging.getLogger(__name__)

MIN_TEXT_CHARS = 1000
_ONLY_URL = re.compile(r"^\s*https?://\S+\s*$")

SCHEMA = pa.schema(
    [
        ("gazette_id", pa.string()),
        ("territory_id", pa.string()),
        ("territory_name", pa.string()),
        ("date", pa.date32()),
        ("edition", pa.string()),
        ("is_extra_edition", pa.bool_()),
        ("url", pa.string()),
        ("txt_url", pa.string()),
        ("text", pa.large_string()),
        ("text_chars", pa.int64()),
        ("text_status", pa.string()),
        ("error", pa.string()),
    ]
)


def text_status(text: str) -> str:
    if not text.strip():
        return "vazio"
    if _ONLY_URL.match(text):
        return "so_link"
    if len(text.strip()) < MIN_TEXT_CHARS:
        return "curto"
    return "ok"


@dataclass
class DownloadSummary:
    gazettes: int = 0
    texts_downloaded: int = 0
    by_status: Counter = field(default_factory=Counter)


class QDStore:
    def __init__(self, data_dir: Path) -> None:
        self.raw = data_dir / "raw" / "qd"
        self.processed = data_dir / "processed"

    @property
    def parquet_path(self) -> Path:
        return self.processed / "qd_gazettes.parquet"

    def _listing_path(self, start: date) -> Path:
        return self.raw / "gazettes" / f"{start:%Y-%m}.json"

    def _text_path(self, g: Gazette) -> Path:
        return self.raw / "txt" / g.territory_id / f"{g.gazette_id}.txt"

    def list_gazettes(
        self, client: QDClient, territory_ids: Sequence[str], since: date, until: date
    ) -> list[Gazette]:
        gazettes: list[Gazette] = []
        for start, end in month_windows(since, until):
            path = self._listing_path(start)
            if path.exists():
                items = json.loads(path.read_text(encoding="utf-8"))
                gazettes.extend(Gazette.model_validate(i) for i in items)
                continue
            window = list(client.iter_gazettes(territory_ids, start, end))
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(
                json.dumps([g.model_dump(mode="json") for g in window], ensure_ascii=False),
                encoding="utf-8",
            )
            log.info("%s a %s: %d diários", start, end, len(window))
            gazettes.extend(window)
        return gazettes

    def _fetch_to_disk(self, client: QDClient, g: Gazette) -> None:
        path = self._text_path(g)
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".part")
        tmp.write_text(client.fetch_text(g), encoding="utf-8")
        tmp.replace(path)

    def download(
        self,
        client: QDClient,
        territory_ids: Sequence[str],
        since: date,
        until: date,
        *,
        workers: int = 4,
    ) -> DownloadSummary:
        summary = DownloadSummary()
        gazettes = self.list_gazettes(client, territory_ids, since, until)

        missing = [g for g in gazettes if g.txt_url and not self._text_path(g).exists()]
        errors: dict[str, str] = {}
        with ThreadPoolExecutor(max_workers=workers) as pool:
            futures = {pool.submit(self._fetch_to_disk, client, g): g for g in missing}
            for i, future in enumerate(as_completed(futures), 1):
                g = futures[future]
                try:
                    future.result()
                    summary.texts_downloaded += 1
                except (FetchError, httpx.HTTPError, OSError) as e:
                    errors[g.gazette_id] = str(e)
                    log.error("%s: %s", g.gazette_id, e)
                if i % 100 == 0:
                    log.info("%d de %d textos", i, len(missing))

        rows = []
        for g in gazettes:
            text, status, error = "", "sem_txt", None
            if g.gazette_id in errors:
                status, error = "erro", errors[g.gazette_id]
            elif g.txt_url:
                text = self._text_path(g).read_text(encoding="utf-8")
                status = text_status(text)
            rows.append(
                {
                    "gazette_id": g.gazette_id,
                    "territory_id": g.territory_id,
                    "territory_name": g.territory_name,
                    "date": g.date,
                    "edition": g.edition,
                    "is_extra_edition": g.is_extra_edition,
                    "url": g.url,
                    "txt_url": g.txt_url,
                    "text": text,
                    "text_chars": len(text),
                    "text_status": status,
                    "error": error,
                }
            )
            summary.by_status[status] += 1
        summary.gazettes = len(rows)

        self.processed.mkdir(parents=True, exist_ok=True)
        pq.write_table(pa.Table.from_pylist(rows, schema=SCHEMA), self.parquet_path)
        return summary
