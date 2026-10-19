---
id: TASK-19
title: 'Ajustements après connexion des vrais comptes (Qonto, Caisse d''Épargne)'
status: Done
assignee:
  - '@claude'
created_date: '2026-10-19 21:13'
updated_date: '2026-10-19 21:15'
labels:
  - bug
dependencies: []
priority: high
type: bug
ordinal: 19000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Premiers comptes réels connectés : Qonto (compte pro de l'EI), Caisse d'Épargne (compte de dépôt joint : revenus Airbnb, échéance du crédit maison ; compte de dépôt vide au nom de Lina). La Caisse d'Épargne n'expose pas les livrets en DSP2 (livret A et LDD perso, livrets A de Paul et Lina) : l'épargne vers eux ne peut être lue que depuis le compte qui verse. Constats : l'épargne versée depuis Qonto vers des comptes non connectés (SPIRICA, Spiko) est classée épargne mais sortie du budget avec le reste du compte pro ; les libellés Qonto (« Envoye depuis Qonto ») ne ressemblent pas à un virement et ne seraient jamais appariés ; l'échéance « ECH PRET » a été classée remboursements par le LLM ; la section Comptes en bas du dashboard n'a pas été trouvée après connexion.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 Une épargne versée depuis un compte pro vers un compte non connecté (classée épargne) compte dans l'épargne du foyer, sans gonfler entrées ni sorties
- [x] #2 Un virement est apparié dès qu'un des deux libellés ressemble à un virement (jamais carte ni chèque), pour les libellés Qonto
- [x] #3 Une règle classe les échéances de prêt (ECH PRET, ECHEANCE PRET) en logement
- [x] #4 La section Comptes est accessible depuis l'en-tête et signalée après une connexion ; elle explique que les livrets ne sont pas exposés par les banques
- [x] #5 Tests pytest couvrent chaque point
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
1. transfers.effective : compte pro, débit non apparié classé épargne -> épargne du foyer
2. transfers.match : un seul libellé de virement suffit (carte et chèque toujours exclus des deux côtés)
3. rules.yaml : ECH PRET / ECHEANCE PRET -> logement, avant les règles génériques
4. Dashboard : lien Comptes dans l'en-tête, message après connexion qui y renvoie, note sur les livrets non exposés
5. Tests pytest d'abord ; puis réglage des comptes réels via l'API (rôles, noms) et correction Paul -> épargne enfants
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
pytest 121 ok (5 nouveaux), node 19 ok. Base réelle : sauvegarde dans le scratchpad puis via l'API rôles / noms des 5 comptes (Lina -> Épargne enfants) et virements vers Paul -> Épargne enfants (5 opérations, ils étaient corrigés en Virements). Sur une copie de la base avec le nouveau code (sans appel LLM) : ECH PRET -> logement, épargne mensuelle 0 / 10 / 1070 / 1070 / 70 / 110 € (mai -> oct.) au lieu de 0 / 10 / 20 / 20 / 20 / 60 € grâce aux versements Qonto vers SPIRICA et Spiko ; entrées et sorties inchangées (l'échéance était déjà comptée en sortie, sous une mauvaise catégorie). Constat Enable Banking : la Caisse d'Épargne n'a renvoyé que 2 comptes de dépôt (CACC, « CPT DEPOT PART. »), celui de Lina à 0 € ; aucun livret. Chrome headless : lien Comptes, défilement après ?connected=1, mobile 390 px sans débordement.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Après connexion des vrais comptes : l'épargne versée depuis Qonto vers des placements non connectés compte dans l'épargne du foyer ; un seul libellé de virement suffit pour apparier (libellés Qonto) ; règle ECH PRET -> logement ; lien Comptes dans l'en-tête, renvoi après connexion et note sur les livrets non exposés en DSP2. Comptes réels réglés via l'API. Vérifié : pytest 121 ok, node 19 ok, copie de la base réelle, Chrome headless.
<!-- SECTION:FINAL_SUMMARY:END -->
