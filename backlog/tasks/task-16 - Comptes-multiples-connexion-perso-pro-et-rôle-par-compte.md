---
id: TASK-16
title: 'Comptes multiples : connexion perso/pro et rôle par compte'
status: Done
assignee:
  - '@claude'
created_date: '2026-10-19 20:30'
updated_date: '2026-10-19 20:38'
labels:
  - feature
dependencies: []
references:
  - app/enable_banking.py
  - 'https://enablebanking.com/docs/api/reference/'
priority: high
type: feature
ordinal: 16000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Le budget ne voit que deux comptes Fortuneo (perso et joint). Il manque le compte pro chez Qonto (banque qui n'accepte que des consentements pro, psu_type business) et la Caisse d'Épargne : livret A, livret des enfants, et un compte de dépôt sur lequel est prélevé le crédit de la maison. Aujourd'hui psu_type est figé à personal (app/enable_banking.py) et le bouton existant « ajouter une banque » ne demande ni le type de connexion ni le rôle des comptes renvoyés. Le rôle d'un compte conditionne la lecture des flux entre comptes (voir la tâche suivante) : courant (dans le budget), épargne (livrets, compte enfants), pro (hors budget), crédit (compte de prêt : mouvements ignorés). Enable Banking renvoie cash_account_type (CACC, SVGS, LOAN...) et usage (PRIV/ORGA) pour proposer un rôle par défaut. En mode restreint gratuit, les comptes doivent d'abord être liés dans le portail Enable Banking. Reprend le besoin de TASK-8 (origine et filtre par compte).
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 L'app propose à tout moment d'ajouter une connexion bancaire, en nombre illimité, en choisissant perso ou pro ; seuls les types acceptés par la banque choisie sont proposés (Qonto : pro uniquement)
- [x] #2 Chaque compte a un rôle (courant, épargne, pro, crédit) proposé d'après le type renvoyé par la banque (SVGS -> épargne, LOAN -> crédit, consentement pro -> pro) et modifiable dans l'app, ainsi qu'un nom affiché personnalisable (ex. Livret enfants)
- [x] #3 Une page ou un panneau Comptes liste banque, nom, rôle, dernière synchro et expiration du consentement de chaque compte
- [x] #4 Les comptes existants gardent le rôle courant après migration, sans perte de données
- [x] #5 Le dashboard indique le compte d'origine de chaque opération et permet de filtrer par compte quand plusieurs sont connectés
- [x] #6 Tests pytest et node couvrent le choix du psu_type, le rôle par défaut, la migration et le filtre par compte
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
1. Table accounts : colonnes role (défaut courant), label (nom affiché choisi), product, cash_account_type, psu_type ; migration ALTER des bases existantes (rôle courant)
2. app/accounts.py : ROLES (courant, epargne, pro, credit) et default_role(compte EB, psu_type) : LOAN -> credit, consentement business ou usage ORGA -> pro, SVGS -> epargne, sinon courant
3. enable_banking.start_auth(psu_type) ; POST /api/connect {bank, psu_type personal|business} ; état d'auth en attente garde le psu_type ; /callback enregistre rôle par défaut, produit et type ; une reconnexion ne touche ni rôle ni label
4. GET /api/banks expose psu_types ; /api/status expose rôle, label, produit ; PUT /api/accounts/{uid} {role, label}
5. Front (pytest + node d'abord) : bouton Ajouter un compte toujours visible, choix Perso/Pro limité aux psu_types de la banque ; section Comptes (banque, nom modifiable, rôle, dernière synchro, expiration) ; compte d'origine sur chaque opération et filtre par compte quand plusieurs comptes (accounts.js + filters.js)
6. Hors périmètre (TASK-17) : l'effet du rôle sur le budget ; README/CLAUDE.md à jour
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
pytest 100 ok (16 nouveaux), node --test 18 ok (3 nouveaux). Migration testée sur une copie de la vraie base : 2 comptes Fortuneo -> courant, 1109 opérations intactes. Vérifié en Chrome headless (CDP) sur la démo + 2 comptes fictifs (livret CE, Qonto) : bouton Ajouter un compte visible avec comptes déjà connectés ; liste réelle /api/banks : Qonto -> « Compte pro uniquement », Fortuneo -> « Compte perso uniquement », Caisse d'Epargne -> Perso / Pro ; filtre par compte (40 -> 1 opération), nom du compte sur chaque opération ; changement de rôle et de nom persistés (PUT), filtre conservé ; mobile 390 px sans débordement après passage à la ligne de l'en-tête ; aucune erreur JS. Non testé : un vrai consentement Qonto / Caisse d'Epargne de bout en bout (nécessite tes identifiants bancaires). Le rôle n'a encore aucun effet sur le budget : un compte pro connecté avant TASK-17 entre dans les totaux.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Connexions multiples : bouton Ajouter un compte toujours présent, choix Perso / Pro limité aux psu_types de la banque (POST /api/connect psu_type, start_auth). Chaque compte reçoit un rôle par défaut (app/accounts.py : LOAN -> crédit, pro, SVGS -> épargne, sinon courant) et un nom affiché, modifiables dans la section Comptes (PUT /api/accounts/{uid}) et préservés aux reconnexions ; migration des bases existantes en courant. Dashboard : compte d'origine sur chaque opération et filtre par compte. Vérifié : pytest 100 ok, node 18 ok, migration sur copie de la vraie base, parcours en Chrome headless CDP.
<!-- SECTION:FINAL_SUMMARY:END -->
