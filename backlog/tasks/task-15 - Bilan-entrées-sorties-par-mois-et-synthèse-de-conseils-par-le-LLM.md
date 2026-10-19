---
id: TASK-15
title: Bilan entrées / sorties par mois et synthèse de conseils par le LLM
status: Done
assignee:
  - '@claude'
created_date: '2026-10-19 19:51'
updated_date: '2026-10-19 20:04'
labels:
  - feature
dependencies: []
priority: medium
type: feature
ordinal: 15000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Les tendances montrent où part l'argent, mais pas si on dépense plus que ce qui rentre. Besoin de voir mois par mois entrées vs sorties (excédent ou déficit), et d'une synthèse de conseils globale sur 6 ou 12 mois produite par le LLM déjà configuré pour la catégorisation (mêmes clés et provider).
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 GET /api/cashflow renvoie par mois (ordre chronologique) les entrées (nature revenu), les sorties (consommation, épargne et virements exclus), l'épargne nette, et signale le mois en cours comme partiel
- [x] #2 La page /tendances affiche deux lignes Entrées / Sorties, l'écart coloré selon excédent ou déficit, le solde signé de chaque mois sous l'axe, une infobulle et un tableau des montants, en suivant la période 6/12/tout
- [x] #3 POST /api/advice produit une synthèse et des conseils pour les 6 ou 12 derniers mois complets via le provider LLM configuré, sur demande explicite uniquement
- [x] #4 Seuls des agrégats (totaux par mois et par catégorie) sont envoyés au LLM pour les conseils : aucun nom de marchand, libellé, date précise ni IBAN
- [x] #5 Une erreur ou un LLM non configuré donne un message clair, sans casser la page
- [x] #6 Tests pytest et node couvrent l'API, le contexte envoyé au LLM et la géométrie de l'écart entre les courbes
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
1. insights.cashflow + GET /api/cashflow (pytest d'abord) : entrées nature revenu, sorties hors épargne/virements, épargne nette, mois en cours marqué partiel
2. insights.advice_context(n) : agrégats des n derniers mois complets (totaux mensuels, moyenne par catégorie, essentiel/optimisable, abonnements, potentiel), sans marchand/libellé/date
3. llm.py : extraire un _chat_<provider>(system, user) commun, réutilisé par la classification ; llm.advise(context) -> {synthese, conseils} ou None
4. POST /api/advice {months: 6|12} : 400 si LLM non configuré, 502 si pas de réponse exploitable
5. app/static/cashflow.js : flowView (période, soldes) et gapRegions (zones entre courbes coupées aux croisements), node --test d'abord
6. trends.html : section Entrées / sorties en tête (lignes bleu/rouge validées CVD, écart teinté excédent/déficit, solde signé sous l'axe, infobulle, tableau), bloc Conseils à la demande
7. README / CLAUDE.md : route, page, et ce qui est envoyé au LLM

8. Timeout dédié aux conseils (ADVICE_TIMEOUT = 300 s) : Gemini a dépassé les 60 s de la classification
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
pytest 84 ok (8 nouveaux), node --test 15 ok (4 nouveaux). Vérifié en Chrome headless piloté par CDP sur la démo : mobile 390px clair (scrollWidth = 390, pas de débordement), desktop sombre, survol (infobulle + réticule affichés puis retirés), aucune erreur JS. Appel réel Gemini (gemini-3.8-flash) sur les agrégats de la démo : 1er essai en timeout 60 s -> message 502 affiché proprement ; avec ADVICE_TIMEOUT synthèse + 5 conseils chiffrés. Choix : lignes bleu/rouge (--flow-in/--flow-out) car vert/rouge échoue au validateur CVD (deutan ΔE 6,9) ; écart teinté --keep/--danger doublé du solde signé ; mois en cours en pointillés, non teinté, hors moyennes et hors conseils. Refacto llm.py : _classify_chunk_* remplacés par _chat_<provider> communs (classification inchangée hors temperature=0 explicite pour Anthropic).
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Section Entrées et sorties en tête de /tendances : deux lignes entrées/sorties par mois, écart teinté excédent/déficit, solde signé sous l'axe, infobulle, tableau, mois en cours neutralisé. Bloc Conseils : POST /api/advice envoie au LLM déjà configuré (mêmes clés) uniquement des agrégats des 6/12 derniers mois complets (insights.advice_context), renvoie synthèse + conseils. API GET /api/cashflow (insights.cashflow). Vérifié : pytest 84 ok, node 15 ok, rendu et interactions en Chrome headless CDP, appel Gemini réel sur la démo.
<!-- SECTION:FINAL_SUMMARY:END -->
