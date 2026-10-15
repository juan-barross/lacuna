from collections.abc import Iterator
from datetime import date

import httpx

from dxp.ingest.fetch import Fetcher, make_client

BASE_URL = "https://pncp.gov.br/api/consulta"
MODALIDADES = range(1, 15)
CONTRATACOES_PAGE = 50
CONTRATOS_PAGE = 500


def yyyymmdd(d: date) -> str:
    return d.strftime("%Y%m%d")


class PNCPClient(Fetcher):
    def __init__(self, http: httpx.Client | None = None, **kw):
        super().__init__(http or make_client(BASE_URL, timeout=120), **kw)

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
            params = {
                "dataInicial": yyyymmdd(since),
                "dataFinal": yyyymmdd(until),
                "codigoModalidadeContratacao": modalidade,
                "codigoMunicipioIbge": ibge,
            }
            for item in self._pages("/v1/contratacoes/publicacao", params, CONTRATACOES_PAGE):
                org = item["orgaoEntidade"]
                if org["esferaId"] == "M":
                    agencies[org["cnpj"]] = org["razaoSocial"]
        return agencies

    def contracts(self, cnpj: str, since: date, until: date) -> list[dict]:
        params = {"dataInicial": yyyymmdd(since), "dataFinal": yyyymmdd(until), "cnpjOrgao": cnpj}
        return list(self._pages("/v1/contratos", params, CONTRATOS_PAGE))
