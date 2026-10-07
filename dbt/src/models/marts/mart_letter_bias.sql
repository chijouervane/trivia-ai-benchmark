-- Gold (analyse exploratoire) : biais de position sur les QCM.
-- Question métier : « Quand il ne sait pas, le modèle choisit-il toujours la même lettre ? »
-- On compare la fréquence de chaque lettre répondue à la fréquence de cette lettre
-- comme bonne réponse : sans biais, les deux pourcentages sont proches (~25 %).
WITH qcm AS (
    SELECT * FROM {{ ref('int_questions_with_answers') }}
    WHERE type = 'multiple'
),

answered AS (
    -- Combien de fois le modèle a répondu chaque lettre
    SELECT model, ai_letter AS letter, COUNT(*) AS nb_answered
    FROM qcm
    GROUP BY model, ai_letter
),

expected AS (
    -- Combien de fois chaque lettre est la bonne réponse
    SELECT model, correct_letter AS letter, COUNT(*) AS nb_expected
    FROM qcm
    GROUP BY model, correct_letter
)

SELECT
    e.model,
    e.letter,
    COALESCE(a.nb_answered, 0)                                                    AS nb_answered,
    e.nb_expected,
    ROUND(COALESCE(a.nb_answered, 0) * 100.0 / SUM(e.nb_expected) OVER (PARTITION BY e.model), 1) AS answered_pct,
    ROUND(e.nb_expected * 100.0 / SUM(e.nb_expected) OVER (PARTITION BY e.model), 1)            AS expected_pct
FROM expected AS e
LEFT JOIN answered AS a
    ON a.model = e.model AND a.letter = e.letter
ORDER BY e.model, e.letter
