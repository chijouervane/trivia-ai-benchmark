-- Gold : performance globale de chaque modèle (taux de bonnes réponses + rapidité).
-- Question métier : « Quel modèle répond le mieux, et à quelle vitesse ? »
SELECT
    model,
    COUNT(*)                                   AS nb_questions,
    SUM(ai_correct::INT)                       AS nb_correct,
    ROUND(AVG(ai_correct::INT) * 100, 1)       AS accuracy_pct,
    ROUND(AVG(response_time), 3)               AS avg_response_time_s
FROM {{ ref('int_questions_with_answers') }}
GROUP BY model
ORDER BY accuracy_pct DESC
