// Page tendances : logique pure, partagée par trends.html et tests/trends.test.mjs.

/**
 * Garde les `limit` plus grosses catégories (plus la catégorie focalisée, même petite),
 * regroupe le reste dans « Autres » et laisse « À classer » à part, en dernier.
 * cats : [{ category, label, amounts: [par mois], total }], déjà restreintes à la période.
 * canName(category) : faux pour une catégorie sans teinte propre, qui irait se confondre
 * avec le gris de « Autres » ; elle y est donc regroupée.
 */
function groupSeries(cats, limit, focus = null, canName = () => true) {
  const known = cats.filter(c => c.category !== "inconnu").sort((a, b) => b.total - a.total);
  const unknown = cats.filter(c => c.category === "inconnu" && c.total > 0);
  const kept = known.filter(c => canName(c.category)).slice(0, limit);
  let rest = known.filter(c => !kept.includes(c));
  const focused = rest.find(c => c.category === focus);
  if (focused) {
    kept.push(focused);
    rest = rest.filter(c => c !== focused);
  }
  const out = [...kept];
  if (rest.length) {
    out.push({
      category: "autres",
      label: "Autres",
      amounts: rest[0].amounts.map((_, i) => rest.reduce((a, c) => a + c.amounts[i], 0)),
      total: rest.reduce((a, c) => a + c.total, 0),
      members: rest.map(c => c.category),
    });
  }
  return out.concat(unknown);
}

/** Ordre d'empilement, du bas vers le haut : la catégorie focalisée d'abord, posée sur l'axe. */
function stackOrder(series, focus) {
  const f = series.find(s => s.category === focus);
  return f ? [f, ...series.filter(s => s !== f)] : series;
}

/** Restreint chaque catégorie aux `n` derniers mois (n = 0 : tout). */
function lastMonths(trends, n) {
  const from = n ? Math.max(0, trends.months.length - n) : 0;
  return {
    months: trends.months.slice(from),
    categories: trends.categories
      .map(c => {
        const amounts = c.amounts.slice(from);
        return { ...c, amounts, total: amounts.reduce((a, b) => a + b, 0) };
      })
      .filter(c => c.total > 0)
      .sort((a, b) => b.total - a.total),
  };
}

/** Pas de graduation « rond » (1, 2, 5 x 10^n) pour environ `count` lignes. */
function niceStep(max, count = 4) {
  if (max <= 0) return 1;
  const raw = max / count;
  const mag = 10 ** Math.floor(Math.log10(raw));
  return [1, 2, 5, 10].map(k => k * mag).find(s => s >= raw);
}

if (typeof module !== "undefined") module.exports = { groupSeries, stackOrder, lastMonths, niceStep };
