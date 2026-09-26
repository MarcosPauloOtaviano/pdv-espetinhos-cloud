export const REALTIME_REFRESH_SCOPES = {
  establishments: ["profile"],
  settings: ["settings"],
  categories: ["catalog"],
  products: ["catalog"],
  cash_sessions: ["cash", "dashboard"],
  cash_movements: ["cash", "dashboard"],
  commands: ["commands", "dashboard"],
  command_items: ["commands", "catalog"],
  payments: ["commands", "cash", "dashboard"],
  profiles: ["profiles"],
  service_queue: ["queue", "dashboard"],
};

export function refreshScopesForTable(table) {
  return REALTIME_REFRESH_SCOPES[table] || ["all"];
}

export function syncStatusMeta({ online, realtimeStatus }) {
  if (!online) return { tone: "offline", label: "Sem internet" };
  if (realtimeStatus === "connected") return { tone: "connected", label: "Sincronizado" };
  if (realtimeStatus === "error") return { tone: "error", label: "Reconectando" };
  return { tone: "connecting", label: "Conectando" };
}

export function auditActionLabel(action) {
  const labels = {
    created: "Comanda criada",
    item_added: "Item adicionado",
    item_quantity_changed: "Quantidade alterada",
    item_removed: "Item removido",
    admin_item_adjusted: "Item corrigido pelo administrador",
    discount_changed: "Desconto alterado",
    info_changed: "Dados da comanda alterados",
    paid: "Pagamento confirmado",
    cancelled: "Comanda cancelada",
    closed: "Caixa fechado",
    opened: "Caixa aberto",
    sangria: "Sangria registrada",
    reforco: "Reforço registrado",
    queued: "Solicitação adicionada à fila",
    claimed: "Solicitação assumida",
    completed: "Solicitação concluída",
    kitchen_status_changed: "Etapa de preparo alterada",
    user_deleted: "Usuário inativo excluído",
  };
  return labels[action] || String(action || "Atividade").replaceAll("_", " ");
}

export function cashDifference(counted, expected) {
  return Math.round((Number(counted || 0) - Number(expected || 0)) * 100) / 100;
}

export function cashCloseNeedsReason(difference, force) {
  return Number(difference || 0) !== 0 || Boolean(force);
}
