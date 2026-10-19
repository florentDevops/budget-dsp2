// Logique des comptes (app/static/accounts.js). Lancer : node --test tests/
import { test } from "node:test";
import assert from "node:assert/strict";
import { createRequire } from "node:module";

const { psuOptions, accountName } = createRequire(import.meta.url)("../app/static/accounts.js");

test("seuls les types de connexion acceptés par la banque sont proposés, perso d'abord", () => {
  assert.deepEqual(psuOptions({ psu_types: ["business"] }).map(o => o.id), ["business"]);  // Qonto
  assert.deepEqual(psuOptions({ psu_types: ["business", "personal"] }).map(o => o.id), ["personal", "business"]);
  assert.deepEqual(psuOptions({}).map(o => o.id), ["personal"]);
  assert.deepEqual(psuOptions(undefined).map(o => o.id), ["personal"]);
  assert.equal(psuOptions({ psu_types: ["business"] })[0].label, "Pro");
});

test("nom affiché : celui choisi, sinon le produit de la banque, sinon le titulaire", () => {
  assert.equal(accountName({ label: "Livret enfants", product: "LIVRET A", name: "M X" }), "Livret enfants");
  assert.equal(accountName({ label: null, product: "LIVRET A", name: "M X" }), "Livret A");
  assert.equal(accountName({ name: "MME A OU M B" }), "Mme A Ou M B");
  assert.equal(accountName({}), "Compte");
});
