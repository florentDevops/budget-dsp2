// Comptes connectés : logique pure, partagée par index.html et tests/accounts.test.mjs.

const PSU = { personal: "Perso", business: "Pro" };

/** Types de connexion proposés pour une banque (psu_types de /api/banks), perso d'abord. */
function psuOptions(bank) {
  const types = (bank && bank.psu_types && bank.psu_types.length) ? bank.psu_types : ["personal"];
  return Object.keys(PSU).filter(id => types.includes(id)).map(id => ({ id, label: PSU[id] }));
}

/** Nom affiché d'un compte : celui choisi, sinon le produit (« Livret A »), sinon le titulaire. */
function accountName(a) {
  if (a.label) return a.label;
  const raw = a.product || a.name;
  if (!raw) return "Compte";
  return raw.toLowerCase().replace(/(^|\s)\S/g, c => c.toUpperCase());
}

/** Étiquette d'une opération : virement entre ses comptes (vers / depuis le jumeau) ou hors budget. */
function flowTag(t, accounts) {
  if (t.transfer_peer) {
    const peer = accounts.find(a => a.uid === t.peer_account);
    return { kind: "interne", text: `Virement ${t.amount < 0 ? "vers" : "depuis"} ${peer ? accountName(peer) : "un autre compte"}` };
  }
  if (t.nature === "hors_budget") return { kind: "hors", text: "Hors budget" };
  return null;
}

if (typeof module !== "undefined") module.exports = { psuOptions, accountName, flowTag };
