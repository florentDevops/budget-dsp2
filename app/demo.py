"""Six mois de relevé fictif, avec des libellés au format des banques françaises."""
import random
from datetime import date, timedelta

from . import db
from .normalize import extract_merchant

DEMO_ACCOUNT = "demo-compte-courant"

FIXED = [  # (jour, libellé, montant)
    (1, "VIR SEPA LOYER APPARTEMENT", -950.00),
    (3, "PRLV SEPA EDF CLIENTS PARTICULIERS", -78.40),
    (4, "PRLV SEPA ORANGE SA FIBRE", -42.99),
    (5, "PRLV SEPA AXA FRANCE IARD HABITATION", -24.10),
    (5, "PRLV SEPA MUTUELLE GENERALE SANTE", -46.00),
    (6, "PRLV SEPA COMUTITRES NAVIGO", -88.80),
    (8, "CB NETFLIX.COM 08/", -13.49),
    (10, "CB SPOTIFY AB 10/", -11.12),
    (12, "CB DISNEY PLUS 12/", -11.99),
    (14, "PRLV SEPA BASIC FIT FRANCE", -29.99),
    (15, "CB APPLE.COM/BILL ICLOUD 15/", -2.99),
    (18, "PRLV SEPA CANAL+ DISTRIBUTION", -27.99),
    (5, "COTISATION CARTE VISA PREMIER", -11.25),
    (2, "VIR SEPA LIVRET A", -200.00),
    (28, "VIR SEPA RECU DE ACME SAS SALAIRE", 3150.00),
]

VARIABLE = [  # (libellé, nb min, nb max, montant min, montant max)
    ("CB CARREFOUR MARKET", 5, 8, 18, 95),
    ("CB LIDL", 2, 4, 25, 70),
    ("CB PICARD", 1, 2, 15, 40),
    ("CB BOULANGERIE DU MARCHE", 5, 9, 2.5, 9),
    ("CB STARBUCKS", 7, 12, 4.2, 6.9),
    ("CB UBER EATS", 2, 4, 17, 34),
    ("CB DELIVEROO", 1, 2, 18, 30),
    ("CB LE PETIT ZINC", 1, 3, 25, 58),
    ("CB SUSHI SHOP", 1, 2, 22, 45),
    ("CB AMAZON PAYMENTS", 2, 4, 12, 85),
    ("CB ZARA", 0, 2, 30, 90),
    ("CB PHARMACIE CENTRALE", 1, 2, 6, 28),
    ("CB TOTAL ACCESS", 1, 2, 45, 70),
    ("CB UGC CINE CITE", 0, 2, 11, 24),
    ("CB ATELIER MIRABELLE", 0, 1, 20, 60),   # marchand inconnu : cas LLM
    ("RETRAIT DAB BNP", 0, 1, 40, 60),
]


def generate(months: int = 6, seed: int = 42) -> list[dict]:
    rng = random.Random(seed)
    today = date.today()
    first = date(today.year, today.month, 1)
    starts = []
    for _ in range(months):
        starts.insert(0, first)
        first = (first - timedelta(days=1)).replace(day=1)

    txs, n = [], 0
    for i, start in enumerate(starts):
        is_last = i == len(starts) - 1
        last_day = today.day if is_last else 28

        def add(day: int, label: str, amount: float):
            nonlocal n
            if day > last_day:
                return
            d = start.replace(day=day)
            n += 1
            if label.endswith("/"):
                full = f"{label}{d.strftime('%m')}"
            elif label.startswith("CB"):
                full = f"{label} {d.strftime('%d/%m')}"
            else:
                full = label
            txs.append({
                "id": f"{DEMO_ACCOUNT}:{n}",
                "account_uid": DEMO_ACCOUNT,
                "date": d.isoformat(),
                "amount": round(amount, 2),
                "currency": "EUR",
                "label": full,
                "counterparty": "",
                "mcc": None,
                "merchant": extract_merchant(full),
            })

        for day, label, amount in FIXED:
            add(day, label, amount)
        for label, lo, hi, amin, amax in VARIABLE:
            count = rng.randint(lo, hi)
            if is_last and "UBER EATS" in label:
                count += 5  # la livraison dérape ce mois-ci : doit apparaître en hausse
            for _ in range(count):
                add(rng.randint(1, 28), label, -rng.uniform(amin, amax))
        if rng.random() < 0.5:
            add(rng.randint(10, 25), "COMMISSION INTERVENTION", -8.00)
    return txs


def load_demo() -> int:
    db.upsert_account({
        "uid": DEMO_ACCOUNT, "session_id": None, "bank": "Démo", "name": "Compte courant",
        "iban": "FR76 •••• 0042", "currency": "EUR", "valid_until": None,
    })
    return db.insert_transactions(generate())
