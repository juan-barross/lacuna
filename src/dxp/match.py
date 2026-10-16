import bisect
import math
from collections import defaultdict
from datetime import date

from dxp.text import sort_key, token_f1

VALUE_TOLERANCE = 0.01
MIN_VALUE_GAP = 1.0
DATE_WINDOW_DAYS = 60
NAME_THRESHOLD = 0.6
CONFLICT_THRESHOLD = 0.3

MATCHED, PROBABLE, UNMATCHED = "casado", "provável", "sem par"
OUT_OF_SCOPE, NO_VALUE = "fora do escopo", "sem valor"
ELIGIBLE = (MATCHED, PROBABLE, UNMATCHED)


def wilson(hits: int, n: int, z: float = 1.96) -> tuple[float, float]:
    if not n:
        return 0.0, 0.0
    p = hits / n
    center = (p + z * z / (2 * n)) / (1 + z * z / n)
    margin = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / (1 + z * z / n)
    return max(0.0, center - margin), min(1.0, center + margin)


def contract_date(contract: dict) -> date:
    return contract["data_assinatura"] or contract["data_publicacao"]


def contract_value(contract: dict) -> float:
    return contract["valor_global"]


class PNCPIndex:
    def __init__(self, contracts: list[dict]) -> None:
        self.by_city = defaultdict(list)
        for contract in sorted((c for c in contracts if c["valor_global"]), key=contract_value):
            self.by_city[contract["territory_id"]].append(contract)

    def near(self, territory_id: str, value: float, when: date) -> list[dict]:
        rows, gap = self.by_city.get(territory_id, []), max(MIN_VALUE_GAP, value * VALUE_TOLERANCE)
        lo = bisect.bisect_left(rows, value - gap, key=contract_value)
        hi = bisect.bisect_right(rows, value + gap, key=contract_value)
        return [c for c in rows[lo:hi] if abs((contract_date(c) - when).days) <= DATE_WINDOW_DAYS]


def rank(match: dict) -> tuple[int, float]:
    return {MATCHED: 2, PROBABLE: 1}.get(match["status"], 0), match.get("similaridade_nome", 0.0)


def classify(ato: dict, index: PNCPIndex) -> dict:
    if ato["tipo"] != "contrato":
        return {"status": OUT_OF_SCOPE}
    if not ato["valor"]:
        return {"status": NO_VALUE}

    best = {"status": UNMATCHED}
    when = ato["data_assinatura"] or ato["date"]
    for contract in index.near(ato["territory_id"], ato["valor"], when):
        same_cnpj = bool(ato["contratada_cnpj"]) and ato["contratada_cnpj"] == contract["fornecedor_ni"]
        similarity = token_f1(ato["contratada_nome"] or "", contract["fornecedor_nome"] or "")
        if ato["contratada_nome"] and not same_cnpj and similarity < CONFLICT_THRESHOLD:
            continue
        candidate = {
            "status": MATCHED if same_cnpj or similarity >= NAME_THRESHOLD else PROBABLE,
            "pncp_numero_controle": contract["numero_controle"],
            "pncp_fornecedor": contract["fornecedor_nome"],
            "pncp_valor": contract["valor_global"],
            "similaridade_nome": round(similarity, 2),
        }
        if rank(candidate) > rank(best):
            best = candidate
    return best


def reconcile(atos: list[dict], contracts: list[dict]) -> list[dict]:
    index = PNCPIndex(contracts)
    return [{**ato, **classify(ato, index)} for ato in atos]


def rates_by_city(rows: list[dict]) -> list[dict]:
    by_city = defaultdict(list)
    for row in rows:
        by_city[row["territory_name"]].append(row["status"])
    out = []
    for city, statuses in sorted(by_city.items(), key=lambda kv: sort_key(kv[0])):
        eligible = [s for s in statuses if s in ELIGIBLE]
        matched = eligible.count(MATCHED)
        low, high = wilson(matched, len(eligible))
        out.append(
            {
                "municipio": city,
                "atos": len(statuses),
                "elegiveis": len(eligible),
                "casados": matched,
                "provaveis": eligible.count(PROBABLE),
                "sem_par": eligible.count(UNMATCHED),
                "fora_do_escopo": statuses.count(OUT_OF_SCOPE),
                "sem_valor": statuses.count(NO_VALUE),
                "taxa": round(matched / len(eligible), 3) if eligible else None,
                "ic_inferior": round(low, 3),
                "ic_superior": round(high, 3),
            }
        )
    return out
