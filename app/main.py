"""Point d'entrée : uvicorn app.main:app --reload"""
import logging
import uuid
from contextlib import asynccontextmanager
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Literal

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from . import classifier, db, demo, insights, llm
from .accounts import ROLES, default_role
from .categories import CATEGORIES
from .config import settings
from .enable_banking import EnableBankingClient, EnableBankingError, normalize_transaction

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("budget")

STATIC = Path(__file__).with_name("static")


@asynccontextmanager
async def lifespan(_app: FastAPI):
    db.init_db()
    yield


app = FastAPI(title="Budget DSP2", lifespan=lifespan)
app.mount("/static", StaticFiles(directory=STATIC), name="static")

_pending_auth: dict[str, dict] = {}  # state -> {bank, psu_type} (usage mono-utilisateur)


def _client() -> EnableBankingClient:
    if not settings.bank_enabled:
        raise HTTPException(400, "Enable Banking n'est pas configuré : renseigne .env et keys/private.pem.")
    return EnableBankingClient()


@app.get("/")
def index():
    return FileResponse(STATIC / "index.html")


@app.get("/tendances")
def trends_page():
    return FileResponse(STATIC / "trends.html")


@app.get("/api/status")
def status():
    return {
        "bank_enabled": settings.bank_enabled,
        "llm_enabled": settings.llm_enabled,
        "accounts": db.rows(
            "SELECT uid, bank, name, label, product, role, psu_type, iban, valid_until, last_sync, "
            "session_id IS NOT NULL AS connected FROM accounts ORDER BY bank, uid"
        ),
        "months": insights.available_months(),
    }


@app.get("/api/account-roles")
def account_roles():
    return [{"id": k, **v} for k, v in ROLES.items()]


class AccountBody(BaseModel):
    role: str | None = None
    label: str | None = None


@app.put("/api/accounts/{uid}")
def update_account(uid: str, body: AccountBody):
    """Rôle et nom affiché d'un compte ; un label vide revient au nom donné par la banque."""
    fields = body.model_dump(exclude_unset=True)
    if "role" in fields and fields["role"] not in ROLES:
        raise HTTPException(400, "Rôle de compte inconnu")
    if "label" in fields:
        fields["label"] = (fields["label"] or "").strip() or None
    if not db.update_account(uid, fields):
        raise HTTPException(404, "Compte inconnu")
    return db.rows("SELECT uid, role, label FROM accounts WHERE uid = ?", (uid,))[0]


@app.get("/api/categories")
def categories():
    return [{"id": k, **v} for k, v in CATEGORIES.items()]


# --- Connexion bancaire -------------------------------------------------------

@app.get("/api/banks")
def banks(country: str = settings.eb_country):
    try:
        return [{"name": b["name"], "country": b["country"],
                 "max_days": b.get("maximum_consent_validity"),
                 "psu_types": b.get("psu_types") or ["personal"]} for b in _client().list_banks(country)]
    except EnableBankingError as exc:
        raise HTTPException(502, str(exc))


class ConnectBody(BaseModel):
    bank: str
    country: str = settings.eb_country
    psu_type: Literal["personal", "business"] = "personal"  # business : compte pro (Qonto...)


@app.post("/api/connect")
def connect(body: ConnectBody):
    state = str(uuid.uuid4())
    try:
        auth = _client().start_auth(body.bank, body.country, state, psu_type=body.psu_type)
    except EnableBankingError as exc:
        raise HTTPException(502, str(exc))
    _pending_auth[state] = {"bank": body.bank, "psu_type": body.psu_type}
    return {"url": auth["url"]}


@app.get("/callback")
def callback(code: str | None = None, state: str | None = None, error: str | None = None):
    if error or not code:
        return RedirectResponse(f"/?error={error or 'consentement_refuse'}")
    pending = _pending_auth.pop(state, {}) if state else {}
    bank = pending.get("bank", "Banque")
    client = _client()
    try:
        session = client.create_session(code)
    except EnableBankingError as exc:
        log.error(exc)
        return RedirectResponse("/?error=session")

    valid_until = (session.get("access") or {}).get("valid_until")
    psu_type = session.get("psu_type") or pending.get("psu_type")
    for acc in session.get("accounts", []):
        uid = acc["uid"] if isinstance(acc, dict) else acc
        info = acc if isinstance(acc, dict) else {}
        db.upsert_account({
            "uid": uid,
            "session_id": session["session_id"],
            "bank": bank,
            "name": info.get("name") or info.get("product") or "Compte",
            "iban": (info.get("account_id") or {}).get("iban", ""),
            "currency": info.get("currency", "EUR"),
            "valid_until": valid_until,
            "role": default_role(info, psu_type),
            "product": info.get("product"),
            "cash_account_type": info.get("cash_account_type"),
            "psu_type": psu_type,
        })
    sync()
    return RedirectResponse("/?connected=1")


# --- Synchronisation ----------------------------------------------------------

@app.post("/api/sync")
def sync():
    accounts = [a for a in db.rows("SELECT * FROM accounts") if a["session_id"]]
    if not accounts:
        return {"inserted": 0, "classified": classifier.classify_pending(), "errors": []}

    client = _client()
    inserted, errors = 0, []
    for acc in accounts:
        last = db.rows("SELECT MAX(date) AS d FROM transactions WHERE account_uid = ?", (acc["uid"],))[0]["d"]
        # On repart quelques jours en arrière : certaines opérations arrivent en retard
        date_from = ((date.fromisoformat(last) - timedelta(days=7)) if last
                     else date.today() - timedelta(days=settings.history_days)).isoformat()
        try:
            batch = []
            for raw in client.iter_transactions(acc["uid"], date_from):
                tx = normalize_transaction(raw, acc["uid"])
                if tx:
                    batch.append(tx)
            inserted += db.insert_transactions(batch)
            with db.connect() as con:
                con.execute("UPDATE accounts SET last_sync = ? WHERE uid = ?",
                            (datetime.now(timezone.utc).isoformat(timespec="seconds"), acc["uid"]))
        except EnableBankingError as exc:
            log.error(exc)
            errors.append({"account": acc["name"], "error": str(exc)[:300]})

    return {"inserted": inserted, "classified": classifier.classify_pending(), "errors": errors}


@app.post("/api/demo")
def load_demo():
    inserted = demo.load_demo()
    return {"inserted": inserted, "classified": classifier.classify_pending()}


@app.post("/api/reclassify")
def reclassify():
    """À lancer après avoir modifié rules.yaml."""
    classifier.load_rules.cache_clear()
    return {"classified": classifier.classify_pending(force=True)}


# --- Lecture et corrections ---------------------------------------------------

@app.get("/api/summary")
def summary(month: str | None = None):
    months = insights.available_months()
    if not months:
        return {"month": None, "transactions": [], "insights": []}
    return insights.monthly_summary(month or months[0])


@app.get("/api/trends")
def trends():
    return insights.category_trends()


@app.get("/api/cashflow")
def cashflow():
    return insights.cashflow()


class AdviceBody(BaseModel):
    months: int = Field(6, ge=1, le=36)


@app.post("/api/advice")
def advice(body: AdviceBody):
    """Synthèse et conseils du LLM sur les derniers mois complets (agrégats seulement)."""
    if not settings.llm_enabled:
        raise HTTPException(400, "Aucun LLM configuré : renseigne LLM_PROVIDER et sa clé dans .env.")
    context = insights.advice_context(body.months)
    if context is None:
        raise HTTPException(400, "Pas encore de mois complet à analyser.")
    answer = llm.advise(context)
    if answer is None:
        raise HTTPException(502, f"Le LLM ({settings.llm_provider}) n'a pas répondu, réessaie dans un instant.")
    return {**answer, "months": [m["mois"] for m in context["mois"]],
            "provider": settings.llm_provider, "model": settings.llm_model}


class OverrideBody(BaseModel):
    category: str
    nature: str | None = None


@app.put("/api/merchants/{key}")
def override(key: str, body: OverrideBody):
    """key = merchant_key (A-Z0-9), jamais le nom affiché qui peut contenir des '/'."""
    if body.category not in CATEGORIES:
        raise HTTPException(400, "Catégorie inconnue")
    updated = classifier.apply_user_override(key, body.category, body.nature)
    if not updated:
        raise HTTPException(404, "Marchand inconnu")
    return {"updated": updated}
