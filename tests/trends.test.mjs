// Logique de la page tendances (app/static/trends.js). Lancer : node --test tests/
import { test } from "node:test";
import assert from "node:assert/strict";
import { createRequire } from "node:module";

const { groupSeries, stackOrder, lastMonths, niceStep } = createRequire(import.meta.url)("../app/static/trends.js");

const cat = (category, amounts) => ({ category, label: category, amounts, total: amounts.reduce((a, b) => a + b, 0) });
const CATS = [
  cat("logement", [800, 800]), cat("courses", [300, 350]), cat("inconnu", [120, 40]),
  cat("restaurants", [90, 140]), cat("impots", [0, 60]), cat("animaux", [20, 0]),
];

test("les catégories au-delà de la limite sont regroupées dans Autres, À classer reste à part", () => {
  const g = groupSeries(CATS, 2);
  assert.deepEqual(g.map(s => s.category), ["logement", "courses", "autres", "inconnu"]);
  assert.deepEqual(g[2].amounts, [110, 200]);
  assert.deepEqual(g[2].members, ["restaurants", "impots", "animaux"]);
  assert.equal(g[2].total, 310);
});

test("pas de groupe Autres quand tout tient dans la limite", () => {
  assert.deepEqual(groupSeries(CATS, 10).map(s => s.category),
    ["logement", "courses", "restaurants", "impots", "animaux", "inconnu"]);
});

test("une catégorie focalisée est sortie de Autres pour être lisible", () => {
  const g = groupSeries(CATS, 2, "impots");
  assert.deepEqual(g.map(s => s.category), ["logement", "courses", "impots", "autres", "inconnu"]);
  assert.deepEqual(g.find(s => s.category === "autres").members, ["restaurants", "animaux"]);
});

test("empilement : la catégorie focalisée passe en bas, les autres gardent leur ordre", () => {
  const g = groupSeries(CATS, 3);
  // sans focus : plus grosse catégorie en bas, Autres puis À classer en haut de la pile
  assert.deepEqual(stackOrder(g, null).map(s => s.category), ["logement", "courses", "restaurants", "autres", "inconnu"]);
  assert.deepEqual(stackOrder(g, "restaurants").map(s => s.category), ["restaurants", "logement", "courses", "autres", "inconnu"]);
  assert.deepEqual(stackOrder(g, "inconnu").map(s => s.category), ["inconnu", "logement", "courses", "restaurants", "autres"]);
});

test("période : garde les n derniers mois, recalcule les totaux et retire les catégories vides", () => {
  const t = { months: ["2026-07", "2026-08", "2026-09"], categories: [cat("courses", [10, 20, 30]), cat("voyages", [500, 0, 0])] };
  const r = lastMonths(t, 2);
  assert.deepEqual(r.months, ["2026-08", "2026-09"]);
  assert.deepEqual(r.categories.map(c => [c.category, c.amounts, c.total]), [["courses", [20, 30], 50]]);
  assert.equal(lastMonths(t, 0).categories[0].category, "voyages"); // 0 = tout, retrié par total
});

test("graduations rondes", () => {
  assert.equal(niceStep(1730), 500);
  assert.equal(niceStep(380), 100);
  assert.equal(niceStep(0), 1);
});

test("seules les catégories qui ont leur propre teinte sont nommées, sauf si focalisées", () => {
  const hasHue = (c) => c !== "restaurants";
  assert.deepEqual(groupSeries(CATS, 3, null, hasHue).map(s => s.category), ["logement", "courses", "impots", "autres", "inconnu"]);
  assert.deepEqual(groupSeries(CATS, 3, null, hasHue)[3].members, ["restaurants", "animaux"]);
  assert.deepEqual(groupSeries(CATS, 3, "restaurants", hasHue).map(s => s.category),
    ["logement", "courses", "impots", "restaurants", "autres", "inconnu"]);
});
