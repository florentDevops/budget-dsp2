---
id: TASK-7
title: Import CSV/OFX en secours
status: To Do
assignee: []
created_date: '2026-09-29 19:52'
labels: []
milestone: m-2
dependencies: []
priority: medium
type: feature
ordinal: 7000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Enable Banking ne couvre pas toutes les banques europeennes. Sans alternative, un utilisateur dont la banque n'est pas couverte ne peut pas utiliser l'application du tout.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Un fichier CSV ou OFX exporte depuis une banque peut etre importe et alimente la table transactions au meme schema que la synchro DSP2
- [ ] #2 Les operations importees passent par la meme classification en cascade que les operations DSP2
- [ ] #3 Un import en double (meme operation reimportee) ne cree pas de doublon
<!-- AC:END -->
