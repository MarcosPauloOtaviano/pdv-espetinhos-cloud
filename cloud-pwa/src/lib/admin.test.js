import test from "node:test";
import assert from "node:assert/strict";
import { commandOwner, filterProducts, inventoryValue, isLowStock } from "./admin.js";

const products = [
  {
    id: "1",
    name: "Espetinho de frango",
    category_id: "cat-1",
    categories: { name: "Espetinhos" },
    active: true,
    track_stock: true,
    stock_quantity: 3,
    low_stock_threshold: 5,
    cost: 4,
  },
  {
    id: "2",
    name: "Refrigerante",
    category_id: "cat-2",
    categories: { name: "Bebidas" },
    active: false,
    track_stock: true,
    stock_quantity: 10,
    low_stock_threshold: 2,
    cost: 3,
  },
];

test("identifica o responsavel pela comanda", () => {
  assert.equal(
    commandOwner({ created_by: "user-1" }, [{ id: "user-1", username: "garcom", full_name: "Maria" }]),
    "Maria"
  );
});

test("filtra estoque por busca, categoria e status", () => {
  assert.deepEqual(filterProducts(products, {}).map((item) => item.id), ["1"]);
  assert.deepEqual(filterProducts(products, { search: "bebidas", showInactive: true }).map((item) => item.id), ["2"]);
  assert.deepEqual(filterProducts(products, { categoryId: "cat-1" }).map((item) => item.id), ["1"]);
});

test("calcula alerta e valor apenas do estoque ativo controlado", () => {
  assert.equal(isLowStock(products[0]), true);
  assert.equal(isLowStock(products[1]), false);
  assert.equal(inventoryValue(products), 12);
});
