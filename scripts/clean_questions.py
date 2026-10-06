"""
Bronze → Silver : nettoyage des questions OpenTDB.

Lit data/bronze/questions_raw.csv et écrit data/silver/questions.parquet :
    1. décodage des entités HTML (&quot; → ", &#039; → ', etc.)
    2. création d'un identifiant question_id (hash), l'API n'en fournit pas
    3. suppression des doublons présents dans la source
    4. préparation des choix mélangés pour le prompt (colonne choices)

Lancement : uv run python scripts/clean_questions.py   (quelques secondes)
"""

import ast
import hashlib
import html
import random
from pathlib import Path

import pandas as pd

# Chemins construits à partir de l'emplacement du script : marche depuis n'importe quel dossier
ROOT = Path(__file__).resolve().parent.parent
INPUT = ROOT / "data" / "bronze" / "questions_raw.csv"
OUTPUT = ROOT / "data" / "silver" / "questions.parquet"

# Graine fixe : les choix sont mélangés de la même façon à chaque exécution (reproductible)
random.seed(42)


def make_id(question, correct_answer):
    """Clé de hachage calculée à partir du contenu (Cours 2 : pas d'ID auto-incrémenté)."""
    key = f"{question}|{correct_answer}"
    return hashlib.sha256(key.encode("utf-8")).hexdigest()[:16]


def shuffle_choices(row):
    """Mélange bonne et mauvaises réponses, sinon la bonne serait toujours en premier."""
    choices = [row["correct_answer"]] + row["incorrect_answers"]
    random.shuffle(choices)
    return choices


df = pd.read_csv(INPUT)
print(f"{len(df)} questions lues depuis le bronze")

# 1. Décodage HTML + suppression des espaces en début/fin
for column in ["category", "question", "correct_answer"]:
    df[column] = df[column].map(html.unescape).str.strip()

# incorrect_answers est stocké en texte "['a', 'b']" dans le CSV → on le relit en vraie liste
df["incorrect_answers"] = df["incorrect_answers"].map(
    lambda text: [html.unescape(answer).strip() for answer in ast.literal_eval(text)]
)

# 2. Identifiant unique de chaque question (après le nettoyage, pour que " Paris" = "Paris")
df["question_id"] = [make_id(q, a) for q, a in zip(df["question"], df["correct_answer"])]

# 3. Qualité de la donnée : OpenTDB contient quelques questions en double
duplicates = df["question_id"].duplicated().sum()
df = df.drop_duplicates(subset="question_id")
print(f"{duplicates} doublon(s) supprimé(s)")

# 4. Choix proposés au modèle (QCM : 4 choix, vrai/faux : 2 choix)
df["choices"] = df.apply(shuffle_choices, axis=1)

# Écriture en Parquet compressé zstd (comme le script du cours), question_id en premier
columns = ["question_id", "type", "difficulty", "category", "question",
           "correct_answer", "incorrect_answers", "choices"]
OUTPUT.parent.mkdir(parents=True, exist_ok=True)
df[columns].to_parquet(OUTPUT, index=False, compression="zstd")
print(f"{len(df)} questions écrites dans {OUTPUT}")
