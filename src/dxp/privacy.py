import re
from collections import Counter

from dxp.files import short_hash
from dxp.text import fold

CPF_MASK = "[CPF]"
EMAIL_MASK = "[EMAIL]"
RG_MASK = "RG [RG]"
ADDRESS_MASK = "[ENDERECO]"
PSEUDONYM_LENGTH = 6
PERSON_TYPE = "pessoal"
LABEL_FIELDS = frozenset({"contratada_nome", "pncp_fornecedor"})
UNTOUCHED_FIELDS = frozenset(
    {"ato_id", "gazette_id", "territory_id", "url", "numero_contrato", "processo", "pncp_numero_controle"}
)
ACCENTED = {"a": "aàáâãäª", "e": "eèéêë", "i": "iìíîï", "o": "oòóôõöº", "u": "uùúûü", "c": "cç", "n": "nñ"}

CPF = re.compile(r"(?<![\d./-])\d{3}\.?\d{3}\.?\d{3}-?\d{2}(?!-?\d)")
LABELED_CPF = re.compile(r"(CPF(?:/MF)?[^\d\n]{0,15}?)\d{3}\.?\d{3}\.?\d{3}\s*-?\s*\d{2}(?!\d)", re.I)
EMAIL = re.compile(r"[\w.+-]+@(?:gmail|hotmail|yahoo|outlook|bol|uol|live|icloud)\.com(?:\.br)?\b", re.I)
RG = re.compile(r"\bRG:?\s*(?:(?i:n)\.?\s?[º°o]\.?\s*)?(?:[A-Z]{2}-)?\d(?:[\d.-]*[\dXx])?")
ADDRESS = re.compile(r"(residente\s+e\s+domiciliad[oa]\s+(?:na|no|em)\s+)(.{0,300})", re.I | re.S)
SENTENCE_END = re.compile(r"\.\s*\n|;")
ADDRESS_END = re.compile(r"\bCEP\W*\d{2}\.?\d{3}-?\d{3}|\bRJ\b")
FIRST_BREAK = re.compile(r"[,\n]|$")
LABEL_CPF = re.compile(r"[\s,:–-]*(?:CPF\W*)?\[CPF\]")
PSEUDONYM = re.compile(rf"Pessoa [0-9A-F]{{{PSEUDONYM_LENGTH}}}")
MARK = re.compile(rf"\[(CPF|EMAIL|RG|ENDERECO)\]|{PSEUDONYM.pattern}")


def check_digit(digits: list[int]) -> int:
    weights = range(len(digits) + 1, 1, -1)
    return sum(d * w for d, w in zip(digits, weights, strict=True)) * 10 % 11 % 10


def is_valid_cpf(candidate: str) -> bool:
    digits = [int(c) for c in re.sub(r"\D", "", candidate)]
    if len(digits) != 11 or len(set(digits)) == 1:
        return False
    return digits[9] == check_digit(digits[:9]) and digits[10] == check_digit(digits[:10])


def mask_cpf(text: str) -> str:
    labeled = LABELED_CPF.sub(lambda m: m.group(1) + CPF_MASK, text)
    return CPF.sub(lambda m: CPF_MASK if is_valid_cpf(m.group()) else m.group(), labeled)


def mask_email(text: str) -> str:
    return EMAIL.sub(EMAIL_MASK, text)


def mask_rg(text: str) -> str:
    return RG.sub(RG_MASK, text)


def address_length(window: str) -> int:
    sentence = SENTENCE_END.split(window, maxsplit=1)[0]
    ends = list(ADDRESS_END.finditer(sentence))
    return ends[-1].end() if ends else FIRST_BREAK.search(sentence).start()


def mask_address(text: str) -> str:
    def replace(match: re.Match) -> str:
        window = match.group(2)
        return match.group(1) + ADDRESS_MASK + mask_address(window[address_length(window) :])

    return ADDRESS.sub(replace, text)


def mask_personal_data(text: str) -> str:
    return mask_address(mask_rg(mask_email(mask_cpf(text))))


def pseudonym(name: str) -> str:
    return f"Pessoa {short_hash(fold(name))[:PSEUDONYM_LENGTH].upper()}"


def name_pattern(name: str) -> re.Pattern:
    tokens = ("".join(f"[{ACCENTED.get(c, c)}]" for c in token) for token in fold(name).split())
    return re.compile(rf"(?<!\w){r'\W+'.join(tokens)}(?!\w)", re.I)


def pseudonymize(text: str, name: str) -> str:
    return name_pattern(name).sub(pseudonym(name), text)


def person_name(row: dict, known: str | None) -> str | None:
    name = known or (row.get("contratada_nome") if row.get("tipo") == PERSON_TYPE else None)
    if not (name and fold(name)) or PSEUDONYM.fullmatch(name):
        return None
    return name


def anonymize_value(key: str, value: str, name: str | None) -> str:
    masked = mask_personal_data(pseudonymize(value, name) if name else value)
    return LABEL_CPF.sub("", masked) if key in LABEL_FIELDS else masked


def anonymize_row(row: dict, known_name: str | None = None) -> dict:
    name = person_name(row, known_name)
    return {
        key: anonymize_value(key, value, name)
        if isinstance(value, str) and key not in UNTOUCHED_FIELDS
        else value
        for key, value in row.items()
    }


def count_marks(rows: list[dict]) -> Counter:
    values = (v for row in rows for v in row.values() if isinstance(v, str))
    return Counter(m.group(1) or "PESSOA" for value in values for m in MARK.finditer(value))
