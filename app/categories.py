"""Catégories de dépenses et nature associée.

La nature est la deuxième dimension de classification :
- essentiel   : dépense utile, difficile à réduire à court terme
- optimisable : dépense sur laquelle on peut faire des économies
- epargne / revenu / transfert : hors budget de consommation
"""

CATEGORIES: dict[str, dict] = {
    "logement":        {"label": "Logement",          "nature": "essentiel"},
    "energie":         {"label": "Énergie & eau",     "nature": "essentiel"},
    "courses":         {"label": "Courses",           "nature": "essentiel"},
    "sante":           {"label": "Santé",             "nature": "essentiel"},
    "assurance":       {"label": "Assurances",        "nature": "essentiel"},
    "transport":       {"label": "Transport",         "nature": "essentiel"},
    "telecom":         {"label": "Téléphone & box",   "nature": "essentiel"},
    "education":       {"label": "Éducation",         "nature": "essentiel"},
    "impots":          {"label": "Impôts & taxes",    "nature": "essentiel"},
    "restaurants":     {"label": "Restos & cafés",    "nature": "optimisable"},
    "livraison":       {"label": "Livraison repas",   "nature": "optimisable"},
    "abonnements":     {"label": "Abonnements",       "nature": "optimisable"},
    "shopping":        {"label": "Shopping",          "nature": "optimisable"},
    "loisirs":         {"label": "Loisirs",           "nature": "optimisable"},
    "voyages":         {"label": "Voyages",           "nature": "optimisable"},
    "frais_bancaires": {"label": "Frais bancaires",   "nature": "optimisable"},
    "retraits":        {"label": "Retraits espèces",  "nature": "optimisable"},
    "epargne":         {"label": "Épargne",           "nature": "epargne"},
    "revenus":         {"label": "Revenus",           "nature": "revenu"},
    "remboursements":  {"label": "Remboursements",    "nature": "revenu"},
    "virements":       {"label": "Virements",         "nature": "transfert"},
    "inconnu":         {"label": "À classer",         "nature": "inconnu"},
}

# Contrats essentiels mais renégociables : signalés quand ils sont récurrents
RENEGOTIABLE = {"energie", "telecom", "assurance"}

# Part de la dépense qu'on estime récupérable, pour le chiffrage du potentiel.
# Heuristique volontairement prudente, à ajuster selon ton propre ressenti.
SAVINGS_RATE = {
    "frais_bancaires": 1.0,
    "livraison": 0.5,
    "abonnements": 0.4,
    "restaurants": 0.3,
    "shopping": 0.3,
    "loisirs": 0.2,
    "voyages": 0.1,
    "retraits": 0.0,
}

# Codes MCC (Merchant Category Code) quand la banque les transmet
MCC_MAP = {
    "5411": "courses", "5422": "courses", "5441": "courses", "5451": "courses", "5499": "courses",
    "5812": "restaurants", "5813": "restaurants", "5814": "restaurants",
    "4111": "transport", "4121": "transport", "4131": "transport", "5541": "transport",
    "5542": "transport", "7523": "transport",
    "5912": "sante", "8011": "sante", "8021": "sante", "8062": "sante",
    "4814": "telecom", "4899": "abonnements",
    "5311": "shopping", "5651": "shopping", "5691": "shopping", "5732": "shopping",
    "5942": "shopping", "5999": "shopping",
    "7832": "loisirs", "7922": "loisirs", "7941": "loisirs", "7997": "abonnements",
    "3000": "voyages", "4511": "voyages", "7011": "voyages",
    "6011": "retraits", "6300": "assurance", "4900": "energie", "9311": "impots",
}


def nature_of(category: str) -> str:
    return CATEGORIES.get(category, CATEGORIES["inconnu"])["nature"]
