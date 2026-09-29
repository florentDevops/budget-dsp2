---
id: TASK-2
title: Alerte avant expiration du consentement bancaire
status: To Do
assignee: []
created_date: '2026-09-29 19:52'
labels: []
milestone: m-0
dependencies: []
priority: high
type: feature
ordinal: 2000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Le consentement Enable Banking expire au plus tard a 180 jours (settings.consent_days). Passe ce delai, la synchro echoue silencieusement jusqu'a ce que l'utilisateur reconnecte sa banque a la main.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Le dashboard signale un compte dont le consentement (valid_until) expire dans moins de 15 jours
- [ ] #2 Le signal reste visible tant que le compte n'a pas ete reconnecte
<!-- AC:END -->
