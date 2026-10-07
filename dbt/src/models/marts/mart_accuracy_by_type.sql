-- Gold : précision par type de question, comparée au hasard.
-- Question métier : « Le modèle fait-il mieux que s'il répondait au hasard ? »
-- QCM : 4 choix → 25 % au hasard ; vrai/faux : 2 choix → 50 % au hasard.
SELECT
    model,
    type,
    COUNT(*)                                               AS nb_questions,
    ROUND(AVG(ai_correct::INT) * 100, 1)                   AS accuracy_pct,
    CASE type WHEN 'multiple' THEN 25.0 ELSE 50.0 END      AS chance_pct,
    ROUND(AVG(ai_correct::INT) * 100
        - CASE type WHEN 'multiple' THEN 25.0 ELSE 50.0 END, 1) AS gain_vs_chance_pct
FROM {{ ref('int_questions_with_answers') }}
GROUP BY model, type
ORDER BY model, type
