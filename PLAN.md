# Plan de travail — Benchmark IA sur Trivial Poursuite (M1 DE)

Dates : 06 & 07 octobre 2026 — Rendu en projet GitHub, groupe de 2.

## 0. Cadrage (30 min, à faire en premier)

- Créer le repo GitHub tout de suite, avec un `README.md` vide et une structure de dossiers dès le départ :
  ```
  /data/bronze
  /data/silver
  /data/gold
  /dbt_project
  /ingestion        # scripts de scraping + appel IA
  /app              # Streamlit
  ```
- Choisir 1 ou 2 modèles **petits** (ex. `llama3.2:1b` ou `gemma2:2b`) — avec le temps imparti, un modèle lourd coûtera des heures en génération. Comparer 2 petits modèles est plus réaliste qu'1 gros modèle.

### ⚠️ Contrainte : un seul PC pour les deux

Vous ne pouvez pas vraiment paralléliser "une personne code l'ingestion, l'autre code dbt" en même temps sur deux machines. Mais le scraping (attente réseau) et surtout la génération IA (Ollama qui tourne question par question) sont du temps **mort** côté humain — c'est ce temps qu'il faut exploiter :

- **Dès que vous avez un petit échantillon** (ex. 50-100 questions enrichies), lancez la génération IA complète en arrière-plan dans un terminal (`python enrich.py &` ou un terminal à part), et pendant que ça tourne, l'autre personne travaille sur dbt/Streamlit **sur ce même PC**, dans un autre terminal/éditeur, en utilisant l'échantillon comme données de test.
- Committez/poussez souvent sur des branches séparées (`feat/ingestion`, `feat/dbt`, `feat/streamlit`) pour éviter de vous marcher dessus sur le même repo, et faites des merges courts et fréquents plutôt qu'un gros merge en fin de journée.
- Répartition concrète suggérée :
  - **Personne A** : écrit et lance le scraping + le script d'enrichichissement IA (c'est elle qui "possède" le clavier pendant ces phases).
  - **Personne B** : pendant que A code/lance ses scripts, B écrit sur papier/dans un fichier texte à part la structure des modèles dbt (schéma staging/intermediate/mart, requêtes SQL des marts) et le squelette Streamlit, puis vient les coder dès que le PC se libère ou dès qu'un terminal est dispo.
- Alternez qui a la main sur le PC plutôt que d'essayer de coder à deux en même temps sur le même clavier — ça évite les blocages.

## 1. Dataset de questions (couche Bronze)

- API OpenTDB : `https://opentdb.com/api.php?amount=50&category=...`. Voir `https://opentdb.com/api_config.php` pour la liste des catégories et le nombre de questions dispo par catégorie/difficulté (limite de 50 par requête).
- Pour récupérer l'intégralité du dataset : boucler sur toutes les catégories et difficultés, avec pagination, en gérant :
  - le **rate limit** (une requête toutes les ~5s sinon code 429),
  - les **tokens de session** OpenTDB (`api_token`) pour éviter les doublons de questions si beaucoup de pagination.
- Sauvegarder le résultat brut, sans transformation, dans `data/bronze/questions_raw.csv` (garder même les entités HTML encodées telles que l'API les renvoie — le nettoyage se fait en Silver, pas ici).

## 2. Intégration IA + enrichissement (vers Silver)

- Installer Ollama, `ollama pull <modele>`, tester en CLI que ça répond avant de scripter.
- Utiliser le package Python `ollama` (ou des requêtes HTTP vers `localhost:11434`) pour boucler sur chaque question.
- Fixer un **prompt standardisé** dès le départ (ex. forcer une réponse courte/un seul terme) et le garder versionné (constante ou fichier `prompts.yaml`) — possibilité de tester des variantes ensuite, mais il faut une version de référence stable pour ne pas repartir de zéro.
- Mesurer `response_time` autour de l'appel au modèle (pas autour du nettoyage).
- Comparer "réponse IA" vs "bonne réponse" n'est pas trivial (casse, accents, synonymes, formulations). Prévoir une fonction de normalisation (minuscule, strip accents/ponctuation) avant de calculer `ai_correct` — documenter cette logique.
- Stocker ce résultat enrichi en **Parquet** dans `data/silver` (réponses brutes du modèle + flags), c'est la couche "pré-traitée".

## 3. Modélisation dbt (staging → intermediate → mart, dans DuckDB)

Ceci reprend **exactement** les conventions vues en Cours 3 (TP Spotify) — mêmes fichiers de config, même logique de dossiers, juste adaptés à vos données.

### 3.1 Installation et config (identique au TP vu en cours)

```bash
pip install dbt-duckdb
```

Deux fichiers de config, comme dans le TP Spotify :

**`dbt_project.yml`** (à la racine du projet dbt) :
```yaml
name: 'projet_trivia'
version: '1.0.0'
profile: 'trivia_tp'

model-paths: ['src/models']

models:
  projet_trivia:
    staging:
      +materialized: view      # couche brute → juste un alias, pas de copie

    intermediate:
      +materialized: table     # étapes réutilisées → on matérialise

    marts:
      +materialized: table     # agrégats métier → toujours en table
      +schema: gold            # isolés dans le schéma "gold" du warehouse
```

**`profiles.yml`** (⚠️ **hors** du dossier projet, dans `~/.dbt/profiles.yml`, **pas** dans le repo Git) :
```yaml
trivia_tp:
  target: dev
  outputs:
    dev:
      type: duckdb
      path: warehouse/trivia.duckdb
```

Le nom du profil (`trivia_tp`) doit être identique entre les deux fichiers.

### 3.2 Déclarer les sources Silver (`src/models/sources.yml`)

Même astuce que le TP Spotify : on déclare une seule fois le chemin Parquet via `meta.external_location`, pour ne jamais le réécrire dans chaque modèle.

```yaml
version: 2

sources:
  - name: silver
    tables:
      - name: questions
        meta:
          external_location: "read_parquet('./silver/questions_enriched.parquet')"
```

(Si vous séparez questions et réponses IA en deux fichiers Parquet, déclarez une table `silver` par fichier.)

### 3.3 Les 3 couches de modèles

- **`src/models/staging/`** (vue) : un modèle par source brute, simple renommage/cast/normalisation légère — pas de jointure, pas de logique métier. Ex. `stg_questions.sql`, `stg_ai_answers.sql` (normalisation des réponses, cast des types, etc.) :
  ```sql
  -- src/models/staging/stg_questions.sql
  SELECT * FROM {{ source('silver', 'questions') }}
  ```
  Toute requête en aval doit référencer `{{ ref('stg_questions') }}`, **jamais** `{{ source(...) }}` directement — exactement l'erreur `drake_tracks` vs `beyonce_tracks` vue en cours : si vous changez une règle de nettoyage dans le staging, les modèles qui contournent le staging ne la recevront jamais.
- **`src/models/intermediate/`** (table) : jointures et enrichissements communs réutilisés par plusieurs marts, ex. `int_questions_with_answers.sql` (jointure questions + réponses IA + prompt utilisé + flag correct/incorrect si le calcul est coûteux).
- **`src/models/marts/`** (table, schéma `gold`) : un modèle par question métier, ex. :
  - `mart_accuracy_by_category`
  - `mart_accuracy_by_difficulty`
  - `mart_response_time_stats`
  - `mart_model_comparison` (si plusieurs modèles testés)
  - `mart_prompt_comparison` (si plusieurs prompts testés)

### 3.4 Exécution et vérification

```bash
dbt run     # depuis la racine du projet dbt, jamais depuis un sous-dossier
dbt test
```

⚠️ Fermez toute connexion DuckDB ouverte (shell `duckdb ...`) avant de lancer `dbt run` — DuckDB verrouille son fichier tant qu'une connexion est active.

Pour vérifier le résultat dans un second terminal :
```bash
duckdb warehouse/trivia.duckdb
SHOW TABLES;
```

### 3.5 Documentation et lignage (bonus si le temps le permet)

```bash
dbt docs generate
dbt docs serve
```

Donne un graphe de lignage visuel staging → intermediate → marts, exploitable pour la présentation. Les fichiers `target/manifest.json` et `target/catalog.json` peuvent aussi être donnés à une IA pour générer le squelette Streamlit (méthode montrée en cours) — mais gardez la logique métier et la relecture sous votre contrôle, l'exercice reste à faire vous-mêmes.

## 4. Dashboard Streamlit

- Se connecter directement au fichier DuckDB gold (`duckdb.connect('path.duckdb')`), lire les marts avec des requêtes SQL simples.
- Un onglet/une section par axe d'analyse : performance globale, par catégorie, par difficulté, par temps de réponse, comparaison modèles/prompts.
- Garder ça simple (metrics + bar charts/tables) — mieux vaut un dashboard qui tourne que 10 graphiques ambitieux à moitié finis.

## 5. Livrables finaux

- **README.md** : architecture (bronze/silver/gold), setup (comment installer Ollama, lancer dbt, lancer Streamlit), choix de modèles/prompts et pourquoi.
- **Présentation 10 min** : se préparer à justifier chaque choix technique (pourquoi DuckDB, pourquoi dbt, pourquoi ce prompt, pourquoi ce modèle).

## Planning suggéré sur 2 jours (1 seul PC)

| Quand | Qui a le clavier | Quoi |
|---|---|---|
| J1 matin | A | Scraping OpenTDB complet → bronze |
| J1 matin (en parallèle, papier/texte) | B | Dessine le schéma staging/intermediate/mart et les requêtes SQL cibles des marts |
| J1 après-midi | A | Setup Ollama + script d'enrichissement, lancé d'abord sur un petit échantillon pour valider, puis lancé en fond sur tout le dataset |
| J1 après-midi (pendant que la génération tourne en fond) | B | Code le squelette dbt (staging + intermediate) sur l'échantillon, prend le clavier dès qu'un terminal est libre |
| J1 fin de journée | A/B | Merge, vérif que bronze/silver sont complets |
| J2 matin | B | Marts gold (DuckDB) |
| J2 matin (en parallèle, papier/texte) | A | Prépare les maquettes des sections Streamlit et le plan de la présentation |
| J2 après-midi | A/B alterné | Streamlit + README + répétition de la présentation |

## Brief original

<aside>

**Date :** 06 & 07 octobre 2026
**Format du rendu :** Projet Github
**En groupes de 2**

</aside>

### Objectif

Concevoir un **rapport de benchmark** évaluant les performances d'un ou plusieurs modèles d'IA sur des questions de culture générale.

L'exercice permet de mettre en œuvre un **pipeline complet** de data ingénierie :
- collecte et intégration de données,
- enrichissement par appel à des modèles d'IA,
- génération et visualisation de résultats.

### Étape 1 : Constitution d'un dataset de questions de culture générale

1. **Source de données** :
    - Utiliser le site Open Trivia Database (OpenTDB), une API publique proposant des milliers de questions catégorisées (science, histoire, divertissement, etc.).
    - Scraper ces données pour récupérer l'intégralité du dataset proposé.

### Étape 2 : Module de data intégration & enrichissement avec un modèle d'IA

1. **Intégration de l'IA** :
    - Installer Ollama ou LMStudio (runtimes légers permettant d'exécuter localement des modèles LLM).
    - Télécharger un modèle adapté à la machine (par exemple `llama`, `gemma`, ou tout autre modèle supporté).
    - Utiliser l'**API Python** de l'outil pour automatiser la génération de réponses IA :
    - Pour chaque question du dataset, interroger le modèle et stocker la réponse générée.
2. **Enrichissement du dataset** :
    - Ajouter les colonnes suivantes :
        - `ai_answer` : réponse donnée par le modèle
        - `ai_correct` : booléen (`True` si la réponse IA correspond à la bonne réponse)
        - `response_time` : temps de génération mesuré en secondes

#### Importance du prompt

Le **prompt** (la façon dont la question est posée au modèle) influence fortement la qualité des réponses obtenues.
- Une même question peut donner des résultats très différents selon le contexte fourni.
- Exemple :
    - Prompt simple : *"Qui a peint la Joconde ?"*
    - Prompt plus robuste : *"Réponds uniquement par un nom propre. Question : Qui a peint la Joconde ?"*
    - Il existe des versions **encore plus optimisées**, à trouver.
- Il est recommandé de **standardiser les prompts** pour que le benchmark soit cohérent.
- Possibilité de tester plusieurs variantes de prompt afin d'observer leur impact sur :
    - le **taux de bonnes réponses**,
    - la **longueur et précision** des réponses,
    - la **robustesse** face aux ambiguïtés.
- Pour un benchmark rigoureux, garder une trace de la formulation du prompt dans le dataset.

### Étape 3 : Rapport de benchmark

Produire un **rapport d'analyse des résultats** afin de comparer les performances du modèle.

#### Analyses possibles

- **Performance globale** : taux de bonnes réponses (%)
- **Par catégorie** : précision par thème (histoire, sciences, etc.)
- **Par niveau de difficulté** : facile vs difficile
- **Par temps de réponse** : rapidité moyenne par question
- **Comparaison de modèles** : exécuter le benchmark avec plusieurs modèles disponibles et comparer leurs performances
- **Analyses exploratoires supplémentaires** : identifier et proposer d'autres axes d'analyse pertinents à partir des données
- Etc.

### Méthodologie

Mettre en place une architecture en médaillon pour stocker les données de ce projet.

**Architecture attendue :**
- `Couche bronze` : données brutes issues du scraping : `questions_raw.csv`
- `Couche silver` : données pré-traitées (nettoyage, normalisation, etc.) + réponses brutes du/des modèles `en parquet`
    - Silver contient des observations propres et exploitables
- `Couche gold` : données métiers (performance des modèles, performance des prompts, etc.) `format duckdb`
    - Gold répond directement à une question métier

Dans la granularité des couches Silver et Gold, utiliser l'organisation `staging`, `intermediate` et `mart` vue en TP (dans une base duckdb).

**Ingénierie des données attendue :**
- Utilisation de dbt pour construire le lignage `staging → intermediate → gold`.

**Visualisation des résultats du benchmark :**
- Utiliser **Streamlit** pour produire un dashboard interactif des résultats du benchmark.

### Livrables attendus

**Une présentation de 10 min avec questions/réponses**

Être en capacité d'expliquer les choix techniques, d'identifier les briques élémentaires de data ingénierie demandées et de répondre à des questions liées à l'exploitation des données.

**Un dépôt GitHub contenant :**
1. L'architecture de projet complète
2. Un `README.md` expliquant la méthodologie, l'organisation du projet et le setup complet
3. Une **application Streamlit** pour un rapport interactif
