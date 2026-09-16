import React, { useCallback, useEffect, useMemo, useState } from "react";
import {
  getProfile,
  isSupabaseConfigured,
  normalizeLogin,
  roleCanEditOrders,
  roleCanManageAdmin,
  roleCanManageMoney,
  supabase,
} from "./lib/supabase";
import {
  COMMAND_STATUS,
  PAYMENT_LABELS,
  ROLE_LABELS,
  currency,
  dateTime,
  parseCurrency,
  todayISO,
} from "./lib/format";
import { buildPixPayload, pixQrDataUrl } from "./lib/pix";

const REALTIME_TABLES = [
  "settings",
  "categories",
  "products",
  "cash_sessions",
  "cash_movements",
  "commands",
  "command_items",
  "payments",
  "profiles",
];

const EMPTY_FORM = {
  name: "",
  category_id: "",
  price: "",
  cost: "",
  track_stock: true,
  stock_quantity: "",
  low_stock_threshold: "5",
  notes: "",
  active: true,
};

const DEFAULT_USER_FORM = {
  username: "",
  fullName: "",
  password: "",
  role: "atendente",
  active: true,
};

function useOnlineStatus() {
  const [online, setOnline] = useState(navigator.onLine);
  useEffect(() => {
    const on = () => setOnline(true);
    const off = () => setOnline(false);
    window.addEventListener("online", on);
    window.addEventListener("offline", off);
    return () => {
      window.removeEventListener("online", on);
      window.removeEventListener("offline", off);
    };
  }, []);
  return online;
}

function useToast() {
  const [toast, setToast] = useState(null);
  const show = useCallback((message, type = "info") => {
    setToast({ message, type, id: Date.now() });
  }, []);
  useEffect(() => {
    if (!toast) return undefined;
    const timer = setTimeout(() => setToast(null), 3600);
    return () => clearTimeout(timer);
  }, [toast]);
  return { toast, show };
}

async function unwrap(query) {
  const { data, error } = await query;
  if (error) throw error;
  return data;
}

function settingsValue(settings, key, fallback = "") {
  return settings.find((item) => item.key === key)?.value ?? fallback;
}

function App() {
  const online = useOnlineStatus();
  const { toast, show } = useToast();
  const [session, setSession] = useState(null);
  const [profile, setProfile] = useState(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [view, setView] = useState("dashboard");
  const [selectedCommandId, setSelectedCommandId] = useState(null);
  const [settings, setSettings] = useState([]);
  const [categories, setCategories] = useState([]);
  const [products, setProducts] = useState([]);
  const [commands, setCommands] = useState([]);
  const [cashSession, setCashSession] = useState(null);
  const [dashboard, setDashboard] = useState(null);
  const [profiles, setProfiles] = useState([]);

  const canMoney = roleCanManageMoney(profile?.role);
  const canAdmin = roleCanManageAdmin(profile?.role);
  const canOrders = roleCanEditOrders(profile?.role);

  const refreshAll = useCallback(async () => {
    if (!supabase || !session) return;
    const [
      settingsData,
      categoriesData,
      productsData,
      commandsData,
      cashData,
      dashboardData,
      profilesData,
    ] = await Promise.all([
      unwrap(supabase.from("settings").select("*").order("key")),
      unwrap(supabase.from("categories").select("*").order("name")),
      unwrap(supabase.from("products").select("*, categories(name)").order("name")),
      unwrap(
        supabase
          .from("commands")
          .select("*, command_items(*), payments(*)")
          .in("status", ["aberto", "aguardando_pagamento", "fiado"])
          .order("opened_at", { ascending: false })
      ),
      unwrap(supabase.from("cash_sessions").select("*").eq("status", "aberto").maybeSingle()),
      unwrap(supabase.rpc("get_dashboard_summary")),
      unwrap(supabase.from("profiles").select("*").order("username")),
    ]);
    setSettings(settingsData || []);
    setCategories(categoriesData || []);
    setProducts(productsData || []);
    setCommands(commandsData || []);
    setCashSession(cashData || null);
    setDashboard(dashboardData || null);
    setProfiles(profilesData || []);
  }, [session]);

  useEffect(() => {
    if (!isSupabaseConfigured) {
      setLoading(false);
      return;
    }
    let mounted = true;
    supabase.auth.getSession().then(async ({ data }) => {
      if (!mounted) return;
      setSession(data.session);
      if (data.session?.user) {
        setProfile(await getProfile(data.session.user.id));
      }
      setLoading(false);
    });
    const { data: subscription } = supabase.auth.onAuthStateChange(async (_event, nextSession) => {
      setSession(nextSession);
      setProfile(nextSession?.user ? await getProfile(nextSession.user.id) : null);
      if (!nextSession) {
        setCommands([]);
        setProducts([]);
        setCashSession(null);
      }
    });
    return () => {
      mounted = false;
      subscription.subscription.unsubscribe();
    };
  }, []);

  useEffect(() => {
    if (!session) return;
    refreshAll().catch((error) => show(error.message, "error"));
  }, [session, refreshAll, show]);

  useEffect(() => {
    if (!session || !supabase) return undefined;
    const channel = supabase.channel("dudair-cloud-sync");
    REALTIME_TABLES.forEach((table) => {
      channel.on(
        "postgres_changes",
        { event: "*", schema: "public", table },
        () => refreshAll().catch((error) => show(error.message, "error"))
      );
    });
    channel.subscribe();
    return () => {
      supabase.removeChannel(channel);
    };
  }, [session, refreshAll, show]);

  const selectedCommand = useMemo(
    () => commands.find((command) => command.id === selectedCommandId),
    [commands, selectedCommandId]
  );

  async function run(action, successMessage) {
    setBusy(true);
    try {
      const result = await action();
      await refreshAll();
      if (successMessage) show(successMessage, "success");
      return result;
    } catch (error) {
      show(error.message, "error");
      return null;
    } finally {
      setBusy(false);
    }
  }

  if (!isSupabaseConfigured) return <SetupScreen />;
  if (loading) return <ShellFrame><div className="empty">Carregando...</div></ShellFrame>;
  if (!session || !profile) return <LoginScreen show={show} />;

  return (
    <ShellFrame toast={toast} online={online}>
      <aside className="sidebar">
        <div className="brand">🔥 DU'DAIR PDV</div>
        <div className="muted userline">
          {profile.username} - {ROLE_LABELS[profile.role] || profile.role}
        </div>
        <NavButton view={view} id="dashboard" label="Painel" setView={setView} />
        <NavButton view={view} id="commands" label="Comandas" setView={setView} />
        <NavButton view={view} id="cash" label="Caixa" setView={setView} />
        <NavButton view={view} id="products" label="Produtos" setView={setView} />
        {canAdmin && <NavButton view={view} id="reports" label="Relatorios" setView={setView} />}
        {canAdmin && <NavButton view={view} id="settings" label="Configuracoes" setView={setView} />}
        <button className="nav logout" onClick={() => supabase.auth.signOut()}>
          Sair
        </button>
      </aside>

      <main className="main">
        <OfflineBanner online={online} />
        {view === "dashboard" && (
          <Dashboard
            data={dashboard}
            cashSession={cashSession}
            setView={setView}
            canOrders={canOrders}
            canMoney={canMoney}
          />
        )}
        {view === "commands" && !selectedCommand && (
          <CommandsList
            commands={commands}
            canOrders={canOrders}
            setSelectedCommandId={setSelectedCommandId}
            run={run}
          />
        )}
        {view === "commands" && selectedCommand && (
          <CommandDetail
            command={selectedCommand}
            products={products}
            categories={categories}
            settings={settings}
            canMoney={canMoney}
            canOrders={canOrders}
            busy={busy}
            run={run}
            close={() => setSelectedCommandId(null)}
          />
        )}
        {view === "cash" && (
          <CashPanel
            cashSession={cashSession}
            canMoney={canMoney}
            canAdmin={canAdmin}
            run={run}
            show={show}
          />
        )}
        {view === "products" && (
          <ProductsPanel
            products={products}
            categories={categories}
            canAdmin={canAdmin}
            run={run}
          />
        )}
        {view === "reports" && canAdmin && <ReportsPanel />}
        {view === "settings" && canAdmin && (
          <SettingsPanel
            settings={settings}
            profiles={profiles}
            run={run}
            show={show}
          />
        )}
      </main>
    </ShellFrame>
  );
}

function ShellFrame({ children, toast, online }) {
  return (
    <div className="app-frame">
      {children}
      {toast && <div className={`toast ${toast.type}`}>{toast.message}</div>}
      {online === false && <div className="offline-dot">Sem internet</div>}
    </div>
  );
}

function SetupScreen() {
  return (
    <ShellFrame>
      <div className="setup">
        <h1>DU'DAIR PDV Cloud</h1>
        <p>Configure o Supabase antes de iniciar.</p>
        <ol>
          <li>Crie um projeto no Supabase.</li>
          <li>Execute o arquivo <code>supabase/schema.sql</code> no SQL Editor.</li>
          <li>Copie <code>.env.example</code> para <code>.env</code>.</li>
          <li>Preencha <code>VITE_SUPABASE_URL</code> e <code>VITE_SUPABASE_PUBLISHABLE_KEY</code>.</li>
        </ol>
      </div>
    </ShellFrame>
  );
}

function LoginScreen({ show }) {
  const [login, setLogin] = useState("admin");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);

  async function submit(event) {
    event.preventDefault();
    setBusy(true);
    const { error } = await supabase.auth.signInWithPassword({
      email: normalizeLogin(login),
      password,
    });
    setBusy(false);
    if (error) show(error.message, "error");
  }

  return (
    <ShellFrame>
      <div className="login-screen">
        <form className="login-card" onSubmit={submit}>
          <div className="flame">🔥</div>
          <h1>DU'DAIR PDV</h1>
          <p>Comandas e caixa sincronizados em nuvem</p>
          <label>Usuario ou email</label>
          <input value={login} onChange={(event) => setLogin(event.target.value)} autoComplete="username" />
          <label>Senha</label>
          <input
            value={password}
            onChange={(event) => setPassword(event.target.value)}
            type="password"
            autoComplete="current-password"
          />
          <button className="primary" disabled={busy}>
            {busy ? "Entrando..." : "Entrar"}
          </button>
          <small>Para usuario simples, use nome@dudair.local no Supabase Auth.</small>
        </form>
      </div>
    </ShellFrame>
  );
}

function NavButton({ id, view, label, setView }) {
  return (
    <button className={`nav ${view === id ? "active" : ""}`} onClick={() => setView(id)}>
      {label}
    </button>
  );
}

function OfflineBanner({ online }) {
  if (online) return null;
  return (
    <div className="warning">
      Sem internet. Para evitar conflito no caixa, vendas e pagamentos devem esperar a conexao voltar.
    </div>
  );
}

function Dashboard({ data, cashSession, setView, canOrders, canMoney }) {
  return (
    <section>
      <Header title="Painel do dia" subtitle="Resumo sincronizado entre celular e computador" />
      <div className="actions-grid">
        {canOrders && <button className="primary big" onClick={() => setView("commands")}>Nova comanda</button>}
        {canMoney && <button className="success big" onClick={() => setView("cash")}>Caixa</button>}
        <button className="neutral big" onClick={() => setView("products")}>Produtos</button>
      </div>
      <div className="metric-grid">
        <Metric label="Caixa" value={cashSession ? "ABERTO" : "FECHADO"} tone={cashSession ? "good" : "bad"} />
        <Metric label="Total vendido hoje" value={currency(data?.total_vendido_hoje)} />
        <Metric label="Comandas abertas" value={data?.qtd_abertas ?? 0} />
        <Metric label="Finalizadas hoje" value={data?.qtd_finalizadas_hoje ?? 0} />
        <Metric label="Dinheiro" value={currency(data?.total_dinheiro)} />
        <Metric label="Pix" value={currency(data?.total_pix)} />
        <Metric label="Cartao" value={currency(data?.total_cartao)} />
        <Metric label="Fiado hoje" value={data?.qtd_pendentes_hoje ?? 0} />
      </div>
    </section>
  );
}

function Header({ title, subtitle }) {
  return (
    <header className="section-header">
      <div>
        <h1>{title}</h1>
        {subtitle && <p>{subtitle}</p>}
      </div>
    </header>
  );
}

function Metric({ label, value, tone }) {
  return (
    <div className={`metric ${tone || ""}`}>
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}

function CommandsList({ commands, canOrders, setSelectedCommandId, run }) {
  const [customer, setCustomer] = useState("");
  const [table, setTable] = useState("");

  async function createCommand(event) {
    event.preventDefault();
    const created = await run(
      async () => {
        const data = await unwrap(
          supabase.rpc("create_command", {
            p_customer_name: customer,
            p_table_ref: table,
          })
        );
        return data;
      },
      "Comanda criada"
    );
    if (created?.id) {
      setCustomer("");
      setTable("");
      setSelectedCommandId(created.id);
    }
  }

  return (
    <section>
      <Header title="Comandas" subtitle="Todas as comandas abertas, atualizadas em tempo real" />
      {canOrders && (
        <form className="quick-form" onSubmit={createCommand}>
          <input placeholder="Cliente" value={customer} onChange={(event) => setCustomer(event.target.value)} />
          <input placeholder="Mesa/identificacao" value={table} onChange={(event) => setTable(event.target.value)} />
          <button className="primary">Criar comanda</button>
        </form>
      )}
      <div className="cards-grid">
        {commands.map((command) => (
          <button className="command-card" key={command.id} onClick={() => setSelectedCommandId(command.id)}>
            <div className="row">
              <strong>Comanda #{String(command.number).padStart(4, "0")}</strong>
              <StatusBadge status={command.status} />
            </div>
            <p>{command.customer_name || "Cliente nao informado"} {command.table_ref ? `- ${command.table_ref}` : ""}</p>
            <div className="row">
              <span>{command.command_items?.length || 0} item(ns)</span>
              <strong className="total">{currency(command.total)}</strong>
            </div>
          </button>
        ))}
      </div>
      {!commands.length && <div className="empty">Nenhuma comanda aberta.</div>}
    </section>
  );
}

function StatusBadge({ status }) {
  return <span className={`status ${status}`}>{COMMAND_STATUS[status] || status}</span>;
}

function CommandDetail({ command, products, categories, settings, canMoney, canOrders, busy, run, close }) {
  const [search, setSearch] = useState("");
  const [categoryId, setCategoryId] = useState("");
  const [customer, setCustomer] = useState(command.customer_name || "");
  const [tableRef, setTableRef] = useState(command.table_ref || "");
  const [notes, setNotes] = useState(command.notes || "");
  const [discount, setDiscount] = useState(String(command.discount || "0"));
  const [paymentMode, setPaymentMode] = useState(null);

  useEffect(() => {
    setCustomer(command.customer_name || "");
    setTableRef(command.table_ref || "");
    setNotes(command.notes || "");
    setDiscount(String(command.discount || "0"));
  }, [command.id, command.customer_name, command.table_ref, command.notes, command.discount]);

  const editable = canOrders && ["aberto", "aguardando_pagamento"].includes(command.status);
  const filteredProducts = products.filter((product) => {
    const active = product.active;
    const matchesSearch = !search || product.name.toLowerCase().includes(search.toLowerCase());
    const matchesCategory = !categoryId || product.category_id === categoryId;
    return active && matchesSearch && matchesCategory;
  });

  async function saveInfo() {
    await run(
      () =>
        unwrap(
          supabase.rpc("update_command_info", {
            p_command_id: command.id,
            p_customer_name: customer,
            p_table_ref: tableRef,
            p_notes: notes,
          })
        ),
      "Comanda atualizada"
    );
  }

  async function addProduct(productId) {
    await run(
      () =>
        unwrap(
          supabase.rpc("add_command_item", {
            p_command_id: command.id,
            p_product_id: productId,
            p_quantity: 1,
            p_notes: "",
          })
        ),
      "Item adicionado"
    );
  }

  async function changeQuantity(item, quantity) {
    if (quantity <= 0) {
      await run(() => unwrap(supabase.rpc("remove_command_item", { p_item_id: item.id })), "Item removido");
      return;
    }
    await run(
      () =>
        unwrap(
          supabase.rpc("update_command_item_quantity", {
            p_item_id: item.id,
            p_quantity: quantity,
          })
        ),
      "Quantidade atualizada"
    );
  }

  async function applyDiscount() {
    await run(
      () =>
        unwrap(
          supabase.rpc("set_command_discount", {
            p_command_id: command.id,
            p_discount: parseCurrency(discount),
          })
        ),
      "Desconto aplicado"
    );
  }

  async function cancelCommand() {
    if (!window.confirm("Cancelar esta comanda?")) return;
    await run(() => unwrap(supabase.rpc("cancel_command", { p_command_id: command.id })), "Comanda cancelada");
    close();
  }

  async function pendingCommand() {
    if (!window.confirm("Marcar esta comanda como fiado/pendente?")) return;
    await run(() => unwrap(supabase.rpc("mark_command_pending", { p_command_id: command.id })), "Comanda marcada como fiado");
    close();
  }

  return (
    <section>
      <div className="detail-top">
        <button className="neutral small" onClick={close}>Voltar</button>
        <h1>Comanda #{String(command.number).padStart(4, "0")}</h1>
        <StatusBadge status={command.status} />
      </div>
      <div className="detail-layout">
        <div className="panel">
          <h2>Itens</h2>
          <div className="form-grid">
            <input value={customer} onChange={(event) => setCustomer(event.target.value)} placeholder="Cliente" disabled={!editable} />
            <input value={tableRef} onChange={(event) => setTableRef(event.target.value)} placeholder="Mesa/Id" disabled={!editable} />
          </div>
          <textarea value={notes} onChange={(event) => setNotes(event.target.value)} placeholder="Observacao" disabled={!editable} />
          {editable && <button className="neutral" onClick={saveInfo}>Salvar dados</button>}

          <div className="items">
            {(command.command_items || []).map((item) => (
              <div className="item" key={item.id}>
                <div>
                  <strong>{item.product_name}</strong>
                  <small>{currency(item.unit_price)} / un</small>
                </div>
                <div className="qty">
                  <button disabled={!editable} onClick={() => changeQuantity(item, Number(item.quantity) - 1)}>-</button>
                  <span>{Number(item.quantity).toLocaleString("pt-BR")}</span>
                  <button disabled={!editable} onClick={() => changeQuantity(item, Number(item.quantity) + 1)}>+</button>
                </div>
                <strong>{currency(item.subtotal)}</strong>
              </div>
            ))}
          </div>

          <div className="total-box">
            <div><span>Subtotal</span><strong>{currency(command.subtotal)}</strong></div>
            <div className="discount-row">
              <span>Desconto</span>
              <input value={discount} onChange={(event) => setDiscount(event.target.value)} disabled={!editable} />
              {editable && <button className="neutral small" onClick={applyDiscount}>Aplicar</button>}
            </div>
            <div className="grand-total"><span>Total</span><strong>{currency(command.total)}</strong></div>
          </div>

          <div className="button-row">
            {["aberto", "aguardando_pagamento", "fiado"].includes(command.status) && (
              <button className="danger" onClick={cancelCommand}>Cancelar</button>
            )}
            {editable && <button className="gold" onClick={pendingCommand}>Fiado</button>}
            {canMoney && ["aberto", "aguardando_pagamento", "fiado"].includes(command.status) && (
              <button className="success" disabled={busy || !command.command_items?.length} onClick={() => setPaymentMode("dinheiro")}>
                Finalizar
              </button>
            )}
          </div>
        </div>

        <div className="panel">
          <h2>Produtos</h2>
          <div className="form-grid">
            <input placeholder="Buscar produto" value={search} onChange={(event) => setSearch(event.target.value)} />
            <select value={categoryId} onChange={(event) => setCategoryId(event.target.value)}>
              <option value="">Todas</option>
              {categories.map((category) => (
                <option key={category.id} value={category.id}>{category.name}</option>
              ))}
            </select>
          </div>
          <div className="product-list">
            {filteredProducts.map((product) => (
              <button key={product.id} className="product-pick" disabled={!editable} onClick={() => addProduct(product.id)}>
                <span>{product.name}</span>
                <strong>{currency(product.price)}</strong>
                {product.track_stock && <small>Estoque: {Number(product.stock_quantity).toLocaleString("pt-BR")}</small>}
              </button>
            ))}
          </div>
        </div>
      </div>
      {paymentMode && (
        <PaymentModal
          command={command}
          settings={settings}
          initialMode={paymentMode}
          onClose={() => setPaymentMode(null)}
          onPaid={close}
          run={run}
        />
      )}
    </section>
  );
}

function PaymentModal({ command, settings, initialMode, onClose, onPaid, run }) {
  const [mode, setMode] = useState(initialMode || "dinheiro");
  const [received, setReceived] = useState(String(command.total || "0"));
  const [mixed, setMixed] = useState([]);
  const [mixedMethod, setMixedMethod] = useState("pix");
  const [mixedAmount, setMixedAmount] = useState("");
  const [qr, setQr] = useState("");
  const total = Number(command.total || 0);

  useEffect(() => {
    async function loadQr() {
      if (mode !== "pix") return;
      try {
        const payload = buildPixPayload({
          pixKey: settingsValue(settings, "pix_key"),
          merchantName: settingsValue(settings, "pix_receiver_name", "ESPETINHO DUDAIR"),
          merchantCity: settingsValue(settings, "pix_city", "SAO PAULO"),
          description: settingsValue(settings, "pix_description", ""),
          amount: total,
          txid: `CMD${command.number}`,
        });
        setQr(await pixQrDataUrl(payload));
      } catch {
        setQr("");
      }
    }
    loadQr();
  }, [mode, settings, total, command.number]);

  const mixedTotal = mixed.reduce((sum, item) => sum + Number(item.amount), 0);
  const remaining = Math.round((total - mixedTotal) * 100) / 100;

  function addMixed() {
    const amount = parseCurrency(mixedAmount);
    if (amount <= 0) return;
    setMixed([...mixed, { method: mixedMethod, amount, received_amount: mixedMethod === "dinheiro" ? amount : undefined }]);
    setMixedAmount("");
  }

  async function finish() {
    let payments = [];
    if (mode === "dinheiro") {
      payments = [{ method: "dinheiro", amount: total, received_amount: parseCurrency(received) }];
    } else if (mode === "pix") {
      payments = [{ method: "pix", amount: total, pix_confirmed: true }];
    } else if (mode === "debito" || mode === "credito") {
      payments = [{ method: mode, amount: total }];
    } else {
      payments = mixed;
    }
    const result = await run(
      () =>
        unwrap(
          supabase.rpc("finalize_command", {
            p_command_id: command.id,
            p_payments: payments,
          })
        ),
      "Pagamento confirmado"
    );
    if (result) {
      onClose();
      onPaid();
    }
  }

  return (
    <div className="modal-backdrop">
      <div className="modal">
        <div className="row">
          <h2>Finalizar #{String(command.number).padStart(4, "0")}</h2>
          <button className="neutral small" onClick={onClose}>Fechar</button>
        </div>
        <div className="pay-total">{currency(total)}</div>
        <div className="tabs">
          {["dinheiro", "pix", "debito", "credito", "misto"].map((item) => (
            <button key={item} className={mode === item ? "active" : ""} onClick={() => setMode(item)}>
              {item === "misto" ? "Misto" : PAYMENT_LABELS[item]}
            </button>
          ))}
        </div>
        {mode === "dinheiro" && (
          <div>
            <label>Valor recebido</label>
            <input value={received} onChange={(event) => setReceived(event.target.value)} />
            <div className="change">Troco: {currency(parseCurrency(received) - total)}</div>
          </div>
        )}
        {mode === "pix" && (
          <div className="pix-box">
            {qr ? <img src={qr} alt="QR Code Pix" /> : <div className="warning">Configure a chave Pix em Configuracoes.</div>}
            <p>Confirme manualmente no app do banco antes de concluir.</p>
          </div>
        )}
        {mode === "misto" && (
          <div>
            <div className="form-grid">
              <select value={mixedMethod} onChange={(event) => setMixedMethod(event.target.value)}>
                {Object.entries(PAYMENT_LABELS).map(([key, label]) => (
                  <option key={key} value={key}>{label}</option>
                ))}
              </select>
              <input placeholder="Valor" value={mixedAmount} onChange={(event) => setMixedAmount(event.target.value)} />
              <button className="neutral" onClick={addMixed}>Adicionar</button>
            </div>
            {mixed.map((item, index) => (
              <div className="row line" key={`${item.method}-${index}`}>
                <span>{PAYMENT_LABELS[item.method]}</span>
                <strong>{currency(item.amount)}</strong>
              </div>
            ))}
            <div className="change">Restante: {currency(remaining)}</div>
          </div>
        )}
        <button className="success" onClick={finish}>Confirmar pagamento</button>
      </div>
    </div>
  );
}

function CashPanel({ cashSession, canMoney, canAdmin, run }) {
  const [opening, setOpening] = useState("0");
  const [notes, setNotes] = useState("");
  const [summary, setSummary] = useState(null);
  const [movementType, setMovementType] = useState("sangria");
  const [movementAmount, setMovementAmount] = useState("");
  const [movementReason, setMovementReason] = useState("");
  const [counted, setCounted] = useState("");
  const [force, setForce] = useState(false);

  const loadSummary = useCallback(async () => {
    if (!cashSession) {
      setSummary(null);
      return;
    }
    const data = await unwrap(supabase.rpc("get_cash_summary", { p_cash_session_id: cashSession.id }));
    setSummary(data);
    setCounted(String(data.dinheiro_esperado || 0));
  }, [cashSession]);

  useEffect(() => {
    loadSummary().catch(() => undefined);
  }, [loadSummary]);

  async function openCash(event) {
    event.preventDefault();
    await run(
      () =>
        unwrap(
          supabase.rpc("open_cash_session", {
            p_opening_amount: parseCurrency(opening),
            p_notes: notes,
          })
        ),
      "Caixa aberto"
    );
  }

  async function addMovement(event) {
    event.preventDefault();
    await run(
      () =>
        unwrap(
          supabase.rpc("add_cash_movement", {
            p_cash_session_id: cashSession.id,
            p_type: movementType,
            p_amount: parseCurrency(movementAmount),
            p_reason: movementReason,
          })
        ),
      "Movimento registrado"
    );
    setMovementAmount("");
    setMovementReason("");
    await loadSummary();
  }

  async function closeCash() {
    if (!window.confirm("Confirmar fechamento de caixa?")) return;
    await run(
      () =>
        unwrap(
          supabase.rpc("close_cash_session", {
            p_cash_session_id: cashSession.id,
            p_counted_amount: parseCurrency(counted),
            p_close_notes: "",
            p_force: force,
          })
        ),
      "Caixa fechado"
    );
  }

  return (
    <section>
      <Header title="Caixa" subtitle="Um unico caixa aberto para todos os dispositivos" />
      {!cashSession && (
        <div className="panel">
          <h2>Caixa fechado</h2>
          <p>Nenhuma venda pode ser finalizada ate abrir o caixa.</p>
          {canMoney && (
            <form className="quick-form" onSubmit={openCash}>
              <input value={opening} onChange={(event) => setOpening(event.target.value)} placeholder="Fundo inicial" />
              <input value={notes} onChange={(event) => setNotes(event.target.value)} placeholder="Observacao" />
              <button className="success">Abrir caixa</button>
            </form>
          )}
        </div>
      )}
      {cashSession && summary && (
        <div className="panel">
          <div className="row">
            <h2>Caixa aberto desde {dateTime(cashSession.opened_at)}</h2>
            <button className="neutral small" onClick={loadSummary}>Atualizar</button>
          </div>
          <div className="metric-grid">
            <Metric label="Fundo inicial" value={currency(summary.opening_amount)} />
            <Metric label="Total vendido" value={currency(summary.total_vendido)} />
            <Metric label="Dinheiro esperado" value={currency(summary.dinheiro_esperado)} />
            <Metric label="Pix" value={currency(summary.por_forma?.pix)} />
            <Metric label="Cartao debito" value={currency(summary.por_forma?.debito)} />
            <Metric label="Cartao credito" value={currency(summary.por_forma?.credito)} />
            <Metric label="Misto" value={currency(summary.por_forma?.misto)} />
            <Metric label="Comandas abertas" value={summary.qtd_abertas} />
          </div>
          {canMoney && (
            <form className="quick-form" onSubmit={addMovement}>
              <select value={movementType} onChange={(event) => setMovementType(event.target.value)}>
                <option value="sangria">Sangria</option>
                <option value="reforco">Reforco</option>
              </select>
              <input value={movementAmount} onChange={(event) => setMovementAmount(event.target.value)} placeholder="Valor" />
              <input value={movementReason} onChange={(event) => setMovementReason(event.target.value)} placeholder="Motivo" />
              <button className="neutral">Registrar</button>
            </form>
          )}
          {canAdmin && (
            <div className="close-box">
              <label>Dinheiro contado</label>
              <input value={counted} onChange={(event) => setCounted(event.target.value)} />
              <label className="check">
                <input type="checkbox" checked={force} onChange={(event) => setForce(event.target.checked)} />
                Forcar fechamento com comandas abertas
              </label>
              <button className="gold" onClick={closeCash}>Fechar caixa</button>
            </div>
          )}
        </div>
      )}
    </section>
  );
}

function ProductsPanel({ products, categories, canAdmin, run }) {
  const [form, setForm] = useState(EMPTY_FORM);
  const [editing, setEditing] = useState(null);

  function setField(key, value) {
    setForm((current) => ({ ...current, [key]: value }));
  }

  function edit(product) {
    setEditing(product.id);
    setForm({
      name: product.name || "",
      category_id: product.category_id || "",
      price: String(product.price || ""),
      cost: String(product.cost || ""),
      track_stock: Boolean(product.track_stock),
      stock_quantity: String(product.stock_quantity || ""),
      low_stock_threshold: String(product.low_stock_threshold || "5"),
      notes: product.notes || "",
      active: Boolean(product.active),
    });
  }

  async function submit(event) {
    event.preventDefault();
    const payload = {
      name: form.name,
      category_id: form.category_id || null,
      price: parseCurrency(form.price),
      cost: parseCurrency(form.cost),
      track_stock: Boolean(form.track_stock),
      stock_quantity: Number(String(form.stock_quantity || "0").replace(",", ".")),
      low_stock_threshold: Number(String(form.low_stock_threshold || "5").replace(",", ".")),
      notes: form.notes || null,
      active: Boolean(form.active),
    };
    await run(
      () =>
        editing
          ? unwrap(supabase.from("products").update(payload).eq("id", editing))
          : unwrap(supabase.from("products").insert(payload)),
      editing ? "Produto atualizado" : "Produto criado"
    );
    setEditing(null);
    setForm(EMPTY_FORM);
  }

  return (
    <section>
      <Header title="Produtos" subtitle="Catalogo e estoque sincronizados" />
      {canAdmin && (
        <form className="panel product-form" onSubmit={submit}>
          <h2>{editing ? "Editar produto" : "Novo produto"}</h2>
          <div className="form-grid">
            <input placeholder="Nome" value={form.name} onChange={(event) => setField("name", event.target.value)} required />
            <select value={form.category_id} onChange={(event) => setField("category_id", event.target.value)}>
              <option value="">Sem categoria</option>
              {categories.map((category) => <option key={category.id} value={category.id}>{category.name}</option>)}
            </select>
            <input placeholder="Preco" value={form.price} onChange={(event) => setField("price", event.target.value)} required />
            <input placeholder="Custo" value={form.cost} onChange={(event) => setField("cost", event.target.value)} />
            <input placeholder="Estoque" value={form.stock_quantity} onChange={(event) => setField("stock_quantity", event.target.value)} />
            <input placeholder="Alerta baixo estoque" value={form.low_stock_threshold} onChange={(event) => setField("low_stock_threshold", event.target.value)} />
          </div>
          <label className="check">
            <input type="checkbox" checked={form.track_stock} onChange={(event) => setField("track_stock", event.target.checked)} />
            Controlar estoque
          </label>
          <label className="check">
            <input type="checkbox" checked={form.active} onChange={(event) => setField("active", event.target.checked)} />
            Produto ativo
          </label>
          <button className="primary">{editing ? "Salvar alteracoes" : "Criar produto"}</button>
        </form>
      )}
      <div className="table-list">
        {products.map((product) => (
          <div className="table-row" key={product.id}>
            <div>
              <strong>{product.name}</strong>
              <small>{product.categories?.name || "Sem categoria"} {product.active ? "" : "- inativo"}</small>
            </div>
            <span>{currency(product.price)}</span>
            <span>{product.track_stock ? `Estoque ${Number(product.stock_quantity).toLocaleString("pt-BR")}` : "Sem estoque"}</span>
            {canAdmin && <button className="neutral small" onClick={() => edit(product)}>Editar</button>}
          </div>
        ))}
      </div>
    </section>
  );
}

function ReportsPanel() {
  const [from, setFrom] = useState(todayISO());
  const [to, setTo] = useState(todayISO());
  const [rows, setRows] = useState([]);
  const [loading, setLoading] = useState(false);

  async function load() {
    setLoading(true);
    try {
      const data = await unwrap(
        supabase
          .from("commands")
          .select("*, command_items(*), payments(*)")
          .gte("business_date", from)
          .lte("business_date", to)
          .order("opened_at", { ascending: false })
      );
      setRows(data || []);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    load();
  }, []);

  const paid = rows.filter((row) => row.status === "paga");
  const total = paid.reduce((sum, row) => sum + Number(row.total || 0), 0);
  const byPayment = paid.flatMap((row) => row.payments || []).reduce((acc, payment) => {
    acc[payment.method] = (acc[payment.method] || 0) + Number(payment.amount || 0);
    return acc;
  }, {});

  return (
    <section>
      <Header title="Relatorios" subtitle="Vendas e pagamentos do periodo" />
      <div className="quick-form">
        <input type="date" value={from} onChange={(event) => setFrom(event.target.value)} />
        <input type="date" value={to} onChange={(event) => setTo(event.target.value)} />
        <button className="primary" onClick={load}>{loading ? "Carregando..." : "Filtrar"}</button>
      </div>
      <div className="metric-grid">
        <Metric label="Total vendido" value={currency(total)} />
        <Metric label="Comandas pagas" value={paid.length} />
        <Metric label="Canceladas" value={rows.filter((row) => row.status === "cancelada").length} />
        <Metric label="Fiado" value={rows.filter((row) => row.status === "fiado").length} />
        <Metric label="Dinheiro" value={currency(byPayment.dinheiro)} />
        <Metric label="Pix" value={currency(byPayment.pix)} />
        <Metric label="Debito" value={currency(byPayment.debito)} />
        <Metric label="Credito" value={currency(byPayment.credito)} />
      </div>
      <div className="table-list">
        {rows.map((row) => (
          <div className="table-row" key={row.id}>
            <strong>#{String(row.number).padStart(4, "0")}</strong>
            <span>{COMMAND_STATUS[row.status]}</span>
            <span>{row.customer_name || "-"}</span>
            <span>{currency(row.total)}</span>
            <span>{dateTime(row.opened_at)}</span>
          </div>
        ))}
      </div>
    </section>
  );
}

function SettingsPanel({ settings, profiles, run, show }) {
  const [values, setValues] = useState({});
  const [userForm, setUserForm] = useState(DEFAULT_USER_FORM);

  useEffect(() => {
    setValues(Object.fromEntries(settings.map((item) => [item.key, item.value || ""])));
  }, [settings]);

  function setValue(key, value) {
    setValues((current) => ({ ...current, [key]: value }));
  }

  async function saveSettings(event) {
    event.preventDefault();
    const updates = Object.entries(values).map(([key, value]) =>
      unwrap(supabase.from("settings").upsert({ key, value }))
    );
    await run(async () => Promise.all(updates), "Configuracoes salvas");
  }

  async function updateRole(profileId, role) {
    await run(
      () => unwrap(supabase.from("profiles").update({ role }).eq("id", profileId)),
      "Perfil atualizado"
    );
  }

  async function updateActive(profileId, active) {
    await run(
      () => unwrap(supabase.from("profiles").update({ active }).eq("id", profileId)),
      active ? "Usuario ativado" : "Usuario desativado"
    );
  }

  async function saveUser(event) {
    event.preventDefault();
    const payload = {
      username: userForm.username.trim(),
      full_name: userForm.fullName.trim(),
      password: userForm.password,
      role: userForm.role,
      active: userForm.active,
    };

    await run(async () => {
      const { data, error } = await supabase.functions.invoke("admin-upsert-user", {
        body: payload,
      });
      if (error) throw error;
      return data;
    }, "Usuario salvo");

    setUserForm(DEFAULT_USER_FORM);
  }

  return (
    <section>
      <Header title="Configuracoes" subtitle="Estabelecimento, Pix e usuarios" />
      <form className="panel" onSubmit={saveSettings}>
        <h2>Estabelecimento e Pix</h2>
        <label>Nome do estabelecimento</label>
        <input value={values.establishment_name || ""} onChange={(event) => setValue("establishment_name", event.target.value)} />
        <label>Chave Pix</label>
        <input value={values.pix_key || ""} onChange={(event) => setValue("pix_key", event.target.value)} />
        <label>Nome do recebedor</label>
        <input value={values.pix_receiver_name || ""} onChange={(event) => setValue("pix_receiver_name", event.target.value)} />
        <label>Cidade</label>
        <input value={values.pix_city || ""} onChange={(event) => setValue("pix_city", event.target.value)} />
        <label>Descricao Pix</label>
        <input value={values.pix_description || ""} onChange={(event) => setValue("pix_description", event.target.value)} />
        <button className="primary">Salvar configuracoes</button>
      </form>

      <div className="panel">
        <div className="row">
          <h2>Usuarios</h2>
          <span className="pill">Admin controla tudo</span>
        </div>
        <form className="form-grid user-form" onSubmit={saveUser}>
          <div>
            <label>Usuario</label>
            <input
              placeholder="ex: atendente2"
              value={userForm.username}
              onChange={(event) => setUserForm((current) => ({ ...current, username: event.target.value }))}
              required
            />
          </div>
          <div>
            <label>Nome</label>
            <input
              placeholder="Nome completo"
              value={userForm.fullName}
              onChange={(event) => setUserForm((current) => ({ ...current, fullName: event.target.value }))}
            />
          </div>
          <div>
            <label>Senha</label>
            <input
              placeholder="minimo 6 caracteres"
              type="password"
              value={userForm.password}
              onChange={(event) => setUserForm((current) => ({ ...current, password: event.target.value }))}
              required
            />
          </div>
          <div>
            <label>Perfil</label>
            <select
              value={userForm.role}
              onChange={(event) => setUserForm((current) => ({ ...current, role: event.target.value }))}
            >
              {Object.entries(ROLE_LABELS).map(([key, label]) => (
                <option key={key} value={key}>{label}</option>
              ))}
            </select>
          </div>
          <label className="checkline">
            <input
              type="checkbox"
              checked={userForm.active}
              onChange={(event) => setUserForm((current) => ({ ...current, active: event.target.checked }))}
            />
            Ativo
          </label>
          <button className="primary">Criar ou atualizar usuario</button>
          <small>
            Para entrar, use apenas o usuario. Se ele ja existir, o app atualiza perfil, nome e senha.
          </small>
        </form>
        <div className="table-list">
          {profiles.map((item) => (
            <div className="table-row" key={item.id}>
              <div>
                <strong>{item.username}</strong>
                <small>{item.full_name || item.email || (item.active ? "ativo" : "inativo")}</small>
              </div>
              <select value={item.role} onChange={(event) => updateRole(item.id, event.target.value)}>
                {Object.entries(ROLE_LABELS).map(([key, label]) => (
                  <option key={key} value={key}>{label}</option>
                ))}
              </select>
              <select
                value={item.active ? "active" : "inactive"}
                onChange={(event) => updateActive(item.id, event.target.value === "active")}
              >
                <option value="active">Ativo</option>
                <option value="inactive">Inativo</option>
              </select>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}

export default App;
