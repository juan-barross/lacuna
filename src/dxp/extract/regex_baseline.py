import re
from datetime import date

from dxp.extract.schema import Ato
from dxp.validate.cnpj import is_valid, normalize

MONTHS = "janeiro fevereiro março abril maio junho julho agosto setembro outubro novembro dezembro"
MONTH_NUMBER = {name: i for i, name in enumerate(MONTHS.split(), 1)}

CNPJ = re.compile(r"\b[0-9A-Z]{2}\.?[0-9A-Z]{3}\.?[0-9A-Z]{3}/?[0-9A-Z]{4}-?\d{2}\b")
MONEY = re.compile(r"R\$\s*(\d{1,3}(?:\.\d{3})*,\d{2})")
VALUE = re.compile(r"valor[^\n:R]{0,40}:?\s*R\$\s*(\d{1,3}(?:\.\d{3})*,\d{2})", re.I)
NUMERIC_DATE = re.compile(r"\b(\d{1,2})/(\d{1,2})/(\d{4})\b")
WRITTEN_DATE = re.compile(r"\b(\d{1,2})º?\s+(?:de\s+)?([a-zç]+)\s+de\s+(\d{4})", re.I)
PLACE_DATE = re.compile(r"[A-ZÁ-Ú][\w ]+,\s+(\d{1,2}º?\s+(?:de\s+)?[a-zç]+\s+de\s+\d{4})", re.I)
CPF = re.compile(r"\b(?:\d{3}|X{3})\.(?:\d{3}|X{3})\.\d{3}-\d{2}\b", re.I)
TEMPORARY_HIRE = re.compile(r"processo seletivo|tempo determinado|excepcional interesse", re.I)
NEXT_LABEL = re.compile(r"(?:[.;]\s+|\n\s*)(?:[IVXL]+\s*[–-]\s*)?\w[\w ]{2,40}:")
CONTRACT_NUMBER = re.compile(
    r"CONTRATO(?:\s+ADMINISTRATIVO)?\s*(?:N[º°o.]*)?\s*[.:]?\s*([\w./-]*\d[\w./-]*)", re.I
)
PROCESS_NUMBER = re.compile(
    r"processo(?:\s+(?:administrativo|instrutivo))?\s*(?:n[º°o.]*)?\s*:?\s*"
    r"((?:[A-Z]{2,}[\w-]*\s)?[\w./-]*\d[\w./-]*)",
    re.I,
)
PARTIES_SPLIT = re.compile(r"\s+e\s+(?:[ao]\s+)?(?:empresa\s+|sra?\.?\s+)?(?=\S)", re.I)
NAME_END = re.compile(
    r",?\s*\(?\s*(?:CNPJ|CPF|inscrit|portador)|\.\s+(?=[A-ZÁ-Ú][a-zà-ú]+[ ,])", re.I
)
MAX_FIELD = 400


def brl(amount: str) -> float:
    return float(amount.replace(".", "").replace(",", "."))


def parse_date(text: str) -> date | None:
    for pattern in (NUMERIC_DATE, WRITTEN_DATE):
        for day, month, year in pattern.findall(text):
            try:
                return date(int(year), int(MONTH_NUMBER.get(month.lower(), month)), int(day))
            except ValueError:
                continue
    return None


def labeled(text: str, label: str) -> str | None:
    match = re.search(rf"{label}\s*:\s*", text, re.I)
    if not match:
        return None
    rest = text[match.end() : match.end() + MAX_FIELD]
    end = NEXT_LABEL.search(rest)
    return " ".join(rest[: end.start() if end else None].split()).strip(" .;,") or None


def number(pattern: re.Pattern, text: str) -> str | None:
    match = pattern.search(text)
    return match.group(1).strip(".") if match else None


def contractor_name(text: str) -> str | None:
    name = labeled(text, r"contratad[ao]")
    if not name and (parties := labeled(text, "partes")):
        name = PARTIES_SPLIT.split(parties, maxsplit=1)[-1]
    if not name:
        return None
    return NAME_END.split(name)[0].strip(" .;,") or None


def contractor_cnpj(text: str) -> str | None:
    found = [(m.start(), normalize(m.group())) for m in CNPJ.finditer(text) if is_valid(m.group())]
    label = re.search(r"contratad[ao]|partes", text, re.I)
    candidates = (
        [c for pos, c in found if pos > label.start()] if label else [c for _, c in found[-1:]]
    )
    return candidates[0] if candidates else None


def signature_date(text: str) -> date | None:
    signed = re.search(r"assinatura", text, re.I)
    if signed and (found := parse_date(text[signed.end() : signed.end() + 80])):
        return found
    place = PLACE_DATE.search(text)
    return parse_date(place.group(1)) if place else None


def extract(text: str) -> Ato:
    value = VALUE.search(text) or MONEY.search(text)
    return Ato(
        tipo="pessoal" if CPF.search(text) or TEMPORARY_HIRE.search(text) else "contrato",
        numero_contrato=number(CONTRACT_NUMBER, text),
        processo=number(PROCESS_NUMBER, text),
        contratada_nome=contractor_name(text),
        contratada_cnpj=contractor_cnpj(text),
        objeto=labeled(text, "objeto"),
        valor=brl(value.group(1)) if value else None,
        data_assinatura=signature_date(text),
    )
