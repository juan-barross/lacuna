from collections.abc import Iterator, Sequence
from datetime import date, timedelta
from functools import partial
from pathlib import Path

import httpx
import pyarrow as pa
import pyarrow.parquet as pq

from dxp.fetch import Fetcher
from dxp.files import cached_json

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
        super().__init__(BASE_URL, http, **{"max_retries": 10, **kw})

    def _search(
        self, path: str, params: dict, size: int, since: date, until: date
    ) -> Iterator[dict]:
        for start, end in windows(since, until):
            page = 1
            while True:
                query = {**params, "dataInicial": f"{start:%Y%m%d}", "dataFinal": f"{end:%Y%m%d}"}
                resp = self.get(path, params={**query, "pagina": page, "tamanhoPagina": size})
                if resp.status_code == httpx.codes.NO_CONTENT:
                    break
                body = resp.json()
                yield from body["data"]
                if body["paginasRestantes"] <= 0:
                    break
                page += 1

    def municipal_agencies(self, ibge: str, since: date, until: date) -> dict[str, str]:
        agencies = {}
        for modalidade in MODALIDADES:
            params = {"codigoModalidadeContratacao": modalidade, "codigoMunicipioIbge": ibge}
            for item in self._search(
                "/v1/contratacoes/publicacao", params, CONTRATACOES_PAGE, since, until
            ):
                org = item["orgaoEntidade"]
                if org["esferaId"] == "M":
                    agencies[org["cnpj"]] = org["razaoSocial"]
        return agencies

    def contracts(self, cnpj: str, since: date, until: date) -> list[dict]:
        return list(
            self._search("/v1/contratos", {"cnpjOrgao": cnpj}, CONTRATOS_PAGE, since, until)
        )


def iso_date(value: str | None) -> date | None:
    return date.fromisoformat(value[:10]) if value else None


def flatten(contract: dict, territory_id: str) -> dict:
    org = contract["orgaoEntidade"]
    return {
        "numero_controle": contract["numeroControlePNCP"],
        "territory_id": territory_id,
        "orgao_cnpj": org["cnpj"],
        "orgao_nome": org["razaoSocial"],
        "fornecedor_ni": contract.get("niFornecedor"),
        "fornecedor_nome": contract.get("nomeRazaoSocialFornecedor"),
        "tipo_pessoa": contract.get("tipoPessoa"),
        "objeto": contract.get("objetoContrato"),
        "valor_global": contract.get("valorGlobal"),
        "data_assinatura": iso_date(contract.get("dataAssinatura")),
        "data_publicacao": iso_date(contract.get("dataPublicacaoPncp")),
        "processo": contract.get("processo"),
        "numero_contrato": contract.get("numeroContratoEmpenho"),
    }


def download(
    client: PNCPClient, territory_ids: Sequence[str], since: date, until: date, data_dir: Path
) -> int:
    raw = data_dir / "raw" / "pncp"
    rows = {}
    for ibge in territory_ids:
        agencies = cached_json(
            raw / "orgaos" / f"{ibge}.json", partial(client.municipal_agencies, ibge, since, until)
        )
        for cnpj in agencies:
            for c in cached_json(
                raw / "contratos" / f"{cnpj}.json", partial(client.contracts, cnpj, since, until)
            ):
                rows[c["numeroControlePNCP"]] = flatten(c, ibge)
    out = data_dir / "processed" / "pncp_contratos.parquet"
    out.parent.mkdir(parents=True, exist_ok=True)
    pq.write_table(pa.Table.from_pylist(list(rows.values())), out)
    return len(rows)
