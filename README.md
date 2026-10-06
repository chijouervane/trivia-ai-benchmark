# Trivia AI Benchmark

Benchmark des performances d'un ou plusieurs modèles d'IA (via Ollama) sur des questions de culture générale issues d'[Open Trivia Database](https://opentdb.com/), avec une architecture en médaillon (bronze/silver/gold) et un dashboard Streamlit.

Projet M1 Data Engineering (Efrei) — voir [`PLAN.md`](./docs/PLAN.md) pour le déroulé détaillé étape par étape.

## Architecture

```
.
├── data/
│   ├── bronze/     # questions_raw.csv — données brutes scrapées depuis OpenTDB
│   ├── silver/     # Parquet — questions nettoyées + réponses IA brutes
│   └── gold/        # DuckDB — marts métier (schéma "gold")
├── dbt_project/
│   ├── dbt_project.yml
│   ├── profiles.yml.example   # à copier vers ~/.dbt/profiles.yml
│   └── src/models/
│       ├── sources.yml
│       ├── staging/           # vues — 1 modèle par source brute
│       ├── intermediate/      # tables — jointures et enrichissements communs
│       └── marts/             # tables (schéma gold) — 1 modèle par question métier
├── ingestion/      # scripts Python : scraping OpenTDB + enrichissement via Ollama
├── app/            # application Streamlit (dashboard)
├── docs/           # local only (gitignored): PLAN.md, opentdb_api.md
└── requirements.txt
```

## Setup

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# Ollama
ollama pull <modele>   # ex: llama3.2:1b, gemma2:2b

# dbt — copier la config utilisateur (hors repo)
cp dbt_project/profiles.yml.example ~/.dbt/profiles.yml
```

## Pipeline

1. **Scraping** (`ingestion/`) : récupération de l'intégralité du dataset OpenTDB → `data/bronze/questions_raw.csv`
2. **Enrichissement IA** (`ingestion/`) : pour chaque question, appel au modèle via Ollama, mesure du temps de réponse, calcul de `ai_correct` → `data/silver/questions_enriched.parquet`
3. **Transformation dbt** (`dbt_project/`) : staging → intermediate → marts (gold)
   ```bash
   cd dbt_project
   dbt run
   dbt test
   ```
4. **Dashboard** (`app/`) :
   ```bash
   streamlit run app/app.py
   ```

## Méthodologie

Voir [`PLAN.md`](./docs/PLAN.md) pour le détail des choix techniques, le planning et le brief complet.
