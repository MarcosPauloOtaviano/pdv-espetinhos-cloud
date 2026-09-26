import test from "node:test";
import assert from "node:assert/strict";
import { auditActionLabel, cashCloseNeedsReason, cashDifference, refreshScopesForTable, syncStatusMeta } from "./operational.js";

test("direciona eventos realtime apenas para os dados relacionados", () => {
  assert.deepEqual(refreshScopesForTable("service_queue"), ["queue", "dashboard"]);
  assert.deepEqual(refreshScopesForTable("products"), ["catalog"]);
  assert.deepEqual(refreshScopesForTable("establishments"), ["profile"]);
  assert.deepEqual(refreshScopesForTable("unknown"), ["all"]);
});

test("resume o estado operacional sem confundir internet com realtime", () => {
  assert.equal(syncStatusMeta({ online: false, realtimeStatus: "connected" }).label, "Sem internet");
  assert.equal(syncStatusMeta({ online: true, realtimeStatus: "connected" }).label, "Sincronizado");
  assert.equal(syncStatusMeta({ online: true, realtimeStatus: "error" }).label, "Reconectando");
});

test("traduz atividades administrativas conhecidas", () => {
  assert.equal(auditActionLabel("admin_item_adjusted"), "Item corrigido pelo administrador");
  assert.equal(auditActionLabel("custom_action"), "custom action");
});

test("calcula divergência e exige justificativa somente quando necessário", () => {
  assert.equal(cashDifference(99.9, 100), -0.1);
  assert.equal(cashCloseNeedsReason(0, false), false);
  assert.equal(cashCloseNeedsReason(-0.1, false), true);
  assert.equal(cashCloseNeedsReason(0, true), true);
});
