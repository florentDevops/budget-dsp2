---
id: TASK-14
title: 'Page tendances : dépenses par catégorie mois par mois'
status: Done
assignee:
  - '@claude'
created_date: '2026-10-14 19:57'
updated_date: '2026-10-14 20:04'
labels: []
dependencies: []
ordinal: 14000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Le dashboard ne montre qu'un mois à la fois : impossible de voir d'un coup d'oeil quelle catégorie pèse le plus d'un mois à l'autre, ni si la part non classée (À classer) grossit. Besoin d'une page dédiée avec l'historique mensuel par catégorie.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 GET /api/trends renvoie, pour chaque mois disponible (ordre chronologique), les dépenses par catégorie, À classer inclus, épargne et virements exclus
- [x] #2 Une page /tendances affiche un histogramme empilé par mois avec une teinte fixe par catégorie et la part À classer distincte
- [x] #3 Choisir une catégorie la place en bas de la pile (alignée sur l'axe) et atténue les autres pour comparer les mois
- [x] #4 Un tableau catégorie x mois donne les montants exacts
- [x] #5 Tests pytest et node couvrent l'API et la logique d'empilement
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
1. insights.category_trends + GET /api/trends (pytest d'abord)
2. app/static/trends.js : groupSeries/stackOrder/lastMonths/niceStep purs (node --test d'abord)
3. trends.html servie sur /tendances : barres empilées SVG, légende-filtre, tooltip, tableau heatmap
4. Tokens CSS -> theme.css et CAT_COLOR -> colors.js, partagés avec index.html
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
pytest 76 ok, node --test 11 ok. Rendu vérifié en Chrome headless sur la démo (vue d'ensemble et ?cat=livraison). Catégories sans teinte propre (livraison, frais, retraits, impôts) regroupées dans Autres sauf si focalisées, pour ne pas se confondre avec son gris. Non vérifié dans un vrai navigateur : clic sur les pastilles/lignes et survol (extension Chrome déconnectée).

Interactions vérifiées en Chrome headless piloté par CDP : clic pastille (focus, 48 segments atténués, montants sous l'axe), clic ligne du tableau (Livraison sortie de Autres), re-clic (retour vue d'ensemble), survol/sortie d'une colonne (tooltip affiché puis masqué), aucune erreur JS. Choix (épargne/virements exclus, catégories sans teinte dans Autres) validés par l'utilisateur.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Page /tendances : barres empilées des dépenses par catégorie et par mois (teinte fixe par catégorie, À classer hachuré), focus d'une catégorie posée sur l'axe, tableau heatmap catégorie x mois, période 6/12/tout. API GET /api/trends (insights.category_trends). Tokens CSS et couleurs extraits dans theme.css/colors.js. Vérifié : pytest 76 ok, node --test 11 ok, rendu et interactions en Chrome headless sur la démo.
<!-- SECTION:FINAL_SUMMARY:END -->
