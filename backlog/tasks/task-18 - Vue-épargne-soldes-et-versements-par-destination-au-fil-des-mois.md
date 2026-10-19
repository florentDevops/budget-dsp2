---
id: TASK-18
title: 'Vue épargne : soldes et versements par destination au fil des mois'
status: To Do
assignee: []
created_date: '2026-10-19 20:30'
labels:
  - feature
dependencies:
  - TASK-17
references:
  - app/enable_banking.py
priority: medium
type: feature
ordinal: 18000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Une fois les comptes d'épargne connectés et les virements interprétés (TASK-16, TASK-17), il manque une vue pour suivre l'épargne : combien est mis de côté chaque mois, vers quel compte (livret A, livret enfants), d'où vient l'argent (compte perso ou compte pro Qonto), et où en sont les soldes. Le client Enable Banking sait déjà lire les soldes (get_balances) mais rien ne les utilise ni ne les stocke.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Les soldes des comptes sont récupérés à chaque synchro et historisés (un relevé par compte et par jour de synchro)
- [ ] #2 Une vue épargne montre, mois par mois, les versements nets par compte de destination, avec l'épargne enfants séparée de l'épargne personnelle, et le compte d'origine (perso ou pro)
- [ ] #3 La vue affiche le solde actuel et l'évolution de chaque compte d'épargne, et le solde restant dû du crédit maison si la banque le transmet
- [ ] #4 Le contexte des conseils du LLM inclut les totaux d'épargne par type (personnelle, enfants), toujours agrégés : ni IBAN ni nom de compte
- [ ] #5 Tests pytest et node couvrent l'historisation des soldes, les agrégats par destination et la logique du graphique
<!-- AC:END -->
