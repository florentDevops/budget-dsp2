---
id: TASK-10
title: HTTPS et chiffrement au repos pour un usage expose
status: To Do
assignee: []
created_date: '2026-09-29 19:53'
labels: []
milestone: m-3
dependencies: []
priority: high
type: feature
ordinal: 10000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Le README recommande HTTPS et le chiffrement du disque/de la base en cas d'exposition, mais rien dans le projet ne l'implemente ou ne le documente concretement au-dela de la recommandation generale.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Une configuration documentee permet de servir l'app en HTTPS (reverse proxy ou TLS applicatif)
- [ ] #2 Le README documente une methode concrete pour chiffrer la base SQLite ou le volume qui la contient
<!-- AC:END -->
