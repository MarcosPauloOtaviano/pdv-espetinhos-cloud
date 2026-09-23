import test from "node:test";
import assert from "node:assert/strict";
import { normalizeOrderQuantity } from "./format.js";

test("normaliza a quantidade escolhida antes de adicionar o produto", () => {
  assert.equal(normalizeOrderQuantity("5"), 5);
  assert.equal(normalizeOrderQuantity("5,9"), 5);
  assert.equal(normalizeOrderQuantity("0"), 1);
  assert.equal(normalizeOrderQuantity("invalido"), 1);
  assert.equal(normalizeOrderQuantity("1000"), 999);
});
