// Logique de filtre du dashboard (app/static/filters.js). Lancer : node --test tests/
import { test } from "node:test";
import assert from "node:assert/strict";
import { createRequire } from "node:module";

const { filterTransactions, toggleCategory } = createRequire(import.meta.url)("../app/static/filters.js");

const TXS = [
  { id: "1", amount: -50, nature: "essentiel", category: "courses" },
  { id: "2", amount: -20, nature: "optimisable", category: "restaurants" },
  { id: "3", amount: -9, nature: "optimisable", category: "abonnements" },
  { id: "4", amount: 2000, nature: "revenu", category: "revenus" },
  { id: "5", amount: -30, nature: "inconnu", category: "inconnu" },
];
const ids = (txs) => txs.map(t => t.id);

test("sans catégorie sélectionnée, seul le filtre de nature s'applique", () => {
  assert.deepEqual(ids(filterTransactions(TXS, "all", new Set())), ["1", "2", "3", "4", "5"]);
  assert.deepEqual(ids(filterTransactions(TXS, "optimisable", new Set())), ["2", "3"]);
  assert.deepEqual(ids(filterTransactions(TXS, "in", new Set())), ["4"]);
});

test("plusieurs catégories sélectionnées : union des catégories", () => {
  assert.deepEqual(ids(filterTransactions(TXS, "all", new Set(["courses", "abonnements"]))), ["1", "3"]);
});

test("catégories et nature se combinent", () => {
  assert.deepEqual(ids(filterTransactions(TXS, "optimisable", new Set(["courses", "abonnements"]))), ["3"]);
});

test("re-cliquer une catégorie la retire, sans muter l'ensemble d'origine", () => {
  const a = new Set(["courses"]);
  const b = toggleCategory(a, "abonnements");
  assert.deepEqual([...b].sort(), ["abonnements", "courses"]);
  assert.deepEqual([...toggleCategory(b, "courses")], ["abonnements"]);
  assert.deepEqual([...a], ["courses"]);
});

test("filtre par compte, combiné aux autres filtres", () => {
  const txs = [
    { id: "a", amount: -10, nature: "essentiel", category: "courses", account_uid: "perso" },
    { id: "b", amount: -20, nature: "essentiel", category: "courses", account_uid: "joint" },
    { id: "c", amount: 500, nature: "revenu", category: "revenus", account_uid: "joint" },
  ];
  assert.deepEqual(ids(filterTransactions(txs, "all", new Set(), "joint")), ["b", "c"]);
  assert.deepEqual(ids(filterTransactions(txs, "essentiel", new Set(), "joint")), ["b"]);
  assert.deepEqual(ids(filterTransactions(txs, "all", new Set(), null)), ["a", "b", "c"]);  // null : tous les comptes
});
