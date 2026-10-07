-- Gold : précision et temps de réponse par niveau de difficulté et par modèle.
-- Question métier : « Les modèles se trompent-ils davantage sur les questions difficiles ? »
SELECT
    model,
    difficulty,
    COUNT(*)                               AS nb_questions,
    ROUND(AVG(ai_correct::INT) * 100, 1)   AS accuracy_pct,
    ROUND(AVG(response_time), 3)           AS avg_response_time_s
FROM {{ ref('int_questions_with_answers') }}
GROUP BY model, difficulty
-- Ordre logique easy → medium → hard plutôt qu'alphabétique
ORDER BY model, CASE difficulty WHEN 'easy' THEN 1 WHEN 'medium' THEN 2 ELSE 3 END
