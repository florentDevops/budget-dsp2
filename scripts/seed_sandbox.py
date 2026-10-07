"""Charge scripts/sandbox_transactions.json (schéma Enable Banking réel) en passant
par le vrai normalize_transaction() : python -m scripts.seed_sandbox

Utile pour tester le parsing EB → classification sans dépendre du Mock ASPSP,
qui ne permet pas d'injecter des transactions personnalisées.
"""
import json
from pathlib import Path

from app import classifier, db
from app.enable_banking import normalize_transaction

ACCOUNT_UID = "sandbox-compte-courant"
FIXTURE = Path(__file__).with_name("sandbox_transactions.json")

if __name__ == "__main__":
    db.init_db()
    db.upsert_account({
        "uid": ACCOUNT_UID, "session_id": None, "bank": "Sandbox EB", "name": "Compte courant",
        "iban": "FR76 •••• 0099", "currency": "EUR", "valid_until": None,
    })
    raw = json.loads(FIXTURE.read_text(encoding="utf-8"))
    txs = [tx for tx in (normalize_transaction(r, ACCOUNT_UID) for r in raw) if tx]
    inserted = db.insert_transactions(txs)
    print(f"{inserted} opérations importées, {classifier.classify_pending()} classées.")
