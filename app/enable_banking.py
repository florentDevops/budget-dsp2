"""Client pour l'API Enable Banking (agrégateur agréé DSP2 / AISP).

Flux :
1. start_auth()      -> URL vers la banque, l'utilisateur s'authentifie (SCA)
2. la banque redirige vers ENABLE_BANKING_REDIRECT_URL?code=...&state=...
3. create_session()  -> session_id + liste des comptes autorisés
4. iter_transactions() pour chaque compte, pagination via continuation_key

Doc : https://enablebanking.com/docs/api/reference/
"""
import hashlib
import time
import uuid
from datetime import datetime, timedelta, timezone

import jwt
import requests

from .config import settings
from .normalize import clean_label, extract_merchant

BASE_URL = "https://api.enablebanking.com"


class EnableBankingError(RuntimeError):
    pass


class EnableBankingClient:
    def __init__(self, app_id: str | None = None, key_path=None):
        self.app_id = app_id or settings.eb_app_id
        path = key_path or settings.eb_private_key_path
        self.private_key = path.read_bytes()

    # --- Authentification applicative : JWT RS256 signé avec ta clé privée ---
    def _token(self) -> str:
        now = int(time.time())
        payload = {
            "iss": "enablebanking.com",
            "aud": "api.enablebanking.com",
            "iat": now,
            "exp": now + 3600,
        }
        return jwt.encode(payload, self.private_key, algorithm="RS256",
                          headers={"kid": self.app_id})

    def _request(self, method: str, path: str, **kwargs) -> dict:
        resp = requests.request(
            method, BASE_URL + path,
            headers={"Authorization": f"Bearer {self._token()}"},
            timeout=30, **kwargs,
        )
        if resp.status_code >= 400:
            raise EnableBankingError(f"{method} {path} -> {resp.status_code} : {resp.text[:500]}")
        return resp.json()

    # --- Banques disponibles ---
    def list_banks(self, country: str = "FR") -> list[dict]:
        data = self._request("GET", "/aspsps", params={"country": country})
        return data.get("aspsps", [])

    # --- Consentement ---
    def start_auth(self, bank_name: str, country: str, state: str | None = None) -> dict:
        valid_until = datetime.now(timezone.utc) + timedelta(days=settings.consent_days)
        body = {
            "access": {"valid_until": valid_until.isoformat()},
            "aspsp": {"name": bank_name, "country": country},
            "state": state or str(uuid.uuid4()),
            "redirect_url": settings.eb_redirect_url,
            "psu_type": "personal",
        }
        return self._request("POST", "/auth", json=body)  # contient "url"

    def create_session(self, code: str) -> dict:
        return self._request("POST", "/sessions", json={"code": code})

    def get_session(self, session_id: str) -> dict:
        return self._request("GET", f"/sessions/{session_id}")

    # --- Données de compte ---
    def get_account_details(self, account_uid: str) -> dict:
        return self._request("GET", f"/accounts/{account_uid}/details")

    def get_balances(self, account_uid: str) -> list[dict]:
        return self._request("GET", f"/accounts/{account_uid}/balances").get("balances", [])

    def iter_transactions(self, account_uid: str, date_from: str):
        params = {"date_from": date_from}
        while True:
            data = self._request("GET", f"/accounts/{account_uid}/transactions", params=params)
            yield from data.get("transactions", [])
            key = data.get("continuation_key")
            if not key:
                break
            params = {"date_from": date_from, "continuation_key": key}


def normalize_transaction(tx: dict, account_uid: str) -> dict | None:
    """Convertit une transaction Enable Banking vers notre schéma. None si en attente."""
    if tx.get("status") == "PDNG":
        return None  # on ne garde que les opérations comptabilisées

    amount = abs(float(tx["transaction_amount"]["amount"]))
    is_debit = tx.get("credit_debit_indicator") == "DBIT"
    if is_debit:
        amount = -amount

    label = " ".join(tx.get("remittance_information") or []).strip()
    party = tx.get("creditor") if is_debit else tx.get("debtor")
    counterparty = (party or {}).get("name") or ""
    date = tx.get("booking_date") or tx.get("value_date") or tx.get("transaction_date")

    ref = tx.get("entry_reference") or tx.get("transaction_id")
    if not ref:  # certaines banques n'envoient pas d'identifiant stable
        ref = hashlib.sha1(f"{date}|{amount}|{label}|{counterparty}".encode()).hexdigest()

    return {
        "id": f"{account_uid}:{ref}",
        "account_uid": account_uid,
        "date": date,
        "amount": round(amount, 2),
        "currency": tx["transaction_amount"].get("currency", "EUR"),
        "label": label or counterparty,
        "counterparty": counterparty,
        "mcc": tx.get("merchant_category_code"),
        "merchant": extract_merchant(counterparty or label),
    }


__all__ = ["EnableBankingClient", "EnableBankingError", "normalize_transaction", "clean_label"]
