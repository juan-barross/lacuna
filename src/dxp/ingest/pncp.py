from collections.abc import Iterator
from datetime import date, timedelta

import httpx

from dxp.ingest.fetch import Fetcher, make_client

BASE_URL = "https://pncp.gov.br/api/consulta"
MODALIDADES = range(1, 15)
CONTRATACOES_PAGE = 50
CONTRATOS_PAGE = 500
MAX_DAYS = 365


def windows(since: date, until: date, days: int = MAX_DAYS) -> list[tuple[date, date]]:
    out = []
    while since <= until:
        end = min(since + timedelta(days=days - 1), until)
        out.append((since, end))
        since = end + timedelta(days=1)
    return out


class PNCPClient(Fetcher):
    def __init__(self, http: httpx.Client | None = None, **kw):
        super().__init__(http or make_client(BASE_URL, timeout=120), **kw)

    def _search(self, path: str, params: dict, size: int, since: date, until: date):
        for start, end in windows(since, until):
            dates = {"dataInicial": f"{start:%Y%m%d}", "dataFinal": f"{end:%Y%m%d}"}
            yield from self._pages(path, {**params, **dates}, size)

    def _pages(self, path: str, params: dict, size: int) -> Iterator[dict]:
        page = 1
        while True:
            resp = self.get(path, params={**params, "pagina": page, "tamanhoPagina": size})
            if resp.status_code == httpx.codes.NO_CONTENT:
                return
            body = resp.json()
            yield from body["data"]
            if body["paginasRestantes"] <= 0:
                return
            page += 1

    def municipal_agencies(self, ibge: str, since: date, until: date) -> dict[str, str]:
        agencies = {}
        for modalidade in MODALIDADES:
            params = {"codigoModalidadeContratacao": modalidade, "codigoMunicipioIbge": ibge}
            path = "/v1/contratacoes/publicacao"
            for item in self._search(path, params, CONTRATACOES_PAGE, since, until):
                org = item["orgaoEntidade"]
                if org["esferaId"] == "M":
                    agencies[org["cnpj"]] = org["razaoSocial"]
        return agencies

    def contracts(self, cnpj: str, since: date, until: date) -> list[dict]:
        params = {"cnpjOrgao": cnpj}
        return list(self._search("/v1/contratos", params, CONTRATOS_PAGE, since, until))
