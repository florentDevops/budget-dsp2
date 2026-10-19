---
id: TASK-17
title: 'Virements entre ses propres comptes : appariement, épargne et flux pro'
status: Done
assignee:
  - '@claude'
created_date: '2026-10-19 20:30'
updated_date: '2026-10-19 20:54'
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
- [x] #1 Un débit sur un compte connecté et un crédit du même montant sur un autre compte connecté, à 3 jours d'écart au plus, sont appariés comme un seul virement interne, compté une seule fois
- [x] #2 Courant vers courant : neutre ; courant vers épargne : épargne ; épargne vers courant : retrait d'épargne (épargne nette diminuée) ; pro vers courant : entrée ; pro vers épargne : épargne, sans gonfler entrées ni sorties ; les dépenses propres du compte pro sont hors budget
- [x] #3 L'échéance du crédit maison prélevée sur le compte de dépôt reste une dépense logement, et le virement qui alimente ce compte est neutre
- [x] #4 Un virement vers un compte non connecté reste classé comme aujourd'hui, sauf règle utilisateur qui le classe en épargne (ex. IBAN du livret enfants)
- [x] #5 L'épargne destinée aux enfants est distinguée de l'épargne personnelle (catégorie ou compte Épargne enfants)
- [x] #6 Le bilan entrées / sorties (/api/cashflow), le résumé mensuel et le contexte des conseils (advice_context) utilisent ces règles ; une correction manuelle d'appariement est possible et prioritaire
- [x] #7 Tests pytest couvrent l'appariement (montant, fenêtre de dates, faux positifs), chaque règle de rôle et l'absence de double comptage
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
1. transactions : colonnes transfer_peer (id de l'opération appariée) et transfer_source (auto | user), migration
2. app/transfers.py : match() apparie débit / crédit de même montant sur deux comptes différents à <= 3 jours (le plus proche d'abord, un pour un), libellés de virement / prélèvement seulement (jamais carte ni chèque), sans toucher aux paires ou dissociations manuelles ; lancé au démarrage, après synchro, démo et reclassement
3. transfers.load() : opérations + rôle du compte et du compte apparié, puis effective() applique les règles de rôle à la lecture (aucun stockage, un changement de rôle s'applique tout de suite) : comptes épargne / enfants / crédit et dépenses pro -> nature hors_budget ; courant<->courant neutre ; courant<->épargne épargne (retrait = épargne négative) ; courant<->enfants épargne_enfants ; pro->courant entrée ; pro->épargne épargne côté pro ; courant->crédit inchangé (échéance = logement) ; correction manuelle prioritaire sur un compte courant
4. Rôle enfants (Épargne enfants) et catégorie epargne_enfants (nature epargne, autorisée en crédit, hors LLM) pour la règle utilisateur sur l'IBAN du livret enfants
5. insights (monthly_summary, category_trends, cashflow, advice_context) lisent via transfers.load et écartent hors_budget des totaux ; les opérations hors budget restent listées
6. PUT /api/transactions/{id}/transfer {peer|null} : appariement ou dissociation manuels
7. Dashboard : tags Virement interne (compte apparié, Dissocier) et Hors budget ; recharge du mois après changement de rôle
8. Tests pytest d'abord : appariement (montant, fenêtre, faux positifs, un pour un), chaque règle, absence de double comptage sur un scénario multi-comptes ; node pour le libellé
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
pytest 116 ok (16 nouveaux), node --test 19 ok (1 nouveau). Scénario multi-comptes d'août (Fortuneo perso + joint, livret A, livret enfants, dépôt CE + prêt, Qonto) : 8 paires, entrées 4 000 €, sorties 1 020 € (échéance + courses), épargne 450 € (200 + 50 enfants + 300 depuis Qonto - 100 retiré), identiques dans /api/cashflow, monthly_summary, category_trends et advice_context. Sur une copie de la vraie base (2 comptes Fortuneo) : 1 seule paire perso <-> joint (80 €), chiffres inchangés ; les 7 virements « VIR INST Virement avec Fortuneo » (-8 200 €) et « provision crédit immo » (-1 000 €) vont vers des comptes non connectés et seront appariés une fois la Caisse d'Épargne connectée. Chrome headless (CDP) : étiquettes Virement vers / depuis <compte> et Hors budget, Dissocier (les deux côtés reprennent leur classement), passage de Qonto en courant puis pro répercuté sur les totaux, aucune erreur JS. Choix : règles appliquées à la lecture (transfers.load) plutôt que stockées, pour qu'un changement de rôle s'applique sans reclassement ; les deux libellés doivent ressembler à un virement / prélèvement (jamais carte ni chèque) pour limiter les faux positifs ; nouveau rôle enfants et catégorie epargne_enfants (hors LLM). Côté hors budget, un virement apparié s'affiche Virements.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Virements entre ses comptes : app/transfers.py apparie débit et crédit jumeaux (même montant, 2 comptes, <= 3 jours, libellés de virement, un pour un) et applique à la lecture les règles de rôle : comptes épargne / enfants / prêt et dépenses pro hors budget, courant<->courant neutre, courant<->épargne épargne (retrait déduit), épargne enfants à part, pro->courant entrée, pro->épargne épargne, échéance du crédit = logement. Bilan, résumé mensuel, tendances et conseils lisent via transfers.load. Appariement / dissociation manuels (PUT /api/transactions/{id}/transfer, bouton Dissocier). Vérifié : pytest 116 ok, node 19 ok, scénario multi-comptes, copie de la vraie base, parcours Chrome headless CDP.
<!-- SECTION:FINAL_SUMMARY:END -->
