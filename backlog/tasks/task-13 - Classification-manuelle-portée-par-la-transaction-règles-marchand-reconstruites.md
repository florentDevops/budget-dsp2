---
id: TASK-13
title: >-
  Classification manuelle portée par la transaction, règles marchand
  reconstruites
status: Done
assignee:
  - '@claude'
created_date: '2026-10-07 20:33'
updated_date: '2026-10-07 20:34'
labels:
  - backend
dependencies: []
ordinal: 13000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Les corrections manuelles ne vivent que dans merchant_overrides, indexé par merchant_key. Si la normalisation des libellés évolue, la clé change et la correction est perdue au prochain reclassement. La transaction doit devenir la source de vérité ; la règle marchand en est déduite. Suite de TASK-12 ; la clé reste lisible (A-Z0-9).
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 Une correction manuelle est stockée sur chaque transaction concernée et survit à un reclassement forcé même sans merchant_overrides
- [x] #2 Une nouvelle opération d'un marchand corrigé hérite de la correction
- [x] #3 Si merchant_key() évolue, les clés stockées sont recalculées au démarrage et les règles marchand utilisateur reconstruites depuis les transactions (correction la plus récente gagne)
- [x] #4 Les bases existantes migrent : les transactions class_source=user conservent leur catégorie comme correction manuelle
- [x] #5 Tests : toute clé générée est A-Z0-9 et PUT /api/merchants/{key} répond 200 pour des libellés piégeux (/, %, #, ?, accents, espaces)
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
TDD : 1. tests rouges (survie au reclassement, héritage, recalcul des clés, migration, clés URL-safe) 2. colonnes user_category/user_nature + migration 3. classify_one prioritise user_category, apply_user_override écrit sur les transactions 4. init_db recalcule les clés et reconstruit les overrides user 5. vert
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
TDD : 3 tests rouges (survie reclassement, recalcul clés, migration legacy) puis vert ; 40 passed. Copie de data/budget.db migrée 2x : 198/198 corrections conservées en user_category, 83 règles user reconstruites. Héritage sur nouvelle opération par la règle marchand (overrides) ; reconstruite depuis les transactions au démarrage.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
user_category/user_nature sur transactions = source de vérité des corrections manuelles ; merchant_overrides user reconstruit au démarrage après recalcul des clés. Vérifié par 40 tests pytest et migration sur copie de la base réelle.
<!-- SECTION:FINAL_SUMMARY:END -->
