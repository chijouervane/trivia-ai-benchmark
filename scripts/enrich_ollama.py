"""
Silver : enrichissement des questions avec les réponses d'un modèle d'IA (Ollama).

Lit data/silver/questions.parquet, pose chaque question au modèle et écrit
data/silver/ai_answers_<modele>.parquet avec les colonnes demandées :
    - ai_answer     : réponse brute du modèle
    - ai_correct    : True si le modèle a donné la bonne réponse
    - response_time : temps de génération en secondes

Prérequis : serveur Ollama lancé et modèle téléchargé (ollama pull <modele>).
Lancement : uv run python scripts/enrich_ollama.py [modele]   (défaut : gemma2:2b)
"""

import re
import sys
import time
import unicodedata
from pathlib import Path

import ollama
import pandas as pd
from tqdm import tqdm

# --- Paramètres du benchmark : à modifier ici ---
# Le modèle peut être donné en argument : uv run python scripts/enrich_ollama.py gemma2:2b
MODEL = sys.argv[1] if len(sys.argv) > 1 else "gemma2:2b"
LIMIT = None  # nombre de questions à traiter ; None = tout le dataset

# Prompt standardisé : le même pour toutes les questions et tous les modèles.
# Prompt retenu après tests sur 50 questions (lettres 54 %, texte 50 %, consignes en français 26 %) :
# choix numérotés A, B, C, D, le modèle répond seulement par la lettre
PROMPT_TEMPLATE = """Answer the following trivia question.
Reply with ONLY the letter of the correct choice, nothing else.

Question: {question}
Choices:
{choices}
Answer:"""

LETTERS = "ABCD"

ROOT = Path(__file__).resolve().parent.parent
INPUT = ROOT / "data" / "silver" / "questions.parquet"
# Un fichier par modèle ("llama3.2:1b" → "llama3.2-1b") : dbt les lira tous avec un *
OUTPUT = ROOT / "data" / "silver" / f"ai_answers_{MODEL.replace(':', '-')}.parquet"


def build_prompt(question, choices):
    """Insère la question et les choix numérotés (A. ..., B. ...) dans le prompt."""
    choices_text = "\n".join(f"{letter}. {choice}" for letter, choice in zip(LETTERS, choices))
    return PROMPT_TEMPLATE.format(question=question, choices=choices_text)


def normalize(text):
    """Rend une réponse comparable : minuscules, sans accents ni ponctuation.

    Ex. : " Léonard de Vinci. " → "leonard de vinci"
    """
    text = unicodedata.normalize("NFKD", text)  # sépare les lettres de leurs accents (é → e + ´)
    text = text.encode("ascii", "ignore").decode("ascii")  # supprime les accents
    text = re.sub(r"[^\w\s]", "", text.lower())  # supprime la ponctuation
    return " ".join(text.split())  # supprime les espaces en trop


def is_correct(ai_answer, question):
    """Compare la lettre donnée par le modèle à la lettre de la bonne réponse."""
    # Lettre attendue = position de la bonne réponse dans les choix mélangés
    expected = LETTERS[list(question.choices).index(question.correct_answer)]
    return ai_answer[:1].upper() == expected  # 1re lettre de la réponse ("D." → "D")


def ask(prompt):
    """Pose la question au modèle. Renvoie (réponse, temps de génération en secondes)."""
    start = time.perf_counter()
    # temperature 0 : toujours la même réponse à la même question → benchmark reproductible
    response = ollama.generate(model=MODEL, prompt=prompt, options={"temperature": 0})
    elapsed = time.perf_counter() - start  # mesuré autour de l'appel au modèle uniquement
    return response["response"].strip(), elapsed


df = pd.read_parquet(INPUT)
if LIMIT:
    df = df.head(LIMIT)

# Premier appel « à vide » : charge le modèle en mémoire, pour ne pas fausser
# le temps de réponse de la première question
ask("Hello")

rows = []
for i, question in enumerate(tqdm(df.itertuples(), total=len(df), desc=MODEL)):
    prompt = build_prompt(question.question, question.choices)
    ai_answer, response_time = ask(prompt)
    rows.append({
        "question_id": question.question_id,
        "model": MODEL,
        "prompt": prompt,
        "ai_answer": ai_answer,
        "ai_correct": is_correct(ai_answer, question),
        "response_time": round(response_time, 3),
    })
    # Sauvegarde régulière : si le script plante au bout d'une heure, on ne perd pas tout
    if i % 200 == 0:
        pd.DataFrame(rows).to_parquet(OUTPUT, index=False, compression="zstd")

result = pd.DataFrame(rows)
result.to_parquet(OUTPUT, index=False, compression="zstd")
print(f"{len(result)} réponses écrites dans {OUTPUT}")
print(f"Taux de bonnes réponses : {result['ai_correct'].mean():.1%}")
print(f"Temps de réponse moyen : {result['response_time'].mean():.2f} s")
