"""Classification en cascade : correction utilisateur > règles > MCC > LLM > à classer."""
import re
from functools import lru_cache
from pathlib import Path

import yaml

from . import db
from .categories import MCC_MAP, nature_of
from .llm import classify_merchants
from .normalize import clean_label

RULES_PATH = Path(__file__).with_name("rules.yaml")

# Catégories qui gardent leur sens sur une entrée d'argent
_CREDIT_CATEGORIES = {"epargne", "virements", "revenus", "remboursements"}


@lru_cache
def load_rules() -> list[tuple[re.Pattern, str]]:
    raw = yaml.safe_load(RULES_PATH.read_text(encoding="utf-8")) or []
    return [(re.compile(r["pattern"]), r["category"]) for r in raw]


def match_rules(text: str) -> str | None:
    cleaned = clean_label(text)
    for pattern, category in load_rules():
        if pattern.search(cleaned):
            return category
    return None


def classify_one(tx: dict, overrides: dict) -> tuple[str, str | None, str] | None:
    """Renvoie (category, nature_forcée, source) ou None si le LLM doit trancher."""
    ov = overrides.get(tx["merchant"])
    if ov and ov["source"] == "user":
        return ov["category"], ov["nature"], "user"

    text = f'{tx.get("label") or ""} {tx.get("counterparty") or ""}'
    category, source = match_rules(text), "rule"
    if not category and tx.get("mcc"):
        category, source = MCC_MAP.get(str(tx["mcc"])), "mcc"
    if not category and ov:
        category, source = ov["category"], ov["source"]

    if tx["amount"] > 0:  # entrée d'argent
        if category in _CREDIT_CATEGORIES:
            return category, None, source
        return "revenus", None, "default"

    if category:
        return category, None, source
    return None


def classify_pending(force: bool = False) -> int:
    """Classe les transactions non encore classées (ou toutes si force=True)."""
    where = "" if force else "WHERE class_source IS NULL OR class_source = 'default'"
    txs = db.rows(f"SELECT * FROM transactions {where}")
    if not txs:
        return 0

    overrides = db.get_overrides()
    results, unknown = {}, set()
    for tx in txs:
        res = classify_one(tx, overrides)
        if res:
            results[tx["id"]] = res
        else:
            unknown.add(tx["merchant"])

    # Un seul appel LLM par marchand inconnu, mis en cache dans merchant_overrides
    llm_cats = classify_merchants(sorted(unknown)) if unknown else {}
    for merchant, cat in llm_cats.items():
        db.save_override(merchant, cat, None, "llm")

    updates = []
    for tx in txs:
        if tx["id"] in results:
            cat, forced_nature, src = results[tx["id"]]
        elif tx["merchant"] in llm_cats:
            cat, forced_nature, src = llm_cats[tx["merchant"]], None, "llm"
        else:
            cat, forced_nature, src = "inconnu", None, "default"
        updates.append((cat, forced_nature or nature_of(cat), src, tx["id"]))
    db.set_classification(updates)
    return len(updates)


def apply_user_override(merchant: str, category: str, nature: str | None = None) -> int:
    """Correction manuelle : mémorisée et appliquée à toutes les opérations du marchand."""
    db.save_override(merchant, category, nature, "user")
    txs = db.rows("SELECT id, amount FROM transactions WHERE merchant = ?", (merchant,))
    updates = [(category, nature or nature_of(category), "user", t["id"]) for t in txs]
    db.set_classification(updates)
    return len(updates)
