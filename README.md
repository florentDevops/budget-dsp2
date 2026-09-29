# Budget DSP2

Application personnelle de suivi de budget : elle récupère tes opérations bancaires via l'open banking (DSP2), les classe automatiquement, sépare les dépenses essentielles des dépenses optimisables et surligne celles sur lesquelles tu peux agir.

Stack : Python, FastAPI, SQLite, Enable Banking pour l'accès aux comptes, Claude (optionnel) pour classer les marchands inconnus, et un dashboard web sans dépendance front.

## Démarrage en 2 minutes (données fictives)

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
uvicorn app.main:app --reload
```

Ouvre http://localhost:8000 puis clique sur « Charger la démo » : six mois de relevé fictif sont importés et classés. Tu peux aussi lancer `python -m scripts.seed_demo`.

## Brancher ta vraie banque

L'API DSP2 des banques n'est ouverte qu'aux prestataires agréés (AISP). Enable Banking joue ce rôle et t'expose une API unifiée pour plus de 2 500 banques européennes.

1. Crée un compte sur https://enablebanking.com et ouvre le Control Panel.
2. Dans *Applications*, enregistre une nouvelle application. Commence par l'environnement **Sandbox** : il fournit une banque fictive (« Mock ASPSP ») pour valider le flux complet.
3. Génère la clé dans le navigateur : un fichier `.pem` est téléchargé, son nom est l'identifiant de l'application. Copie-le dans `keys/private.pem` et l'identifiant dans `ENABLE_BANKING_APP_ID`.
4. Déclare `http://localhost:8000/callback` comme URL de redirection. Si l'environnement exige du HTTPS, passe par un tunnel (ngrok, Cloudflare Tunnel) et mets l'URL publique dans `ENABLE_BANKING_REDIRECT_URL`.
5. Pour tes vrais comptes, crée une application **Production**. Enable Banking propose un usage restreint gratuit limité aux comptes que tu lies toi-même depuis le Control Panel ; vérifie les conditions à jour dans leur documentation.
6. Relance le serveur : le bouton « Connecter ma banque » apparaît. Choisis ta banque, authentifie-toi chez elle, tu es renvoyé sur le dashboard avec tes opérations.

Le consentement dure 180 jours au maximum (limite fixée par chaque banque). À expiration, la synchro renvoie une erreur : reconnecte simplement la banque. La profondeur d'historique récupérée à la première connexion dépend aussi de la banque, souvent 90 jours.

## Comment ça marche

```
Banque ──DSP2──> Enable Banking ──> enable_banking.py ──> SQLite
                                                           │
                        classifier.py (règles > MCC > LLM) ┤
                                                           │
                        insights.py (abonnements, hausses) ┴──> API FastAPI ──> dashboard
```

**Classification en cascade**, la première source qui répond gagne :

1. ta correction manuelle, mémorisée par marchand et appliquée à tout l'historique ;
2. les règles regex de `app/rules.yaml` sur le libellé nettoyé ;
3. le code MCC si la banque le transmet ;
4. Claude, uniquement pour les marchands restés inconnus, avec un seul appel par marchand puis mise en cache ;
5. à défaut, « À classer ».

Seuls les noms de marchands sont envoyés au LLM : jamais les montants, dates, IBAN ou soldes. Sans clé `ANTHROPIC_API_KEY`, l'application fonctionne avec les règles seules.

**Chaque catégorie a une nature** (`app/categories.py`) : essentiel, optimisable, épargne, revenu ou transfert. Les montants optimisables sont surlignés dans la liste des opérations.

**Pistes d'économies** détectées par `app/insights.py` :

- abonnements actifs : même marchand, montant stable à ±15 %, rythme mensuel, vu sur au moins 3 mois et encore prélevé récemment ;
- frais bancaires du mois ;
- catégories optimisables en hausse de plus de 20 % par rapport aux 3 mois précédents ;
- micro-dépenses répétées : moins de 15 €, au moins 6 fois dans le mois chez le même marchand ;
- contrats essentiels mais renégociables (énergie, box, assurances) quand ils sont récurrents.

Le potentiel affiché en haut applique une part récupérable par catégorie (`SAVINGS_RATE`) : 100 % des frais bancaires, 50 % des livraisons, 30 % des restos et du shopping, etc. C'est une heuristique prudente, à ajuster à ta situation.

## Personnaliser

- **Nouveau marchand mal classé** : corrige-le dans le dashboard, la correction s'applique à toutes ses opérations passées et futures.
- **Nouvelle règle** : ajoute une ligne dans `app/rules.yaml` (les plus spécifiques en haut), puis `curl -X POST localhost:8000/api/reclassify`.
- **Changer ce qui est « utile »** : modifie la nature d'une catégorie dans `app/categories.py`. Pour un seul marchand (Uber pour le travail, par exemple), l'API accepte une nature forcée : `PUT /api/merchants/UBER {"category": "transport", "nature": "essentiel"}`.
- **Seuils de détection** : constantes en tête de `app/insights.py`.

## API

| Méthode | Route | Rôle |
|---|---|---|
| GET | `/api/status` | Comptes connectés, mois disponibles, options actives |
| GET | `/api/banks?country=FR` | Banques disponibles chez Enable Banking |
| POST | `/api/connect` | Démarre le consentement, renvoie l'URL de la banque |
| GET | `/callback` | Retour de la banque, crée la session et synchronise |
| POST | `/api/sync` | Récupère les nouvelles opérations et les classe |
| GET | `/api/summary?month=YYYY-MM` | Totaux, pistes, surbrillances et opérations du mois |
| PUT | `/api/merchants/{marchand}` | Corrige la catégorie d'un marchand |
| POST | `/api/reclassify` | Reclasse tout après modification des règles |
| POST | `/api/demo` | Charge le relevé fictif |

## Tests

```bash
pytest -q
```

## Lancer avec Docker

```bash
cp .env.example .env   # puis renseigne tes clés si besoin
docker compose up --build
```

Le conteneur sert l'app sur http://localhost:8000. `data/` (base SQLite) et `keys/` (clé privée Enable Banking) sont montés en volumes depuis la racine du projet pour persister entre les redémarrages.

## Sécurité

Application pensée pour un usage local et mono-utilisateur. Avant de l'exposer sur internet : ajoute une authentification devant le dashboard, sers-la en HTTPS, et chiffre le disque ou la base (la base contient ton historique bancaire). La clé privée et le `.env` sont exclus de Git par le `.gitignore`.

## Pistes d'évolution

- Budgets mensuels par catégorie avec alerte de dépassement
- Détection des abonnements annuels (rythme de 365 jours)
- Import CSV/OFX en secours pour les banques non couvertes
- Synchro quotidienne automatique (cron ou Prefect)
- Application mobile (PWA) à partir du dashboard existant
