"""Virements entre ses propres comptes : appariement, puis lecture selon le rôle des comptes.

Un virement Fortuneo -> livret apparaît deux fois (-200 sur l'un, +200 sur l'autre). match()
relie les deux opérations ; effective() décide ensuite, à la lecture, comment chacune compte
dans le budget selon le rôle de son compte et du compte jumeau (app/accounts.py). Rien n'est
stocké : un changement de rôle s'applique immédiatement, sans reclassement.
"""
import re
from datetime import date

from . import db
from .normalize import is_cheque

MATCH_WINDOW_DAYS = 3   # débit et crédit jumeaux à 3 jours d'écart au plus

OUT = "hors_budget"     # nature à la lecture des opérations qui ne sont pas du budget du foyer
NEUTRAL = ("virements", "transfert")
SAVINGS = {"epargne": ("epargne", "epargne"), "enfants": ("epargne_enfants", "epargne")}

# Un libellé de virement ou de prélèvement d'au moins un côté (Qonto n'écrit que la référence
# saisie, « Envoye depuis Qonto »), et jamais de carte ni de chèque d'un côté comme de l'autre :
# un paiement carte de 50 € et un virement reçu de 50 € le même jour ne sont pas un virement
# entre ses comptes.
_TRANSFER = re.compile(r"\bVIR\b|VIREMENT|VERSEMENT|TRANSFER|\bPRLV\b|PRELEVEMENT|ECHEANCE", re.I)
_CARD = re.compile(r"^\s*(CB|CARTE|PAIEMENT PAR CARTE)\b", re.I)


def _looks_like_transfer(t: dict) -> bool:
    return bool(_TRANSFER.search(f"{t['label'] or ''} {t['counterparty'] or ''}"))


def _can_be_transfer(t: dict) -> bool:
    return not _CARD.match(t["label"] or "") and not is_cheque(t["label"] or "")


def match() -> int:
    """Apparie un pour un, l'écart de dates le plus court d'abord. Les paires et dissociations
    manuelles (transfer_source = 'user') ne sont jamais remises en cause. Renvoie le nombre de paires créées."""
    free = [t for t in db.rows(
        """SELECT id, account_uid, date, amount, label, counterparty FROM transactions
           WHERE transfer_peer IS NULL AND transfer_source IS NULL""") if _can_be_transfer(t)]
    credits: dict[float, list[dict]] = {}
    for t in free:
        if t["amount"] > 0:
            credits.setdefault(round(t["amount"], 2), []).append(t)
    candidates = []
    for d in (t for t in free if t["amount"] < 0):
        for c in credits.get(round(-d["amount"], 2), []):
            gap = abs((date.fromisoformat(c["date"]) - date.fromisoformat(d["date"])).days)
            if c["account_uid"] != d["account_uid"] and gap <= MATCH_WINDOW_DAYS \
                    and (_looks_like_transfer(d) or _looks_like_transfer(c)):
                candidates.append((gap, d["date"], d["id"], c["id"]))
    used, pairs = set(), []
    for _, _, debit, credit in sorted(candidates):
        if debit not in used and credit not in used:
            used |= {debit, credit}
            pairs.append((debit, credit))
    with db.connect() as con:
        con.executemany("UPDATE transactions SET transfer_peer=?, transfer_source='auto' WHERE id=?",
                        [p for d, c in pairs for p in ((c, d), (d, c))])
    return len(pairs)


def set_peer(tx_id: str, peer_id: str | None) -> None:
    """Correction manuelle : apparie tx_id avec peer_id, ou le dissocie (peer_id None).
    Les anciens jumeaux sont libérés ; une dissociation est figée des deux côtés."""
    with db.connect() as con:
        ids = [tx_id] + ([peer_id] if peer_id else [])
        olds = [r[0] for r in con.execute(
            f"SELECT transfer_peer FROM transactions WHERE id IN ({','.join('?' * len(ids))}) "
            "AND transfer_peer IS NOT NULL", ids)]
        freed = 'user' if peer_id is None else None  # dissocié : le jumeau ne doit pas être réapparié
        con.executemany("UPDATE transactions SET transfer_peer=NULL, transfer_source=? WHERE id=?",
                        [(freed, o) for o in olds if o not in ids])
        if peer_id is None:
            con.execute("UPDATE transactions SET transfer_peer=NULL, transfer_source='user' WHERE id=?", (tx_id,))
        else:
            con.executemany("UPDATE transactions SET transfer_peer=?, transfer_source='user' WHERE id=?",
                            [(peer_id, tx_id), (tx_id, peer_id)])


def _out_category(t: dict, peer: str | None) -> str | None:
    """Côté hors budget, un virement apparié s'affiche « Virements » (pas « Revenus » pour un
    versement arrivé sur le livret) ; les opérations propres du compte gardent leur catégorie."""
    return NEUTRAL[0] if peer else t["category"]


def effective(t: dict) -> dict:
    """Catégorie et nature d'une opération dans le budget, selon le rôle de son compte et du
    compte jumeau. t vient de load() (account_role, peer_account, peer_role)."""
    role = t.get("account_role") or "courant"
    peer = t.get("peer_role") or ("courant" if t.get("peer_account") else None)
    if role == "pro":
        # Seule l'épargne versée directement depuis la société compte, côté pro : vers un livret
        # connecté (lui-même hors budget), ou vers un placement non connecté (assurance vie,
        # fonds) classé épargne. Ses dépenses et ses virements vers tes comptes courants non.
        if t["amount"] < 0 and peer in SAVINGS:
            cat_nat = SAVINGS[peer]
        elif t["amount"] < 0 and peer is None and t["nature"] == "epargne":
            return t
        else:
            cat_nat = (_out_category(t, peer), OUT)
    elif role != "courant":
        cat_nat = (_out_category(t, peer), OUT)  # livrets, compte enfants, prêt : lus depuis le compte courant
    elif t.get("user_category"):
        return t  # correction manuelle : source de vérité sur un compte courant
    elif peer == "courant":
        cat_nat = NEUTRAL
    elif peer in SAVINGS:
        cat_nat = SAVINGS[peer]  # versement, ou retrait si crédit (épargne nette diminuée)
    elif peer == "pro":
        cat_nat = ("revenus", "revenu") if t["amount"] > 0 else NEUTRAL
    else:
        return t  # non apparié, ou échéance vers le prêt : classement habituel
    return {**t, "category": cat_nat[0], "nature": cat_nat[1]}


def load(where: str = "", params: tuple = (), include_out: bool = False) -> list[dict]:
    """Opérations lues selon le rôle des comptes. where porte sur l'alias t (« WHERE t.date >= ? »).
    Les opérations hors budget ne sont renvoyées qu'avec include_out (liste du dashboard)."""
    rows = db.rows(
        f"""SELECT t.*, a.role AS account_role, p.account_uid AS peer_account, pa.role AS peer_role
            FROM transactions t
            LEFT JOIN accounts a ON a.uid = t.account_uid
            LEFT JOIN transactions p ON p.id = t.transfer_peer
            LEFT JOIN accounts pa ON pa.uid = p.account_uid
            {where}""", params)
    txs = [effective(t) for t in rows]
    return txs if include_out else [t for t in txs if t["nature"] != OUT]
