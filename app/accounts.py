"""Rôle de chaque compte connecté : conditionne la lecture des flux entre comptes.

- courant : dans le budget (comptes de tous les jours, compte joint, compte de dépôt
  qui paie le crédit maison)
- epargne : livrets, compte des enfants ; l'argent qui y arrive est de l'épargne
- pro     : compte professionnel, hors budget
- credit  : compte de prêt ; ses mouvements ne sont pas des dépenses
"""

ROLES: dict[str, dict] = {
    "courant": {"label": "Courant"},
    "epargne": {"label": "Épargne"},
    "pro":     {"label": "Pro"},
    "credit":  {"label": "Crédit"},
}


def default_role(account: dict, psu_type: str | None) -> str:
    """Rôle proposé d'après le compte renvoyé par Enable Banking (cash_account_type, usage)
    et le type de consentement ; l'utilisateur peut le changer ensuite."""
    if account.get("cash_account_type") == "LOAN":
        return "credit"
    if psu_type == "business" or account.get("usage") == "ORGA":
        return "pro"  # même un livret de la société n'est pas ton épargne
    if account.get("cash_account_type") == "SVGS":
        return "epargne"
    return "courant"
