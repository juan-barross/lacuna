from datetime import date
from typing import Literal

from pydantic import BaseModel, Field, field_validator

from dxp.cnpj import is_valid, normalize

FIELDS = [
    "tipo",
    "numero_contrato",
    "processo",
    "contratada_nome",
    "contratada_cnpj",
    "objeto",
    "valor",
    "data_assinatura",
]


class Ato(BaseModel):
    tipo: Literal["contrato", "pessoal", "outro"] = Field(
        description="contrato com fornecedor, pessoa física por tempo determinado, ou outro"
    )
    numero_contrato: str | None = Field(None, description="número do contrato, como no texto")
    processo: str | None = Field(None, description="número do processo administrativo")
    contratada_nome: str | None = Field(None, description="razão social ou nome da contratada")
    contratada_cnpj: str | None = Field(None, description="CNPJ da contratada, nunca o do órgão")
    objeto: str | None = Field(None, description="objeto do contrato")
    valor: float | None = Field(None, description="valor total do contrato em reais")
    data_assinatura: date | None = Field(None, description="data de assinatura")

    @field_validator("contratada_cnpj")
    @classmethod
    def _only_alnum(cls, cnpj: str | None) -> str | None:
        return normalize(cnpj) if cnpj else None

    def problems(self) -> list[str]:
        out = []
        if self.contratada_cnpj and not is_valid(self.contratada_cnpj):
            out.append(f"CNPJ inválido: {self.contratada_cnpj}")
        if self.valor is not None and self.valor <= 0:
            out.append(f"valor não positivo: {self.valor}")
        return out
