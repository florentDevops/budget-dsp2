"""Détection des dépenses optimisables et chiffrage du potentiel d'économies.

Tous les seuils sont regroupés ici pour être ajustés facilement.
"""
from collections import defaultdict
from datetime import date, timedelta
from statistics import mean, median

from . import db
from .categories import CATEGORIES, RENEGOTIABLE, SAVINGS_RATE
from .normalize import is_cheque

RECURRING_MIN_MONTHS = 3        # vu sur au moins 3 mois distincts
RECURRING_AMOUNT_TOLERANCE = 0.15  # montant stable à ±15 %
RECURRING_INTERVAL = (25, 35)   # écart médian en jours entre deux prélèvements
RECURRING_ACTIVE_DAYS = 45      # encore prélevé récemment
DRIFT_RATIO = 1.2               # +20 % vs moyenne des 3 mois précédents
DRIFT_MIN_DELTA = 30.0          # et au moins 30 € d'écart
MICRO_MAX_AMOUNT = 15.0         # une micro-dépense fait moins de 15 €
MICRO_MIN_COUNT = 6             # et revient au moins 6 fois dans le mois
CHEQUE_NAG_MIN = 3              # à partir de 3 chèques émis dans le mois, petit clin d'œil


def pretty(merchant: str) -> str:
    """'EDF CLIENTS PARTICULIERS' -> 'EDF Clients Particuliers', 'NETFLIX.COM' -> 'Netflix.com'."""
    words = []
    for w in merchant.split():
        if len(w) <= 3 and w.isalpha():
            words.append(w)
        else:
            words.append(w.capitalize())
    return " ".join(words)


def eur(x: float, decimals: int = 2) -> str:
    """Format français : 1 171,50 €"""
    txt = f"{x:,.{decimals}f}".replace(",", " ").replace(".", ",")
    return f"{txt} €"


def _month(d: str) -> str:
    return d[:7]


def _prev_months(month: str, n: int) -> list[str]:
    y, m = map(int, month.split("-"))
    out = []
    for _ in range(n):
        m -= 1
        if m == 0:
            y, m = y - 1, 12
        out.append(f"{y:04d}-{m:02d}")
    return out


def available_months() -> list[str]:
    return [r["m"] for r in db.rows(
        "SELECT DISTINCT substr(date,1,7) AS m FROM transactions ORDER BY m DESC")]


def detect_recurring(txs: list[dict]) -> list[dict]:
    """Abonnements et prélèvements réguliers : même marchand, montant stable, ~mensuel."""
    if not txs:
        return []
    last_date = max(date.fromisoformat(t["date"]) for t in txs)
    by_merchant = defaultdict(list)
    for t in txs:
        if t["amount"] < 0 and t["nature"] not in ("epargne", "transfert"):
            by_merchant[t["merchant_key"]].append(t)

    found = []
    for key, items in by_merchant.items():
        items.sort(key=lambda t: t["date"])
        months = {_month(t["date"]) for t in items}
        if len(months) < RECURRING_MIN_MONTHS:
            continue
        amounts = [-t["amount"] for t in items]
        ref = median(amounts)
        stable = [a for a in amounts if abs(a - ref) <= ref * RECURRING_AMOUNT_TOLERANCE]
        if len(stable) < 0.8 * len(amounts):
            continue
        dates = [date.fromisoformat(t["date"]) for t in items]
        gaps = [(b - a).days for a, b in zip(dates, dates[1:])]
        if not gaps or not (RECURRING_INTERVAL[0] <= median(gaps) <= RECURRING_INTERVAL[1]):
            continue
        if (last_date - dates[-1]).days > RECURRING_ACTIVE_DAYS:
            continue  # abonnement probablement résilié
        category = items[-1]["category"]
        found.append({
            "merchant": items[-1]["merchant"],
            "merchant_key": key,
            "category": category,
            "nature": items[-1]["nature"],
            "monthly": round(ref, 2),
            "yearly": round(ref * 12, 2),
            "months": len(months),
        })
    return sorted(found, key=lambda r: -r["monthly"])


def monthly_summary(month: str) -> dict:
    history_start = _prev_months(month, 6)[-1] + "-01"
    all_txs = db.rows(
        "SELECT * FROM transactions WHERE date >= ? AND date < ? ORDER BY date DESC",
        (history_start, _next_month(month) + "-01"),
    )
    txs = [t for t in all_txs if _month(t["date"]) == month]

    # Totaux par nature et par catégorie (dépenses en valeur positive)
    by_nature, by_category = defaultdict(float), defaultdict(float)
    income = 0.0
    for t in txs:
        if t["amount"] > 0:
            if t["nature"] == "revenu":
                income += t["amount"]
            continue
        by_nature[t["nature"]] += -t["amount"]
        by_category[t["category"]] += -t["amount"]

    insights = []
    flags: dict[str, set] = defaultdict(set)  # tx_id -> raisons de surbrillance

    # 1. Abonnements récurrents
    recurring = detect_recurring(all_txs)
    recurring_merchants = {r["merchant_key"]: r for r in recurring}
    subs = [r for r in recurring
            if r["nature"] == "optimisable" and r["category"] != "frais_bancaires"]
    if subs:
        total = sum(r["monthly"] for r in subs)
        insights.append({
            "kind": "abonnements",
            "title": f"{len(subs)} abonnements actifs",
            "detail": "Vérifie ceux que tu utilises vraiment : "
                      + ", ".join(f'{pretty(r["merchant"])} ({eur(r["monthly"])})' for r in subs[:6]),
            "amount": round(total, 2),
            "yearly": round(total * 12, 2),
        })
    contracts = [r for r in recurring if r["category"] in RENEGOTIABLE]
    if contracts:
        yearly = sum(r["yearly"] for r in contracts)
        insights.append({
            "kind": "contrat",
            "title": f"{len(contracts)} contrats à comparer",
            "detail": "Énergie, box et assurances se renégocient une fois par an : "
                      + ", ".join(f'{pretty(r["merchant"])} ({eur(r["yearly"], 0)}/an)' for r in contracts)
                      + ".",
            "amount": round(yearly / 12, 2),
            "yearly": round(yearly, 2),
        })

    # 2. Frais bancaires
    fees = [t for t in txs if t["category"] == "frais_bancaires" and t["amount"] < 0]
    if fees:
        total = sum(-t["amount"] for t in fees)
        insights.append({
            "kind": "frais",
            "title": "Frais bancaires",
            "detail": f"{len(fees)} prélèvement{"s" if len(fees) > 1 else ""} de frais ce mois-ci. "
                      "Commissions d'intervention et cotisations se négocient, ou disparaissent "
                      "dans une banque en ligne.",
            "amount": round(total, 2),
            "yearly": round(total * 12, 2),
        })
        for t in fees:
            flags[t["id"]].add("frais")

    # 3. Catégories en hausse par rapport aux 3 mois précédents
    prev = _prev_months(month, 3)
    prev_by_cat = defaultdict(lambda: defaultdict(float))
    for t in all_txs:
        m = _month(t["date"])
        if m in prev and t["amount"] < 0:
            prev_by_cat[t["category"]][m] += -t["amount"]
    drifting = set()
    for cat, spent in by_category.items():
        if CATEGORIES.get(cat, {}).get("nature") != "optimisable":
            continue
        history = prev_by_cat.get(cat)
        if not history:
            continue
        avg = mean(history.get(m, 0.0) for m in prev)
        if avg > 0 and spent > avg * DRIFT_RATIO and spent - avg >= DRIFT_MIN_DELTA:
            drifting.add(cat)
            insights.append({
                "kind": "hausse",
                "title": f'{CATEGORIES[cat]["label"]} en hausse de {100 * (spent / avg - 1):.0f} %',
                "detail": f"{eur(spent, 0)} ce mois-ci contre {eur(avg, 0)} en moyenne sur les 3 mois précédents.",
                "amount": round(spent - avg, 2),
                "yearly": None,
            })

    # 4. Micro-dépenses répétées
    small = defaultdict(list)
    for t in txs:
        if t["amount"] < 0 and -t["amount"] < MICRO_MAX_AMOUNT and t["nature"] == "optimisable":
            small[t["merchant_key"]].append(t)
    for items in small.values():
        if len(items) >= MICRO_MIN_COUNT:
            total = sum(-t["amount"] for t in items)
            insights.append({
                "kind": "micro",
                "title": f"{len(items)} passages chez {pretty(items[-1]['merchant'])}",
                "detail": f"Environ {eur(total / len(items))} à chaque fois, soit {eur(total, 0)} sur le mois.",
                "amount": round(total, 2),
                "yearly": round(total * 12, 2),
            })
            for t in items:
                flags[t["id"]].add("micro")

    # Surbrillance des opérations
    for t in txs:
        if t["amount"] >= 0:
            continue
        if t["nature"] == "optimisable":
            flags[t["id"]].add("optimisable")
        rec = recurring_merchants.get(t["merchant_key"])
        if rec and rec["nature"] == "optimisable" and rec["category"] != "frais_bancaires":
            flags[t["id"]].add("abonnement")
        if rec and rec["category"] in RENEGOTIABLE:
            flags[t["id"]].add("contrat")
        if t["category"] in drifting:
            flags[t["id"]].add("hausse")

    # Potentiel d'économies estimé
    savings = sum(by_category.get(cat, 0.0) * rate for cat, rate in SAVINGS_RATE.items())

    order = {"frais": 0, "hausse": 1, "abonnements": 2, "micro": 3, "contrat": 4}
    insights.sort(key=lambda i: (order.get(i["kind"], 9), -(i["amount"] or 0)))

    return {
        "month": month,
        "income": round(income, 2),
        "spent": round(sum(v for k, v in by_nature.items() if k not in ("epargne", "transfert")), 2),
        "by_nature": {k: round(v, 2) for k, v in by_nature.items()},
        "by_category": sorted(
            ({"category": k, "label": CATEGORIES.get(k, CATEGORIES["inconnu"])["label"],
              "nature": CATEGORIES.get(k, CATEGORIES["inconnu"])["nature"], "amount": round(v, 2)}
             for k, v in by_category.items()),
            key=lambda c: -c["amount"],
        ),
        "savings_estimate": round(savings, 2),
        "cheque_nag": _cheque_nag(txs),
        "insights": insights,
        "recurring": recurring,
        "flags": {k: sorted(v) for k, v in flags.items()},
        "transactions": txs,
    }


def category_trends() -> dict:
    """Dépenses par catégorie pour chaque mois disponible (ordre chronologique).

    Épargne et virements internes sont exclus : ce n'est pas de la consommation.
    Une opération pas encore classée compte dans « À classer ».
    """
    months = sorted(available_months())
    index = {m: i for i, m in enumerate(months)}
    amounts: dict[str, list[float]] = defaultdict(lambda: [0.0] * len(months))
    for t in db.rows("SELECT date, amount, category, nature FROM transactions WHERE amount < 0"):
        if t["nature"] in ("epargne", "transfert"):
            continue
        amounts[t["category"] or "inconnu"][index[_month(t["date"])]] += -t["amount"]
    categories = [
        {"category": k, "label": CATEGORIES.get(k, CATEGORIES["inconnu"])["label"],
         "nature": CATEGORIES.get(k, CATEGORIES["inconnu"])["nature"],
         "amounts": [round(v, 2) for v in vals], "total": round(sum(vals), 2)}
        for k, vals in amounts.items()
    ]
    return {"months": months, "categories": sorted(categories, key=lambda c: -c["total"])}


def cashflow() -> dict:
    """Entrées vs sorties pour chaque mois disponible (ordre chronologique).

    Entrées : nature revenu (salaires, remboursements). Sorties : la consommation, comme
    dans category_trends (épargne et virements internes exclus, non classé inclus).
    Épargne : versements nets vers l'épargne. Le mois en cours est signalé partiel.
    """
    months = sorted(available_months())
    index = {m: i for i, m in enumerate(months)}
    income, spent, savings = ([0.0] * len(months) for _ in range(3))
    for t in db.rows("SELECT date, amount, nature FROM transactions"):
        i = index[_month(t["date"])]
        if t["nature"] == "epargne":
            savings[i] -= t["amount"]
        elif t["amount"] > 0:
            if t["nature"] == "revenu":
                income[i] += t["amount"]
        elif t["nature"] != "transfert":
            spent[i] -= t["amount"]
    current = date.today().isoformat()[:7]
    return {
        "months": months,
        "income": [round(v, 2) for v in income],
        "spent": [round(v, 2) for v in spent],
        "savings": [round(v, 2) for v in savings],
        "partial": current if months and months[-1] == current else None,
    }


ADVICE_TOP_CATEGORIES = 12      # catégories détaillées dans le contexte envoyé au LLM


def advice_context(n: int) -> dict | None:
    """Agrégats des n derniers mois complets, seule matière envoyée au LLM pour ses conseils.

    Uniquement des totaux par mois et par catégorie : aucun marchand, libellé ni jour précis.
    """
    flow = cashflow()
    last = len(flow["months"]) - (flow["partial"] is not None)
    start = max(0, last - n)
    months = flow["months"][start:last]
    if not months:
        return None
    k = len(months)
    rows = [{"mois": m, "entrees": flow["income"][i], "sorties": flow["spent"][i],
             "solde": round(flow["income"][i] - flow["spent"][i], 2), "epargne": flow["savings"][i]}
            for i, m in zip(range(start, last), months)]

    trends = category_trends()
    cols = [trends["months"].index(m) for m in months]
    by_cat, by_nature, potential = [], defaultdict(float), 0.0
    for c in trends["categories"]:
        amounts = [c["amounts"][i] for i in cols]
        if not sum(amounts):
            continue
        monthly = sum(amounts) / k
        by_nature[c["nature"]] += monthly
        potential += monthly * SAVINGS_RATE.get(c["category"], 0.0)
        half = k // 2
        before, after = amounts[:half], amounts[half:]
        evol = (round(100 * (mean(after) / mean(before) - 1)) if half and mean(before) else None)
        by_cat.append({"categorie": c["label"], "nature": c["nature"],
                       "moyenne_mensuelle": round(monthly, 2), "evolution_pct": evol})
    by_cat.sort(key=lambda c: -c["moyenne_mensuelle"])

    txs = db.rows("SELECT * FROM transactions WHERE date >= ? AND date < ?",
                  (months[0] + "-01", _next_month(months[-1]) + "-01"))
    subs = [r for r in detect_recurring(txs)
            if r["nature"] == "optimisable" and r["category"] != "frais_bancaires"]
    return {
        "periode_mois": k,
        "mois": rows,
        "moyennes": {key: round(sum(r[key] for r in rows) / k, 2) for key in ("entrees", "sorties", "solde", "epargne")},
        "mois_en_deficit": sum(r["solde"] < 0 for r in rows),
        "sorties_par_nature": {nat: round(v, 2) for nat, v in by_nature.items()},
        "depenses_par_categorie": by_cat[:ADVICE_TOP_CATEGORIES],
        "abonnements": {"nombre": len(subs), "total_mensuel": round(sum(r["monthly"] for r in subs), 2)},
        "potentiel_economies_mensuel": round(potential, 2),
    }


def _next_month(month: str) -> str:
    y, m = map(int, month.split("-"))
    return f"{y + (m == 12):04d}-{(m % 12) + 1:02d}"


# Utilitaire pour d'autres modules
def today_minus(days: int) -> str:
    return (date.today() - timedelta(days=days)).isoformat()


def _cheque_nag(txs: list[dict]) -> str | None:
    """Commentaire discret quand les chèques s'accumulent : chacun est à classer à la main."""
    n = sum(1 for t in txs if t["amount"] < 0 and is_cheque(t.get("label") or ""))
    if n < CHEQUE_NAG_MIN:
        return None
    return f"{n} chèques ce mois-ci, à classer un par un à la main... Oublie un peu ton chéquier ;-)"
