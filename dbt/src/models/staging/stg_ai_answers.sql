-- Staging : les réponses des modèles, nettoyage léger uniquement.
-- La colonne prompt n'est pas reprise : le prompt est le même partout, il n'apporte rien à l'analyse.
SELECT
    question_id,
    model,
    ai_answer,
    -- Lettre réellement choisie par le modèle : "A." ou " a" → "A"
    UPPER(LEFT(TRIM(ai_answer), 1)) AS ai_letter,
    ai_correct,
    response_time
FROM {{ source('silver', 'ai_answers') }}
