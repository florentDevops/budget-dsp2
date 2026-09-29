from datetime import date, timedelta

import pytest

from app.categories import nature_of
from app.classifier import classify_one, match_rules
from app.enable_banking import normalize_transaction
from app.insights import detect_recurring
from app.normalize import extract_merchant


@pytest.mark.parametrize("label, merchant", [
    ("CB CARREFOUR MARKET 12/03 PARIS", "CARREFOUR MARKET"),
    ("CARTE X4821 14/03 UBER EATS", "UBER EATS"),
    ("PRLV SEPA FREE MOBILE FM123456789", "FREE MOBILE"),
    ("PAIEMENT PAR CARTE X1234 STARBUCKS 0231 PARIS", "STARBUCKS"),
    ("VIR SEPA RECU DE ACME SAS SALAIRE", "ACME SAS SALAIRE"),
])
def test_extract_merchant(label, merchant):
    assert extract_merchant(label) == merchant


@pytest.mark.parametrize("label, category", [
    ("CARTE X4821 14/03 UBER EATS", "livraison"),   # avant la règle transport UBER
    ("CB UBER TRIP 14/03", "transport"),
    ("PRLV SEPA TOTALENERGIES ELEC", "energie"),     # pas la station TOTAL
    ("CB TOTAL ACCESS 02/04", "transport"),
    ("VIR SEPA ASSURANCE VIE LINXEA", "epargne"),    # pas assurance
    ("VIR SEPA LOYER JUIN", "logement"),             # pas virements
    ("COMMISSION INTERVENTION", "frais_bancaires"),
    ("CB BOULANGERIE DU MARCHE", "courses"),
])
def test_rules(label, category):
    assert match_rules(label) == category


def test_credit_defaults_to_revenus():
    tx = {"merchant": "AMAZON", "label": "REMBOURSEMENT AMAZON", "amount": 25.0}
    assert classify_one(tx, {})[0] == "revenus"


def test_user_override_wins_over_rules():
    tx = {"merchant": "UBER", "label": "CB UBER", "amount": -12.0}
    overrides = {"UBER": {"category": "transport", "nature": "essentiel", "source": "user"}}
    assert classify_one(tx, overrides) == ("transport", "essentiel", "user")


def test_unknown_merchant_goes_to_llm():
    tx = {"merchant": "ATELIER MIRABELLE", "label": "CB ATELIER MIRABELLE", "amount": -30.0}
    assert classify_one(tx, {}) is None


def test_normalize_enable_banking_payload():
    raw = {
        "entry_reference": "ABC123",
        "transaction_amount": {"currency": "EUR", "amount": "13.49"},
        "credit_debit_indicator": "DBIT",
        "status": "BOOK",
        "booking_date": "2026-09-08",
        "remittance_information": ["CB NETFLIX.COM 08/09"],
        "creditor": {"name": "NETFLIX.COM"},
    }
    tx = normalize_transaction(raw, "acc1")
    assert tx["amount"] == -13.49 and tx["merchant"] == "NETFLIX.COM" and tx["id"] == "acc1:ABC123"
    assert normalize_transaction({**raw, "status": "PDNG"}, "acc1") is None


def _tx(i, d, merchant, amount, category="abonnements"):
    return {"id": str(i), "date": d.isoformat(), "merchant": merchant, "amount": amount,
            "category": category, "nature": nature_of(category)}


def test_detect_recurring():
    start = date.today() - timedelta(days=150)
    txs = [_tx(i, start + timedelta(days=30 * i), "NETFLIX.COM", -13.49) for i in range(6)]
    txs += [_tx(10 + i, start + timedelta(days=9 * i), "CARREFOUR", -20.0 - 7 * i, "courses")
            for i in range(15)]
    found = detect_recurring(txs)
    assert [r["merchant"] for r in found] == ["NETFLIX.COM"]
    assert found[0]["yearly"] == pytest.approx(161.88)


def test_llm_results_are_cached(tmp_path, monkeypatch):
    from app import classifier, config, db
    monkeypatch.setattr(config.settings, "db_path", tmp_path / "t.db")
    db.init_db()
    db.insert_transactions([{
        "id": "a:1", "account_uid": "a", "date": "2026-09-01", "amount": -30.0, "currency": "EUR",
        "label": "CB ATELIER MIRABELLE", "counterparty": "", "mcc": None, "merchant": "ATELIER MIRABELLE",
    }])
    calls = []
    monkeypatch.setattr(classifier, "classify_merchants",
                        lambda ms: calls.append(ms) or {m: "shopping" for m in ms})
    classifier.classify_pending()
    assert db.rows("SELECT category, class_source FROM transactions")[0] == \
        {"category": "shopping", "class_source": "llm"}
    classifier.classify_pending(force=True)  # 2e passage : servi depuis le cache
    assert calls == [["ATELIER MIRABELLE"]]
