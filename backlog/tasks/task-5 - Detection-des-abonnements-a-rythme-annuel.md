---
id: TASK-5
title: Detection des abonnements a rythme annuel
status: To Do
assignee: []
created_date: '2026-09-29 19:52'
labels: []
milestone: m-1
dependencies: []
priority: medium
type: feature
ordinal: 5000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
detect_recurring (app/insights.py) ne reconnait que les prelevements a rythme mensuel (RECURRING_INTERVAL 25-35 jours). Les abonnements factures une fois par an (assurances, certains logiciels) ne sont donc jamais signales comme recurrents alors qu'ils representent souvent le plus gros montant unitaire.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Un prelevement au meme marchand, montant stable, revenant a environ 365 jours d'intervalle sur au moins 2 occurrences est detecte comme abonnement annuel
- [ ] #2 Le resultat distingue la cadence (mensuelle/annuelle) dans la reponse de /api/summary
- [ ] #3 Les tests couvrent un cas annuel en plus du cas mensuel existant
<!-- AC:END -->
