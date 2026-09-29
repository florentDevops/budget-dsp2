---
id: TASK-9
title: Authentification devant le dashboard
status: To Do
assignee: []
created_date: '2026-09-29 19:53'
labels: []
milestone: m-3
dependencies: []
priority: high
type: feature
ordinal: 9000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
README > Securite : l'app n'a aucune authentification et n'est prevue que pour un usage local. Avant toute exposition au-dela de localhost, un login est necessaire pour ne pas laisser l'historique bancaire accessible a quiconque atteint le port 8000.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Toutes les routes /api/* et le dashboard exigent une authentification, sauf en developpement local explicite
- [ ] #2 Les identifiants ne sont pas stockes en clair
- [ ] #3 La documentation (README) explique comment configurer l'authentification avant une exposition reseau
<!-- AC:END -->
