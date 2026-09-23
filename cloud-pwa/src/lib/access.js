const KITCHEN_VIEW = "queue";

export function defaultViewForRole(role, requestedView = "dashboard") {
  return role === "cozinha" ? KITCHEN_VIEW : requestedView;
}

export function roleCanAccessView(role, view) {
  if (role === "cozinha") return view === KITCHEN_VIEW;
  return true;
}

export function realtimeTablesForRole(role, defaultTables) {
  return role === "cozinha" ? ["service_queue"] : defaultTables;
}
