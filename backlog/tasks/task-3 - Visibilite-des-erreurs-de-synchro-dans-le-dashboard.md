---
id: TASK-3
title: Visibilite des erreurs de synchro dans le dashboard
status: To Do
assignee: []
created_date: '2026-09-29 19:52'
labels: []
milestone: m-0
dependencies: []
priority: medium
type: enhancement
ordinal: 3000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
POST /api/sync renvoie deja un champ errors par compte, mais rien dans app/static/index.html ne l'affiche : les echecs passent inapercus tant que l'utilisateur ne regarde pas les logs serveur.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Une erreur de synchro pour un compte est visible dans le dashboard apres l'appel a /api/sync
- [ ] #2 Le message affiche identifie le compte concerne
<!-- AC:END -->
