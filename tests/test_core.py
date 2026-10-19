from datetime import date, timedelta

import pytest

from app.categories import nature_of
from app.classifier import classify_one, match_rules
from app.enable_banking import normalize_transaction
from app.insights import detect_recurring
from app.normalize import extract_merchant, merchant_key


@pytest.mark.parametrize("label, merchant", [
    ("CB CARREFOUR MARKET 12/03 PARIS", "CARREFOUR MARKET"),
    ("CARTE X4821 14/03 UBER EATS", "UBER EATS"),
    ("PRLV SEPA FREE MOBILE FM123456789", "FREE MOBILE"),
    ("PAIEMENT PAR CARTE X1234 STARBUCKS 0231 PARIS", "STARBUCKS"),
    ("VIR SEPA RECU DE ACME SAS SALAIRE", "ACME SAS SALAIRE"),
    ("CARTE 23/09 PPG*SKIN AND OUT PARIS", "PPG SKIN AND OUT"),
    ("VIR INST WERO GAUCHOUX JULIE  01a0e365e8ea7108b0ed9107486c29d8", "WERO GAUCHOUX JULIE"),
    ("PRLV SEPA KEREIS FRANCE POUR CARDIF / / 123456", "KEREIS FRANCE POUR CARDIF"),
])
def test_extract_merchant(label, merchant):
    assert extract_merchant(label) == merchant


def test_merchant_key_is_url_safe_and_punctuation_insensitive():
    assert merchant_key("KEREIS FRANCE POUR CARDIF / /") == "KEREISFRANCEPOURCARDIF"
    assert merchant_key("NETFLIX.COM") == merchant_key("Netflix com") == "NETFLIXCOM"


@pytest.mark.parametrize("label, category", [
    ("CARTE X4821 14/03 UBER EATS", "livraison"),   # avant la règle transport UBER
    ("CB UBER TRIP 14/03", "transport"),
    ("PRLV SEPA TOTALENERGIES ELEC", "energie"),     # pas la station TOTAL
    ("CB TOTAL ACCESS 02/04", "transport"),
    ("VIR SEPA ASSURANCE VIE LINXEA", "epargne"),    # pas assurance
    ("VIR SEPA LOYER JUIN", "logement"),             # pas virements
    ("COMMISSION INTERVENTION", "frais_bancaires"),
    ("CB BOULANGERIE DU MARCHE", "courses"),
    ("CARTE 12/05 INTERFLORA", "cadeaux"),
    ("CB FLEURISTE LES JARDINS", "cadeaux"),
    ("CB AU BOUQUET DE FLEURS", "cadeaux"),
    ("CB SMARTBOX GROUP", "cadeaux"),
    ("VIR INST KDO MARIAGE", "cadeaux"),            # avant la règle virements
    ("CB FLEURY MICHON", None),                      # pas un fleuriste
    ("CB ZOOMALIA LATRESN LATRESNE", "animaux"),
    ("CB ZOOMAG LATRESNE", "animaux"),
    ("PAYPAL ZOOPLUS LUXEMBOURG", "animaux"),
    ("CB VETERINAIRES DE LANGOIRAN", "animaux"),     # pas sante
    ("CB MAXI ZOO BEGLES", "animaux"),
    ("CB TOM&CO MERIGNAC", "animaux"),
    ("CB ZOOM.US 888-799", None),                    # visio, pas une animalerie
    ("CB LA POSTE.FR PARIS CEDEX", "shopping"),
    ("CB LAPOSTE LANGOIRAN", "shopping"),
    ("PAYPAL LA POSTE LUXEMBOURG", "shopping"),
    ("CB BUREAU VALLEE BEGLES", "shopping"),
    ("CB PAPETERIE DU CENTRE", "shopping"),
    ("PRLV LA BANQUE POSTALE COTISATION", "frais_bancaires"),  # la banque, pas le courrier
])
def test_rules(label, category):
    assert match_rules(label) == category


def test_credit_defaults_to_revenus():
    tx = {"merchant": "AMAZON", "merchant_key": "AMAZON", "label": "CREDIT DIVERS AMAZON", "amount": 25.0}
    assert classify_one(tx, {})[0] == "revenus"


def test_refund_classified_as_remboursements():
    tx = {"merchant": "SPENDESK", "merchant_key": "SPENDESK", "label": "VIR EVINA SPENDESK NOTE DE FRAIS", "amount": 15.5}
    assert classify_one(tx, {})[0] == "remboursements"


def test_user_override_wins_over_rules():
    tx = {"merchant": "UBER", "merchant_key": "UBER", "label": "CB UBER", "amount": -12.0}
    overrides = {"UBER": {"category": "transport", "nature": "essentiel", "source": "user"}}
    assert classify_one(tx, overrides) == ("transport", "essentiel", "user")


def test_unknown_merchant_goes_to_llm():
    tx = {"merchant": "ATELIER MIRABELLE", "merchant_key": "ATELIERMIRABELLE", "label": "CB ATELIER MIRABELLE", "amount": -30.0}
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
    return {"id": str(i), "date": d.isoformat(), "merchant": merchant,
            "merchant_key": merchant_key(merchant), "amount": amount,
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


def test_user_override_by_key_handles_slash_in_name(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient
    from app import config, db, main
    monkeypatch.setattr(config.settings, "db_path", tmp_path / "t.db")
    db.init_db()
    db.insert_transactions([{
        "id": "a:1", "account_uid": "a", "date": "2026-09-01", "amount": -40.0, "currency": "EUR",
        "label": "PRLV SEPA KEREIS FRANCE POUR CARDIF / /", "counterparty": "", "mcc": None,
        "merchant": "KEREIS FRANCE POUR CARDIF / /",
    }])
    client = TestClient(main.app)
    r = client.put("/api/merchants/KEREISFRANCEPOURCARDIF", json={"category": "assurance"})
    assert r.status_code == 200 and r.json() == {"updated": 1}
    assert db.get_overrides()["KEREISFRANCEPOURCARDIF"]["category"] == "assurance"
    assert client.put("/api/merchants/NOPE", json={"category": "assurance"}).status_code == 404


def test_migrates_legacy_merchant_schema(tmp_path, monkeypatch):
    import sqlite3
    from app import config, db
    path = tmp_path / "old.db"
    con = sqlite3.connect(path)
    con.executescript("""
        CREATE TABLE transactions (id TEXT PRIMARY KEY, account_uid TEXT NOT NULL, date TEXT NOT NULL,
            amount REAL NOT NULL, currency TEXT, label TEXT, counterparty TEXT, mcc TEXT, merchant TEXT,
            category TEXT, nature TEXT, class_source TEXT);
        CREATE TABLE merchant_overrides (merchant TEXT PRIMARY KEY, category TEXT NOT NULL,
            nature TEXT, source TEXT NOT NULL);
        INSERT INTO transactions (id, account_uid, date, amount, merchant)
            VALUES ('a:1', 'a', '2026-09-01', -40, 'KEREIS FRANCE POUR CARDIF / /');
        INSERT INTO merchant_overrides VALUES ('NETFLIX.COM', 'abonnements', NULL, 'user');
        INSERT INTO merchant_overrides VALUES ('NETFLIX COM', 'loisirs', NULL, 'llm');
    """)
    con.commit(); con.close()
    monkeypatch.setattr(config.settings, "db_path", path)
    db.init_db()
    db.init_db()  # idempotent
    assert db.rows("SELECT merchant, merchant_key FROM transactions") == \
        [{"merchant": "KEREIS FRANCE POUR CARDIF", "merchant_key": "KEREISFRANCEPOURCARDIF"}]
    assert db.get_overrides()["NETFLIXCOM"]["source"] == "user"


# --- Clés marchand URL-safe et corrections manuelles durables ------------------

def _fresh_db(tmp_path, monkeypatch):
    from app import config, db
    monkeypatch.setattr(config.settings, "db_path", tmp_path / "t.db")
    db.init_db()
    return db


def _raw(i, merchant, d="2026-09-01", amount=-40.0):
    return {"id": f"a:{i}", "account_uid": "a", "date": d, "amount": amount, "currency": "EUR",
            "label": f"PRLV SEPA {merchant}", "counterparty": "", "mcc": None, "merchant": merchant}


NASTY = ["KEREIS FRANCE POUR CARDIF / /", "A/B C", "100% BIO", "SHOP #12", "WHAT? NOW",
         "CAFÉ DE L'ÉTÉ", "BACK\\SLASH", "  ESPACES   MULTIPLES  ", "AMAZON.FR+PRIME", "/"]


@pytest.mark.parametrize("merchant", NASTY)
def test_merchant_key_from_nasty_names_is_alnum_and_routable(tmp_path, monkeypatch, merchant):
    import re
    from urllib.parse import quote
    from fastapi.testclient import TestClient
    from app import main
    db = _fresh_db(tmp_path, monkeypatch)
    db.insert_transactions([_raw(1, merchant)])
    key = db.rows("SELECT merchant_key FROM transactions")[0]["merchant_key"]
    assert re.fullmatch(r"[A-Z0-9]+", key)
    r = TestClient(main.app).put(f"/api/merchants/{quote(key, safe='')}", json={"category": "assurance"})
    assert r.status_code == 200, r.text


def test_manual_correction_survives_forced_reclassify_without_overrides(tmp_path, monkeypatch):
    from app import classifier
    db = _fresh_db(tmp_path, monkeypatch)
    db.insert_transactions([_raw(1, "ATELIER MIRABELLE")])
    monkeypatch.setattr(classifier, "classify_merchants", lambda ms: {})
    classifier.apply_user_override("ATELIERMIRABELLE", "loisirs")
    with db.connect() as con:
        con.execute("DELETE FROM merchant_overrides")
    classifier.classify_pending(force=True)
    assert db.rows("SELECT category, class_source FROM transactions") == \
        [{"category": "loisirs", "class_source": "user"}]


def test_new_transaction_inherits_merchant_correction(tmp_path, monkeypatch):
    from app import classifier
    db = _fresh_db(tmp_path, monkeypatch)
    monkeypatch.setattr(classifier, "classify_merchants", lambda ms: {})
    db.insert_transactions([_raw(1, "ATELIER MIRABELLE")])
    classifier.apply_user_override("ATELIERMIRABELLE", "loisirs")
    db.insert_transactions([_raw(2, "ATELIER MIRABELLE", d="2026-10-01")])
    classifier.classify_pending()
    assert db.rows("SELECT category FROM transactions WHERE id='a:2'") == [{"category": "loisirs"}]


def test_stale_keys_are_recomputed_and_user_rules_rebuilt(tmp_path, monkeypatch):
    """Simule une évolution de merchant_key() : clés stockées périmées, règle orpheline."""
    from app import classifier
    db = _fresh_db(tmp_path, monkeypatch)
    monkeypatch.setattr(classifier, "classify_merchants", lambda ms: {})
    db.insert_transactions([_raw(1, "ATELIER MIRABELLE", d="2026-08-01"),
                            _raw(2, "ATELIER MIRABELLE", d="2026-09-01")])
    classifier.apply_user_override("ATELIERMIRABELLE", "shopping")
    with db.connect() as con:  # plus récente correction : loisirs, sur l'opération de septembre
        con.execute("UPDATE transactions SET user_category='loisirs', category='loisirs' WHERE id='a:2'")
        con.execute("UPDATE transactions SET merchant_key='OLD-KEY'")
        con.execute("DELETE FROM merchant_overrides")
    db.init_db()
    assert {r["merchant_key"] for r in db.rows("SELECT merchant_key FROM transactions")} == {"ATELIERMIRABELLE"}
    assert db.get_overrides()["ATELIERMIRABELLE"]["category"] == "loisirs"
    db.insert_transactions([_raw(3, "ATELIER MIRABELLE", d="2026-10-01")])
    classifier.classify_pending()
    assert db.rows("SELECT category FROM transactions WHERE id='a:3'") == [{"category": "loisirs"}]


def test_legacy_user_classifications_become_transaction_corrections(tmp_path, monkeypatch):
    import sqlite3
    from app import classifier, config, db
    path = tmp_path / "old.db"
    con = sqlite3.connect(path)
    con.executescript("""
        CREATE TABLE transactions (id TEXT PRIMARY KEY, account_uid TEXT NOT NULL, date TEXT NOT NULL,
            amount REAL NOT NULL, currency TEXT, label TEXT, counterparty TEXT, mcc TEXT, merchant TEXT,
            category TEXT, nature TEXT, class_source TEXT);
        INSERT INTO transactions (id, account_uid, date, amount, merchant, category, nature, class_source)
            VALUES ('a:1', 'a', '2026-09-01', -40, 'ATELIER MIRABELLE', 'loisirs', 'optimisable', 'user');
    """)
    con.commit(); con.close()
    monkeypatch.setattr(config.settings, "db_path", path)
    monkeypatch.setattr(classifier, "classify_merchants", lambda ms: {})
    db.init_db()
    classifier.classify_pending(force=True)
    assert db.rows("SELECT category, user_category, class_source FROM transactions") == \
        [{"category": "loisirs", "user_category": "loisirs", "class_source": "user"}]


def test_dashboard_loads_filter_script():
    from fastapi.testclient import TestClient
    from app import main
    client = TestClient(main.app)
    assert '<script src="/static/filters.js"></script>' in client.get("/").text
    r = client.get("/static/filters.js")
    assert r.status_code == 200 and "function filterTransactions" in r.text


# --- Chèques émis : seul l'utilisateur connaît le bénéficiaire -----------------

@pytest.mark.parametrize("label, expected", [
    ("CHQ 0538322", True),
    ("CHEQUE 0538322", True),
    ("CHQ N 0538322", True),
    ("REM CHQ 4625630 0034 002 CHQ", False),  # remise de chèque = encaissement
    ("CB CHQUEMIN DU LAC", False),
])
def test_is_cheque(label, expected):
    from app.normalize import is_cheque
    assert is_cheque(label) is expected


def test_debited_cheque_stays_unclassified_despite_rules_and_llm_cache():
    tx = {"merchant": "CHQ 0538322", "merchant_key": "CHQ0538322", "label": "CHQ 0538322", "amount": -60.0}
    overrides = {"CHQ0538322": {"category": "frais_bancaires", "nature": None, "source": "llm"}}
    assert classify_one(tx, overrides) == ("inconnu", None, "default")


def test_user_correction_on_cheque_wins():
    tx = {"merchant": "CHQ 0538322", "merchant_key": "CHQ0538322", "label": "CHQ 0538322",
          "amount": -60.0, "user_category": "sante", "user_nature": None}
    assert classify_one(tx, {}) == ("sante", None, "user")


def test_cheques_are_never_sent_to_llm(tmp_path, monkeypatch):
    from app import classifier
    db = _fresh_db(tmp_path, monkeypatch)
    db.insert_transactions([{**_raw(1, "CHQ 0538322"), "label": "CHQ 0538322"},
                            {**_raw(2, "ATELIER MIRABELLE"), "label": "CB ATELIER MIRABELLE"}])
    calls = []
    monkeypatch.setattr(classifier, "classify_merchants", lambda ms: calls.append(ms) or {})
    classifier.classify_pending()
    assert calls == [["ATELIER MIRABELLE"]]
    assert db.rows("SELECT category FROM transactions WHERE id='a:1'") == [{"category": "inconnu"}]


def test_startup_resets_cheques_misclassified_by_llm(tmp_path, monkeypatch):
    db = _fresh_db(tmp_path, monkeypatch)
    db.insert_transactions([{**_raw(1, "CHQ 0538320"), "label": "CHQ 0538320"},
                            {**_raw(2, "CHQ 0538324"), "label": "CHQ 0538324"}])
    with db.connect() as con:
        con.execute("""UPDATE transactions SET category='frais_bancaires', nature='optimisable',
                       class_source='llm' WHERE id='a:1'""")
        con.execute("""UPDATE transactions SET category='sante', nature='essentiel', class_source='user',
                       user_category='sante' WHERE id='a:2'""")
    db.save_override("CHQ0538320", "frais_bancaires", None, "llm")
    db.init_db()
    assert db.rows("SELECT id, category, class_source FROM transactions ORDER BY id") == [
        {"id": "a:1", "category": "inconnu", "class_source": "default"},
        {"id": "a:2", "category": "sante", "class_source": "user"},
    ]
    assert "CHQ0538320" not in db.get_overrides()


@pytest.mark.parametrize("count, nag", [(2, False), (3, True)])
def test_cheque_nag_when_too_many_cheques(tmp_path, monkeypatch, count, nag):
    from app import insights
    db = _fresh_db(tmp_path, monkeypatch)
    db.insert_transactions([{**_raw(i, f"CHQ 053832{i}"), "label": f"CHQ 053832{i}"} for i in range(count)])
    s = insights.monthly_summary("2026-09")
    assert (s["cheque_nag"] is not None) is nag
    if nag:
        assert "chéquier" in s["cheque_nag"]



def test_cadeaux_category_is_optimisable_with_savings_rate():
    from app.categories import CATEGORIES, SAVINGS_RATE
    assert CATEGORIES["cadeaux"] == {"label": "Cadeaux & fleurs", "nature": "optimisable"}
    assert "cadeaux" in SAVINGS_RATE



def test_animaux_category_is_essential():
    from app.categories import CATEGORIES
    assert CATEGORIES["animaux"] == {"label": "Animaux", "nature": "essentiel"}


# --- Tendances : dépenses par catégorie, mois par mois --------------------------

def test_trends_by_category_per_month(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient
    from app import main
    db = _fresh_db(tmp_path, monkeypatch)
    db.insert_transactions([
        _raw(1, "CARREFOUR", "2026-08-03", -100.0), _raw(2, "CARREFOUR", "2026-09-03", -60.0),
        _raw(3, "CARREFOUR", "2026-09-20", -15.5), _raw(4, "NETFLIX", "2026-09-05", -13.0),
        _raw(5, "MYSTERE", "2026-08-10", -42.0),  # jamais classé (category NULL) -> à classer
        _raw(6, "LIVRET A", "2026-09-01", -500.0), _raw(7, "EMPLOYEUR", "2026-09-28", 2500.0),
    ])
    with db.connect() as con:
        for ids, cat, nat in [("'a:1','a:2','a:3'", "courses", "essentiel"), ("'a:4'", "abonnements", "optimisable"),
                              ("'a:6'", "epargne", "epargne"), ("'a:7'", "revenus", "revenu")]:
            con.execute(f"UPDATE transactions SET category = ?, nature = ? WHERE id IN ({ids})", (cat, nat))

    r = TestClient(main.app).get("/api/trends")
    assert r.status_code == 200
    body = r.json()
    assert body["months"] == ["2026-08", "2026-09"]
    by_cat = {c["category"]: c for c in body["categories"]}
    assert set(by_cat) == {"courses", "abonnements", "inconnu"}  # ni épargne, ni entrées
    assert by_cat["courses"]["amounts"] == [100.0, 75.5]
    assert by_cat["courses"]["label"] == "Courses" and by_cat["courses"]["total"] == 175.5
    assert by_cat["inconnu"]["amounts"] == [42.0, 0.0]
    assert by_cat["abonnements"]["amounts"] == [0.0, 13.0]
    assert [c["category"] for c in body["categories"]] == ["courses", "inconnu", "abonnements"]


def test_trends_empty_without_transactions(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient
    from app import main
    _fresh_db(tmp_path, monkeypatch)
    assert TestClient(main.app).get("/api/trends").json() == {"months": [], "categories": []}


def test_trends_page_is_served():
    from fastapi.testclient import TestClient
    from app import main
    client = TestClient(main.app)
    page = client.get("/tendances")
    assert page.status_code == 200 and '<script src="/static/trends.js"></script>' in page.text
    assert 'href="/tendances"' in client.get("/").text


# --- Bilan entrées / sorties et conseils du LLM ----------------------------------

def _classify(db, rows):
    with db.connect() as con:
        for ids, cat, nat in rows:
            con.execute(f"UPDATE transactions SET category = ?, nature = ? WHERE id IN ({ids})", (cat, nat))


def _cashflow_db(tmp_path, monkeypatch):
    db = _fresh_db(tmp_path, monkeypatch)
    db.insert_transactions([
        _raw(1, "EMPLOYEUR", "2026-07-28", 2500.0), _raw(2, "CARREFOUR", "2026-07-03", -300.0),
        _raw(3, "EMPLOYEUR", "2026-08-28", 2500.0), _raw(4, "CARREFOUR", "2026-08-03", -2700.0),
        _raw(5, "AMELI", "2026-08-12", 40.0),  # remboursement : compte en entrée
        _raw(6, "LIVRET A", "2026-08-01", -500.0), _raw(7, "LIVRET A", "2026-08-20", 100.0),  # épargne nette 400
        _raw(8, "COMPTE JOINT", "2026-08-15", -800.0),  # virement interne : ni entrée ni sortie
        _raw(9, "MYSTERE", "2026-08-10", -42.0),  # pas encore classé : compte en sortie
        _raw(10, "NETFLIX", "2026-06-08", -13.0), _raw(11, "NETFLIX", "2026-07-08", -13.0),
        _raw(12, "NETFLIX", "2026-08-08", -13.0),
    ])
    _classify(db, [("'a:1','a:3'", "revenus", "revenu"), ("'a:5'", "remboursements", "revenu"),
                   ("'a:2','a:4'", "courses", "essentiel"), ("'a:6','a:7'", "epargne", "epargne"),
                   ("'a:8'", "virements", "transfert"), ("'a:10','a:11','a:12'", "abonnements", "optimisable")])
    return db


def test_cashflow_income_vs_spending_per_month(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient
    from app import main
    _cashflow_db(tmp_path, monkeypatch)
    body = TestClient(main.app).get("/api/cashflow").json()
    assert body["months"] == ["2026-06", "2026-07", "2026-08"]
    assert body["income"] == [0.0, 2500.0, 2540.0]
    assert body["spent"] == [13.0, 313.0, 2755.0]
    assert body["savings"] == [0.0, 0.0, 400.0]
    assert body["partial"] is None


def test_cashflow_flags_current_month_as_partial(tmp_path, monkeypatch):
    from app import insights
    db = _fresh_db(tmp_path, monkeypatch)
    today = date.today()
    db.insert_transactions([_raw(1, "CARREFOUR", today.isoformat(), -20.0),
                            _raw(2, "CARREFOUR", (today.replace(day=1) - timedelta(days=1)).isoformat(), -20.0)])
    assert insights.cashflow()["partial"] == today.isoformat()[:7]


def test_cashflow_empty_without_transactions(tmp_path, monkeypatch):
    from app import insights
    _fresh_db(tmp_path, monkeypatch)
    assert insights.cashflow() == {"months": [], "income": [], "spent": [], "savings": [], "partial": None}


def test_advice_context_holds_only_aggregates_of_complete_months(tmp_path, monkeypatch):
    import json
    from app import insights
    db = _cashflow_db(tmp_path, monkeypatch)
    db.insert_transactions([_raw(20, "CARREFOUR", date.today().isoformat(), -9999.0)])  # mois en cours ignoré
    ctx = insights.advice_context(2)
    assert [m["mois"] for m in ctx["mois"]] == ["2026-07", "2026-08"]
    assert ctx["mois"][1] == {"mois": "2026-08", "entrees": 2540.0, "sorties": 2755.0, "solde": -215.0, "epargne": 400.0}
    assert ctx["moyennes"]["solde"] == round((2187.0 - 215.0) / 2, 2)
    assert ctx["mois_en_deficit"] == 1
    cats = {c["categorie"]: c for c in ctx["depenses_par_categorie"]}
    assert cats["Courses"]["moyenne_mensuelle"] == 1500.0 and cats["Courses"]["nature"] == "essentiel"
    assert "Épargne" not in cats and "Revenus" not in cats
    sent = json.dumps(ctx, ensure_ascii=False).upper()
    for secret in ("CARREFOUR", "NETFLIX", "EMPLOYEUR", "LIVRET", "MYSTERE", "PRLV", "-03", "-28"):
        assert secret not in sent  # ni marchand, ni libellé, ni jour précis


def test_advice_context_none_without_complete_month(tmp_path, monkeypatch):
    from app import insights
    db = _fresh_db(tmp_path, monkeypatch)
    assert insights.advice_context(6) is None
    db.insert_transactions([_raw(1, "CARREFOUR", date.today().isoformat(), -20.0)])
    assert insights.advice_context(6) is None


def test_advise_parses_llm_answer(monkeypatch):
    from app import config, llm
    monkeypatch.setattr(config.settings, "llm_provider", "ollama")
    seen = {}

    def fake_chat(system, user, **kw):
        seen["user"] = user
        return 'Voici : {"synthese": "Tu dépenses plus que tu ne gagnes.", "conseils": ["Revois les courses", "Coupe un abonnement"]}'
    monkeypatch.setitem(llm._CHAT, "ollama", fake_chat)
    out = llm.advise({"mois": [{"mois": "2026-08", "solde": -215.0}]})
    assert out == {"synthese": "Tu dépenses plus que tu ne gagnes.", "conseils": ["Revois les courses", "Coupe un abonnement"]}
    assert '"solde": -215.0' in seen["user"]

    monkeypatch.setitem(llm._CHAT, "ollama", lambda system, user, **kw: "Réponse libre, sans JSON.")
    assert llm.advise({}) == {"synthese": "Réponse libre, sans JSON.", "conseils": []}

    def boom(system, user, **kw):
        raise ConnectionError("ollama absent")
    monkeypatch.setitem(llm._CHAT, "ollama", boom)
    assert llm.advise({}) is None


def test_classification_goes_through_shared_chat(monkeypatch):
    from app import config, llm
    monkeypatch.setattr(config.settings, "llm_provider", "ollama")
    monkeypatch.setitem(llm._CHAT, "ollama", lambda system, user, **kw: '{"UBER EATS": "livraison"}')
    assert llm.classify_merchants(["UBER EATS"]) == {"UBER EATS": "livraison"}


def test_api_advice(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient
    from app import config, llm, main
    _cashflow_db(tmp_path, monkeypatch)
    client = TestClient(main.app)

    monkeypatch.setattr(config.settings, "llm_provider", "gemini")
    monkeypatch.setattr(config.settings, "gemini_api_key", "")
    assert client.post("/api/advice", json={"months": 6}).status_code == 400  # pas de clé

    monkeypatch.setattr(config.settings, "gemini_api_key", "k")
    seen = []
    monkeypatch.setattr(llm, "advise", lambda ctx: seen.append(ctx) or {"synthese": "ok", "conseils": ["a"]})
    r = client.post("/api/advice", json={"months": 12})
    assert r.status_code == 200
    assert r.json()["synthese"] == "ok" and r.json()["months"] == ["2026-06", "2026-07", "2026-08"]
    assert r.json()["provider"] == "gemini"
    assert len(seen[0]["mois"]) == 3

    monkeypatch.setattr(llm, "advise", lambda ctx: None)
    assert client.post("/api/advice", json={"months": 6}).status_code == 502
    assert client.post("/api/advice", json={"months": 0}).status_code == 422
