-- Intermediate : jointure réponses + questions, réutilisée par tous les marts.
-- Une ligne par (question, modèle). Matérialisée en table (dbt_project.yml) :
-- la jointure est faite une fois au lieu d'être refaite dans chaque mart.
SELECT
    a.question_id,
    a.model,
    q.type,
    q.difficulty,
    q.category,
    q.question,
    q.correct_answer,
    q.correct_letter,
    a.ai_answer,
    a.ai_letter,
    a.ai_correct,
    a.response_time
FROM {{ ref('stg_ai_answers') }} AS a
JOIN {{ ref('stg_questions') }} AS q
    ON a.question_id = q.question_id
