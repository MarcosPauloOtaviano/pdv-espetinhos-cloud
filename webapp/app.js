/* DUDAIR-PDV - PWA para garcom / cozinha (e consulta rapida por caixa/admin).
   Vanilla JS, sem build step. Fala com a mesma API que o app do computador. */

const state = {
  token: localStorage.getItem("dudair_token") || null,
  user: JSON.parse(localStorage.getItem("dudair_user") || "null"),
  view: "login",
  currentCommandId: null,
  ws: null,
  products: [],
  categories: [],
  catalogSearch: "",
  catalogCategory: null,
  customerAccessToken: new URLSearchParams(location.search).get("access"),
};

const KITCHEN_NEXT = { pendente: "preparando", preparando: "pronto", pronto: "entregue", entregue: "entregue" };
const KITCHEN_LABELS = { pendente: "Pendente", preparando: "Preparando", pronto: "Pronto", entregue: "Entregue" };
const STATUS_LABELS = { aberto: "Em aberto", aguardando_pagamento: "Aguardando pagamento", paga: "Paga", cancelada: "Cancelada", fiado: "Fiado/Pendente" };

function fmt(v) {
  return "R$ " + (Number(v) || 0).toFixed(2).replace(".", ",");
}

function escapeHtml(text) {
  const div = document.createElement("div");
  div.textContent = text == null ? "" : String(text);
  return div.innerHTML;
}

async function api(method, path, body) {
  const headers = { "Content-Type": "application/json" };
  if (state.token) headers["Authorization"] = "Bearer " + state.token;
  let res;
  try {
    res = await fetch(path, { method, headers, body: body !== undefined ? JSON.stringify(body) : undefined });
  } catch (e) {
    throw new Error("Sem conexao com o servidor. Verifique o Wi-Fi.");
  }
  if (res.status === 401) {
    logout(false);
    throw new Error("Sessao expirada. Faca login novamente.");
  }
  if (!res.ok) {
    let detail = "Erro (" + res.status + ")";
    try { detail = (await res.json()).detail || detail; } catch (e) {}
    throw new Error(detail);
  }
  if (res.status === 204) return null;
  const text = await res.text();
  return text ? JSON.parse(text) : null;
}

async function apiBlob(path) {
  const headers = {};
  if (state.token) headers["Authorization"] = "Bearer " + state.token;
  let res;
  try {
    res = await fetch(path, { headers });
  } catch (e) {
    throw new Error("Sem conexao com o servidor. Verifique o Wi-Fi.");
  }
  if (!res.ok) {
    let detail = "Erro (" + res.status + ")";
    try { detail = (await res.json()).detail || detail; } catch (e) {}
    throw new Error(detail);
  }
  return res.blob();
}

function formatDateTime(value) {
  if (!value) return "-";
  const parsed = new Date(String(value).replace(" ", "T"));
  return Number.isNaN(parsed.getTime()) ? value : parsed.toLocaleString("pt-BR");
}

function appRoot() { return document.getElementById("app"); }

function showToast(message, kind) {
  const t = document.createElement("div");
  t.className = "toast" + (kind ? " " + kind : "");
  t.textContent = message;
  document.body.appendChild(t);
  setTimeout(() => t.remove(), 3200);
}

function showModal(innerHtml) {
  const overlay = document.createElement("div");
  overlay.style.cssText = "position:fixed;inset:0;background:rgba(0,0,0,.6);z-index:40;display:flex;align-items:flex-end;justify-content:center;";
  overlay.innerHTML = `<div style="background:var(--bg-panel);width:100%;max-width:480px;border-radius:16px 16px 0 0;padding:18px;max-height:88vh;overflow:auto;">${innerHtml}</div>`;
  overlay.closeModal = () => {
    overlay.dispatchEvent(new Event("modalclose"));
    overlay.remove();
  };
  overlay.addEventListener("click", (e) => { if (e.target === overlay) overlay.closeModal(); });
  document.body.appendChild(overlay);
  return overlay;
}

function topbarHtml(title) {
  return `<div class="topbar">
    <div>
      <h1>🔥 ${escapeHtml(title || "DUDAIR-PDV")}</h1>
      <div class="sub">${escapeHtml(state.user ? state.user.username + " (" + state.user.role + ")" : "")}</div>
    </div>
    <button class="btn btn-neutral btn-sm" id="topbar-logout">Sair</button>
  </div>`;
}

function attachTopbarEvents() {
  const btn = document.getElementById("topbar-logout");
  if (btn) btn.addEventListener("click", () => logout(true));
}

function bottomNavHtml(active) {
  if (state.user && state.user.role === "cozinha") {
    return `<div class="bottom-nav">
      <button data-nav="cozinha" class="${active === "cozinha" ? "active" : ""}">🍳 Cozinha</button>
    </div>`;
  }
  return `<div class="bottom-nav">
    <button data-nav="comandas" class="${active === "comandas" ? "active" : ""}">📋 Comandas</button>
  </div>`;
}

function attachBottomNavEvents() {
  document.querySelectorAll("[data-nav]").forEach((el) => {
    el.addEventListener("click", () => {
      const nav = el.dataset.nav;
      if (nav === "comandas") { state.view = "comandas"; renderCurrentView(); }
      if (nav === "cozinha") { state.view = "cozinha"; renderCurrentView(); }
    });
  });
}

function addFab(root, label, onClick) {
  const fab = document.createElement("button");
  fab.className = "fab";
  fab.textContent = label;
  fab.addEventListener("click", onClick);
  root.appendChild(fab);
}

// ------------------------------------------------------------------ AUTH

async function doLogin(username, password) {
  try {
    const data = await api("POST", "/api/auth/login", { username, password });
    state.token = data.token;
    state.user = data.user;
    localStorage.setItem("dudair_token", state.token);
    localStorage.setItem("dudair_user", JSON.stringify(state.user));
    connectWs();
    goHome();
  } catch (e) {
    const err = document.getElementById("login-error");
    if (err) err.textContent = e.message;
  }
}

function goHome() {
  state.view = state.user && state.user.role === "cozinha" ? "cozinha" : "comandas";
  renderCurrentView();
}

function logout(showLoginScreen) {
  state.token = null;
  state.user = null;
  localStorage.removeItem("dudair_token");
  localStorage.removeItem("dudair_user");
  if (state.ws) { try { state.ws.close(); } catch (e) {} state.ws = null; }
  if (showLoginScreen) {
    state.view = "login";
    renderCurrentView();
  }
}

// ------------------------------------------------------------------ WEBSOCKET

function connectWs() {
  if (state.ws) { try { state.ws.close(); } catch (e) {} }
  const proto = location.protocol === "https:" ? "wss" : "ws";
  const ws = new WebSocket(`${proto}://${location.host}/ws?token=${encodeURIComponent(state.token)}`);
  ws.onmessage = (ev) => {
    try {
      const msg = JSON.parse(ev.data);
      handleWsEvent(msg);
    } catch (e) {}
  };
  ws.onclose = () => { if (state.token) setTimeout(connectWs, 2000); };
  ws.onerror = () => {};
  state.ws = ws;
}

const REFRESH_EVENTS = new Set([
  "command.created", "command.updated", "command.closed", "command.access_changed",
  "cash.opened", "cash.movement", "cash.closed",
  "kitchen.updated", "product.changed",
]);

function handleWsEvent(msg) {
  if (!REFRESH_EVENTS.has(msg.event)) return;
  renderCurrentView();
}

// ------------------------------------------------------------------ LOGIN VIEW

async function renderLogin() {
  const root = appRoot();
  let establishment = "Espetinho DU'DAIR";
  try {
    const s = await api("GET", "/api/settings/public");
    establishment = s.establishment_name || establishment;
  } catch (e) {}

  root.innerHTML = `
    <div class="login-wrap">
      <div class="login-card">
        <div class="flame">🔥</div>
        <h2>${escapeHtml(establishment)}</h2>
        <p>Comandas em tempo real - garcom / cozinha</p>
        <input id="login-user" placeholder="Usuario" autocomplete="username" />
        <input id="login-pass" placeholder="Senha" type="password" autocomplete="current-password" />
        <div class="error-text" id="login-error"></div>
        <button class="btn btn-primary" id="login-submit">ENTRAR</button>
      </div>
    </div>
  `;
  const submit = () => doLogin(document.getElementById("login-user").value.trim(), document.getElementById("login-pass").value);
  document.getElementById("login-submit").addEventListener("click", submit);
  document.getElementById("login-pass").addEventListener("keydown", (e) => { if (e.key === "Enter") submit(); });
}

// ------------------------------------------------------------------ COMANDAS

function cmdCardHtml(cmd) {
  const who = cmd.customer_name || "Cliente nao informado";
  const table = cmd.table_ref ? ` • ${escapeHtml(cmd.table_ref)}` : "";
  return `<div class="card" data-open-cmd="${cmd.id}">
    <div class="row">
      <strong>Comanda #${String(cmd.number).padStart(4, "0")}</strong>
      <span class="badge badge-${cmd.status}">${STATUS_LABELS[cmd.status] || cmd.status}</span>
    </div>
    <div class="muted">${escapeHtml(who)}${table}</div>
    <div class="row" style="margin-top:8px">
      <span class="muted">${cmd.item_count != null ? cmd.item_count + " item(ns)" : ""}</span>
      <span class="total">${fmt(cmd.total)}</span>
    </div>
  </div>`;
}

async function renderComandas() {
  const root = appRoot();
  root.innerHTML = topbarHtml() + `<div class="content" id="content"><div class="empty-state">Carregando...</div></div>` + bottomNavHtml("comandas");
  attachTopbarEvents();
  attachBottomNavEvents();
  try {
    const commands = await api("GET", "/api/commands/open");
    const content = document.getElementById("content");
    content.innerHTML = commands.length
      ? commands.map(cmdCardHtml).join("")
      : `<div class="empty-state">Nenhuma comanda em aberto.<br>Toque em + para criar uma nova.</div>`;
    content.querySelectorAll("[data-open-cmd]").forEach((el) => {
      el.addEventListener("click", () => { state.currentCommandId = parseInt(el.dataset.openCmd, 10); state.view = "comanda"; renderCurrentView(); });
    });
  } catch (e) {
    showToast(e.message, "error");
  }
  addFab(root, "+", showNewCommandForm);
}

function showNewCommandForm() {
  const overlay = showModal(`
    <h3>Nova comanda</h3>
    <label>Nome do cliente (opcional)</label>
    <input id="nc-name" />
    <label>Mesa / identificacao (opcional)</label>
    <input id="nc-table" />
    <button class="btn btn-primary" id="nc-submit">Criar comanda</button>
  `);
  overlay.querySelector("#nc-submit").addEventListener("click", async () => {
    try {
      const cmd = await api("POST", "/api/commands", {
        customer_name: overlay.querySelector("#nc-name").value,
        table_ref: overlay.querySelector("#nc-table").value,
      });
      overlay.remove();
      state.currentCommandId = cmd.id;
      state.view = "comanda";
      renderCurrentView();
    } catch (e) {
      showToast(e.message, "error");
    }
  });
}

// ------------------------------------------------------------------ DETALHE DA COMANDA

function itemRowHtml(item, editable) {
  return `<div class="item-row">
    <div style="flex:1">
      <div>${escapeHtml(item.product_name)}</div>
      <div class="muted">${fmt(item.unit_price)} / un${item.notes ? " • obs: " + escapeHtml(item.notes) : ""}</div>
    </div>
    <div class="qty-controls">
      <button data-qty-minus="${item.id}" ${editable ? "" : "disabled"}>-</button>
      <span>${item.quantity}</span>
      <button data-qty-plus="${item.id}" ${editable ? "" : "disabled"}>+</button>
    </div>
    <div style="width:64px;text-align:right;font-weight:700;color:var(--gold)">${fmt(item.subtotal)}</div>
    <button class="btn btn-sm btn-danger" data-remove-item="${item.id}" ${editable ? "" : "disabled"} style="margin-left:6px">✕</button>
  </div>`;
}

async function ensureCatalog() {
  if (!state.products.length) state.products = await api("GET", "/api/products");
  if (!state.categories.length) state.categories = await api("GET", "/api/categories");
}

async function renderComandaDetail() {
  const root = appRoot();
  const cmdId = state.currentCommandId;
  root.innerHTML = topbarHtml() + `<div class="content" id="content"><div class="empty-state">Carregando...</div></div>` + bottomNavHtml("comandas");
  attachTopbarEvents();

  let cmd;
  let access = null;
  try {
    cmd = await api("GET", `/api/commands/${cmdId}`);
    if (state.user.role === "admin" || state.user.role === "garcom") {
      access = await api("GET", `/api/commands/${cmdId}/access`);
    }
    await ensureCatalog();
  } catch (e) {
    showToast(e.message, "error");
    state.view = "comandas";
    return renderCurrentView();
  }

  const editable = cmd.status === "aberto" || cmd.status === "aguardando_pagamento";
  const canMoney = state.user.role === "admin" || state.user.role === "caixa";
  const canManageAccess = state.user.role === "admin" || state.user.role === "garcom";

  const content = document.getElementById("content");
  content.innerHTML = `
    <button class="btn btn-neutral btn-sm" id="back-btn" style="width:auto;margin-bottom:10px">⬅ Voltar</button>
    <div class="card">
      <div class="row">
        <strong>Comanda #${String(cmd.number).padStart(4, "0")}</strong>
        <span class="badge badge-${cmd.status}">${STATUS_LABELS[cmd.status] || cmd.status}</span>
      </div>
      <label>Cliente</label>
      <input id="cust-name" value="${escapeHtml(cmd.customer_name || "")}" ${editable ? "" : "disabled"} />
      <label>Mesa / identificacao</label>
      <input id="cust-table" value="${escapeHtml(cmd.table_ref || "")}" ${editable ? "" : "disabled"} />
      <button class="btn btn-neutral btn-sm" id="save-customer">Salvar cliente/mesa</button>
    </div>

    ${canManageAccess ? commandAccessCardHtml(access) : ""}

    <div class="card">
      <strong>Itens</strong>
      <div id="items-list" style="margin-top:8px">${cmd.items.length ? cmd.items.map((i) => itemRowHtml(i, editable)).join("") : '<div class="muted">Nenhum item ainda.</div>'}</div>
      <div class="row" style="margin-top:10px">
        <span class="muted">Subtotal</span><span>${fmt(cmd.subtotal)}</span>
      </div>
      ${cmd.discount ? `<div class="row"><span class="muted">Desconto</span><span>-${fmt(cmd.discount)}</span></div>` : ""}
      <div class="row" style="margin-top:6px"><strong>TOTAL</strong><span class="total">${fmt(cmd.total)}</span></div>
    </div>

    ${editable ? `
    <div class="card">
      <strong>Adicionar produto</strong>
      <div class="search-box">
        <input id="catalog-search" placeholder="Buscar produto..." value="${escapeHtml(state.catalogSearch)}" />
      </div>
      <div class="chips" id="chips"></div>
      <div id="catalog-list"></div>
    </div>` : ""}

    <div class="card">
      <label>Observacao da comanda</label>
      <textarea id="cmd-notes" rows="2">${escapeHtml(cmd.notes || "")}</textarea>
      <button class="btn btn-neutral btn-sm" id="save-notes">Salvar observacao</button>
    </div>

    ${editable ? `
    <div style="display:flex;gap:8px;margin-top:6px">
      <button class="btn btn-danger" id="cancel-cmd">Cancelar comanda</button>
      <button class="btn btn-gold" id="pending-cmd">Marcar fiado</button>
    </div>
    ${canMoney ? '<button class="btn btn-success" id="finalize-cmd" style="margin-top:10px">Finalizar / Pagamento</button>' : '<p class="muted" style="text-align:center;margin-top:10px">Pagamento e feito no caixa.</p>'}
    ` : ""}
  `;

  document.getElementById("back-btn").addEventListener("click", () => { state.view = "comandas"; renderCurrentView(); });

  if (canManageAccess) attachCommandAccessEvents(cmdId, access);

  document.getElementById("save-customer").addEventListener("click", async () => {
    try {
      await api("PUT", `/api/commands/${cmdId}/customer`, {
        customer_name: document.getElementById("cust-name").value,
        table_ref: document.getElementById("cust-table").value,
      });
      showToast("Cliente/mesa atualizado", "success");
    } catch (e) { showToast(e.message, "error"); }
  });

  document.getElementById("save-notes").addEventListener("click", async () => {
    try {
      await api("PUT", `/api/commands/${cmdId}/notes`, { notes: document.getElementById("cmd-notes").value });
      showToast("Observacao salva", "success");
    } catch (e) { showToast(e.message, "error"); }
  });

  content.querySelectorAll("[data-qty-plus]").forEach((el) => {
    el.addEventListener("click", async () => {
      const item = cmd.items.find((i) => i.id === parseInt(el.dataset.qtyPlus, 10));
      await changeQty(item, item.quantity + 1);
    });
  });
  content.querySelectorAll("[data-qty-minus]").forEach((el) => {
    el.addEventListener("click", async () => {
      const item = cmd.items.find((i) => i.id === parseInt(el.dataset.qtyMinus, 10));
      await changeQty(item, item.quantity - 1);
    });
  });
  content.querySelectorAll("[data-remove-item]").forEach((el) => {
    el.addEventListener("click", async () => {
      try {
        await api("DELETE", `/api/commands/items/${el.dataset.removeItem}`);
        renderCurrentView();
      } catch (e) { showToast(e.message, "error"); }
    });
  });

  async function changeQty(item, newQty) {
    try {
      if (newQty <= 0) {
        await api("DELETE", `/api/commands/items/${item.id}`);
      } else {
        await api("PUT", `/api/commands/items/${item.id}/quantity`, { quantity: newQty });
      }
      renderCurrentView();
    } catch (e) { showToast(e.message, "error"); }
  }

  if (editable) {
    renderCatalog(cmdId);
    document.getElementById("catalog-search").addEventListener("input", (e) => {
      state.catalogSearch = e.target.value;
      renderCatalogList(cmdId);
    });
  }

  const cancelBtn = document.getElementById("cancel-cmd");
  if (cancelBtn) cancelBtn.addEventListener("click", async () => {
    if (!confirm("Cancelar esta comanda?")) return;
    try { await api("POST", `/api/commands/${cmdId}/cancel`); state.view = "comandas"; renderCurrentView(); }
    catch (e) { showToast(e.message, "error"); }
  });
  const pendingBtn = document.getElementById("pending-cmd");
  if (pendingBtn) pendingBtn.addEventListener("click", async () => {
    if (!confirm("Marcar esta comanda como fiado/pendente?")) return;
    try { await api("POST", `/api/commands/${cmdId}/pending`); state.view = "comandas"; renderCurrentView(); }
    catch (e) { showToast(e.message, "error"); }
  });
  const finalizeBtn = document.getElementById("finalize-cmd");
  if (finalizeBtn) finalizeBtn.addEventListener("click", () => showToast("Use o caixa no computador para finalizar o pagamento.", ""));
}

function commandAccessCardHtml(access) {
  const labels = { sem_acesso: "Nao gerado", ativo: "Ativo", revogado: "Revogado" };
  const active = access && access.status === "ativo";
  return `<div class="card access-card">
    <div class="row">
      <strong>📱 Acesso do cliente</strong>
      <span class="access-status access-${escapeHtml(access.status)}">${escapeHtml(labels[access.status] || access.status)}</span>
    </div>
    <div class="muted" style="margin-top:8px">
      ${access.created_at ? `Criado em ${escapeHtml(formatDateTime(access.created_at))}` : "Nenhum QR Code foi gerado para esta comanda."}
      ${access.last_regenerated_at ? `<br>Ultima regeneracao: ${escapeHtml(formatDateTime(access.last_regenerated_at))}` : ""}
      ${access.revoked_at ? `<br>Revogado em: ${escapeHtml(formatDateTime(access.revoked_at))}` : ""}
    </div>
    <div class="access-actions">
      ${active ? '<button class="btn btn-neutral btn-sm" id="show-access-qr">Mostrar QR Code</button>' : ""}
      <button class="btn btn-gold btn-sm" id="regenerate-access">${active ? "Gerar novo QR Code" : "Gerar QR Code"}</button>
      ${active ? '<button class="btn btn-danger btn-sm" id="revoke-access">Revogar acesso</button>' : ""}
    </div>
  </div>`;
}

function attachCommandAccessEvents(commandId, access) {
  const showBtn = document.getElementById("show-access-qr");
  if (showBtn) showBtn.addEventListener("click", () => showAccessQr(commandId, access));

  document.getElementById("regenerate-access").addEventListener("click", async () => {
    if (access.status === "ativo" && !confirm("Gerar um novo QR Code? O acesso anterior deixara de funcionar imediatamente.")) return;
    try {
      const generated = await api("POST", `/api/commands/${commandId}/access/regenerate`);
      await showAccessQr(commandId, generated);
      renderCurrentView();
    } catch (e) { showToast(e.message, "error"); }
  });

  const revokeBtn = document.getElementById("revoke-access");
  if (revokeBtn) revokeBtn.addEventListener("click", async () => {
    if (!confirm("Revogar o acesso digital atual? A comanda e os pedidos serao mantidos.")) return;
    try {
      await api("POST", `/api/commands/${commandId}/access/revoke`);
      showToast("Acesso revogado. A comanda continua aberta.", "success");
      renderCurrentView();
    } catch (e) { showToast(e.message, "error"); }
  });
}

async function showAccessQr(commandId, access) {
  const overlay = showModal(`
    <h3 style="margin-top:0">QR Code da comanda</h3>
    <p class="muted">Escaneie para abrir a mesma comanda. Nenhuma nova comanda sera criada.</p>
    <div class="qr-wrap"><div class="muted" id="qr-loading">Gerando QR Code...</div><img class="qr-image" id="access-qr-image" alt="QR Code de acesso da comanda" /></div>
    <label>Link de acesso</label>
    <input id="access-link" value="${escapeHtml(access.access_url || "")}" readonly />
    <button class="btn btn-neutral" id="copy-access-link">Copiar link</button>
    <button class="btn btn-primary" id="close-access-modal" style="margin-top:8px">Fechar</button>
  `);
  overlay.querySelector("#close-access-modal").addEventListener("click", () => overlay.closeModal());
  overlay.querySelector("#copy-access-link").addEventListener("click", async () => {
    try {
      await navigator.clipboard.writeText(access.access_url);
      showToast("Link copiado", "success");
    } catch (e) { showToast("Nao foi possivel copiar automaticamente.", "error"); }
  });
  try {
    const blob = await apiBlob(`/api/commands/${commandId}/access/qr`);
    const url = URL.createObjectURL(blob);
    const image = overlay.querySelector("#access-qr-image");
    image.src = url;
    image.onload = () => overlay.querySelector("#qr-loading").remove();
    overlay.addEventListener("modalclose", () => URL.revokeObjectURL(url), { once: true });
  } catch (e) {
    overlay.querySelector("#qr-loading").textContent = e.message;
  }
}

async function renderCustomerAccess() {
  const root = appRoot();
  root.innerHTML = `<div class="customer-shell"><div class="empty-state">Carregando comanda...</div></div>`;
  try {
    const command = await api("GET", `/api/customer/command?token=${encodeURIComponent(state.customerAccessToken)}`);
    root.innerHTML = `<div class="customer-shell">
      <div class="customer-header">
        <div class="flame">🔥</div>
        <div><h1>${escapeHtml(command.establishment_name)}</h1><div class="muted">Acompanhamento da comanda</div></div>
      </div>
      <div class="card">
        <div class="row"><strong>Comanda #${String(command.number).padStart(4, "0")}</strong><span class="badge badge-${command.status}">${STATUS_LABELS[command.status] || command.status}</span></div>
        <div class="muted" style="margin-top:6px">${escapeHtml(command.customer_name || "Cliente")}${command.table_ref ? " • " + escapeHtml(command.table_ref) : ""}</div>
      </div>
      <div class="card">
        <strong>Itens da comanda</strong>
        <div style="margin-top:10px">${command.items.length ? command.items.map((item) => `<div class="item-row"><div><strong>${item.quantity}x ${escapeHtml(item.product_name)}</strong>${item.notes ? `<div class="muted">${escapeHtml(item.notes)}</div>` : ""}</div><strong>${fmt(item.subtotal)}</strong></div>`).join("") : '<div class="muted">Nenhum item adicionado ainda.</div>'}</div>
        <div class="row" style="margin-top:12px"><span class="muted">Subtotal</span><span>${fmt(command.subtotal)}</span></div>
        ${command.discount ? `<div class="row"><span class="muted">Desconto</span><span>-${fmt(command.discount)}</span></div>` : ""}
        <div class="row" style="margin-top:8px"><strong>TOTAL</strong><span class="total">${fmt(command.total)}</span></div>
      </div>
      <button class="btn btn-primary" id="refresh-customer-command">Atualizar comanda</button>
      <p class="muted" style="text-align:center">Este acesso vale somente para esta comanda.</p>
    </div>`;
    document.getElementById("refresh-customer-command").addEventListener("click", renderCustomerAccess);
  } catch (e) {
    root.innerHTML = `<div class="login-wrap"><div class="login-card"><div class="flame">🔒</div><h2>Acesso indisponivel</h2><p>${escapeHtml(e.message)}</p><button class="btn btn-neutral" id="staff-login">Acesso do estabelecimento</button></div></div>`;
    document.getElementById("staff-login").addEventListener("click", () => {
      history.replaceState({}, "", location.pathname);
      state.customerAccessToken = null;
      renderCurrentView();
    });
  }
}

function renderCatalog(cmdId) {
  const chips = document.getElementById("chips");
  const cats = ["Todas", ...state.categories.map((c) => c.name)];
  chips.innerHTML = cats.map((name) => `<div class="chip ${((!state.catalogCategory && name === "Todas") || state.catalogCategory === name) ? "active" : ""}" data-cat="${escapeHtml(name)}">${escapeHtml(name)}</div>`).join("");
  chips.querySelectorAll("[data-cat]").forEach((el) => {
    el.addEventListener("click", () => {
      state.catalogCategory = el.dataset.cat === "Todas" ? null : el.dataset.cat;
      renderCatalog(cmdId);
      renderCatalogList(cmdId);
    });
  });
  renderCatalogList(cmdId);
}

function renderCatalogList(cmdId) {
  const list = document.getElementById("catalog-list");
  const search = state.catalogSearch.toLowerCase();
  const filtered = state.products.filter((p) => {
    const matchesSearch = !search || p.name.toLowerCase().includes(search);
    const matchesCat = !state.catalogCategory || p.category_name === state.catalogCategory;
    return matchesSearch && matchesCat;
  });
  list.innerHTML = filtered.map((p) => `
    <div class="item-row">
      <div style="flex:1">
        <div>${escapeHtml(p.name)}</div>
        <div class="muted">${fmt(p.price)}</div>
      </div>
      <button class="btn btn-primary btn-sm" data-add-product="${p.id}">+ Adicionar</button>
    </div>
  `).join("") || '<div class="muted">Nenhum produto encontrado.</div>';
  list.querySelectorAll("[data-add-product]").forEach((el) => {
    el.addEventListener("click", async () => {
      try {
        await api("POST", `/api/commands/${cmdId}/items`, { product_id: parseInt(el.dataset.addProduct, 10), quantity: 1 });
        renderCurrentView();
      } catch (e) { showToast(e.message, "error"); }
    });
  });
}

// ------------------------------------------------------------------ COZINHA

function kitchenItemHtml(item) {
  return `<div class="card" data-kitchen-item="${item.id}" data-status="${item.kitchen_status}">
    <div class="row">
      <strong>Comanda #${String(item.command_number).padStart(4, "0")}${item.table_ref ? " • " + escapeHtml(item.table_ref) : ""}</strong>
      <span class="badge badge-kitchen-${item.kitchen_status}">${KITCHEN_LABELS[item.kitchen_status]}</span>
    </div>
    <div style="margin-top:6px;font-size:15px">${item.quantity}x ${escapeHtml(item.product_name)}</div>
    ${item.notes ? `<div class="muted">obs: ${escapeHtml(item.notes)}</div>` : ""}
    <button class="btn btn-gold btn-sm" style="margin-top:8px;width:100%" data-advance="${item.id}">
      Avancar para "${KITCHEN_LABELS[KITCHEN_NEXT[item.kitchen_status]]}"
    </button>
  </div>`;
}

async function renderKitchen() {
  const root = appRoot();
  root.innerHTML = topbarHtml() + `<div class="content" id="content"><div class="empty-state">Carregando...</div></div>` + bottomNavHtml("cozinha");
  attachTopbarEvents();
  attachBottomNavEvents();
  try {
    const items = await api("GET", "/api/kitchen/queue");
    const content = document.getElementById("content");
    content.innerHTML = items.length ? items.map(kitchenItemHtml).join("") : `<div class="empty-state">Nenhum pedido pendente. 🎉</div>`;
    content.querySelectorAll("[data-advance]").forEach((el) => {
      el.addEventListener("click", async () => {
        const card = el.closest("[data-kitchen-item]");
        const next = KITCHEN_NEXT[card.dataset.status];
        try {
          await api("PUT", `/api/commands/items/${el.dataset.advance}/kitchen-status`, { status: next });
          renderCurrentView();
        } catch (e) { showToast(e.message, "error"); }
      });
    });
  } catch (e) {
    showToast(e.message, "error");
  }
}

// ------------------------------------------------------------------ ROUTER

function renderCurrentView() {
  if (state.customerAccessToken) return renderCustomerAccess();
  if (!state.token || !state.user) { state.view = "login"; return renderLogin(); }
  if (state.view === "comandas") return renderComandas();
  if (state.view === "comanda") return renderComandaDetail();
  if (state.view === "cozinha") return renderKitchen();
  return renderLogin();
}

// ------------------------------------------------------------------ BOOT

(async function boot() {
  if ("serviceWorker" in navigator) {
    navigator.serviceWorker.register("sw.js").catch(() => {});
  }
  if (state.customerAccessToken) {
    renderCustomerAccess();
    return;
  }
  if (state.token) {
    try {
      state.user = await api("GET", "/api/auth/me");
      connectWs();
      goHome();
      return;
    } catch (e) {
      logout(false);
    }
  }
  renderCurrentView();
})();
