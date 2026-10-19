---
id: TASK-17
title: 'Virements entre ses propres comptes : appariement, épargne et flux pro'
status: To Do
assignee: []
created_date: '2026-10-19 20:30'
labels:
  - feature
dependencies:
  - TASK-16
priority: high
type: feature
ordinal: 17000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Avec plusieurs comptes connectés, un même virement apparaît deux fois (-200 sur le compte source, +200 sur le compte cible). Aujourd'hui tous les virements sont classés virements/transfert et exclus partout : sur les données réelles, 35 virements (-13 056 €) ne comptent ni en dépense ni en épargne, dont l'argent envoyé sur le livret des enfants. Le bilan entrées / sorties et les conseils du LLM (TASK-15) sous-estiment donc l'épargne. Il faut interpréter chaque flux selon le rôle des comptes (TASK-16). Cas réels : Fortuneo perso et joint (courant), Caisse d'Épargne livret A et livret enfants (épargne), compte de dépôt Caisse d'Épargne qui paie le crédit maison (courant : l'échéance reste une dépense logement), Qonto (pro). Gain rapide possible avant même de connecter la Caisse d'Épargne : une règle sur l'IBAN ou le libellé des virements vers le livret enfants.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Un débit sur un compte connecté et un crédit du même montant sur un autre compte connecté, à 3 jours d'écart au plus, sont appariés comme un seul virement interne, compté une seule fois
- [ ] #2 Courant vers courant : neutre ; courant vers épargne : épargne ; épargne vers courant : retrait d'épargne (épargne nette diminuée) ; pro vers courant : entrée ; pro vers épargne : épargne, sans gonfler entrées ni sorties ; les dépenses propres du compte pro sont hors budget
- [ ] #3 L'échéance du crédit maison prélevée sur le compte de dépôt reste une dépense logement, et le virement qui alimente ce compte est neutre
- [ ] #4 Un virement vers un compte non connecté reste classé comme aujourd'hui, sauf règle utilisateur qui le classe en épargne (ex. IBAN du livret enfants)
- [ ] #5 L'épargne destinée aux enfants est distinguée de l'épargne personnelle (catégorie ou compte Épargne enfants)
- [ ] #6 Le bilan entrées / sorties (/api/cashflow), le résumé mensuel et le contexte des conseils (advice_context) utilisent ces règles ; une correction manuelle d'appariement est possible et prioritaire
- [ ] #7 Tests pytest couvrent l'appariement (montant, fenêtre de dates, faux positifs), chaque règle de rôle et l'absence de double comptage
<!-- AC:END -->
