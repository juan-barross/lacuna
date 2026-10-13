import unicodedata
from pathlib import Path

import altair as alt
import pandas as pd
import streamlit as st

DATA = Path(__file__).parent / "data" / "cobertura.csv"
REPO = "https://github.com/juan-barross/lacuna"
COLORS = {
    "light": {"Com texto": "#2a78d6", "Sem texto": "#eb6834", "surface": "#ffffff"},
    "dark": {"Com texto": "#3987e5", "Sem texto": "#d95926", "surface": "#0e1117"},
}

st.set_page_config(page_title="Lacuna", layout="wide")


def sort_key(name: str) -> str:
    decomposed = unicodedata.normalize("NFKD", name.casefold())
    return "".join(ch for ch in decomposed if not unicodedata.combining(ch))


@st.cache_data
def load() -> pd.DataFrame:
    df = pd.read_csv(DATA, dtype={"territory_id": str})
    df["sem_texto"] = df["diarios"] - df["ok"]
    df["tem_texto"] = df["pct_texto"] > 0
    df["ordem"] = df["municipio"].map(sort_key)
    return df.sort_values(["tem_texto", "ordem"])


df = load()
theme = st.context.theme.type or "light"
palette = COLORS.get(theme, COLORS["light"])
sem_texto = df[~df["tem_texto"]]

st.title("Lacuna")
st.markdown(
    "Diários oficiais de municípios do RJ comparados com o "
    "Portal Nacional de Contratações Públicas (PNCP). "
    f"[Código e metodologia]({REPO})"
)

c1, c2, c3, c4 = st.columns(4)
c1.metric("Diários no período", f"{df['diarios'].sum():,}".replace(",", "."))
c2.metric("Municípios", len(df))
c3.metric("Com texto disponível", len(df) - len(sem_texto))
c4.metric("Só com link para o PDF", len(sem_texto))

st.subheader("Texto disponível no Querido Diário, por município")
st.caption(
    f"Outubro de 2025 a setembro de 2026. Em {len(sem_texto)} municípios o arquivo de texto "
    "traz só o link para o PDF da prefeitura, então os atos de contratação não podem ser "
    "lidos automaticamente."
)

long = df.melt(
    id_vars=["municipio", "diarios", "pct_texto"],
    value_vars=["ok", "sem_texto"],
    var_name="categoria",
    value_name="n",
)
long["categoria"] = long["categoria"].map({"ok": "Com texto", "sem_texto": "Sem texto"})

chart = (
    alt.Chart(long)
    .mark_bar(stroke=palette["surface"], strokeWidth=2)
    .encode(
        y=alt.Y(
            "municipio:N",
            sort=df["municipio"].tolist(),
            title=None,
            axis=alt.Axis(labelLimit=220),
        ),
        x=alt.X("n:Q", title="Diários", stack="zero", axis=alt.Axis(grid=False)),
        color=alt.Color(
            "categoria:N",
            title=None,
            scale=alt.Scale(
                domain=["Com texto", "Sem texto"],
                range=[palette["Com texto"], palette["Sem texto"]],
            ),
            legend=alt.Legend(orient="top"),
        ),
        order=alt.Order("categoria:N"),
        tooltip=[
            alt.Tooltip("municipio:N", title="Município"),
            alt.Tooltip("categoria:N", title="Situação"),
            alt.Tooltip("n:Q", title="Diários"),
            alt.Tooltip("pct_texto:Q", title="% com texto", format=".1f"),
        ],
    )
    .properties(height=alt.Step(26))
)
st.altair_chart(chart, use_container_width=True)

with st.expander("Ver a tabela"):
    table = df.sort_values("ordem")[["municipio", "diarios", "ok", "so_link", "curto"]]
    st.dataframe(
        table.rename(
            columns={
                "municipio": "Município",
                "diarios": "Diários",
                "ok": "Com texto",
                "so_link": "Só link do PDF",
                "curto": "Aviso curto",
            }
        ),
        hide_index=True,
        use_container_width=True,
    )

st.subheader("Próximas etapas")
st.markdown(
    "- Extração dos atos de contratação (empresa, CNPJ, valor, objeto) com regex e com LLM\n"
    "- Conciliação com os contratos do PNCP\n"
    "- Taxa de conciliação por município, com intervalo de confiança"
)
st.caption(
    "Um ato publicado no diário sem registro correspondente no PNCP é tratado como lacuna "
    "de dados, não como irregularidade. Fontes: Querido Diário (Open Knowledge Brasil) e PNCP."
)
