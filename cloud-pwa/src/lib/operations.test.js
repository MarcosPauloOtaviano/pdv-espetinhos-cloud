import test from "node:test";
import assert from "node:assert/strict";
import { runMutationWithRefresh } from "./operations.js";

test("preserva o resultado da mutação quando a recarga falha", async () => {
  const result = await runMutationWithRefresh(
    async () => ({ id: "saved" }),
    async () => { throw new Error("refresh indisponível"); }
  );

  assert.equal(result.result.id, "saved");
  assert.equal(result.refreshError.message, "refresh indisponível");
});

test("propaga erro da mutação sem executar recarga", async () => {
  let refreshed = false;
  await assert.rejects(
    () => runMutationWithRefresh(
      async () => { throw new Error("mutação recusada"); },
      async () => { refreshed = true; }
    ),
    /mutação recusada/
  );
  assert.equal(refreshed, false);
});
