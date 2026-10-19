---
id: TASK-12
title: Clé technique marchand distincte du libellé affiché
status: Done
assignee:
  - '@claude'
created_date: '2026-10-07 20:21'
updated_date: '2026-10-07 20:34'
labels:
  - bug
  - backend
dependencies: []
ordinal: 12000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
PUT /api/merchants/{merchant} renvoie 404 quand le nom normalisé contient un '/' (ex. 'KEREIS FRANCE POUR CARDIF / /') : Starlette décode %2F avant le routage. Le nom affiché sert aujourd'hui aussi de clé de regroupement et d'URL ; il faut une clé stable sans espaces ni caractères spéciaux, séparée du libellé affiché.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 Chaque transaction porte une merchant_key alphanumérique (A-Z0-9) dérivée du marchand normalisé
- [x] #2 Les corrections manuelles et le cache LLM sont indexés par merchant_key
- [x] #3 Le dashboard envoie la merchant_key dans PUT /api/merchants/{key} ; un marchand contenant '/' se met à jour sans 404
- [x] #4 Les bases existantes sont migrées au démarrage (colonne ajoutée, clés calculées, overrides repris)
- [x] #5 Les tokens purement ponctuation ('/') ne figurent plus dans le nom affiché
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
1. normalize.merchant_key() + filtre des tokens sans alphanumérique dans extract_merchant
2. db: colonne transactions.merchant_key, merchant_overrides indexé par merchant_key, migration idempotente dans init_db, insert calcule la clé
3. classifier/insights: regroupement et overrides par clé, LLM reçoit toujours le nom affiché
4. main.py + index.html: route et select par clé
5. Tests
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
pytest: 26 passed (nouveaux tests : clé marchand, PUT par clé avec '/', migration legacy idempotente). Migration testée sur une copie de data/budget.db : 0 merchant_key NULL, 265 overrides migrés, 'KEREIS FRANCE POUR CARDIF / /' -> 'KEREIS FRANCE POUR CARDIF'. PUT /api/merchants/KEREISFRANCEPOURCARDIF -> 26 opérations mises à jour (sur la copie). AC3 : API vérifiée, JS du dashboard vérifié syntaxiquement ; clic réel dans le navigateur non fait (extension Chrome déconnectée) — à valider après rebuild du conteneur docker.

AC3 couvert par tests TestClient sur libellés piégeux (/, %, #, ?, accents, espaces) dans TASK-13.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
merchant_key A-Z0-9 distincte du nom affiché, utilisée en URL/regroupement/overrides ; migration testée. Vérifié par pytest.
<!-- SECTION:FINAL_SUMMARY:END -->
