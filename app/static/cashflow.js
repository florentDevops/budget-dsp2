// Bilan entrées / sorties : logique pure, partagée par trends.html et tests/cashflow.test.mjs.

/** Restreint le bilan aux `n` derniers mois (n = 0 : tout) et calcule le solde mensuel. */
function flowView(cf, n) {
  const from = n ? Math.max(0, cf.months.length - n) : 0;
  const months = cf.months.slice(from);
  const income = cf.income.slice(from), spent = cf.spent.slice(from);
  return {
    months, income, spent,
    savings: cf.savings.slice(from),
    net: income.map((v, i) => Math.round((v - spent[i]) * 100) / 100),
    partialIndex: months.indexOf(cf.partial),
  };
}

/**
 * Zones entre deux courbes a (entrées) et b (sorties), coupées là où elles se croisent
 * ou se touchent, pour teinter chacune selon son signe (1 : a au-dessus, -1 : en dessous).
 * t est la position en mois (fractionnaire au point d'intersection).
 */
function gapRegions(a, b) {
  const d = a.map((v, i) => v - b[i]);
  const regions = [];
  let pts = [{ t: 0, a: a[0], b: b[0] }];
  const close = () => {
    const first = pts.find(p => p.a !== p.b);
    regions.push({ sign: first && first.a < first.b ? -1 : 1, pts });
  };
  for (let i = 0; i < a.length - 1; i++) {
    if (d[i] * d[i + 1] < 0) {
      const f = d[i] / (d[i] - d[i + 1]);
      const v = a[i] + (a[i + 1] - a[i]) * f;
      const cross = { t: i + f, a: v, b: v };
      pts.push(cross);
      close();
      pts = [cross];
    }
    pts.push({ t: i + 1, a: a[i + 1], b: b[i + 1] });
    if (d[i + 1] === 0 && i + 1 < a.length - 1) {
      close();
      pts = [pts[pts.length - 1]];
    }
  }
  close();
  return regions;
}

if (typeof module !== "undefined") module.exports = { flowView, gapRegions };
