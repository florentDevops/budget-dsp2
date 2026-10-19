// Logique du bilan entrées / sorties (app/static/cashflow.js). Lancer : node --test tests/
import { test } from "node:test";
import assert from "node:assert/strict";
import { createRequire } from "node:module";

const { flowView, gapRegions } = createRequire(import.meta.url)("../app/static/cashflow.js");

const CF = {
  months: ["2026-06", "2026-07", "2026-08", "2026-09"],
  income: [2500, 2500, 2540, 900], spent: [2000, 2700, 2400, 300], savings: [200, 0, 400, 0], partial: "2026-09",
};

test("période : garde les n derniers mois, calcule le solde et repère le mois partiel", () => {
  const v = flowView(CF, 3);
  assert.deepEqual(v.months, ["2026-07", "2026-08", "2026-09"]);
  assert.deepEqual(v.net, [-200, 140, 600]);
  assert.deepEqual(v.savings, [0, 400, 0]);
  assert.equal(v.partialIndex, 2);
  assert.equal(flowView(CF, 0).months.length, 4);  // 0 = tout
  assert.equal(flowView({ ...CF, partial: null }, 2).partialIndex, -1);
});

test("écart sans croisement : une seule zone, du côté excédent", () => {
  assert.deepEqual(gapRegions([100, 120], [50, 60]), [
    { sign: 1, pts: [{ t: 0, a: 100, b: 50 }, { t: 1, a: 120, b: 60 }] },
  ]);
});

test("les courbes se croisent : la zone est coupée au point d'intersection", () => {
  const r = gapRegions([100, 100, 100], [50, 50, 150]);
  assert.deepEqual(r.map(z => z.sign), [1, -1]);
  assert.deepEqual(r[0].pts.map(p => p.t), [0, 1, 1.5]);
  assert.deepEqual(r[0].pts[2], { t: 1.5, a: 100, b: 100 });
  assert.deepEqual(r[1].pts.map(p => p.t), [1.5, 2]);
});

test("un mois à l'équilibre sépare aussi deux zones de signe opposé", () => {
  const r = gapRegions([110, 100, 90], [100, 100, 100]);
  assert.deepEqual(r.map(z => [z.sign, z.pts.map(p => p.t)]), [[1, [0, 1]], [-1, [1, 2]]]);
});
