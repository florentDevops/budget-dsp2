# Roadmap

Vue d'ensemble des grandes étapes du projet. Le détail des tâches (features à trancher, critères d'acceptation, statut) est géré avec [Backlog.md](https://github.com/MrLesk/Backlog.md) dans le dossier `backlog/` — voir `npx backlog.md board` ou `npx backlog.md task list --plain`.

## État actuel

- Backend FastAPI + SQLite fonctionnel.
- Connexion bancaire DSP2 via Enable Banking (sandbox + production).
- Classification en cascade (règles > MCC > LLM Claude > à classer).
- Moteur de pistes d'économies (abonnements, frais, hausses, micro-dépenses, contrats renégociables).
- Dashboard web sans dépendance front.
- Suite de tests (19 tests, `pytest -q`).
- Déploiement local via `docker compose up`.

## Étape 1 — Fiabiliser l'usage quotidien (milestone `m-0`)

Objectif : pouvoir utiliser l'app au quotidien sans intervention manuelle.

- Synchro automatique périodique (cron interne ou tâche planifiée). — `TASK-1`
- Alerte / notification quand un consentement bancaire approche de l'expiration (180 jours max). — `TASK-2`
- Gestion des erreurs de synchro plus visible côté dashboard (au-delà du champ `errors` de `/api/sync`). — `TASK-3`

## Étape 2 — Budget actif, pas seulement rétrospectif (milestone `m-1`)

Objectif : passer d'un constat mensuel à un pilotage proactif.

- Budgets mensuels par catégorie avec alerte de dépassement. — `TASK-4`
- Détection des abonnements à rythme annuel (365 jours), pas seulement mensuel. — `TASK-5`
- Historique et tendance du potentiel d'économies sur plusieurs mois. — `TASK-6`

## Étape 3 — Élargir les sources de données (milestone `m-2`)

Objectif : couvrir les cas où l'open banking ne suffit pas.

- Import CSV/OFX en secours pour les banques non couvertes par Enable Banking. — `TASK-7`
- Support multi-comptes/multi-banques plus visible dans le dashboard (actuellement mono-utilisateur). — `TASK-8`

## Étape 4 — Accès et sécurité (milestone `m-3`)

Objectif : rendre l'app exposable au-delà d'un usage strictement local.

- Authentification devant le dashboard. — `TASK-9`
- HTTPS et chiffrement du disque/de la base en cas d'exposition réseau. — `TASK-10`

## Étape 5 — Mobilité (milestone `m-4`)

Objectif : consulter son budget sans être devant l'ordinateur.

- Progressive Web App (PWA) à partir du dashboard existant. — `TASK-11`

## Non prioritaire pour l'instant

- Multi-utilisateurs / multi-foyers.
- Export comptable (FEC, etc.).
