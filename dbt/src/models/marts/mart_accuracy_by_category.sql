-- Gold : précision par thème et par modèle.
-- Question métier : « Sur quels thèmes les modèles sont-ils forts ou faibles ? »
SELECT
    model,
    category,
    COUNT(*)                               AS nb_questions,
    ROUND(AVG(ai_correct::INT) * 100, 1)   AS accuracy_pct
FROM {{ ref('int_questions_with_answers') }}
GROUP BY model, category
ORDER BY model, accuracy_pct DESC
