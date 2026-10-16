import json
import logging
from collections.abc import Callable, Sequence
from datetime import date
from functools import partial
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq

from dxp.pncp import PNCPClient

log = logging.getLogger(__name__)

SCHEMA = pa.schema(
    [
        ("numero_controle", pa.string()),
        ("territory_id", pa.string()),
        ("orgao_cnpj", pa.string()),
        ("orgao_nome", pa.string()),
        ("fornecedor_ni", pa.string()),
        ("fornecedor_nome", pa.string()),
        ("tipo_pessoa", pa.string()),
        ("objeto", pa.string()),
        ("valor_global", pa.float64()),
        ("data_assinatura", pa.date32()),
        ("data_publicacao", pa.date32()),
        ("processo", pa.string()),
        ("numero_contrato", pa.string()),
    ]
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


def cached_json(path: Path, fetch: Callable[[], object]):
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    data = fetch()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".part")
    tmp.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    tmp.replace(path)
    return data


class PNCPStore:
    def __init__(self, data_dir: Path) -> None:
        self.raw = data_dir / "raw" / "pncp"
        self.parquet_path = data_dir / "processed" / "pncp_contratos.parquet"

    def download(
        self, client: PNCPClient, territory_ids: Sequence[str], since: date, until: date
    ) -> int:
        rows: dict[str, dict] = {}
        for ibge in territory_ids:
            agencies = cached_json(
                self.raw / "orgaos" / f"{ibge}.json",
                partial(client.municipal_agencies, ibge, since, until),
            )
            log.info("%s: %d órgãos municipais", ibge, len(agencies))
            for cnpj in agencies:
                contracts = cached_json(
                    self.raw / "contratos" / f"{cnpj}.json",
                    partial(client.contracts, cnpj, since, until),
                )
                for c in contracts:
                    rows[c["numeroControlePNCP"]] = flatten(c, ibge)

        self.parquet_path.parent.mkdir(parents=True, exist_ok=True)
        pq.write_table(pa.Table.from_pylist(list(rows.values()), schema=SCHEMA), self.parquet_path)
        return len(rows)
