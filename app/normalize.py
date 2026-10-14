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
# Références techniques (hex, UUID...) : lettres+chiffres mêlés sans 4 chiffres consécutifs,
# donc non couvertes par _LONG_NUMBERS (ex. "01A0E365E8EA7108B0ED9107486C29D8").
_REF_CODE = re.compile(r"\b(?=[A-Z0-9]*\d)(?=[A-Z0-9]*[A-Z])[A-Z0-9]{10,}\b")
_NOISE = re.compile(r"[^A-Z0-9&+./' ]")
_SPACES = re.compile(r"\s+")
_NON_ALNUM = re.compile(r"[^A-Z0-9]")
# Chèque émis ("CHQ 0538322") ; une remise de chèque ("REM CHQ ...") est un encaissement
_CHEQUE = re.compile(r"^(?:CHQ|CHEQUE)(?: N)? ?\d{5,}\b")

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
    """Nom affiché du marchand : 'CB CARREFOUR MARKET 12/03 PARIS' -> 'CARREFOUR MARKET'.
    La clé de regroupement en est dérivée par merchant_key()."""
    s = clean_label(text)
    for _ in range(3):  # certains libellés empilent plusieurs préfixes
        new = _PREFIXES.sub("", s).strip()
        if new == s:
            break
        s = new
    s = _DATES.sub(" ", s)
    s = _LONG_NUMBERS.sub(" ", s)
    s = _REF_CODE.sub(" ", s)
    # Un token sans lettre ni chiffre ("/", "-") n'est que du bruit de séparation
    tokens = [t for t in _SPACES.sub(" ", s).strip().split(" ")
              if _NON_ALNUM.sub("", t) and not t.isdigit()]
    while len(tokens) > 1 and tokens[-1] in _TRAILING:
        tokens.pop()
    # Volontairement généreux (8 mots) : couper plus court perd des mots distinctifs
    # ("PPG*SKIN AND OUT PARIS" -> "PPG SKIN AND" sans le "OUT" qui identifie le commerce).
    return " ".join(tokens[:8]) or clean_label(text)[:30] or "INCONNU"


def merchant_key(merchant: str) -> str:
    """Clé technique du marchand : A-Z0-9 seulement, sûre en URL et insensible à la
    ponctuation ('NETFLIX.COM' et 'NETFLIX COM' -> 'NETFLIXCOM'). Distincte du nom affiché."""
    return _NON_ALNUM.sub("", clean_label(merchant)) or "INCONNU"


def is_cheque(label: str) -> bool:
    """Chèque émis : le libellé ne dit rien du bénéficiaire, seul l'utilisateur le connaît."""
    return bool(_CHEQUE.match(clean_label(label)))
