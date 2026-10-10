"""Cliente da API do Querido Diário (https://api.queridodiario.org.br)."""

from datetime import date, datetime, timedelta
from pathlib import PurePosixPath
from urllib.parse import urlparse

from pydantic import BaseModel, Field

# A URL antiga (queridodiario.ok.org.br/api) só redireciona para esta.
BASE_URL = "https://api.queridodiario.org.br"


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
