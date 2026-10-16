import sys
from pathlib import Path

import altair as alt
import pandas as pd
import pyarrow.parquet as pq
import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from dxp.bm25 import BM25
from dxp.text import sort_key

DATA = ROOT / "app" / "data"
REPO = "https://github.com/juan-barross/lacuna"
STATUSES = ["casado", "provável", "sem par"]
PALETTE = {"light": ("#2a78d6", "#eb6834", "#ffffff"), "dark": ("#3987e5", "#d95926", "#0e1117")}

st.set_page_config(page_title="Lacuna", layout="wide")
blue, orange, surface = PALETTE.get(st.context.theme.type or "light", PALETTE["light"])


def read(name: str) -> pd.DataFrame:
    return pd.read_csv(DATA / name, dtype={"territory_id": str})


@st.cache_resource
def load():
    coverage = read("cobertura.csv")
    cities = (
        coverage[["territory_id", "municipio", "pct_texto"]]
        .merge(read("conciliacao.csv").drop(columns="municipio"), on="territory_id", how="left")
        .merge(read("pncp_contratos.csv"), on="territory_id", how="left")
        .fillna({"pncp_contratos": 0})
        .sort_values("municipio", key=lambda s: s.map(sort_key))
    )
    cities["situacao"] = cities["taxa"].map(lambda t: "conciliado" if pd.notna(t) else "sem texto")
    return coverage, cities, pq.read_table(DATA / "atos.parquet").to_pandas()


@st.cache_resource
def index() -> BM25:
    return BM25(pq.read_table(DATA / "atos.parquet", columns=["ato_id", "text"]))


def city_axis(order: list[str]) -> alt.Y:
    return alt.Y("municipio:N", sort=order, title=None, axis=alt.Axis(labelLimit=220))


coverage, cities, atos = load()
eligible = atos[atos["status"].isin(STATUSES)]

st.title("Lacuna")
st.markdown(
    "Extratos de contrato dos diários oficiais de municípios do RJ, conferidos contra o "
    f"Portal Nacional de Contratações Públicas (PNCP). [Código e metodologia]({REPO})"
)
c1, c2, c3, c4 = st.columns(4)
c1.metric("Extratos de contrato lidos", f"{len(atos):,}".replace(",", "."))
c2.metric("Com par no PNCP", f"{(eligible['status'] == 'casado').mean():.0%}", help="casados / elegíveis")
c3.metric("Sem par no PNCP", f"{(eligible['status'] == 'sem par').mean():.0%}")
c4.metric("Municípios sem texto no diário", int((coverage["pct_texto"] == 0).sum()))
st.caption(
    "Outubro de 2025 a setembro de 2026. Elegível é o extrato de contrato com fornecedor e valor "
    "identificado; contratação temporária de pessoal fica de fora, porque não vai para o PNCP. "
    "Um ato sem par é uma lacuna de dados, não uma irregularidade."
)

tab_rates, tab_atos, tab_coverage = st.tabs(["Conciliação", "Atos", "Cobertura do diário"])

with tab_rates:
    st.subheader("Extratos com par no PNCP, por município")
    reconciled = cities.dropna(subset=["taxa"])
    base = alt.Chart(reconciled).encode(y=city_axis(reconciled.sort_values("taxa")["municipio"].tolist()))
    axis = alt.Axis(format="%", grid=False)
    interval = base.mark_rule(strokeWidth=2, color=blue, opacity=0.4).encode(
        x=alt.X("ic_inferior:Q", title="Com par no PNCP", axis=axis), x2="ic_superior:Q"
    )
    tooltip = ["municipio", alt.Tooltip("taxa:Q", format=".0%"), "elegiveis", "casados", "pncp_contratos"]
    rate = base.mark_circle(size=90, color=blue, opacity=1).encode(x="taxa:Q", tooltip=tooltip)
    st.altair_chart((interval + rate).properties(height=alt.Step(28)), use_container_width=True)
    st.caption("O ponto é a taxa; a barra, o intervalo de confiança de 95% (Wilson).")
    columns = [
        "municipio",
        "situacao",
        "elegiveis",
        "casados",
        "provaveis",
        "sem_par",
        "taxa",
        "pncp_contratos",
    ]
    progress = st.column_config.ProgressColumn("com par", format="percent", min_value=0, max_value=1)
    st.dataframe(cities[columns], column_config={"taxa": progress}, hide_index=True, use_container_width=True)

with tab_atos:
    left, mid, right = st.columns([3, 2, 2])
    query = left.text_input("Buscar nos extratos", placeholder="merenda escolar, locação de veículos")
    city = mid.selectbox("Município", ["Todos", *cities["municipio"]])
    status = right.multiselect("Situação", STATUSES, default=STATUSES)

    shown = atos[atos["status"].isin(status) & ((atos["territory_name"] == city) | (city == "Todos"))]
    if query.strip():
        scores = dict(index().search(query, k=500))
        shown = shown[shown["ato_id"].isin(scores)].sort_values("ato_id", key=lambda s: -s.map(scores))
    st.caption(f"{len(shown)} extratos")
    columns = ["territory_name", "date", "contratada_nome", "valor", "status", "pncp_fornecedor"]
    picked = st.dataframe(
        shown[columns],
        hide_index=True,
        use_container_width=True,
        on_select="rerun",
        selection_mode="single-row",
    )
    if picked.selection.rows:
        ato = shown.iloc[picked.selection.rows[0]]
        text_col, data_col = st.columns([3, 2])
        text_col.text(ato["text"])
        data_col.markdown(f"**Situação:** {ato['status']}  \n**Diário:** [{ato['date']}]({ato['url']})")
        if pd.notna(ato["pncp_numero_controle"]):
            data_col.markdown(
                f"**PNCP:** `{ato['pncp_numero_controle']}`  \n**Fornecedor:** {ato['pncp_fornecedor']}  \n"
                f"**Valor no PNCP:** R$ {ato['pncp_valor']:,.2f}"
            )

with tab_coverage:
    st.subheader("Texto disponível no Querido Diário, por município")
    st.caption("Em alguns municípios o arquivo de texto traz só o link para o PDF da prefeitura.")
    data = coverage.assign(**{"com texto": coverage["ok"], "sem texto": coverage["diarios"] - coverage["ok"]})
    order = data.sort_values(["pct_texto", "municipio"])["municipio"].tolist()
    long = data.melt(["municipio", "pct_texto"], ["com texto", "sem texto"], var_name="c", value_name="n")
    scale = alt.Scale(domain=["com texto", "sem texto"], range=[blue, orange])
    bars = (
        alt.Chart(long)
        .mark_bar(stroke=surface, strokeWidth=2)
        .encode(
            y=city_axis(order),
            x=alt.X("n:Q", title="Diários", stack="zero", axis=alt.Axis(grid=False)),
            color=alt.Color("c:N", title=None, legend=alt.Legend(orient="top"), scale=scale),
            tooltip=["municipio", "c", "n", "pct_texto"],
        )
    )
    st.altair_chart(bars.properties(height=alt.Step(26)), use_container_width=True)
