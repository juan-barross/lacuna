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
PALETTE = {
    "light": {
        "casado": "#2a78d6",
        "sem par": "#eb6834",
        "provável": "#1baf7a",
        "surface": "#ffffff",
    },
    "dark": {
        "casado": "#3987e5",
        "sem par": "#d95926",
        "provável": "#199e70",
        "surface": "#0e1117",
    },
}

st.set_page_config(page_title="Lacuna", layout="wide")
colors = PALETTE.get(st.context.theme.type or "light", PALETTE["light"])


@st.cache_resource
def load():
    coverage = pd.read_csv(DATA / "cobertura.csv", dtype={"territory_id": str})
    rates = pd.read_csv(DATA / "conciliacao.csv", dtype={"territory_id": str})
    pncp = pd.read_csv(DATA / "pncp_contratos.csv", dtype={"territory_id": str})
    cities = coverage[["territory_id", "municipio", "pct_texto"]].merge(
        rates.drop(columns="municipio"), on="territory_id", how="left"
    )
    cities = cities.merge(pncp, on="territory_id", how="left").fillna({"pncp_contratos": 0})
    cities["ordem"] = cities["municipio"].map(sort_key)
    atos = pq.read_table(DATA / "atos.parquet").to_pandas()
    return coverage, cities, atos


@st.cache_resource
def index() -> BM25:
    return BM25(pq.read_table(DATA / "atos.parquet", columns=["ato_id", "text"]))


coverage, cities, atos = load()
eligible = atos[atos["status"].isin(STATUSES)]
matched = (eligible["status"] == "casado").sum()
reconciled = cities.dropna(subset=["taxa"])

st.title("Lacuna")
st.markdown(
    "Extratos de contrato dos diários oficiais de municípios do RJ, conferidos contra o "
    f"Portal Nacional de Contratações Públicas (PNCP). [Código e metodologia]({REPO})"
)
c1, c2, c3, c4 = st.columns(4)
c1.metric("Extratos de contrato lidos", f"{len(atos):,}".replace(",", "."))
c2.metric("Com par no PNCP", f"{matched / len(eligible):.0%}", help="casados / elegíveis")
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
    order = reconciled.sort_values("taxa")["municipio"].tolist()
    base = alt.Chart(reconciled).encode(
        y=alt.Y("municipio:N", sort=order, title=None, axis=alt.Axis(labelLimit=220))
    )
    rule = base.mark_rule(strokeWidth=2, color=colors["casado"], opacity=0.4).encode(
        x=alt.X("ic_inferior:Q", title="Com par no PNCP", axis=alt.Axis(format="%", grid=False)),
        x2="ic_superior:Q",
    )
    dot = base.mark_circle(size=90, color=colors["casado"], opacity=1).encode(
        x="taxa:Q",
        tooltip=[
            alt.Tooltip("municipio:N", title="Município"),
            alt.Tooltip("taxa:Q", title="Com par", format=".0%"),
            alt.Tooltip("ic_inferior:Q", title="IC 95% de", format=".0%"),
            alt.Tooltip("ic_superior:Q", title="até", format=".0%"),
            alt.Tooltip("elegiveis:Q", title="Extratos elegíveis"),
            alt.Tooltip("pncp_contratos:Q", title="Contratos no PNCP"),
        ],
    )
    st.altair_chart((rule + dot).properties(height=alt.Step(28)), use_container_width=True)
    st.caption("O ponto é a taxa; a barra, o intervalo de confiança de 95% (Wilson).")

    table = cities.sort_values("ordem").assign(
        situacao=lambda d: d["taxa"].map(lambda t: "conciliado" if pd.notna(t) else "sem texto")
    )
    columns = {
        "municipio": "Município",
        "situacao": "Situação",
        "elegiveis": "Elegíveis",
        "casados": "Casados",
        "provaveis": "Prováveis",
        "sem_par": "Sem par",
        "taxa": "Com par",
        "pncp_contratos": "Contratos no PNCP",
    }
    st.dataframe(
        table[list(columns)].rename(columns=columns),
        column_config={
            "Com par": st.column_config.ProgressColumn(format="percent", min_value=0, max_value=1)
        },
        hide_index=True,
        use_container_width=True,
    )

with tab_atos:
    left, mid, right = st.columns([3, 2, 2])
    query = left.text_input(
        "Buscar nos extratos", placeholder="merenda escolar, locação de veículos"
    )
    names = sorted(atos["territory_name"].unique(), key=sort_key)
    city = mid.selectbox("Município", ["Todos", *names])
    status = right.multiselect("Situação", STATUSES, default=STATUSES)

    shown = atos[atos["status"].isin(status)]
    if city != "Todos":
        shown = shown[shown["territory_name"] == city]
    if query.strip():
        hits = dict(index().search(query, k=500))
        shown = shown[shown["ato_id"].isin(hits)].assign(score=lambda d: d["ato_id"].map(hits))
        shown = shown.sort_values("score", ascending=False)

    st.caption(f"{len(shown)} extratos")
    columns = {
        "territory_name": "Município",
        "date": "Diário",
        "contratada_nome": "Contratada (extraída)",
        "valor": "Valor (R$)",
        "status": "Situação",
        "pncp_fornecedor": "Fornecedor no PNCP",
    }
    picked = st.dataframe(
        shown[list(columns)].rename(columns=columns),
        column_config={"Valor (R$)": st.column_config.NumberColumn(format="%.2f")},
        hide_index=True,
        use_container_width=True,
        on_select="rerun",
        selection_mode="single-row",
    )
    if picked.selection.rows:
        ato = shown.iloc[picked.selection.rows[0]]
        text_col, data_col = st.columns([3, 2])
        text_col.text(ato["text"])
        data_col.markdown(f"**Situação:** {ato['status']}")
        data_col.markdown(f"**Diário:** [{ato['date']}]({ato['url']})")
        if pd.notna(ato["pncp_numero_controle"]):
            data_col.markdown(f"**PNCP:** `{ato['pncp_numero_controle']}`")
            data_col.markdown(f"**Fornecedor no PNCP:** {ato['pncp_fornecedor']}")
            data_col.markdown(f"**Valor no PNCP:** R$ {ato['pncp_valor']:,.2f}")

with tab_coverage:
    st.subheader("Texto disponível no Querido Diário, por município")
    st.caption(
        "Em alguns municípios o arquivo de texto do Querido Diário traz só o link para o PDF da "
        "prefeitura, então os extratos não podem ser lidos automaticamente."
    )
    data = coverage.assign(
        sem_texto=coverage["diarios"] - coverage["ok"],
        tem_texto=coverage["pct_texto"] > 0,
        ordem=coverage["municipio"].map(sort_key),
    )
    order = data.sort_values(["tem_texto", "ordem"])["municipio"].tolist()
    long = data.melt(
        id_vars=["municipio", "pct_texto"],
        value_vars=["ok", "sem_texto"],
        var_name="c",
        value_name="n",
    )
    long["c"] = long["c"].map({"ok": "Com texto", "sem_texto": "Sem texto"})
    scale = alt.Scale(
        domain=["Com texto", "Sem texto"], range=[colors["casado"], colors["sem par"]]
    )
    chart = (
        alt.Chart(long)
        .mark_bar(stroke=colors["surface"], strokeWidth=2)
        .encode(
            y=alt.Y("municipio:N", sort=order, title=None, axis=alt.Axis(labelLimit=220)),
            x=alt.X("n:Q", title="Diários", stack="zero", axis=alt.Axis(grid=False)),
            color=alt.Color("c:N", title=None, legend=alt.Legend(orient="top"), scale=scale),
            tooltip=[
                alt.Tooltip("municipio:N", title="Município"),
                alt.Tooltip("c:N", title="Situação"),
                alt.Tooltip("n:Q", title="Diários"),
                alt.Tooltip("pct_texto:Q", title="% com texto", format=".1f"),
            ],
        )
        .properties(height=alt.Step(26))
    )
    st.altair_chart(chart, use_container_width=True)
