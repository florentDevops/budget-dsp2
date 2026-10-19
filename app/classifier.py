"""Classification en cascade : correction utilisateur > règles > MCC > LLM > à classer."""
import re
from functools import lru_cache
from pathlib import Path

import yaml

from . import db
from .categories import MCC_MAP, nature_of
from .llm import classify_merchants
from .normalize import clean_label, is_cheque

RULES_PATH = Path(__file__).with_name("rules.yaml")

# Catégories qui gardent leur sens sur une entrée d'argent
_CREDIT_CATEGORIES = {"epargne", "epargne_enfants", "virements", "revenus", "remboursements"}


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
    if tx.get("user_category"):  # correction manuelle portée par la transaction elle-même
        return tx["user_category"], tx.get("user_nature"), "user"
    ov = overrides.get(tx["merchant_key"])
    if ov and ov["source"] == "user":
        return ov["category"], ov["nature"], "user"
    if tx["amount"] < 0 and is_cheque(tx.get("label") or ""):
        return "inconnu", None, "default"  # ni règle ni LLM : à classer à la main

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
    results, unknown = {}, {}  # unknown : nom affiché -> clé
    for tx in txs:
        res = classify_one(tx, overrides)
        if res:
            results[tx["id"]] = res
        else:
            unknown.setdefault(tx["merchant"], tx["merchant_key"])

    # Un seul appel LLM par marchand inconnu (on lui envoie le nom lisible), mis en
    # cache dans merchant_overrides sous la clé technique
    by_name = classify_merchants(sorted(unknown)) if unknown else {}
    llm_cats = {unknown[m]: cat for m, cat in by_name.items() if m in unknown}
    for key, cat in llm_cats.items():
        db.save_override(key, cat, None, "llm")

    updates = []
    for tx in txs:
        if tx["id"] in results:
            cat, forced_nature, src = results[tx["id"]]
        elif tx["merchant_key"] in llm_cats:
            cat, forced_nature, src = llm_cats[tx["merchant_key"]], None, "llm"
        else:
            cat, forced_nature, src = "inconnu", None, "default"
        updates.append((cat, forced_nature or nature_of(cat), src, tx["id"]))
    db.set_classification(updates)
    return len(updates)


def apply_user_override(key: str, category: str, nature: str | None = None) -> int:
    """Correction manuelle : écrite sur toutes les opérations du marchand (source de vérité),
    et mémorisée en règle marchand pour les opérations à venir."""
    with db.connect() as con:
        updated = con.execute(
            """UPDATE transactions SET user_category=?, user_nature=?, category=?, nature=?,
                   class_source='user' WHERE merchant_key=?""",
            (category, nature, category, nature or nature_of(category), key),
        ).rowcount
    if updated:
        db.save_override(key, category, nature, "user")
    return updated
