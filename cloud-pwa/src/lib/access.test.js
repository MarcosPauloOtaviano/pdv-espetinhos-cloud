import test from "node:test";
import assert from "node:assert/strict";
import { defaultViewForRole, realtimeTablesForRole, roleCanAccessView } from "./access.js";

test("cozinha abre somente a fila de pedidos", () => {
  assert.equal(defaultViewForRole("cozinha", "cash"), "queue");
  assert.equal(roleCanAccessView("cozinha", "queue"), true);
  assert.equal(roleCanAccessView("cozinha", "dashboard"), false);
  assert.equal(roleCanAccessView("cozinha", "commands"), false);
  assert.equal(roleCanAccessView("cozinha", "cash"), false);
  assert.equal(roleCanAccessView("cozinha", "products"), false);
  assert.deepEqual(realtimeTablesForRole("cozinha", ["commands", "service_queue"]), ["service_queue"]);
});

test("demais perfis mantêm a navegação solicitada", () => {
  assert.equal(defaultViewForRole("atendente", "commands"), "commands");
  assert.equal(roleCanAccessView("admin", "settings"), true);
});
