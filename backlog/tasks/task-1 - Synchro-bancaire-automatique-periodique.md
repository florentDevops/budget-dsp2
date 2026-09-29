---
id: TASK-1
title: Synchro bancaire automatique periodique
status: To Do
assignee: []
created_date: '2026-09-29 19:52'
labels: []
milestone: m-0
dependencies: []
priority: high
type: feature
ordinal: 1000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Aujourd'hui la synchro (/api/sync) est declenchee manuellement depuis le dashboard. Pour un usage quotidien reel, les operations doivent arriver sans action de l'utilisateur.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Une tache planifiee (cron interne ou scheduler) appelle la synchro pour tous les comptes connectes a intervalle regulier
- [ ] #2 L'intervalle est configurable via .env
- [ ] #3 Un echec de synchro planifiee n'interrompt pas le serveur et est journalise
<!-- AC:END -->
