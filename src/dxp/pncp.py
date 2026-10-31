from collections.abc import Iterator, Sequence
from datetime import date
from functools import partial
from pathlib import Path

import httpx

from dxp.fetch import Fetcher, RetryPolicy, new_client
from dxp.files import cached_json, path_inside, short_hash, write_parquet
from dxp.ids import ALPHANUMERIC_ID, TERRITORY_ID, checked_id
from dxp.period import Period

BASE_URL = "https://pncp.gov.br/api/consulta"
MODALIDADES = range(1, 15)
CONTRATACOES_PAGE = 50
CONTRATOS_PAGE = 500
PNCP_RETRY = RetryPolicy(max_retries=10)


class PNCPClient(Fetcher):
    def __init__(self, http: httpx.Client | None = None, retry: RetryPolicy = PNCP_RETRY) -> None:
        super().__init__(http or new_client(BASE_URL), retry)

    def _search(self, path: str, params: dict, size: int, period: Period) -> Iterator[dict]:
        for window in period.yearly():
            page = 1
            while True:
                query = {
                    **params,
                    "dataInicial": f"{window.since:%Y%m%d}",
                    "dataFinal": f"{window.until:%Y%m%d}",
                    "pagina": page,
                    "tamanhoPagina": size,
                }
                resp = self.get(path, params=query)
                if resp.status_code == httpx.codes.NO_CONTENT:
                    break
                body = resp.json()
                yield from body["data"]
                if body["paginasRestantes"] <= 0:
                    break
                page += 1

    def municipal_agencies(self, ibge: str, period: Period) -> dict[str, str]:
        agencies = {}
        for modalidade in MODALIDADES:
            params = {"codigoModalidadeContratacao": modalidade, "codigoMunicipioIbge": ibge}
            for item in self._search("/v1/contratacoes/publicacao", params, CONTRATACOES_PAGE, period):
                org = item["orgaoEntidade"]
                if org["esferaId"] == "M":
                    agencies[org["cnpj"]] = org["razaoSocial"]
        return agencies

    def contracts(self, cnpj: str, period: Period) -> list[dict]:
        return list(self._search("/v1/contratos", {"cnpjOrgao": cnpj}, CONTRATOS_PAGE, period))


def iso_date(value: str | None) -> date | None:
    return date.fromisoformat(value[:10]) if value else None


def flatten(contract: dict, territory_id: str) -> dict:
    return {
        "numero_controle": contract["numeroControlePNCP"],
        "territory_id": territory_id,
        "fornecedor_ni": contract.get("niFornecedor"),
        "fornecedor_nome": contract.get("nomeRazaoSocialFornecedor"),
        "valor_global": contract.get("valorGlobal"),
        "data_assinatura": iso_date(contract.get("dataAssinatura")),
        "data_publicacao": iso_date(contract.get("dataPublicacaoPncp")),
    }


def cache_path(raw: Path, kind: str, entity_id: str, period: Period) -> Path:
    name = f"{entity_id}_{short_hash(period.since, period.until)}.json"
    return path_inside(raw / kind, name)


def download(client: PNCPClient, territory_ids: Sequence[str], period: Period, data_dir: Path) -> int:
    raw = data_dir / "raw" / "pncp"
    rows = {}
    for ibge in territory_ids:
        checked_id(TERRITORY_ID, ibge, "código IBGE")
        agencies = cached_json(
            cache_path(raw, "orgaos", ibge, period), partial(client.municipal_agencies, ibge, period)
        )
        for cnpj in agencies:
            checked_id(ALPHANUMERIC_ID, cnpj, "CNPJ do órgão")
            contracts = cached_json(
                cache_path(raw, "contratos", cnpj, period), partial(client.contracts, cnpj, period)
            )
            for contract in contracts:
                rows[contract["numeroControlePNCP"]] = flatten(contract, ibge)
    write_parquet(list(rows.values()), data_dir / "processed" / "pncp_contratos.parquet")
    return len(rows)
