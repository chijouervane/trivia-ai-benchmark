# Trivia AI Benchmark

Benchmark de modèles d'IA locaux (via [Ollama](https://ollama.com/)) sur les questions de culture générale d'[Open Trivia Database](https://opentdb.com/) : collecte des données, enrichissement par l'IA, modélisation en architecture médaillon (bronze / silver / gold) avec dbt et DuckDB, puis restitution dans un dashboard Streamlit.

Projet M1 Data Engineering — Efrei, module *Data Lakes & Data Integration*.

## Résultats

5 296 questions posées à chaque modèle, avec le même prompt (QCM et vrai/faux, réponse par lettre).

| Modèle | Bonnes réponses | Temps moyen par question* |
|---|---|---|
| `gemma2:2b` | **62,3 %** | 0,14 s |
| `qwen2.5:1.5b` | 54,3 % | **0,08 s** |

\* Mesuré sur Google Colab (GPU T4), sur la même machine pour les deux modèles.

- Les deux modèles font nettement mieux que le hasard (25 % en QCM, 50 % en vrai/faux), surtout en QCM (+37 points pour `gemma2:2b`).
- La précision baisse avec la difficulté : de 70,5 % (facile) à 53,8 % (difficile) pour `gemma2:2b`.
- Thèmes les mieux réussis : mythologie et art (> 80 %) ; les moins bien réussis : jeux vidéo, anime/manga et jeux de société (35 à 47 %).
- **Biais de position** : quand il hésite, chaque modèle privilégie certaines lettres (`gemma2:2b` choisit C dans 32 % des cas au lieu de 24 % attendus, `qwen2.5:1.5b` sur-choisit A et B).

## Architecture

```
API OpenTDB ──► BRONZE ──────────────► SILVER ─────────────────────────► GOLD ──────────────► Streamlit
               questions_raw.csv      questions.parquet                  trivia.duckdb
               (brut, tel quel)       ai_answers_<modele>.parquet        (marts, schéma gold)
                                      (nettoyé + réponses brutes IA)
   scripts/scrape_opentdb.py   scripts/clean_questions.py        dbt : staging → intermediate → marts     app/app.py
                               scripts/enrich_ollama.py (Ollama)
```

```
.
├── data/
│   ├── bronze/     # questions_raw.csv — données brutes scrapées depuis OpenTDB
│   ├── silver/     # Parquet — questions nettoyées + réponses brutes des modèles
│   └── gold/       # trivia.duckdb — marts métier (schéma gold), généré par dbt
├── scripts/        # Python : scraping, nettoyage, enrichissement IA
├── dbt/
│   ├── dbt_project.yml
│   ├── profiles.yml           # connexion DuckDB (aucun secret, lu depuis dbt/)
│   └── src/models/
│       ├── sources.yml        # déclaration des fichiers Parquet silver
│       ├── staging/           # vues — stg_questions, stg_ai_answers (+ tests)
│       ├── intermediate/      # table — int_questions_with_answers (jointure)
│       └── marts/             # tables (schéma gold) — 1 modèle par question métier
├── app/app.py      # dashboard Streamlit
└── requirements.txt
```

Les données (CSV, Parquet, DuckDB) ne sont pas versionnées : elles sont régénérées par le pipeline.

## Setup

Prérequis : [uv](https://docs.astral.sh/uv/) et [Ollama](https://ollama.com/download). La version de Python (3.14.7) est fixée dans `.python-version`.

```bash
uv venv                              # crée .venv/ avec la version de .python-version
uv pip install -r requirements.txt   # installe les dépendances dans .venv/

ollama pull gemma2:2b
ollama pull qwen2.5:1.5b
```

## Lancer le pipeline

Toutes les commandes depuis la racine du projet, sauf dbt (depuis `dbt/`).

| Étape | Commande | Produit | Durée |
|---|---|---|---|
| 1. Bronze : scraping | `uv run python scripts/scrape_opentdb.py` | `data/bronze/questions_raw.csv` | ~10 min (limite de l'API) |
| 2. Silver : nettoyage | `uv run python scripts/clean_questions.py` | `data/silver/questions.parquet` | quelques secondes |
| 3. Silver : réponses IA | `uv run python scripts/enrich_ollama.py gemma2:2b` puis `… qwen2.5:1.5b` | `data/silver/ai_answers_<modele>.parquet` | ~10 min par modèle sur GPU, ~3–4 h sur CPU |
| 4. Gold : dbt | `cd dbt && uv run dbt run && uv run dbt test` | `data/gold/trivia.duckdb` | quelques secondes |
| 5. Dashboard | `uv run streamlit run app/app.py` | application web | — |

Lignage dbt (graphe visuel) : `cd dbt && uv run dbt docs generate && uv run dbt docs serve`.

## Méthodologie

### Bronze — collecte (`scrape_opentdb.py`)
- Récupération de **toutes les questions vérifiées** de l'API OpenTDB (5 299), par lots de 50.
- **Token de session** : l'API ne renvoie jamais deux fois la même question.
- **Rate limit** : une requête toutes les 5,5 s (l'API en autorise une toutes les 5 s).
- Sauvegarde **sans transformation** en CSV (format imposé), entités HTML comprises : bronze = copie fidèle de la source.

### Silver — nettoyage (`clean_questions.py`)
- Décodage des entités HTML (`&quot;` → `"`), suppression des espaces superflus.
- **Clé `question_id`** = hash SHA-256 de `question | bonne réponse` : l'API ne fournit pas d'identifiant, on utilise une clé de hachage plutôt qu'un ID auto-incrémenté.
- **Qualité** : 3 questions présentes en double dans OpenTDB supprimées → 5 296 questions.
- Mélange des choix de réponse (graine fixe, donc reproductible), sinon la bonne réponse serait toujours en premier.
- Écriture en **Parquet** (typé, compressé zstd, colonnes de type liste conservées).

### Silver — enrichissement IA (`enrich_ollama.py`)
- Chaque question est posée au modèle via l'API Python d'Ollama, avec un **prompt standardisé** identique pour toutes les questions et tous les modèles :
  ```
  Answer the following trivia question.
  Reply with ONLY the letter of the correct choice, nothing else.

  Question: …
  Choices:
  A. …
  B. …
  Answer:
  ```
- **Choix du prompt** : trois variantes testées sur un échantillon de 50 questions avec `llama3.2:1b` — réponse par lettre (54 %), réponse par le texte du choix (50 %), consignes en français (26 %, le modèle se met à rédiger des phrases en français au lieu de répondre). La réponse par lettre est retenue : meilleure précision, plus rapide, et la correction devient une simple comparaison de lettres (pas besoin de normaliser casse, accents ou synonymes).
- **Température 0** : le modèle donne toujours la même réponse à la même question → benchmark reproductible.
- Colonnes ajoutées : `ai_answer` (réponse brute), `ai_correct` (1re lettre de la réponse = lettre de la bonne réponse), `response_time` (secondes, mesuré autour de l'appel au modèle uniquement, après un appel de chauffe qui charge le modèle).
- **Un fichier Parquet par modèle** : les questions ne sont stockées qu'une fois, ajouter un modèle = ajouter un fichier.

### Choix des modèles
- Petits modèles (1,5 à 2 milliards de paramètres), adaptés à une machine personnelle : `gemma2:2b` (Google) et `qwen2.5:1.5b` (Alibaba).
- Génération exécutée sur **Google Colab (GPU T4)** avec Ollama, avec l'accord de l'enseignant : sur le CPU du PC, un modèle prenait 3 à 4 heures, contre une dizaine de minutes sur GPU. Les deux modèles ont tourné sur la même machine, donc leurs temps de réponse sont comparables.

### Gold — dbt + DuckDB
- **Sources** : les Parquet silver sont déclarés une seule fois dans `sources.yml` (`read_parquet`, avec `ai_answers_*.parquet` pour lire tous les modèles).
- **Staging** (vues) : `stg_questions` (+ lettre de la bonne réponse), `stg_ai_answers` (+ lettre choisie, sans la colonne `prompt`). Seul le staging lit les sources.
- **Tests de qualité** (`dbt test`) : `question_id` unique et non nul, chaque réponse reliée à une question existante.
- **Intermediate** (table) : `int_questions_with_answers`, la jointure réponses × questions réutilisée par tous les marts.
- **Marts** (tables, schéma gold — `main_gold` dans DuckDB) :

| Mart | Question métier |
|---|---|
| `mart_model_comparison` | Quel modèle répond le mieux, et à quelle vitesse ? |
| `mart_accuracy_by_category` | Sur quels thèmes les modèles sont-ils forts ou faibles ? |
| `mart_accuracy_by_difficulty` | Se trompent-ils davantage sur les questions difficiles ? |
| `mart_accuracy_by_type` | Font-ils mieux que le hasard (QCM vs vrai/faux) ? |
| `mart_letter_bias` | Quand ils hésitent, choisissent-ils toujours la même lettre ? |

### Dashboard (`app/app.py`)
Lit les marts dans `data/gold/trivia.duckdb` (lecture seule) : vue d'ensemble, précision par thème, par difficulté, comparaison au hasard et biais de position, avec un filtre par modèle et le tableau de chaque graphique.

## Limites
- **Questions à choix** : le modèle reconnaît la bonne réponse parmi des propositions, ce qui est plus facile que d'y répondre librement.
- **Hasard** : une partie des bonnes réponses vient du hasard (25 % en QCM, 50 % en vrai/faux) — d'où le mart de comparaison au hasard.
- **Biais de position** : un seul ordre de choix par question ; un autre mélange donnerait des scores légèrement différents.
- **Un seul prompt** pour le benchmark complet ; les variantes n'ont été comparées que sur 50 questions.
