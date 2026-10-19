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
    ("ECH PRET   9068203 DU 05/10/26", "logement"),     # échéance du crédit maison, pas un remboursement reçu
    ("PRLV ECHEANCE PRET IMMO", "logement"),
    ("VIR LDDS FLORENT", "epargne"),
    ("VIREMENT VERS LDD", "epargne"),
    ("VIR LIVRET DEVELOPPEMENT DURABLE", "epargne"),
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


# --- Comptes multiples : connexion perso / pro et rôle par compte ---------------

@pytest.mark.parametrize("account, psu_type, role", [
    ({"cash_account_type": "CACC", "usage": "PRIV"}, "personal", "courant"),
    ({"cash_account_type": "SVGS", "usage": "PRIV"}, "personal", "epargne"),   # livret A, livret enfants
    ({"cash_account_type": "LOAN"}, "personal", "credit"),                    # crédit maison
    ({"cash_account_type": "CACC"}, "business", "pro"),                       # Qonto
    ({"cash_account_type": "CACC", "usage": "ORGA"}, "personal", "pro"),
    ({"cash_account_type": "SVGS"}, "business", "pro"),                       # épargne de la société, pas la tienne
    ({"cash_account_type": "LOAN"}, "business", "credit"),
    ({}, None, "courant"),
])
def test_default_account_role(account, psu_type, role):
    from app.accounts import default_role
    assert default_role(account, psu_type) == role


def test_start_auth_sends_requested_psu_type(tmp_path, monkeypatch):
    from app.enable_banking import EnableBankingClient
    key = tmp_path / "k.pem"
    key.write_bytes(b"x")
    client = EnableBankingClient(app_id="app", key_path=key)
    sent = []
    monkeypatch.setattr(client, "_request", lambda method, path, **kw: sent.append(kw["json"]) or {"url": "u"})
    client.start_auth("Qonto", "FR", "s", psu_type="business")
    client.start_auth("Fortuneo", "FR", "s")
    assert [b["psu_type"] for b in sent] == ["business", "personal"]


class _FakeBank:
    """Client Enable Banking factice : enregistre les appels, renvoie une session donnée."""
    def __init__(self, session=None):
        self.session, self.auths = session, []

    def list_banks(self, country):
        return [{"name": "Qonto", "country": "FR", "maximum_consent_validity": 15552000, "psu_types": ["business"]},
                {"name": "Fortuneo", "country": "FR", "maximum_consent_validity": 15552000}]

    def start_auth(self, bank, country, state, psu_type="personal"):
        self.auths.append((bank, psu_type))
        return {"url": "https://bank.example/auth"}

    def create_session(self, code):
        return self.session


CE_SESSION = {
    "session_id": "sess-ce", "psu_type": "personal", "access": {"valid_until": "2027-04-01T00:00:00Z"},
    "accounts": [
        {"uid": "ce-livret", "name": "M LEMAITRE FLORENT", "product": "LIVRET A", "cash_account_type": "SVGS",
         "usage": "PRIV", "currency": "EUR", "account_id": {"iban": "FR7600000000000000000000001"}},
        {"uid": "ce-depot", "name": "M LEMAITRE FLORENT", "product": "COMPTE DE DEPOT", "cash_account_type": "CACC",
         "usage": "PRIV", "currency": "EUR", "account_id": {"iban": "FR7600000000000000000000002"}},
        {"uid": "ce-pret", "name": "M LEMAITRE FLORENT", "product": "PRET IMMOBILIER", "cash_account_type": "LOAN",
         "currency": "EUR"},
    ],
}


def _connect_flow(monkeypatch, client, bank, session, psu_type="personal"):
    from app import main
    fake = _FakeBank(session)
    monkeypatch.setattr(main, "_client", lambda: fake)
    monkeypatch.setattr(main, "sync", lambda: None)
    assert client.post("/api/connect", json={"bank": bank, "psu_type": psu_type}).status_code == 200
    state = next(iter(main._pending_auth))
    r = client.get(f"/callback?code=c&state={state}", follow_redirects=False)
    assert r.headers["location"] == "/?connected=1"
    return fake


def test_banks_expose_accepted_psu_types(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient
    from app import main
    _fresh_db(tmp_path, monkeypatch)
    monkeypatch.setattr(main, "_client", lambda: _FakeBank())
    banks = {b["name"]: b["psu_types"] for b in TestClient(main.app).get("/api/banks").json()}
    assert banks == {"Qonto": ["business"], "Fortuneo": ["personal"]}  # absent = perso seulement


def test_connect_rejects_unknown_psu_type(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient
    from app import main
    _fresh_db(tmp_path, monkeypatch)
    monkeypatch.setattr(main, "_client", lambda: _FakeBank())
    assert TestClient(main.app).post("/api/connect", json={"bank": "Qonto", "psu_type": "corporate"}).status_code == 422


def test_callback_stores_accounts_with_default_roles(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient
    from app import main
    db = _fresh_db(tmp_path, monkeypatch)
    client = TestClient(main.app)
    _connect_flow(monkeypatch, client, "Caisse d'Epargne Aquitaine Poitou-Charentes", CE_SESSION)
    qonto = {"session_id": "sess-q", "psu_type": "business", "access": {"valid_until": "2027-04-01T00:00:00Z"},
             "accounts": [{"uid": "q-main", "name": "MA SOCIETE SAS", "cash_account_type": "CACC", "currency": "EUR"}]}
    fake = _connect_flow(monkeypatch, client, "Qonto", qonto, psu_type="business")
    assert fake.auths == [("Qonto", "business")]
    accs = {a["uid"]: a for a in db.rows("SELECT * FROM accounts")}
    assert {u: a["role"] for u, a in accs.items()} == \
        {"ce-livret": "epargne", "ce-depot": "courant", "ce-pret": "credit", "q-main": "pro"}
    assert accs["ce-livret"]["product"] == "LIVRET A" and accs["ce-livret"]["cash_account_type"] == "SVGS"
    assert accs["q-main"]["psu_type"] == "business" and accs["ce-depot"]["bank"].startswith("Caisse d'Epargne")


def test_reconnecting_keeps_user_role_and_label(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient
    from app import main
    db = _fresh_db(tmp_path, monkeypatch)
    client = TestClient(main.app)
    _connect_flow(monkeypatch, client, "Caisse d'Epargne", CE_SESSION)
    r = client.put("/api/accounts/ce-livret", json={"role": "epargne", "label": "Livret enfants"})
    assert r.status_code == 200
    client.put("/api/accounts/ce-depot", json={"role": "credit"})
    _connect_flow(monkeypatch, client, "Caisse d'Epargne", {**CE_SESSION, "session_id": "sess-ce-2"})
    accs = {a["uid"]: a for a in db.rows("SELECT * FROM accounts")}
    assert accs["ce-livret"]["label"] == "Livret enfants" and accs["ce-depot"]["role"] == "credit"
    assert accs["ce-livret"]["session_id"] == "sess-ce-2"


def test_update_account_validation(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient
    from app import main
    db = _fresh_db(tmp_path, monkeypatch)
    client = TestClient(main.app)
    _connect_flow(monkeypatch, client, "Caisse d'Epargne", CE_SESSION)
    assert client.put("/api/accounts/ce-livret", json={"role": "bitcoin"}).status_code == 400
    assert client.put("/api/accounts/inconnu", json={"role": "epargne"}).status_code == 404
    client.put("/api/accounts/ce-livret", json={"label": "Livret enfants"})
    client.put("/api/accounts/ce-livret", json={"label": "   "})  # vide : retour au nom de la banque
    assert db.rows("SELECT role, label FROM accounts WHERE uid='ce-livret'") == [{"role": "epargne", "label": None}]


def test_status_lists_account_roles(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient
    from app import main
    _fresh_db(tmp_path, monkeypatch)
    client = TestClient(main.app)
    _connect_flow(monkeypatch, client, "Caisse d'Epargne", CE_SESSION)
    accs = {a["uid"]: a for a in client.get("/api/status").json()["accounts"]}
    assert accs["ce-pret"]["role"] == "credit" and accs["ce-pret"]["product"] == "PRET IMMOBILIER"
    assert accs["ce-livret"]["connected"] == 1 and "label" in accs["ce-livret"]
    assert {r["id"] for r in client.get("/api/account-roles").json()} == {"courant", "epargne", "enfants", "pro", "credit"}


def test_existing_accounts_become_courant_after_migration(tmp_path, monkeypatch):
    import sqlite3
    from app import config, db
    path = tmp_path / "old.db"
    con = sqlite3.connect(path)
    con.executescript("""
        CREATE TABLE accounts (uid TEXT PRIMARY KEY, session_id TEXT, bank TEXT, name TEXT, iban TEXT,
                               currency TEXT, valid_until TEXT, last_sync TEXT);
        INSERT INTO accounts VALUES ('fo-perso', 's', 'Fortuneo', 'M LEMAITRE FLORENT', 'FR76', 'EUR', NULL, NULL);
    """)
    con.commit()
    con.close()
    monkeypatch.setattr(config.settings, "db_path", path)
    db.init_db()
    db.insert_transactions([_raw(1, "CARREFOUR")])
    assert db.rows("SELECT uid, role, label, name FROM accounts") == \
        [{"uid": "fo-perso", "role": "courant", "label": None, "name": "M LEMAITRE FLORENT"}]
    db.init_db()  # migration idempotente
    assert len(db.rows("SELECT * FROM accounts")) == 1


# --- Virements entre ses propres comptes : appariement et rôle des comptes -------

def _acc(db, uid, role, bank="Banque"):
    db.upsert_account({"uid": uid, "session_id": "s", "bank": bank, "name": uid, "iban": "", "currency": "EUR",
                       "valid_until": None, "role": role})


def _mtx(i, acc, d, amount, label, category=None, nature=None):
    return {"id": f"{acc}:{i}", "account_uid": acc, "date": d, "amount": amount, "currency": "EUR",
            "label": label, "counterparty": "", "mcc": None, "merchant": label, "_cls": (category, nature)}


def _insert(db, txs):
    db.insert_transactions(txs)
    with db.connect() as con:
        for t in txs:
            if t["_cls"][0]:
                con.execute("UPDATE transactions SET category=?, nature=?, class_source='rule' WHERE id=?",
                            (*t["_cls"], t["id"]))


def _peers(db):
    return {r["id"]: r["transfer_peer"] for r in db.rows("SELECT id, transfer_peer FROM transactions")}


def test_transfers_match_debit_and_credit_across_accounts(tmp_path, monkeypatch):
    from app import transfers
    db = _fresh_db(tmp_path, monkeypatch)
    _acc(db, "fo", "courant"), _acc(db, "ce", "epargne")
    _insert(db, [_mtx(1, "fo", "2026-08-01", -200.0, "VIR SEPA LIVRET A"),
                 _mtx(2, "ce", "2026-08-03", 200.0, "VIREMENT RECU M LEMAITRE")])  # 2 jours : apparié
    assert transfers.match() == 1
    assert _peers(db) == {"fo:1": "ce:2", "ce:2": "fo:1"}
    assert transfers.match() == 0  # idempotent


@pytest.mark.parametrize("debit, credit", [
    (_mtx(1, "fo", "2026-08-01", -200.0, "VIR SEPA LIVRET A"), _mtx(2, "ce", "2026-08-05", 200.0, "VIREMENT RECU")),  # 4 jours
    (_mtx(1, "fo", "2026-08-01", -200.0, "VIR SEPA LIVRET A"), _mtx(2, "ce", "2026-08-01", 199.0, "VIREMENT RECU")),  # montant
    (_mtx(1, "fo", "2026-08-01", -50.0, "CB CARREFOUR 01/08"), _mtx(2, "ce", "2026-08-01", 50.0, "VIREMENT RECU")),  # carte
    (_mtx(1, "fo", "2026-08-01", -50.0, "CHQ 0538322"), _mtx(2, "ce", "2026-08-01", 50.0, "VIREMENT RECU")),        # chèque
    (_mtx(1, "fo", "2026-08-01", -50.0, "AMAZON PAYMENTS"), _mtx(2, "ce", "2026-08-01", 50.0, "REMBOURSEMENT AMAZON")),  # pas un virement
    (_mtx(1, "fo", "2026-08-01", -200.0, "VIR SEPA LIVRET A"), _mtx(2, "fo", "2026-08-01", 200.0, "VIREMENT RECU")),  # même compte
])
def test_transfers_false_positives_are_not_matched(tmp_path, monkeypatch, debit, credit):
    from app import transfers
    db = _fresh_db(tmp_path, monkeypatch)
    _acc(db, "fo", "courant"), _acc(db, "ce", "epargne")
    _insert(db, [debit, credit])
    assert transfers.match() == 0


def test_transfers_are_matched_one_to_one_closest_date_first(tmp_path, monkeypatch):
    from app import transfers
    db = _fresh_db(tmp_path, monkeypatch)
    _acc(db, "fo", "courant"), _acc(db, "jt", "courant")
    _insert(db, [_mtx(1, "fo", "2026-08-01", -100.0, "VIR COMPTE JOINT"), _mtx(2, "fo", "2026-08-03", -100.0, "VIR COMPTE JOINT"),
                 _mtx(3, "jt", "2026-08-03", 100.0, "VIR RECU FLORENT")])
    assert transfers.match() == 1
    assert _peers(db)["jt:3"] == "fo:2" and _peers(db)["fo:1"] is None


def _household(tmp_path, monkeypatch):
    """Août 2026 sur les comptes réels : Fortuneo perso et joint, Caisse d'Épargne (livret A, livret
    enfants, compte de dépôt du crédit, prêt), Qonto."""
    from app import transfers
    db = _fresh_db(tmp_path, monkeypatch)
    for uid, role in [("fo", "courant"), ("jt", "courant"), ("la", "epargne"), ("le", "enfants"),
                      ("dep", "courant"), ("pret", "credit"), ("q", "pro")]:
        _acc(db, uid, role)
    _insert(db, [
        _mtx(1, "fo", "2026-08-28", 3000.0, "VIR SEPA RECU ACME SALAIRE", "revenus", "revenu"),
        _mtx(2, "fo", "2026-08-02", -500.0, "VIR COMPTE JOINT", "virements", "transfert"),
        _mtx(3, "jt", "2026-08-02", 500.0, "VIR RECU M LEMAITRE", "revenus", "revenu"),          # courant -> courant
        _mtx(4, "fo", "2026-08-03", -200.0, "VIR SEPA LIVRET A", "epargne", "epargne"),
        _mtx(5, "la", "2026-08-04", 200.0, "VIREMENT RECU", "revenus", "revenu"),                # courant -> épargne
        _mtx(6, "fo", "2026-08-03", -50.0, "VIR LIVRET ENFANTS", "epargne", "epargne"),
        _mtx(7, "le", "2026-08-03", 50.0, "VIREMENT RECU", "revenus", "revenu"),                 # courant -> enfants
        _mtx(8, "q", "2026-08-10", -1000.0, "TRANSFER TO FLORENT LEMAITRE", "virements", "transfert"),
        _mtx(9, "fo", "2026-08-11", 1000.0, "VIR SEPA RECU MA SOCIETE SAS", "revenus", "revenu"),  # pro -> courant
        _mtx(10, "q", "2026-08-12", -300.0, "TRANSFER TO LIVRET A", "virements", "transfert"),
        _mtx(11, "la", "2026-08-12", 300.0, "VIREMENT RECU MA SOCIETE", "revenus", "revenu"),    # pro -> épargne
        _mtx(12, "q", "2026-08-15", -80.0, "CB AMAZON BUSINESS", "shopping", "optimisable"),     # dépense pro
        _mtx(13, "q", "2026-08-15", -9.0, "FRAIS QONTO", "frais_bancaires", "optimisable"),       # frais pro
        _mtx(14, "fo", "2026-08-04", -900.0, "VIR SEPA COMPTE DEPOT CE", "virements", "transfert"),
        _mtx(15, "dep", "2026-08-05", 900.0, "VIREMENT RECU", "revenus", "revenu"),              # alimente le dépôt
        _mtx(16, "dep", "2026-08-06", -900.0, "PRLV ECHEANCE PRET IMMO", "logement", "essentiel"),
        _mtx(17, "pret", "2026-08-06", 900.0, "ECHEANCE PRET REMBOURSEMENT", "revenus", "revenu"),  # échéance du prêt
        _mtx(18, "la", "2026-08-20", -100.0, "VIR VERS COMPTE COURANT", "virements", "transfert"),
        _mtx(19, "fo", "2026-08-20", 100.0, "VIR SEPA RECU LIVRET A", "revenus", "revenu"),      # retrait d'épargne
        _mtx(20, "jt", "2026-08-22", -120.0, "CB CARREFOUR", "courses", "essentiel"),
    ])
    assert transfers.match() == 8
    return db


def test_roles_count_each_flow_once(tmp_path, monkeypatch):
    from app import insights
    _household(tmp_path, monkeypatch)
    cf = insights.cashflow()
    i = cf["months"].index("2026-08")
    assert cf["income"][i] == 4000.0      # salaire + versement de la société, pas les virements internes
    assert cf["spent"][i] == 1020.0       # échéance du crédit + courses ; ni Qonto ni virements
    assert cf["savings"][i] == 450.0      # 200 livret + 50 enfants + 300 depuis Qonto - 100 retiré


def test_monthly_summary_applies_account_roles(tmp_path, monkeypatch):
    from app import insights
    _household(tmp_path, monkeypatch)
    s = insights.monthly_summary("2026-08")
    assert s["income"] == 4000.0 and s["spent"] == 1020.0
    cats = {c["category"]: c["amount"] for c in s["by_category"]}
    assert cats["logement"] == 900.0 and cats["epargne_enfants"] == 50.0 and cats["epargne"] == 500.0
    assert "shopping" not in cats and "frais_bancaires" not in cats  # dépenses de la société
    assert not any(i["kind"] == "frais" for i in s["insights"])
    by_id = {t["id"]: t for t in s["transactions"]}
    assert by_id["q:12"]["nature"] == "hors_budget"           # toujours listée, mais hors budget
    assert by_id["q:12"]["category"] == "shopping"             # dépense propre du compte pro
    assert by_id["la:5"]["category"] == "virements"            # pas « Revenus » côté livret
    assert by_id["fo:2"]["nature"] == "transfert" and by_id["fo:2"]["peer_account"] == "jt"
    assert by_id["dep:16"]["category"] == "logement"           # l'échéance reste une dépense logement
    assert by_id["fo:14"]["nature"] == "transfert"             # le virement qui alimente le dépôt est neutre


def test_trends_and_advice_follow_account_roles(tmp_path, monkeypatch):
    from app import insights
    _household(tmp_path, monkeypatch)
    trends = {c["category"]: c["amounts"] for c in insights.category_trends()["categories"]}
    assert set(trends) == {"logement", "courses"}
    ctx = insights.advice_context(12)
    assert ctx["mois"][-1] == {"mois": "2026-08", "entrees": 4000.0, "sorties": 1020.0, "solde": 2980.0, "epargne": 450.0}


def test_user_rule_sends_unconnected_transfer_to_kids_savings(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient
    from app import insights, main
    db = _fresh_db(tmp_path, monkeypatch)
    _acc(db, "fo", "courant")
    _insert(db, [_mtx(1, "fo", "2026-08-05", -80.0, "VIR SEPA LIVRET JEUNE LOU", "virements", "transfert")])
    key = db.rows("SELECT merchant_key FROM transactions")[0]["merchant_key"]
    assert TestClient(main.app).put(f"/api/merchants/{key}", json={"category": "epargne_enfants"}).status_code == 200
    assert insights.cashflow()["savings"] == [80.0]
    assert insights.monthly_summary("2026-08")["by_category"][0]["category"] == "epargne_enfants"


def test_user_category_wins_on_a_matched_courant_transaction(tmp_path, monkeypatch):
    from app import classifier, insights
    db = _household(tmp_path, monkeypatch)
    with db.connect() as con:
        con.execute("UPDATE transactions SET merchant_key='CADEAUJOINT' WHERE id='fo:2'")
    classifier.apply_user_override("CADEAUJOINT", "cadeaux")
    by_id = {t["id"]: t for t in insights.monthly_summary("2026-08")["transactions"]}
    assert by_id["fo:2"]["category"] == "cadeaux"


def test_manual_transfer_pairing_wins_over_auto_matching(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient
    from app import main, transfers
    db = _household(tmp_path, monkeypatch)
    client = TestClient(main.app)
    assert client.put("/api/transactions/fo:4/transfer", json={"peer": None}).status_code == 200
    assert _peers(db)["fo:4"] is None and _peers(db)["la:5"] is None
    transfers.match()
    assert _peers(db)["fo:4"] is None  # la dissociation manuelle tient
    # appariement manuel hors fenêtre automatique
    _insert(db, [_mtx(30, "fo", "2026-09-01", -60.0, "VIR LIVRET A"), _mtx(31, "la", "2026-09-09", 60.0, "VIREMENT RECU")])
    assert client.put("/api/transactions/fo:30/transfer", json={"peer": "la:31"}).status_code == 200
    assert _peers(db)["la:31"] == "fo:30"
    assert client.put("/api/transactions/fo:30/transfer", json={"peer": "fo:1"}).status_code == 400  # même compte
    assert client.put("/api/transactions/nope/transfer", json={"peer": None}).status_code == 404
    assert client.put("/api/transactions/fo:30/transfer", json={"peer": "nope"}).status_code == 404


def test_transfer_columns_are_added_to_old_databases(tmp_path, monkeypatch):
    import sqlite3
    from app import config, db
    path = tmp_path / "old.db"
    con = sqlite3.connect(path)
    con.executescript("""CREATE TABLE transactions (id TEXT PRIMARY KEY, account_uid TEXT NOT NULL, date TEXT NOT NULL,
        amount REAL NOT NULL, currency TEXT, label TEXT, counterparty TEXT, mcc TEXT, merchant TEXT, merchant_key TEXT,
        category TEXT, nature TEXT, class_source TEXT, user_category TEXT, user_nature TEXT);""")
    con.close()
    monkeypatch.setattr(config.settings, "db_path", path)
    db.init_db()
    cols = {r["name"] for r in db.rows("PRAGMA table_info(transactions)")}
    assert {"transfer_peer", "transfer_source"} <= cols


def test_kids_savings_role_and_category_exist():
    from app.accounts import ROLES
    from app.categories import CATEGORIES
    from app.classifier import _CREDIT_CATEGORIES
    from app.llm import _ALLOWED
    assert ROLES["enfants"]["label"] == "Épargne enfants"
    assert CATEGORIES["epargne_enfants"]["nature"] == "epargne" and "epargne_enfants" in _CREDIT_CATEGORIES
    assert "epargne_enfants" not in _ALLOWED  # le LLM ne devine pas l'épargne des enfants


# --- Comptes réels : épargne versée depuis le compte pro, libellés Qonto ------------

def test_pro_savings_to_unconnected_account_count_as_household_savings(tmp_path, monkeypatch):
    from app import insights, transfers
    db = _fresh_db(tmp_path, monkeypatch)
    _acc(db, "fo", "courant"), _acc(db, "q", "pro")
    _insert(db, [
        _mtx(1, "q", "2026-08-10", -50.0, "940322588 - Versement libre programme", "epargne", "epargne"),  # SPIRICA
        _mtx(2, "q", "2026-08-04", -1000.0, "Epargne Florent", "epargne", "epargne"),                     # Spiko
        _mtx(3, "q", "2026-08-12", 700.0, "S.A.S. HFC DISTRIBUTION", "revenus", "revenu"),               # chiffre d'affaires
        _mtx(4, "q", "2026-08-04", -969.0, "UR 727000000653085290", "impots", "essentiel"),              # URSSAF
        _mtx(5, "fo", "2026-08-28", 3000.0, "VIR SEPA RECU SALAIRE", "revenus", "revenu"),
    ])
    transfers.match()
    cf = insights.cashflow()
    assert (cf["income"], cf["spent"], cf["savings"]) == ([3000.0], [0.0], [1050.0])


def test_qonto_transfer_labels_are_matched_when_the_other_side_looks_like_a_transfer(tmp_path, monkeypatch):
    from app import insights, transfers
    db = _fresh_db(tmp_path, monkeypatch)
    _acc(db, "fo", "courant"), _acc(db, "q", "pro")
    _insert(db, [_mtx(1, "q", "2026-05-27", -700.0, "Envoye depuis Qonto", "virements", "transfert"),
                 _mtx(2, "fo", "2026-05-28", 700.0, "VIR INST EI LEMAITRE FLORENT", "virements", "transfert"),
                 _mtx(3, "q", "2026-05-27", -45.0, "Envoye depuis Qonto", "virements", "transfert"),
                 _mtx(4, "fo", "2026-05-27", 45.0, "AMAZON REMBOURSEMENT", "remboursements", "revenu")])
    assert transfers.match() == 1
    assert _peers(db)["q:1"] == "fo:2" and _peers(db)["q:3"] is None
    assert insights.cashflow()["income"] == [745.0]  # le versement de l'EI est une entrée


def test_accounts_section_is_reachable_from_the_header():
    from fastapi.testclient import TestClient
    from app import main
    page = TestClient(main.app).get("/").text
    assert 'id="goto-accounts"' in page and 'href="#accounts"' in page
    assert "livrets" in page.lower()  # pourquoi les livrets n'apparaissent pas
