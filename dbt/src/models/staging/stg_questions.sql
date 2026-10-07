-- Staging : les questions telles qu'en silver, avec une seule colonne ajoutée.
-- Tous les modèles en aval passent par ce modèle, jamais par la source (Cours 3, DRY).
SELECT
    question_id,
    type,
    difficulty,
    category,
    question,
    correct_answer,
    choices,
    -- Lettre de la bonne réponse dans les choix mélangés (A = 1er choix, B = 2e…).
    -- list_position renvoie la position (à partir de 1), chr(65) = 'A'
    chr(64 + list_position(choices, correct_answer)) AS correct_letter
FROM {{ source('silver', 'questions') }}
