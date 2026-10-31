import sys
from pathlib import Path

import altair as alt
import pandas as pd
import pyarrow.parquet as pq
import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from dxp.bm25 import BM25
from dxp.match import ELIGIBLE, MATCHED, UNMATCHED
from dxp.text import sort_key

DATA = ROOT / "app" / "data"
REPO = "https://github.com/juan-barross/lacuna"
PALETTE = {"light": ("#2a78d6", "#eb6834", "#ffffff"), "dark": ("#3987e5", "#d95926", "#0e1117")}
MAX_QUERY_CHARS = 200
MAX_SEARCH_HITS = 500
MISSING = "—"
COUNT_COLUMNS = ["elegiveis", "casados", "provaveis", "sem_par", "pncp_contratos"]
RATE_TABLE_COLUMNS = [
    "municipio",
    "situacao",
    "elegiveis",
    "casados",
    "provaveis",
    "sem_par",
    "taxa",
    "pncp_contratos",
]
ATO_TABLE_COLUMNS = ["territory_name", "date", "contratada_nome", "valor", "status", "pncp_fornecedor"]

st.set_page_config(page_title="Lacuna", layout="wide")
blue, orange, surface = PALETTE.get(st.context.theme.type or "light", PALETTE["light"])


def read(name: str) -> pd.DataFrame:
    return pd.read_csv(DATA / name, dtype={"territory_id": str})


def city_status(cities: pd.DataFrame) -> pd.Series:
    no_text = cities["pct_texto"] == 0
    no_eligible = cities["elegiveis"].fillna(0) == 0
    status = pd.Series("conciliado", index=cities.index)
    return status.mask(no_eligible, "sem elegíveis").mask(no_text, "sem texto")


@st.cache_resource
def load() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    coverage = read("cobertura.csv")
    cities = (
        coverage[["territory_id", "municipio", "pct_texto"]]
        .merge(read("conciliacao.csv").drop(columns="municipio"), on="territory_id", how="left")
        .merge(read("pncp_contratos.csv"), on="territory_id", how="left")
        .sort_values("municipio", key=lambda s: s.map(sort_key))
    )
    cities["situacao"] = city_status(cities)
    return coverage, cities, pq.read_table(DATA / "atos.parquet").to_pandas()


@st.cache_resource
def index() -> BM25:
    return BM25(pq.read_table(DATA / "atos.parquet", columns=["ato_id", "text"]))


def city_axis(order: list[str]) -> alt.Y:
    return alt.Y("municipio:N", sort=order, title=None, axis=alt.Axis(labelLimit=220))


def count_or_missing(value: float) -> str:
    return MISSING if pd.isna(value) else f"{int(value)}"


def rates_table(cities: pd.DataFrame) -> pd.DataFrame:
    table = cities[RATE_TABLE_COLUMNS].copy()
    for column in COUNT_COLUMNS:
        table[column] = table[column].map(count_or_missing)
    return table


def rates_chart(cities: pd.DataFrame) -> alt.LayerChart:
    reconciled = cities.dropna(subset=["taxa"])
    base = alt.Chart(reconciled).encode(y=city_axis(reconciled.sort_values("taxa")["municipio"].tolist()))
    axis = alt.Axis(format="%", grid=False)
    interval = base.mark_rule(strokeWidth=2, color=blue, opacity=0.4).encode(
        x=alt.X("ic_inferior:Q", title="Com par no PNCP", axis=axis), x2="ic_superior:Q"
    )
    tooltip = ["municipio", alt.Tooltip("taxa:Q", format=".0%"), "elegiveis", "casados", "pncp_contratos"]
    rate = base.mark_circle(size=90, color=blue, opacity=1).encode(x="taxa:Q", tooltip=tooltip)
    return (interval + rate).properties(height=alt.Step(28))


def coverage_chart(coverage: pd.DataFrame) -> alt.Chart:
    labels = ["com texto", "sem texto"]
    data = coverage.assign(**{"com texto": coverage["ok"], "sem texto": coverage["diarios"] - coverage["ok"]})
    order = data.sort_values(["pct_texto", "municipio"])["municipio"].tolist()
    stacked = data.melt(["municipio", "pct_texto"], labels, var_name="texto", value_name="quantidade")
    scale = alt.Scale(domain=labels, range=[blue, orange])
    return (
        alt.Chart(stacked)
        .mark_bar(stroke=surface, strokeWidth=2)
        .encode(
            y=city_axis(order),
            x=alt.X("quantidade:Q", title="Diários", stack="zero", axis=alt.Axis(grid=False)),
            color=alt.Color("texto:N", title=None, legend=alt.Legend(orient="top"), scale=scale),
            tooltip=["municipio", "texto", "quantidade", "pct_texto"],
        )
        .properties(height=alt.Step(26))
    )


def render_metrics(atos: pd.DataFrame, eligible: pd.DataFrame, coverage: pd.DataFrame) -> None:
    read_col, matched_col, unmatched_col, no_text_col = st.columns(4)
    read_col.metric("Extratos de contrato lidos", f"{len(atos):,}".replace(",", "."))
    matched_col.metric(
        "Com par no PNCP", f"{(eligible['status'] == MATCHED).mean():.0%}", help="casados / elegíveis"
    )
    unmatched_col.metric("Sem par no PNCP", f"{(eligible['status'] == UNMATCHED).mean():.0%}")
    no_text_col.metric("Municípios sem texto no diário", int((coverage["pct_texto"] == 0).sum()))


def render_rates_tab(cities: pd.DataFrame) -> None:
    st.subheader("Extratos com par no PNCP, por município")
    st.altair_chart(rates_chart(cities), use_container_width=True)
    st.caption("O ponto é a taxa; a barra, o intervalo de confiança de 95% (Wilson).")
    progress = st.column_config.ProgressColumn("com par", format="percent", min_value=0, max_value=1)
    st.dataframe(
        rates_table(cities), column_config={"taxa": progress}, hide_index=True, use_container_width=True
    )


def search_atos(atos: pd.DataFrame, query: str) -> pd.DataFrame:
    scores = dict(index().search(query, k=MAX_SEARCH_HITS))
    return atos[atos["ato_id"].isin(scores)].sort_values("ato_id", key=lambda s: -s.map(scores))


def render_ato_details(ato: pd.Series) -> None:
    text_col, data_col = st.columns([3, 2])
    text_col.text(ato["text"])
    data_col.markdown(f"**Situação:** {ato['status']}  \n**Diário:** [{ato['date']}]({ato['url']})")
    if pd.notna(ato["pncp_numero_controle"]):
        data_col.markdown(
            f"**PNCP:** `{ato['pncp_numero_controle']}`  \n**Fornecedor:** {ato['pncp_fornecedor']}  \n"
            f"**Valor no PNCP:** R$ {ato['pncp_valor']:,.2f}"
        )


def render_atos_tab(atos: pd.DataFrame, cities: pd.DataFrame) -> None:
    query_col, city_col, status_col = st.columns([3, 2, 2])
    query = query_col.text_input(
        "Buscar nos extratos",
        placeholder="merenda escolar, locação de veículos",
        max_chars=MAX_QUERY_CHARS,
    )
    city = city_col.selectbox("Município", ["Todos", *cities["municipio"]])
    statuses = status_col.multiselect("Situação", list(ELIGIBLE), default=list(ELIGIBLE))

    shown = atos[atos["status"].isin(statuses) & ((atos["territory_name"] == city) | (city == "Todos"))]
    if query.strip():
        shown = search_atos(shown, query)
    st.caption(f"{len(shown)} extratos")
    picked = st.dataframe(
        shown[ATO_TABLE_COLUMNS],
        hide_index=True,
        use_container_width=True,
        on_select="rerun",
        selection_mode="single-row",
    )
    if picked.selection.rows:
        render_ato_details(shown.iloc[picked.selection.rows[0]])


def render_coverage_tab(coverage: pd.DataFrame) -> None:
    st.subheader("Texto disponível no Querido Diário, por município")
    st.caption("Em alguns municípios o arquivo de texto traz só o link para o PDF da prefeitura.")
    st.altair_chart(coverage_chart(coverage), use_container_width=True)


def render_page() -> None:
    coverage, cities, atos = load()
    eligible = atos[atos["status"].isin(list(ELIGIBLE))]

    st.title("Lacuna")
    st.markdown(
        "Extratos de contrato dos diários oficiais de municípios do RJ, conferidos contra o "
        f"Portal Nacional de Contratações Públicas (PNCP). [Código e metodologia]({REPO})"
    )
    render_metrics(atos, eligible, coverage)
    st.caption(
        "Outubro de 2025 a setembro de 2026. Elegível é o extrato de contrato com fornecedor e valor "
        "identificado; contratação temporária de pessoal fica de fora, porque não vai para o PNCP. "
        "Um ato sem par é uma lacuna de dados, não uma irregularidade."
    )
    tab_rates, tab_atos, tab_coverage = st.tabs(["Conciliação", "Atos", "Cobertura do diário"])
    with tab_rates:
        render_rates_tab(cities)
    with tab_atos:
        render_atos_tab(atos, cities)
    with tab_coverage:
        render_coverage_tab(coverage)


render_page()
