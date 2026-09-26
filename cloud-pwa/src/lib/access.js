const DEFAULT_VIEW_BY_ROLE = {
  admin: "dashboard",
  caixa: "dashboard",
  atendente: "commands",
  cozinha: "queue",
};

const VIEW_ACCESS_BY_ROLE = {
  admin: new Set(["dashboard", "commands", "queue", "cash", "products", "reports", "settings", "platform"]),
  caixa: new Set(["dashboard", "commands", "queue", "cash"]),
  atendente: new Set(["dashboard", "commands", "queue"]),
  cozinha: new Set(["queue"]),
};

export function defaultViewForRole(role, requestedView = "dashboard") {
  return roleCanAccessView(role, requestedView)
    ? requestedView
    : DEFAULT_VIEW_BY_ROLE[role] || "dashboard";
}

export function roleCanAccessView(role, view) {
  return VIEW_ACCESS_BY_ROLE[role]?.has(view) ?? false;
}

export function realtimeTablesForRole(role, defaultTables) {
  return role === "cozinha" ? ["service_queue"] : defaultTables;
}
