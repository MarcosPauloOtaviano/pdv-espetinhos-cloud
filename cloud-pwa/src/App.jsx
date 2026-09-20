import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  getProfile,
  isSupabaseConfigured,
  normalizeLogin,
  roleCanEditOrders,
  roleCanManageQueue,
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
import { commandOwner, filterProducts, inventoryValue, isLowStock } from "./lib/admin";
import CustomerAccess from './CustomerAccess';

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
  "service_queue",
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

const QUEUE_LABELS = {
  pedido_digital: "Pedido",
  chamar_garcom: "Chamar garcom",
  solicitar_fechamento: "Solicitar fechamento",
};

const QUEUE_META = {
  pedido_digital: {
    label: "Novo pedido",
    shortLabel: "Pedido",
    tone: "order",
    icon: "🍽",
  },
  chamar_garcom: {
    label: "Chamar atendente",
    shortLabel: "Atendente",
    tone: "waiter",
    icon: "🔔",
  },
  solicitar_fechamento: {
    label: "Fechar comanda",
    shortLabel: "Fechamento",
    tone: "close",
    icon: "✓",
  },
};

function queueMeta(type) {
  return QUEUE_META[type] || {
    label: QUEUE_LABELS[type] || type,
    shortLabel: QUEUE_LABELS[type] || type,
    tone: "other",
    icon: "•",
  };
}

function businessDateLabel(value) {
  if (!value) return "período selecionado";
  const [year, month, day] = String(value).split("-").map(Number);
  if (!year || !month || !day) return value;
  return new Intl.DateTimeFormat("pt-BR", {
    day: "2-digit",
    month: "long",
    year: "numeric",
  }).format(new Date(year, month - 1, day, 12));
}

function businessDateStartISO(value) {
  if (!value) return null;
  return new Date(`${value}T00:00:00-03:00`).toISOString();
}

function nextBusinessDate(value) {
  if (!value) return null;
  const date = new Date(`${value}T12:00:00-03:00`);
  date.setUTCDate(date.getUTCDate() + 1);
  return date.toISOString().slice(0, 10);
}

const KITCHEN_STATUS = {
  pendente: "Aguardando aceite",
  preparando: "Em preparo",
  pronto: "Pronto",
  entregue: "Entregue",
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
  const [passwordRecovery, setPasswordRecovery] = useState(false);
  const [busy, setBusy] = useState(false);
  const [view, setView] = useState(() => new URLSearchParams(window.location.search).get("view") || "dashboard");
  const [selectedCommandId, setSelectedCommandId] = useState(null);
  const [settings, setSettings] = useState([]);
  const [categories, setCategories] = useState([]);
  const [products, setProducts] = useState([]);
  const [commands, setCommands] = useState([]);
  const [cashSession, setCashSession] = useState(null);
  const [dashboard, setDashboard] = useState(null);
  const [profiles, setProfiles] = useState([]);
  const [serviceQueue, setServiceQueue] = useState([]);
  const [establishments, setEstablishments] = useState([]);
  const [soundEnabled, setSoundEnabled] = useState(false);
  const [notificationPermission, setNotificationPermission] = useState(
    typeof window !== "undefined" && "Notification" in window ? Notification.permission : "unsupported"
  );
  const audioContextRef = useRef(null);
  const notifiedRequestsRef = useRef(new Set());
  const refreshTimerRef = useRef(null);
  const refreshInFlightRef = useRef(false);
  const refreshQueuedRef = useRef(false);

  const canMoney = roleCanManageMoney(profile?.role);
  const canAdmin = roleCanManageAdmin(profile?.role);
  const canOrders = roleCanEditOrders(profile?.role);
  const canQueue = roleCanManageQueue(profile?.role);
  const isSuperAdmin = profile?.platform_role === "super_admin";

  const playQueueSound = useCallback((requestType = "pedido_digital") => {
    const context = audioContextRef.current;
    if (!context || context.state !== "running") return;
    const oscillator = context.createOscillator();
    const gain = context.createGain();
    oscillator.type = "sine";
    const frequency = requestType === "chamar_garcom" ? 660 : requestType === "solicitar_fechamento" ? 520 : 880;
    oscillator.frequency.setValueAtTime(frequency, context.currentTime);
    gain.gain.setValueAtTime(0.0001, context.currentTime);
    gain.gain.exponentialRampToValueAtTime(0.18, context.currentTime + 0.02);
    gain.gain.exponentialRampToValueAtTime(0.0001, context.currentTime + 0.28);
    oscillator.connect(gain);
    gain.connect(context.destination);
    oscillator.start();
    oscillator.stop(context.currentTime + 0.3);
  }, []);

  async function enableSound() {
    if (typeof window !== "undefined" && "Notification" in window) {
      const permission = Notification.permission === "default"
        ? await Notification.requestPermission()
        : Notification.permission;
      setNotificationPermission(permission);
      if (permission === "granted") {
        show("Notificações do celular ativadas", "success");
        return;
      }
      if (permission === "denied") {
        show("Notificações bloqueadas. Libere-as nas configurações do navegador para ouvir o som padrão do celular.", "error");
      }
    }
    const AudioContextClass = window.AudioContext || window.webkitAudioContext;
    if (!AudioContextClass) {
      show("Este navegador não oferece notificações sonoras.", "error");
      return;
    }
    const context = audioContextRef.current || new AudioContextClass();
    audioContextRef.current = context;
    await context.resume();
    setSoundEnabled(true);
    playQueueSound();
    show("Fallback sonoro ativado neste navegador", "success");
  }

  const showSystemNotification = useCallback(async (request, place, meta) => {
    if (typeof window === "undefined" || !("Notification" in window) || Notification.permission !== "granted") {
      return false;
    }
    const body = `${meta.label}${place ? ` · ${place}` : ""}`;
    const options = {
      body,
      icon: "/icons/icon-192.png",
      badge: "/icons/icon-192.png",
      tag: `service-queue-${request.id}`,
      renotify: true,
      requireInteraction: true,
      silent: false,
      data: { url: `${window.location.origin}/?view=queue` },
    };
    try {
      const registration = "serviceWorker" in navigator ? await navigator.serviceWorker.ready : null;
      if (registration?.showNotification) {
        await registration.showNotification("PDV Espetinhos", options);
      } else {
        new Notification("PDV Espetinhos", options);
      }
      return true;
    } catch {
      return false;
    }
  }, []);

  const notifyQueueRequest = useCallback(async (request) => {
    const meta = queueMeta(request.request_type);
    let place = "";
    if (request.command_id) {
      const { data: command } = await supabase
        .from("commands")
        .select("number, customer_name, table_ref")
        .eq("id", request.command_id)
        .maybeSingle();
      if (command) {
        const table = command.table_ref ? `Mesa ${command.table_ref}` : `Comanda #${String(command.number || 0).padStart(4, "0")}`;
        place = `${table}${command.customer_name ? ` · ${command.customer_name}` : ""}`;
      }
    }
    const systemNotificationShown = await showSystemNotification(request, place, meta);
    if (!systemNotificationShown && soundEnabled) playQueueSound(request.request_type);
    show(`${meta.icon} ${place ? `${place} · ` : ""}${meta.label}`, `queue-${meta.tone}`);
  }, [playQueueSound, show, showSystemNotification, soundEnabled]);

  const refreshAll = useCallback(async () => {
    if (!supabase || !session) return;
    const [
      currentProfileData,
      settingsData,
      categoriesData,
      productsData,
      commandsData,
      cashData,
      dashboardData,
      profilesData,
      queueData,
      establishmentsData,
    ] = await Promise.all([
      getProfile(session.user.id),
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
      unwrap(
        supabase
          .from("service_queue")
          .select("*, commands(number, customer_name, table_ref)")
          .in("status", ["pendente", "em_atendimento"])
          .order("requested_at", { ascending: true })
          .order("id", { ascending: true })
      ),
      unwrap(supabase.from("establishments").select("*").order("name")),
    ]);
    setProfile(currentProfileData || null);
    setSettings(settingsData || []);
    setCategories(categoriesData || []);
    setProducts(productsData || []);
    setCommands(commandsData || []);
    setCashSession(cashData || null);
    setDashboard(dashboardData || null);
    setProfiles(profilesData || []);
    setServiceQueue(queueData || []);
    setEstablishments(establishmentsData || []);
  }, [session]);

  useEffect(() => {
    const theme = profile?.establishments;
    if (!theme) return undefined;
    const root = document.documentElement;
    const previous = {
      orange: root.style.getPropertyValue("--orange"),
      orange2: root.style.getPropertyValue("--orange-2"),
      gold: root.style.getPropertyValue("--gold"),
      bg: root.style.getPropertyValue("--bg"),
    };
    root.style.setProperty("--orange", theme.primary_color || "#a85a2a");
    root.style.setProperty("--orange-2", theme.secondary_color || "#6f3f2b");
    root.style.setProperty("--gold", theme.accent_color || "#d79a3a");
    root.style.setProperty("--bg", theme.background_color || "#f6f2ec");
    return () => {
      root.style.setProperty("--orange", previous.orange);
      root.style.setProperty("--orange-2", previous.orange2);
      root.style.setProperty("--gold", previous.gold);
      root.style.setProperty("--bg", previous.bg);
    };
  }, [profile?.establishments]);

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
    const { data: subscription } = supabase.auth.onAuthStateChange(async (event, nextSession) => {
      if (event === "PASSWORD_RECOVERY") setPasswordRecovery(true);
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

  const scheduleRefresh = useCallback((delay = 400) => {
    if (refreshInFlightRef.current) {
      refreshQueuedRef.current = true;
      return;
    }
    if (refreshTimerRef.current) return;
    refreshTimerRef.current = setTimeout(() => {
      refreshTimerRef.current = null;
      refreshInFlightRef.current = true;
      refreshAll()
        .catch((error) => show(error.message, "error"))
        .finally(() => {
          refreshInFlightRef.current = false;
          if (refreshQueuedRef.current) {
            refreshQueuedRef.current = false;
            scheduleRefresh(delay);
          }
        });
    }, delay);
  }, [refreshAll, show]);

  useEffect(() => () => {
    if (refreshTimerRef.current) clearTimeout(refreshTimerRef.current);
  }, []);

  useEffect(() => {
    if (!("serviceWorker" in navigator)) return undefined;
    const onServiceWorkerMessage = (event) => {
      if (event.data?.type === "OPEN_QUEUE") setView("queue");
    };
    navigator.serviceWorker.addEventListener("message", onServiceWorkerMessage);
    return () => navigator.serviceWorker.removeEventListener("message", onServiceWorkerMessage);
  }, []);

  // The financial summary is calculated by Supabase using the Sao Paulo
  // business date. Refresh at the next local midnight so an open dashboard
  // rolls over to zero without requiring a manual reload.
  useEffect(() => {
    if (!session) return undefined;
    let timer;
    const scheduleMidnightRefresh = () => {
      const now = new Date();
      const next = new Date(now);
      next.setHours(24, 0, 3, 0);
      timer = setTimeout(async () => {
        await refreshAll().catch((error) => show(error.message, "error"));
        scheduleMidnightRefresh();
      }, Math.max(1_000, next.getTime() - now.getTime()));
    };
    scheduleMidnightRefresh();
    return () => clearTimeout(timer);
  }, [session, refreshAll, show]);

  useEffect(() => {
    if (!session || !supabase) return undefined;
    if (!profile?.establishment_id) return undefined;
    const channel = supabase.channel(`pdv-sync-${profile.establishment_id}`);
    REALTIME_TABLES.forEach((table) => {
      channel.on(
        "postgres_changes",
        {
          event: "*",
          schema: "public",
          table,
          filter: `establishment_id=eq.${profile.establishment_id}`,
        },
        async (payload) => {
          if (table === "service_queue" && payload.eventType === "INSERT") {
            const requestId = payload.new?.id;
            if (requestId && !notifiedRequestsRef.current.has(requestId)) {
              notifiedRequestsRef.current.add(requestId);
              await notifyQueueRequest(payload.new);
            }
          }
          scheduleRefresh();
        }
      );
    });
    channel.subscribe((status) => {
      if (status === "CHANNEL_ERROR" || status === "TIMED_OUT") {
        show("A conexão em tempo real foi interrompida. O sistema tentará reconectar.", "error");
      }
    });
    return () => {
      supabase.removeChannel(channel);
    };
  }, [session, profile?.establishment_id, scheduleRefresh, show, notifyQueueRequest]);

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
  if (passwordRecovery && session) {
    return <ChangePasswordScreen show={show} onDone={() => setPasswordRecovery(false)} />;
  }
  if (!session || !profile) return <LoginScreen show={show} />;

  return (
    <ShellFrame toast={toast} online={online}>
      <header className="sidebar">
        <div className="brand-lockup">
          <span className="brand-overline">PDV ESPETINHOS</span>
          <div className="brand">{profile.establishments?.name || "PDV Espetinhos"}</div>
        </div>
        <nav className="nav-list" aria-label="Navegação principal">
          <NavButton view={view} id="dashboard" label="Painel" setView={setView} />
          <NavButton view={view} id="commands" label="Comandas" setView={setView} />
          {canQueue && <NavButton view={view} id="queue" label={`Fila (${serviceQueue.filter((item) => item.status === "pendente").length})`} setView={setView} />}
          <NavButton view={view} id="cash" label="Caixa" setView={setView} />
          <NavButton view={view} id="products" label="Estoque" setView={setView} />
          {canAdmin && <NavButton view={view} id="reports" label="Relatórios" setView={setView} />}
          {canAdmin && <NavButton view={view} id="settings" label="Administração" setView={setView} />}
          {isSuperAdmin && <NavButton view={view} id="platform" label="Plataforma" setView={setView} />}
        </nav>
        <div className="account-area">
          <div className="userline">
            <strong>{profile.username}</strong>
            <span>{ROLE_LABELS[profile.role] || profile.role}</span>
          </div>
          <button className="logout" onClick={() => supabase.auth.signOut()}>Sair</button>
        </div>
      </header>

      <main className="main">
        <OfflineBanner online={online} />
        <button className={`sound-toggle ${notificationPermission === "granted" || soundEnabled ? "enabled" : ""}`} onClick={enableSound}>
          {notificationPermission === "granted" ? "Notificações do celular ativas" : soundEnabled ? "Fallback sonoro ativo" : "Ativar som do celular"}
        </button>
        {view === "dashboard" && (
          <Dashboard
            data={dashboard}
            cashSession={cashSession}
            setView={setView}
            canOrders={canOrders}
            canMoney={canMoney}
            canAdmin={canAdmin}
            establishmentName={profile.establishments?.name}
            queuePending={serviceQueue.filter((item) => item.status === "pendente").length}
          />
        )}
        {view === "commands" && !selectedCommand && (
          <CommandsList
            commands={commands}
            profiles={profiles}
            canOrders={canOrders}
            setSelectedCommandId={setSelectedCommandId}
            run={run}
          />
        )}
        {view === "commands" && selectedCommand && (
          <CommandDetail
            command={selectedCommand}
            profiles={profiles}
            products={products}
            categories={categories}
            settings={settings}
            canMoney={canMoney}
            canOrders={canOrders}
            canAdmin={canAdmin}
            canQueue={canQueue}
            queueRequests={serviceQueue.filter((item) => item.command_id === selectedCommand.id)}
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
        {view === "queue" && canQueue && (
          <QueuePanel requests={serviceQueue} profiles={profiles} run={run} />
        )}
        {view === "products" && (
          <ProductsPanel
            products={products}
            categories={categories}
            canAdmin={canAdmin}
            run={run}
          />
        )}
        {view === "reports" && canAdmin && <ReportsPanel profiles={profiles} />}
        {view === "settings" && canAdmin && (
          <SettingsPanel
            settings={settings}
            profiles={profiles}
            establishment={profile.establishments}
            establishmentId={profile.establishment_id}
            run={run}
            show={show}
          />
        )}
        {view === "platform" && isSuperAdmin && (
          <PlatformPanel establishments={establishments} run={run} />
        )}
      </main>
    </ShellFrame>
  );
}

function ShellFrame({ children, toast, online }) {
  return (
    <div className="app-frame">
      {children}
      {toast && <div role="status" aria-live="polite" aria-atomic="true" className={`toast ${toast.type}`}>{toast.message}</div>}
      {online === false && <div className="offline-dot">Sem internet</div>}
    </div>
  );
}

function SetupScreen() {
  return (
    <ShellFrame>
      <div className="setup">
        <h1>PDV Espetinhos</h1>
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
  const [login, setLogin] = useState("");
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

  async function forgotPassword() {
    if (!login.includes("@")) {
      show("Digite o email completo cadastrado para recuperar a senha.", "error");
      return;
    }
    setBusy(true);
    const { error } = await supabase.auth.resetPasswordForEmail(login.trim(), {
      redirectTo: window.location.origin,
    });
    setBusy(false);
    if (error) show(error.message, "error");
    else show("Se o email estiver cadastrado, o link de recuperacao foi enviado.", "success");
  }

  return (
    <ShellFrame>
      <div className="login-screen">
        <div className="login-layout">
          <section className="login-showcase">
            <span className="brand-overline">PDV ESPETINHOS</span>
            <h1>Uma operação mais clara, acolhedora e eficiente.</h1>
            <p>Comandas, fila, estoque e caixa organizados em um só lugar.</p>
            <div className="login-highlights" aria-label="Recursos principais">
              <span>Dados protegidos por estabelecimento</span>
              <span>Atualização em tempo real</span>
              <span>Experiência simples para toda a equipe</span>
            </div>
          </section>
          <form className="login-card" onSubmit={submit}>
            <span className="eyebrow">Acesso da equipe</span>
            <h2>Bem-vindo</h2>
            <p>Entre para acessar o ambiente do seu estabelecimento.</p>
            <label>Usuário ou e-mail</label>
            <input
              value={login}
              onChange={(event) => setLogin(event.target.value)}
              autoComplete="username"
              placeholder="Digite seu usuário ou e-mail"
              autoFocus
            />
            <label>Senha</label>
            <input
              value={password}
              onChange={(event) => setPassword(event.target.value)}
              type="password"
              autoComplete="current-password"
            />
            <button className="primary" disabled={busy}>
              {busy ? "Entrando..." : "Entrar no sistema"}
            </button>
            <button type="button" className="text-action" disabled={busy} onClick={forgotPassword}>Esqueci minha senha</button>
            <small>Use o usuário cadastrado pelo administrador ou seu e-mail de acesso.</small>
          </form>
        </div>
      </div>
    </ShellFrame>
  );
}

function ChangePasswordScreen({ show, onDone }) {
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);

  async function save(event) {
    event.preventDefault();
    setBusy(true);
    const { error } = await supabase.auth.updateUser({ password });
    setBusy(false);
    if (error) show(error.message, "error");
    else {
      show("Senha alterada", "success");
      onDone();
    }
  }

  return (
    <ShellFrame>
      <div className="login-screen">
        <form className="login-card" onSubmit={save}>
          <h1>Nova senha</h1>
          <p>Crie uma senha com pelo menos 8 caracteres.</p>
          <input type="password" minLength="8" value={password} onChange={(event) => setPassword(event.target.value)} required autoFocus />
          <button className="primary" disabled={busy}>{busy ? "Salvando..." : "Salvar nova senha"}</button>
        </form>
      </div>
    </ShellFrame>
  );
}

function NavButton({ id, view, label, setView }) {
  return (
    <button
      className={`nav ${view === id ? "active" : ""}`}
      aria-current={view === id ? "page" : undefined}
      onClick={() => setView(id)}
    >
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

function Dashboard({ data, cashSession, setView, canOrders, canMoney, canAdmin, establishmentName, queuePending }) {
  const businessDate = data?.business_date || todayISO();
  return (
    <section>
      <Header title={establishmentName || "Painel do dia"} subtitle={`Resultados de ${businessDateLabel(businessDate)} · sincronizado entre celular e computador`} />
      <div className="actions-grid">
        {canOrders && <button className="primary big" onClick={() => setView("commands")}><span>Operação</span><strong>Nova comanda</strong></button>}
        {canMoney && <button className="success big" onClick={() => setView("cash")}><span>Financeiro</span><strong>Acessar caixa</strong></button>}
        <button className="neutral big" onClick={() => setView("products")}><span>Catálogo</span><strong>Produtos e estoque</strong></button>
        {canOrders && <button className="neutral big" onClick={() => setView("queue")}><span>Atendimento</span><strong>Ver fila</strong></button>}
      </div>
      <div className="metric-grid">
        <Metric label="Caixa" value={cashSession ? "ABERTO" : "FECHADO"} tone={cashSession ? "good" : "bad"} />
        <Metric label="Total vendido hoje" value={currency(data?.total_vendido_hoje)} />
        <Metric label="Comandas abertas agora" value={data?.qtd_abertas ?? 0} />
        <Metric label="Finalizadas hoje" value={data?.qtd_finalizadas_hoje ?? 0} />
        <Metric label="Dinheiro" value={currency(data?.total_dinheiro)} />
        <Metric label="Pix" value={currency(data?.total_pix)} />
        <Metric label="Cartao" value={currency(data?.total_cartao)} />
        <Metric label="Fila pendente agora" value={queuePending ?? data?.fila_pendente ?? 0} tone={queuePending ? "bad" : "good"} />
      </div>
      <div className="dashboard-period-note">
        <div>
          <span className="eyebrow">Fechamento diário</span>
          <strong>O painel mostra somente o movimento de hoje.</strong>
          <p>Ao virar o dia, os indicadores financeiros começam novamente em zero. O histórico completo continua disponível em Relatórios.</p>
        </div>
        {canAdmin && <button className="neutral" onClick={() => setView("reports")}>Abrir histórico completo</button>}
      </div>
    </section>
  );
}

function Header({ title, subtitle }) {
  return (
    <header className="section-header">
      <div>
        <span className="eyebrow">Central de operação</span>
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

function CommandsList({ commands, profiles, canOrders, setSelectedCommandId, run }) {
  const [customer, setCustomer] = useState("");
  const [table, setTable] = useState("");
  const [ownerId, setOwnerId] = useState("");

  const visibleCommands = ownerId
    ? commands.filter((command) => command.created_by === ownerId)
    : commands;

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
      <div className="command-filters">
        <label>
          Responsavel
          <select value={ownerId} onChange={(event) => setOwnerId(event.target.value)}>
            <option value="">Todas as pessoas</option>
            {profiles.filter((item) => item.active).map((item) => (
              <option key={item.id} value={item.id}>{item.full_name || item.username}</option>
            ))}
          </select>
        </label>
      </div>
      {canOrders && (
        <form className="quick-form" onSubmit={createCommand}>
          <input aria-label="Nome do cliente" placeholder="Cliente" value={customer} onChange={(event) => setCustomer(event.target.value)} />
          <input aria-label="Mesa ou identificação" placeholder="Mesa/identificacao" value={table} onChange={(event) => setTable(event.target.value)} />
          <button className="primary">Criar comanda</button>
        </form>
      )}
      <div className="cards-grid">
        {visibleCommands.map((command) => (
          <button className="command-card" key={command.id} onClick={() => setSelectedCommandId(command.id)}>
            <div className="row">
              <strong>Comanda #{String(command.number).padStart(4, "0")}</strong>
              <StatusBadge status={command.status} />
            </div>
            <p>{command.customer_name || "Cliente nao informado"} {command.table_ref ? `- ${command.table_ref}` : ""}</p>
            <small className="owner-line">Aberta por {commandOwner(command, profiles)}</small>
            <div className="row">
              <span>{command.command_items?.length || 0} item(ns)</span>
              <strong className="total">{currency(command.total)}</strong>
            </div>
          </button>
        ))}
      </div>
      {!visibleCommands.length && <div className="empty">Nenhuma comanda aberta para este filtro.</div>}
    </section>
  );
}

function StatusBadge({ status }) {
  return <span className={`status ${status}`}>{COMMAND_STATUS[status] || status}</span>;
}

function CommandDetail({ command, profiles, products, categories, settings, canMoney, canOrders, canAdmin, canQueue, queueRequests, busy, run, close }) {
  const [search, setSearch] = useState("");
  const [categoryId, setCategoryId] = useState("");
  const [customer, setCustomer] = useState(command.customer_name || "");
  const [tableRef, setTableRef] = useState(command.table_ref || "");
  const [notes, setNotes] = useState(command.notes || "");
  const [discount, setDiscount] = useState(String(command.discount || "0"));
  const [paymentMode, setPaymentMode] = useState(null);
  const [adjustingItem, setAdjustingItem] = useState(null);

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
    const result = await run(() => unwrap(supabase.rpc("cancel_command", { p_command_id: command.id })), "Comanda cancelada");
    if (result !== null) close();
  }

  async function sendOrderToQueue() {
    await run(
      () => unwrap(supabase.rpc("enqueue_service_request", {
        p_command_id: command.id,
        p_request_type: "pedido_digital",
        p_payload: { source: "pdv", command_version: command.version },
        p_idempotency_key: `pdv-${command.id}-${command.version}`,
      })),
      "Pedido enviado para a fila"
    );
  }

  async function claimRequest(requestId) {
    await run(
      () => unwrap(supabase.rpc("claim_service_request", { p_request_id: requestId })),
      "Solicitação aceita e enviada para preparo"
    );
  }

  async function completeRequest(requestId) {
    await run(
      () => unwrap(supabase.rpc("complete_service_request", { p_request_id: requestId })),
      "Solicitação concluída"
    );
  }

  return (
    <section>
      <div className="detail-top">
        <button className="neutral small" onClick={close}>Voltar</button>
        <h1>Comanda #{String(command.number).padStart(4, "0")}</h1>
        <StatusBadge status={command.status} />
      </div>
      <p className="detail-owner">Aberta por <strong>{commandOwner(command, profiles)}</strong> em {dateTime(command.opened_at)}</p>
      {editable && <CustomerAccess commandId={command.id} />}
      {canQueue && queueRequests.length > 0 && (
        <section className="panel command-queue-shortcut" aria-label="Solicitações desta comanda">
          <div className="row">
            <div>
              <span className="eyebrow">Atalho da fila</span>
              <h2>Solicitações desta comanda</h2>
            </div>
            <span className="pill">{queueRequests.length} ativa(s)</span>
          </div>
          <p className="muted">Aceite diretamente aqui quando estiver atendendo esta mesa. A fila geral continua respeitando a ordem de chegada.</p>
          <div className="command-queue-list">
            {queueRequests.map((request) => {
              const meta = queueMeta(request.request_type);
              const active = request.status === "em_atendimento";
              return (
                <div className={`command-queue-row command-queue-${meta.tone}`} key={request.id}>
                  <span className="queue-type-badge"><span aria-hidden="true">{meta.icon}</span>{meta.shortLabel}</span>
                  <div>
                    <strong>{active ? "Em atendimento" : "Aguardando aceite"}</strong>
                    <small>{dateTime(request.requested_at)}</small>
                  </div>
                  {active ? (
                    <button className="success small" onClick={() => completeRequest(request.id)}>Concluir</button>
                  ) : (
                    <button className="primary small" onClick={() => claimRequest(request.id)}>Aceitar agora</button>
                  )}
                </div>
              );
            })}
          </div>
        </section>
      )}
      <div className="detail-layout">
        <div className="panel">
          <h2>Itens</h2>
          <div className="form-grid">
            <input aria-label="Nome do cliente" value={customer} onChange={(event) => setCustomer(event.target.value)} placeholder="Cliente" disabled={!editable} />
            <input aria-label="Mesa ou identificação" value={tableRef} onChange={(event) => setTableRef(event.target.value)} placeholder="Mesa/Id" disabled={!editable} />
          </div>
          <textarea aria-label="Observações da comanda" value={notes} onChange={(event) => setNotes(event.target.value)} placeholder="Observacao" disabled={!editable} />
          {editable && <button className="neutral" onClick={saveInfo}>Salvar dados</button>}

          <div className="items">
            {(command.command_items || []).map((item) => (
              <div className="item" key={item.id}>
                <div>
                  <strong>{item.product_name}</strong>
                  <small>{currency(item.unit_price)} / un · {KITCHEN_STATUS[item.kitchen_status] || item.kitchen_status}</small>
                </div>
                <div className="item-controls">
                  <span>{Number(item.quantity).toLocaleString("pt-BR")} un</span>
                  {canAdmin && editable && <button className="neutral small" onClick={() => setAdjustingItem(item)}>Ajustar</button>}
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
            {editable && (
              <button className="primary" disabled={busy || !command.command_items?.length} onClick={sendOrderToQueue}>
                Enviar pedido para fila
              </button>
            )}
            {["aberto", "aguardando_pagamento", "fiado"].includes(command.status) && (
              <button className="danger" onClick={cancelCommand}>Cancelar</button>
            )}
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
      {adjustingItem && (
        <ItemAdjustmentModal
          item={adjustingItem}
          products={products}
          run={run}
          onClose={() => setAdjustingItem(null)}
        />
      )}
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

function ItemAdjustmentModal({ item, products, run, onClose }) {
  const [productId, setProductId] = useState(item.product_id || "");
  const [quantity, setQuantity] = useState(String(item.quantity || 0));
  const [reason, setReason] = useState("");

  async function save() {
    const parsedQuantity = Number(String(quantity).replace(",", "."));
    if (!Number.isFinite(parsedQuantity) || parsedQuantity < 0) return;
    if (reason.trim().length < 5) return;
    const result = await run(
      () => unwrap(supabase.rpc("admin_adjust_command_item", {
        p_item_id: item.id,
        p_product_id: productId || null,
        p_quantity: parsedQuantity,
        p_reason: reason.trim(),
      })),
      parsedQuantity === 0 ? "Item removido com justificativa" : "Ajuste registrado com justificativa"
    );
    if (result) onClose();
  }

  return (
    <div className="modal-backdrop" role="dialog" aria-modal="true" aria-labelledby="adjust-item-title">
      <div className="modal item-adjustment-modal">
        <div className="row"><h2 id="adjust-item-title">Ajustar item</h2><button className="neutral small" onClick={onClose}>Fechar</button></div>
        <p>Somente administradores podem corrigir um pedido. A justificativa fica registrada no histórico.</p>
        <label>Produto</label>
        <select value={productId} onChange={(event) => setProductId(event.target.value)}>
          {products.filter((product) => product.active || product.id === item.product_id).map((product) => (
            <option key={product.id} value={product.id}>{product.name}</option>
          ))}
        </select>
        <label>Quantidade <small>Use 0 para remover o item.</small></label>
        <input type="number" min="0" max="999" step="1" value={quantity} onChange={(event) => setQuantity(event.target.value)} />
        <label>Justificativa obrigatória</label>
        <textarea maxLength="500" value={reason} onChange={(event) => setReason(event.target.value)} placeholder="Ex.: item lançado errado pelo atendente" />
        <button className={Number(quantity) === 0 ? "danger" : "primary"} disabled={reason.trim().length < 5} onClick={save}>
          {Number(quantity) === 0 ? "Remover e registrar" : "Salvar ajuste"}
        </button>
      </div>
    </div>
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
          merchantName: settingsValue(settings, "pix_receiver_name", "PDV ESPETINHOS"),
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

function QueuePanel({ requests, profiles, run }) {
  const [filter, setFilter] = useState("all");
  const [search, setSearch] = useState("");
  const pending = requests.filter((item) => item.status === "pendente");
  const inProgress = requests.filter((item) => item.status === "em_atendimento");

  const matches = (item) => {
    if (filter !== "all" && item.request_type !== filter) return false;
    const command = item.commands || {};
    const haystack = [
      command.table_ref,
      command.customer_name,
      command.number,
      item.request_type,
      QUEUE_LABELS[item.request_type],
    ].filter(Boolean).join(" ").toLocaleLowerCase();
    return !search.trim() || haystack.includes(search.trim().toLocaleLowerCase());
  };

  const visiblePending = pending.filter(matches);
  const visibleInProgress = inProgress.filter(matches);

  async function claimNext() {
    await run(
      () => unwrap(supabase.rpc("claim_next_service_request")),
      "Próxima solicitação aceita e enviada para preparo"
    );
  }

  async function claimRequest(requestId) {
    await run(
      () => unwrap(supabase.rpc("claim_service_request", { p_request_id: requestId })),
      "Solicitação aceita e enviada para preparo"
    );
  }

  async function complete(requestId) {
    await run(
      () => unwrap(supabase.rpc("complete_service_request", { p_request_id: requestId })),
      "Solicitacao concluida"
    );
  }

  function requestCard(item, index, active = false) {
    const command = item.commands || {};
    const claimedBy = profiles.find((profile) => profile.id === item.claimed_by);
    const meta = queueMeta(item.request_type);
    return (
      <div className={`queue-card queue-card-${meta.tone} ${active ? "active" : ""}`} key={item.id}>
        <div className="queue-position">{active ? "Em atendimento" : `#${index + 1} da fila`}</div>
        <div>
          <span className="queue-type-badge"><span aria-hidden="true">{meta.icon}</span>{meta.label}</span>
          <p>Comanda #{String(command.number || 0).padStart(4, "0")} · {command.customer_name || command.table_ref || "Cliente"}</p>
          <small>Solicitado em {dateTime(item.requested_at)}</small>
          {item.payload?.source === 'customer' && <small>Solicitação pelo celular do cliente</small>}
          {item.payload?.items?.map((line) => <p key={line.id}>{line.quantity} × {line.name}{line.notes ? ` · ${line.notes}` : ''}</p>)}
          {claimedBy && <small>Atendido por {claimedBy.full_name || claimedBy.username}</small>}
        </div>
        <div className="queue-card-actions">
          {active ? <button className="success small" onClick={() => complete(item.id)}>Concluir</button> : <button className="primary small" onClick={() => claimRequest(item.id)}>Atender esta</button>}
        </div>
      </div>
    );
  }

  return (
    <section>
      <Header title="Fila de atendimento" subtitle="Ordem FIFO: ao aceitar um pedido digital, ele entra em preparo e não pode mais ser alterado pelo cliente" />
      <div className="metric-grid inventory-metrics">
        <Metric label="Aguardando" value={pending.length} tone={pending.length ? "bad" : "good"} />
        <Metric label="Em atendimento" value={inProgress.length} />
      </div>
      <div className="panel queue-controls">
        <div className="row queue-controls-heading">
          <div><span className="eyebrow">Visão rápida</span><h2>Encontre qualquer mesa</h2></div>
          <span className="queue-count">{requests.length} ativa(s)</span>
        </div>
        <div className="form-grid">
          <input value={search} onChange={(event) => setSearch(event.target.value)} placeholder="Buscar mesa, comanda ou cliente" aria-label="Buscar na fila" />
          <select value={filter} onChange={(event) => setFilter(event.target.value)} aria-label="Filtrar tipo de solicitação">
            <option value="all">Todos os tipos</option>
            <option value="pedido_digital">🍽 Novo pedido</option>
            <option value="chamar_garcom">🔔 Chamar atendente</option>
            <option value="solicitar_fechamento">✓ Fechar comanda</option>
          </select>
        </div>
        <div className="queue-legend" aria-label="Legenda das cores da fila">
          <span><i className="queue-legend-dot order" />Pedidos</span>
          <span><i className="queue-legend-dot waiter" />Atendente</span>
          <span><i className="queue-legend-dot close" />Fechamento</span>
        </div>
      </div>
      {pending.length > 0 && (
        <button className="primary queue-next" onClick={claimNext}>Aceitar próxima solicitação</button>
      )}
      {visibleInProgress.length > 0 && (
        <div className="queue-section">
          <h2>Em atendimento</h2>
          {visibleInProgress.map((item, index) => requestCard(item, index, true))}
        </div>
      )}
      <div className="queue-section">
        <h2>Aguardando em ordem de chegada</h2>
        {visiblePending.map((item) => requestCard(item, pending.indexOf(item)))}
        {!visiblePending.length && <div className="empty">{pending.length ? "Nenhuma solicitação corresponde ao filtro." : "A fila está vazia."}</div>}
      </div>
    </section>
  );
}

function ProductsPanel({ products, categories, canAdmin, run }) {
  const [form, setForm] = useState(EMPTY_FORM);
  const [editing, setEditing] = useState(null);
  const [search, setSearch] = useState("");
  const [categoryFilter, setCategoryFilter] = useState("");
  const [showInactive, setShowInactive] = useState(false);
  const [categoryName, setCategoryName] = useState("");

  const visibleProducts = filterProducts(products, {
    search,
    categoryId: categoryFilter,
    showInactive,
  });
  const lowStock = products.filter((product) => product.active && isLowStock(product));

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

  async function createCategory(event) {
    event.preventDefault();
    const name = categoryName.trim();
    if (!name) return;
    const result = await run(
      () => unwrap(supabase.from("categories").insert({ name })),
      "Categoria criada"
    );
    if (result !== null) setCategoryName("");
  }

  async function toggleActive(product) {
    await run(
      () => unwrap(supabase.from("products").update({ active: !product.active }).eq("id", product.id)),
      product.active ? "Produto desativado" : "Produto reativado"
    );
  }

  function cancelEdit() {
    setEditing(null);
    setForm(EMPTY_FORM);
  }

  return (
    <section>
      <Header title="Estoque e produtos" subtitle="Catalogo, custos e quantidades sincronizados" />
      <div className="metric-grid inventory-metrics">
        <Metric label="Produtos ativos" value={products.filter((product) => product.active).length} />
        <Metric label="Estoque baixo" value={lowStock.length} tone={lowStock.length ? "bad" : "good"} />
        <Metric label="Valor em estoque" value={currency(inventoryValue(products))} />
        <Metric label="Categorias" value={categories.length} />
      </div>
      {canAdmin && (
        <>
          <form className="panel category-form" onSubmit={createCategory}>
            <h2>Categorias</h2>
            <div className="quick-form">
              <input placeholder="Nova categoria" value={categoryName} onChange={(event) => setCategoryName(event.target.value)} />
              <button className="neutral">Criar categoria</button>
            </div>
          </form>
          <form className="panel product-form" onSubmit={submit}>
            <div className="row">
              <h2>{editing ? "Editar produto" : "Novo produto"}</h2>
              {editing && <button type="button" className="neutral small" onClick={cancelEdit}>Cancelar edicao</button>}
            </div>
            <div className="form-grid">
              <div><label>Nome</label><input placeholder="Nome" value={form.name} onChange={(event) => setField("name", event.target.value)} required /></div>
              <div><label>Categoria</label><select value={form.category_id} onChange={(event) => setField("category_id", event.target.value)}>
                <option value="">Sem categoria</option>
                {categories.map((category) => <option key={category.id} value={category.id}>{category.name}</option>)}
              </select></div>
              <div><label>Preco de venda</label><input placeholder="0,00" value={form.price} onChange={(event) => setField("price", event.target.value)} required /></div>
              <div><label>Custo</label><input placeholder="0,00" value={form.cost} onChange={(event) => setField("cost", event.target.value)} /></div>
              <div><label>Quantidade em estoque</label><input placeholder="0" value={form.stock_quantity} onChange={(event) => setField("stock_quantity", event.target.value)} /></div>
              <div><label>Alerta de estoque baixo</label><input placeholder="5" value={form.low_stock_threshold} onChange={(event) => setField("low_stock_threshold", event.target.value)} /></div>
            </div>
            <label>Observacoes</label>
            <textarea placeholder="Observacoes internas do produto" value={form.notes} onChange={(event) => setField("notes", event.target.value)} />
            <div className="button-row checks-row">
              <label className="check"><input type="checkbox" checked={form.track_stock} onChange={(event) => setField("track_stock", event.target.checked)} />Controlar estoque</label>
              <label className="check"><input type="checkbox" checked={form.active} onChange={(event) => setField("active", event.target.checked)} />Produto ativo</label>
            </div>
            <button className="primary">{editing ? "Salvar alteracoes" : "Criar produto"}</button>
          </form>
        </>
      )}
      <div className="panel inventory-filters">
        <div className="form-grid">
          <div><label>Buscar</label><input placeholder="Nome, categoria ou observacao" value={search} onChange={(event) => setSearch(event.target.value)} /></div>
          <div><label>Categoria</label><select value={categoryFilter} onChange={(event) => setCategoryFilter(event.target.value)}>
            <option value="">Todas</option>
            {categories.map((category) => <option key={category.id} value={category.id}>{category.name}</option>)}
          </select></div>
          <label className="checkline"><input type="checkbox" checked={showInactive} onChange={(event) => setShowInactive(event.target.checked)} />Mostrar inativos</label>
        </div>
      </div>
      <div className="table-list">
        {visibleProducts.map((product) => (
          <div className={`table-row inventory-row ${isLowStock(product) ? "low-stock" : ""}`} key={product.id}>
            <div>
              <strong>{product.name}</strong>
              <small>{product.categories?.name || "Sem categoria"} {!product.active && "- inativo"}</small>
              {product.notes && <small>{product.notes}</small>}
            </div>
            <div><small>Venda / custo</small><span>{currency(product.price)} / {currency(product.cost)}</span></div>
            <div><small>Estoque</small><strong>{product.track_stock ? Number(product.stock_quantity).toLocaleString("pt-BR") : "Nao controlado"}</strong></div>
            {isLowStock(product) && <span className="stock-alert">Estoque baixo</span>}
            {canAdmin && <div className="button-row inventory-actions">
              <button className="neutral small" onClick={() => edit(product)}>Editar</button>
              <button className={product.active ? "danger small" : "success small"} onClick={() => toggleActive(product)}>{product.active ? "Desativar" : "Reativar"}</button>
            </div>}
          </div>
        ))}
      </div>
      {!visibleProducts.length && <div className="empty">Nenhum produto encontrado.</div>}
    </section>
  );
}

function ReportsPanel({ profiles }) {
  const [from, setFrom] = useState(todayISO());
  const [to, setTo] = useState(todayISO());
  const [period, setPeriod] = useState("today");
  const [rows, setRows] = useState([]);
  const [loading, setLoading] = useState(false);

  async function load(range = { from, to }) {
    setLoading(true);
    try {
      let query = supabase
        .from("commands")
        .select("*, command_items(*), payments(*)")
        .order("opened_at", { ascending: false });
      if (range.from) query = query.gte("business_date", range.from);
      if (range.to) query = query.lte("business_date", range.to);
      const data = await unwrap(query);

      // The dashboard uses the payment/closing date for today's totals. Add
      // paid or cancelled commands closed in the selected period even when
      // they were opened on the previous business date (e.g. after midnight).
      let closedData = [];
      if (range.from || range.to) {
        let closedQuery = supabase
          .from("commands")
          .select("*, command_items(*), payments(*)")
          .not("closed_at", "is", null)
          .order("closed_at", { ascending: false });
        if (range.from) closedQuery = closedQuery.gte("closed_at", businessDateStartISO(range.from));
        if (range.to) closedQuery = closedQuery.lt("closed_at", businessDateStartISO(nextBusinessDate(range.to)));
        closedData = await unwrap(closedQuery);
      }

      const rowsById = new Map([...(data || []), ...(closedData || [])].map((row) => [row.id, row]));
      // Keep cancellations with items for operational history; discard empty drafts from this report.
      setRows([...rowsById.values()].filter((row) => row.status !== "cancelada" || row.command_items?.length > 0));
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    load({ from: todayISO(), to: todayISO() });
  }, []);

  function selectToday() {
    const date = todayISO();
    setFrom(date);
    setTo(date);
    setPeriod("today");
    load({ from: date, to: date });
  }

  function selectAllHistory() {
    setFrom("");
    setTo("");
    setPeriod("all");
    load({ from: "", to: "" });
  }

  const paid = rows.filter((row) => row.status === "paga");
  const total = paid.reduce((sum, row) => sum + Number(row.total || 0), 0);
  const byPayment = paid.flatMap((row) => row.payments || []).reduce((acc, payment) => {
    acc[payment.method] = (acc[payment.method] || 0) + Number(payment.amount || 0);
    return acc;
  }, {});

  return (
    <section>
      <Header title="Relatórios" subtitle="Vendas e pagamentos por período" />
      <div className="panel report-toolbar">
        <div className="quick-form">
          <div><label>De</label><input type="date" value={from} onChange={(event) => { setFrom(event.target.value); setPeriod("custom"); }} /></div>
          <div><label>Até</label><input type="date" value={to} onChange={(event) => { setTo(event.target.value); setPeriod("custom"); }} /></div>
          <button className="primary" onClick={() => load({ from, to })}>{loading ? "Carregando..." : "Filtrar período"}</button>
          <button className="neutral" onClick={selectToday}>Hoje</button>
          <button className="neutral" onClick={selectAllHistory}>Histórico completo</button>
        </div>
        <p className="report-period">{period === "all" ? "Exibindo todo o histórico disponível" : period === "today" ? `Exibindo ${businessDateLabel(todayISO())}` : "Exibindo o período selecionado"}</p>
      </div>
      <div className="metric-grid">
        <Metric label="Total vendido" value={currency(total)} />
        <Metric label="Comandas pagas" value={paid.length} />
        <Metric label="Canceladas" value={rows.filter((row) => row.status === "cancelada").length} />
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
            <span>{commandOwner(row, profiles)}</span>
            <span>{currency(row.total)}</span>
            <span>{dateTime(row.opened_at)}</span>
          </div>
        ))}
      </div>
    </section>
  );
}

function PlatformPanel({ establishments, run }) {
  const [name, setName] = useState("");
  const [adminForm, setAdminForm] = useState({
    establishmentId: "",
    username: "",
    fullName: "",
    email: "",
    password: "",
  });

  function slugify(value) {
    return value
      .normalize("NFD")
      .replace(/[\u0300-\u036f]/g, "")
      .toLowerCase()
      .trim()
      .replace(/[^a-z0-9]+/g, "-")
      .replace(/^-|-$/g, "");
  }

  async function createEstablishment(event) {
    event.preventDefault();
    const cleanName = name.trim();
    if (!cleanName) return;
    const created = await run(
      () => unwrap(supabase.from("establishments").insert({ name: cleanName, slug: slugify(cleanName) })),
      "Estabelecimento criado"
    );
    if (created !== null) setName("");
  }

  async function toggleEstablishment(item) {
    if (item.slug === "du-dair" && item.active) {
      window.alert("O estabelecimento em uso nao pode ser desativado por esta tela.");
      return;
    }
    await run(
      () => unwrap(supabase.from("establishments").update({ active: !item.active }).eq("id", item.id)),
      item.active ? "Estabelecimento desativado" : "Estabelecimento ativado"
    );
  }

  async function createEstablishmentAdmin(event) {
    event.preventDefault();
    const saved = await run(async () => {
      const { data, error } = await supabase.functions.invoke("admin-upsert-user", {
        body: {
          establishment_id: adminForm.establishmentId,
          username: adminForm.username.trim(),
          full_name: adminForm.fullName.trim(),
          email: adminForm.email.trim() || undefined,
          password: adminForm.password,
          role: "admin",
          active: true,
        },
      });
      if (error) throw error;
      return data;
    }, "Administrador do estabelecimento salvo");
    if (saved !== null) {
      setAdminForm({ establishmentId: "", username: "", fullName: "", email: "", password: "" });
    }
  }

  return (
    <section>
      <Header title="Plataforma" subtitle="Todos usam a mesma aplicacao, com dados isolados por estabelecimento" />
      <form className="panel quick-form" onSubmit={createEstablishment}>
        <div><label>Novo estabelecimento</label><input value={name} onChange={(event) => setName(event.target.value)} placeholder="Nome do estabelecimento" required /></div>
        <button className="primary">Criar estabelecimento</button>
      </form>
      <form className="panel" onSubmit={createEstablishmentAdmin}>
        <h2>Administrador do estabelecimento</h2>
        <div className="form-grid">
          <div><label>Estabelecimento</label><select value={adminForm.establishmentId} onChange={(event) => setAdminForm((current) => ({ ...current, establishmentId: event.target.value }))} required>
            <option value="">Selecione</option>
            {establishments.filter((item) => item.active).map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}
          </select></div>
          <div><label>Usuario</label><input pattern="[a-z0-9_.-]+" title="Use apenas letras minúsculas, números, ponto, hífen ou sublinhado." value={adminForm.username} onChange={(event) => setAdminForm((current) => ({ ...current, username: event.target.value }))} required /></div>
          <div><label>Nome</label><input value={adminForm.fullName} onChange={(event) => setAdminForm((current) => ({ ...current, fullName: event.target.value }))} /></div>
          <div><label>Email real</label><input type="email" value={adminForm.email} onChange={(event) => setAdminForm((current) => ({ ...current, email: event.target.value }))} placeholder="Para recuperar a senha" /></div>
          <div><label>Senha inicial</label><input type="password" minLength="6" value={adminForm.password} onChange={(event) => setAdminForm((current) => ({ ...current, password: event.target.value }))} required /></div>
        </div>
        <button className="primary">Criar ou atualizar administrador</button>
      </form>
      <div className="table-list">
        {establishments.map((item) => (
          <div className="table-row" key={item.id}>
            <div><strong>{item.name}</strong><small>{item.slug}</small></div>
            <span className={`status ${item.active ? "aberto" : "cancelada"}`}>{item.active ? "Ativo" : "Inativo"}</span>
            <button className={item.active ? "danger small" : "success small"} onClick={() => toggleEstablishment(item)}>
              {item.active ? "Desativar" : "Ativar"}
            </button>
          </div>
        ))}
      </div>
    </section>
  );
}

function SettingsPanel({ settings, profiles, establishment, establishmentId, run, show }) {
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
      unwrap(supabase.from("settings").upsert(
        { establishment_id: establishmentId, key, value },
        { onConflict: "establishment_id,key" }
      ))
    );
    updates.push(
      unwrap(
        supabase
          .from("establishments")
          .update({
            name: values.establishment_name || establishment?.name,
            primary_color: values.primary_color || establishment?.primary_color,
            secondary_color: values.secondary_color || establishment?.secondary_color,
            accent_color: values.accent_color || establishment?.accent_color,
            background_color: values.background_color || establishment?.background_color,
          })
          .eq("id", establishmentId)
      )
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

    const saved = await run(async () => {
      const { data, error } = await supabase.functions.invoke("admin-upsert-user", {
        body: payload,
      });
      if (error) throw error;
      return data;
    }, "Usuario salvo");

    if (saved !== null) setUserForm(DEFAULT_USER_FORM);
  }

  return (
    <section>
      <Header title="Administracao" subtitle="Estabelecimento, Pix e usuarios da equipe" />
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
        <div className="theme-grid">
          <label>Cor principal<input type="color" value={values.primary_color || establishment?.primary_color || "#a85a2a"} onChange={(event) => setValue("primary_color", event.target.value)} /></label>
          <label>Cor secundaria<input type="color" value={values.secondary_color || establishment?.secondary_color || "#6f3f2b"} onChange={(event) => setValue("secondary_color", event.target.value)} /></label>
          <label>Destaque<input type="color" value={values.accent_color || establishment?.accent_color || "#d79a3a"} onChange={(event) => setValue("accent_color", event.target.value)} /></label>
          <label>Fundo<input type="color" value={values.background_color || establishment?.background_color || "#f6f2ec"} onChange={(event) => setValue("background_color", event.target.value)} /></label>
        </div>
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
              pattern="[a-z0-9_.-]+"
              title="Use apenas letras minúsculas, números, ponto, hífen ou sublinhado. Não é necessário usar @."
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
            Para entrar, use apenas o usuario (sem @). Use letras minúsculas, números, ponto, hífen ou sublinhado; o sistema cria o email técnico internamente.
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
