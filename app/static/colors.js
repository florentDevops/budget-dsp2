// Une teinte fixe par catégorie de dépense courante (jamais réassignée par rang/mois) ;
// les catégories restantes (impôts, à classer, virements…) partagent un gris neutre.
const CAT_COLOR = {
  courses:     "var(--cat-1)",
  logement:    "var(--cat-2)",
  restaurants: "var(--cat-3)",
  transport:   "var(--cat-4)",
  abonnements: "var(--cat-5)",
  sante:       "var(--cat-6)",
  shopping:    "var(--cat-7)",
  loisirs:     "var(--cat-8)",
  assurance:   "var(--cat-9)",
  energie:     "var(--cat-10)",
  telecom:     "var(--cat-11)",
  voyages:     "var(--cat-12)",
  cadeaux:     "var(--cat-12)",  // partagée avec voyages, la moins fréquente des 12 (le libellé départage)
  animaux:     "var(--cat-6)",   // partagée avec santé (vétérinaire), dépenses rares
};
const catColor = (c) => CAT_COLOR[c.category] || "var(--unknown)";

if (typeof module !== "undefined") module.exports = { CAT_COLOR, catColor };
