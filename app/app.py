"""
Dashboard Streamlit du benchmark : lit les marts de la couche gold (DuckDB).

Prérequis : `dbt run` lancé depuis dbt/ (crée data/gold/trivia.duckdb).
Lancement : uv run streamlit run app/app.py
"""

from pathlib import Path

import altair as alt
import duckdb
import streamlit as st

ROOT = Path(__file__).resolve().parent.parent
DB_PATH = ROOT / "data" / "gold" / "trivia.duckdb"
SCHEMA = "main_gold"  # dbt préfixe le schéma personnalisé "gold" par le schéma par défaut "main"

# Une couleur fixe par modèle (palette vérifiée daltonisme) : la couleur suit le
# modèle, jamais son rang, même quand on filtre
MODEL_COLORS = {
    "gemma2:2b": "#2a78d6",
    "qwen2.5:1.5b": "#eb6834",
}
EXTRA_COLORS = ["#1baf7a", "#eda100", "#e87ba4"]  # si d'autres modèles sont ajoutés
REFERENCE_GRAY = "#9a998f"  # valeurs de référence (hasard, fréquence attendue)

st.set_page_config(page_title="Benchmark IA – Trivia", layout="wide")


@st.cache_data
def load(mart):
    """Lit une table du schéma gold. Connexion en lecture seule : ne bloque pas dbt."""
    with duckdb.connect(str(DB_PATH), read_only=True) as con:
        return con.execute(f"SELECT * FROM {SCHEMA}.{mart}").df()


def color_scale(models):
    """Échelle de couleurs Altair : chaque modèle garde toujours la même couleur."""
    extra = iter(EXTRA_COLORS)
    colors = [MODEL_COLORS.get(m) or next(extra) for m in models]
    return alt.Scale(domain=list(models), range=colors)


def grouped_bars(df, category, title, sort=None):
    """Barres horizontales groupées : une barre par modèle pour chaque catégorie."""
    return (
        alt.Chart(df)
        .mark_bar(cornerRadiusEnd=4)
        .encode(
            y=alt.Y(f"{category}:N", title=None, sort=sort, axis=alt.Axis(labelLimit=320)),
            yOffset=alt.YOffset("model:N"),
            x=alt.X("accuracy_pct:Q", title="Bonnes réponses (%)", scale=alt.Scale(domain=[0, 100])),
            color=alt.Color("model:N", title="Modèle", scale=color_scale(all_models),
                            legend=alt.Legend(orient="top")),
            tooltip=[alt.Tooltip("model:N", title="Modèle"),
                     alt.Tooltip(f"{category}:N", title=title),
                     alt.Tooltip("accuracy_pct:Q", title="Bonnes réponses (%)"),
                     alt.Tooltip("nb_questions:Q", title="Questions")],
        )
    )


# --- Vérification : la base gold existe-t-elle ? ---
if not DB_PATH.exists():
    st.error(f"Base gold introuvable : {DB_PATH}\n\nLancer d'abord `dbt run` depuis le dossier dbt/.")
    st.stop()

st.title("Benchmark de modèles d'IA sur des questions de culture générale")
st.caption("Questions : Open Trivia DB · Modèles exécutés avec Ollama · "
           "Pipeline : bronze (CSV) → silver (Parquet) → gold (DuckDB, dbt)")

comparison = load("mart_model_comparison")
all_models = sorted(comparison["model"])

# Filtre unique, au-dessus de tous les graphiques
selected = st.multiselect("Modèles affichés", all_models, default=all_models)
if not selected:
    st.info("Sélectionner au moins un modèle.")
    st.stop()


def only_selected(df):
    return df[df["model"].isin(selected)].copy()  # copie : on peut modifier sans toucher au cache


overview, by_category, by_difficulty, vs_chance, bias = st.tabs(
    ["Vue d'ensemble", "Par catégorie", "Par difficulté", "Comparaison au hasard", "Biais de position"]
)

# --- 1. Vue d'ensemble : performance globale + temps de réponse ---
with overview:
    data = only_selected(comparison).sort_values("accuracy_pct", ascending=False)

    # Chiffres clés : un bloc par modèle
    for col, row in zip(st.columns(len(data)), data.itertuples()):
        col.metric(row.model, f"{row.accuracy_pct:.1f} % de bonnes réponses")
        col.caption(f"{row.avg_response_time_s:.2f} s par question · {row.nb_questions} questions")

    # Deux graphiques séparés (deux unités différentes → jamais deux axes sur un même graphique)
    left, right = st.columns(2)
    base = alt.Chart(data).encode(y=alt.Y("model:N", title=None, sort="-x"))
    # La couleur identifie le modèle sur les barres ; les valeurs restent en texte neutre
    model_color = alt.Color("model:N", scale=color_scale(all_models), legend=None)
    with left:
        st.subheader("Taux de bonnes réponses")
        bars = base.mark_bar(cornerRadiusEnd=4, height=22).encode(
            color=model_color,
            x=alt.X("accuracy_pct:Q", title="Bonnes réponses (%)", scale=alt.Scale(domain=[0, 100])),
            tooltip=[alt.Tooltip("model:N", title="Modèle"),
                     alt.Tooltip("accuracy_pct:Q", title="Bonnes réponses (%)"),
                     alt.Tooltip("nb_correct:Q", title="Réponses justes"),
                     alt.Tooltip("nb_questions:Q", title="Questions")],
        )
        labels = base.mark_text(align="left", dx=4, color="gray").encode(
            x="accuracy_pct:Q", text=alt.Text("accuracy_pct:Q", format=".1f"))
        st.altair_chart(bars + labels, width="stretch")
    with right:
        st.subheader("Temps de réponse moyen")
        bars = base.mark_bar(cornerRadiusEnd=4, height=22).encode(
            color=model_color,
            x=alt.X("avg_response_time_s:Q", title="Secondes par question"),
            tooltip=[alt.Tooltip("model:N", title="Modèle"),
                     alt.Tooltip("avg_response_time_s:Q", title="Temps moyen (s)")],
        )
        labels = base.mark_text(align="left", dx=4, color="gray").encode(
            x="avg_response_time_s:Q", text=alt.Text("avg_response_time_s:Q", format=".2f"))
        st.altair_chart(bars + labels, width="stretch")

    with st.expander("Voir le tableau"):
        st.dataframe(data, hide_index=True)

# --- 2. Par catégorie ---
with by_category:
    data = only_selected(load("mart_accuracy_by_category"))
    st.subheader("Précision par thème")
    # Thèmes triés par précision moyenne, du meilleur au moins bon
    order = data.groupby("category")["accuracy_pct"].mean().sort_values(ascending=False).index.tolist()
    st.altair_chart(grouped_bars(data, "category", "Thème", sort=order).properties(height=len(order) * 34),
                    width="stretch")
    with st.expander("Voir le tableau"):
        st.dataframe(data, hide_index=True)

# --- 3. Par difficulté ---
with by_difficulty:
    data = only_selected(load("mart_accuracy_by_difficulty"))
    st.subheader("Précision par niveau de difficulté")
    st.altair_chart(grouped_bars(data, "difficulty", "Difficulté", sort=["easy", "medium", "hard"])
                    .properties(height=260), width="stretch")
    with st.expander("Voir le tableau"):
        st.dataframe(data, hide_index=True)

# --- 4. Comparaison au hasard (QCM vs vrai/faux) ---
with vs_chance:
    data = only_selected(load("mart_accuracy_by_type"))
    data["type"] = data["type"].map({"multiple": "QCM (4 choix)", "boolean": "Vrai / Faux (2 choix)"})
    st.subheader("Le modèle fait-il mieux que le hasard ?")
    st.caption("Trait gris : score obtenu en répondant au hasard (25 % en QCM, 50 % en vrai/faux).")
    chance = (
        alt.Chart(data.drop_duplicates("type"))
        .mark_tick(color=REFERENCE_GRAY, thickness=2, size=44)
        .encode(y="type:N", x="chance_pct:Q",
                tooltip=[alt.Tooltip("chance_pct:Q", title="Hasard (%)")])
    )
    st.altair_chart((grouped_bars(data, "type", "Type") + chance).properties(height=200),
                    width="stretch")
    with st.expander("Voir le tableau"):
        st.dataframe(data, hide_index=True)

# --- 5. Biais de position (analyse exploratoire) ---
with bias:
    data = only_selected(load("mart_letter_bias"))
    st.subheader("Quelle lettre le modèle choisit-il en QCM ?")
    st.caption("Sans biais, chaque lettre serait choisie à peu près aussi souvent qu'elle est "
               "la bonne réponse (~25 %). Un écart montre une préférence pour une position.")
    model = st.selectbox("Modèle", [m for m in all_models if m in selected])
    one = data[data["model"] == model]
    # Format long : une ligne par (lettre, mesure) pour afficher les deux barres côte à côte
    long = one.melt(id_vars="letter", value_vars=["answered_pct", "expected_pct"],
                    var_name="mesure", value_name="pct")
    long["mesure"] = long["mesure"].map({"answered_pct": "Choisie par le modèle",
                                         "expected_pct": "Bonne réponse"})
    chart = (
        alt.Chart(long)
        .mark_bar(cornerRadiusEnd=4)
        .encode(
            x=alt.X("letter:N", title="Lettre", axis=alt.Axis(labelAngle=0),
                    scale=alt.Scale(paddingInner=0.4)),
            xOffset=alt.XOffset("mesure:N"),
            y=alt.Y("pct:Q", title="% des réponses"),
            color=alt.Color("mesure:N", title=None, legend=alt.Legend(orient="top"),
                            scale=alt.Scale(domain=["Choisie par le modèle", "Bonne réponse"],
                                            range=[MODEL_COLORS.get(model, EXTRA_COLORS[0]), REFERENCE_GRAY])),
            tooltip=[alt.Tooltip("letter:N", title="Lettre"),
                     alt.Tooltip("mesure:N", title="Mesure"),
                     alt.Tooltip("pct:Q", title="%")],
        )
        .properties(height=320)
    )
    st.altair_chart(chart, width="stretch")
    with st.expander("Voir le tableau"):
        st.dataframe(one, hide_index=True)
