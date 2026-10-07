"""
Scraping de toutes les questions vérifiées d'Open Trivia DB → couche bronze.

L'API renvoie du JSON ; on l'enregistre tel quel (entités HTML comprises)
dans data/bronze/questions_raw.csv. Le nettoyage se fait plus tard, en silver.

Lancement : uv run python scripts/scrape_opentdb.py   (~10 min)
"""

import time
from pathlib import Path

import pandas as pd
import requests

BASE_URL = "https://opentdb.com"

# Chemin construit à partir de l'emplacement du script : marche depuis n'importe quel dossier
OUTPUT = Path(__file__).resolve().parent.parent / "data" / "bronze" / "questions_raw.csv"


def get(endpoint, params=None):
    """Appelle un endpoint OpenTDB et renvoie la réponse JSON sous forme de dict."""
    time.sleep(5.5)  # rate limit : 1 requête toutes les 5 s par IP (+0,5 s de marge)
    return requests.get(f"{BASE_URL}/{endpoint}", params=params, timeout=30).json()


# Avec un token de session, l'API ne renvoie jamais deux fois la même question
token = get("api_token.php", {"command": "request"})["token"]

# Nombre de questions vérifiées = ce que api.php peut réellement renvoyer
stats = get("api_count_global.php")
remaining = stats["overall"]["total_num_of_verified_questions"]
print(f"{remaining} questions à récupérer")

all_questions = []
while remaining > 0:
    # Ne jamais demander plus que ce qu'il reste : si amount > questions non vues,
    # l'API renvoie un code 4 sans résultat au lieu d'un lot partiel
    data = get("api.php", {"amount": min(50, remaining), "token": token})
    if data["response_code"] != 0:  # 4 = token épuisé, 5 = rate limit...
        print(f"Arrêt anticipé, response_code={data['response_code']}")
        break
    all_questions.extend(data["results"])
    remaining -= len(data["results"])
    print(f"{len(all_questions)} questions récupérées")

# JSON → CSV : une ligne par question, une colonne par clé JSON
OUTPUT.parent.mkdir(parents=True, exist_ok=True)  # data/bronze/ n'existe pas après un git clone
pd.DataFrame(all_questions).to_csv(OUTPUT, index=False)
print(f"{len(all_questions)} questions enregistrées dans {OUTPUT}")
