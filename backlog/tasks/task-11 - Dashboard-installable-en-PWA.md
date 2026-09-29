---
id: TASK-11
title: Dashboard installable en PWA
status: To Do
assignee: []
created_date: '2026-09-29 19:53'
labels: []
milestone: m-4
dependencies: []
priority: low
type: feature
ordinal: 11000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
app/static/index.html est deja un dashboard sans dependance front, mais il n'est pas installable ni utilisable hors ligne sur mobile, ce qui limite la consultation du budget en dehors de l'ordinateur.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Le dashboard est installable comme PWA (manifest + service worker) sur mobile et desktop
- [ ] #2 La derniere vue /api/summary chargee reste consultable hors connexion
<!-- AC:END -->
