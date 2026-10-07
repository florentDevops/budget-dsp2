"""Nettoyage des libellés bancaires français et extraction du marchand."""
import re
import unicodedata

# Préfixes techniques ajoutés par les banques, sans valeur pour la classification
_PREFIXES = re.compile(
    r"^(?:"
    r"PAIEMENT PAR CARTE|PAIEMENT CB|ACHAT CB|FACTURE CARTE|CARTE|CB\*?\d*|"
    r"PRLV SEPA|PRELEVEMENT(?: SEPA)?|PRLV|"
    r"VIR(?:EMENT)?(?: SEPA)?(?: INST(?:ANTANE)?)?(?: RECU| EMIS)?(?: DE| A| VERS)?|"
    r"ECHEANCE PRET|TIP|CHQ|CHEQUE"
    r")\b\s*"
)
_DATES = re.compile(r"\b\d{2}[/.-]\d{2}(?:[/.-]\d{2,4})?\b")
_LONG_NUMBERS = re.compile(r"\b[A-Z]*\d{4,}[A-Z\d]*\b")
_NOISE = re.compile(r"[^A-Z0-9&+./' ]")
_SPACES = re.compile(r"\s+")

# Mots à retirer en fin de marchand (villes fréquentes, suffixes juridiques)
_TRAILING = {"PARIS", "LYON", "MARSEILLE", "FR", "FRANCE", "SAS", "SA", "SARL", "EUR"}


def clean_label(text: str) -> str:
    """Majuscules, sans accents ni ponctuation : sert au matching des règles."""
    if not text:
        return ""
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    text = _NOISE.sub(" ", text.upper())
    return _SPACES.sub(" ", text).strip()


def extract_merchant(text: str) -> str:
    """Clé stable de regroupement : 'CB CARREFOUR MARKET 12/03 PARIS' -> 'CARREFOUR MARKET'."""
    s = clean_label(text)
    for _ in range(3):  # certains libellés empilent plusieurs préfixes
        new = _PREFIXES.sub("", s).strip()
        if new == s:
            break
        s = new
    s = _DATES.sub(" ", s)
    s = _LONG_NUMBERS.sub(" ", s)
    tokens = [t for t in _SPACES.sub(" ", s).strip().split(" ") if t and not t.isdigit()]
    while len(tokens) > 1 and tokens[-1] in _TRAILING:
        tokens.pop()
    return " ".join(tokens[:3]) or clean_label(text)[:30] or "INCONNU"
