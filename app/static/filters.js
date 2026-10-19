// Filtres de la liste d'opérations : logique pure, partagée par index.html et tests/dashboard.test.mjs.

/** nature : "all" | "in" (entrées) | nature de dépense ; cats : Set de catégories (vide = toutes) ;
 *  account : uid du compte (null = tous). */
function filterTransactions(txs, nature, cats, account = null) {
  return txs.filter(t => {
    if (account && t.account_uid !== account) return false;
    if (cats.size && !cats.has(t.category)) return false;
    if (nature === "all") return true;
    if (nature === "in") return t.amount > 0;
    return t.amount < 0 && t.nature === nature;
  });
}

/** Ajoute la catégorie, ou la retire si elle est déjà sélectionnée (nouvel ensemble). */
function toggleCategory(cats, id) {
  const next = new Set(cats);
  if (!next.delete(id)) next.add(id);
  return next;
}

if (typeof module !== "undefined") module.exports = { filterTransactions, toggleCategory };
