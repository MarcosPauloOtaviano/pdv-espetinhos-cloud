import test from "node:test";
import assert from "node:assert/strict";
import { groupProductsByCategory } from "./catalog.js";

test("agrupa o cardapio por categoria sem misturar estabelecimentos ou produtos", () => {
  const products = [
    { id: "1", name: "Skol", category: "Cerveja 600 ml" },
    { id: "2", name: "Skol", category: "Lata 350 ml" },
    { id: "3", name: "Agua", category: "" },
  ];

  assert.deepEqual(groupProductsByCategory(products, (product) => product.category), [
    { name: "Cerveja 600 ml", items: [products[0]] },
    { name: "Lata 350 ml", items: [products[1]] },
    { name: "Outros", items: [products[2]] },
  ]);
});
