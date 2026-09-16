"""Shell principal: sidebar de navegacao + area de conteudo trocavel."""
import customtkinter as ctk

from app import api_client as services
from app.api_client import ServiceError
from ui import theme
from ui.widgets import show_error
from ui.ws_client import WsListener

# Eventos que devem disparar uma atualizacao da tela atual (mudanca feita
# pelo computador OU por um celular na rede, em tempo real).
REFRESH_EVENTS = {
    "command.created", "command.updated", "command.closed", "command.access_changed",
    "cash.opened", "cash.movement", "cash.closed",
    "kitchen.updated", "product.changed",
}


class MainWindow(ctk.CTkFrame):
    def __init__(self, parent, user: dict, on_logout):
        super().__init__(parent, fg_color=theme.BG_DARK)
        self.user = user
        self.on_logout = on_logout
        self.current_page_name = None
        self.current_page_widget = None

        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)

        self._build_sidebar()

        self.content = ctk.CTkFrame(self, fg_color=theme.BG_DARK)
        self.content.grid(row=0, column=1, sticky="nsew", padx=18, pady=18)

        root = self.winfo_toplevel()
        root.bind("<F2>", lambda e: self.novo_comanda())
        root.bind("<F3>", lambda e: self.show_page("comanda_consulta"))

        self.ws_listener = WsListener()
        self.bind("<Destroy>", lambda e: self.ws_listener.stop())
        self.after(300, self._poll_ws_events)

        self.show_page("dashboard")

    def _poll_ws_events(self):
        events = self.ws_listener.poll()
        if events:
            self._refresh_cash_status()
            relevant = any(e.get("event") in REFRESH_EVENTS for e in events)
            if relevant and self.current_page_widget is not None:
                if hasattr(self.current_page_widget, "_reload"):
                    try:
                        self.current_page_widget._reload()
                    except Exception:
                        pass
                elif hasattr(self.current_page_widget, "_search"):
                    try:
                        self.current_page_widget._search()
                    except Exception:
                        pass
        self.after(500, self._poll_ws_events)

    # ------------------------------------------------------------------
    def _build_sidebar(self):
        sidebar = ctk.CTkFrame(self, fg_color=theme.BG_PANEL, width=230, corner_radius=0)
        sidebar.grid(row=0, column=0, sticky="nsw")
        sidebar.grid_propagate(False)

        establishment = services.get_setting("establishment_name", "Espetinho DU'DAIR")
        ctk.CTkLabel(sidebar, text="🔥 " + establishment, font=theme.font(16, "bold"),
                     text_color=theme.ORANGE, wraplength=200, justify="left").pack(pady=(22, 4), padx=16, anchor="w")
        ctk.CTkLabel(sidebar, text=f"{self.user['username']} ({self.user['role']})",
                     font=theme.font(11), text_color=theme.TEXT_MUTED).pack(pady=(0, 18), padx=16, anchor="w")

        is_admin = self.user["role"] == "admin"

        items = [
            ("🆕  Nova comanda", self.novo_comanda, True),
            ("🔍  Consultar comanda", lambda: self.show_page("comanda_consulta"), True),
            ("📋  Comandas abertas", lambda: self.show_page("comandas_abertas"), True),
            ("🍢  Produtos", lambda: self.show_page("produtos"), True),
            ("💰  Caixa", lambda: self.show_page("caixa"), True),
            ("📊  Relatorios", lambda: self.show_page("relatorios"), is_admin),
            ("⚙️  Configuracoes", lambda: self.show_page("configuracoes"), is_admin),
        ]

        self.nav_buttons = {}
        for label, command, enabled in items:
            btn = ctk.CTkButton(
                sidebar, text=label, command=command if enabled else None,
                state="normal" if enabled else "disabled",
                fg_color="transparent", hover_color=theme.BG_PANEL_LIGHT,
                text_color=theme.TEXT_LIGHT if enabled else theme.GRAY,
                **theme.NAV_BUTTON(),
            )
            btn.pack(fill="x", padx=10, pady=3)
            self.nav_buttons[label] = btn

        self.cash_status_label = ctk.CTkLabel(sidebar, text="", font=theme.font(12, "bold"))
        self.cash_status_label.pack(side="bottom", pady=(0, 6), padx=16)
        self._refresh_cash_status()

        ctk.CTkButton(
            sidebar, text="Sair / Trocar usuario", command=self._logout, height=36,
            **theme.NEUTRAL_BUTTON
        ).pack(side="bottom", fill="x", padx=10, pady=10)

    def _refresh_cash_status(self):
        session = services.get_open_cash_session()
        if session:
            self.cash_status_label.configure(text="🟢 Caixa aberto", text_color=theme.TEXT_SUCCESS)
        else:
            self.cash_status_label.configure(text="🔴 Caixa fechado", text_color=theme.TEXT_DANGER)

    def _logout(self):
        self.on_logout()

    # ------------------------------------------------------------------
    def novo_comanda(self):
        try:
            cmd_id = services.create_command(created_by=self.user["username"])
        except ServiceError as exc:
            show_error(self, "Nao foi possivel criar", str(exc))
            return
        self.show_page("comanda_detalhe", command_id=cmd_id, return_page="comandas_abertas")

    def show_page(self, name, **kwargs):
        for child in self.content.winfo_children():
            child.destroy()

        self.current_page_name = name

        if name == "dashboard":
            from ui.dashboard_window import DashboardFrame
            page = DashboardFrame(self.content, self)
        elif name == "comandas_abertas":
            from ui.comandas_window import ComandasAbertasFrame
            page = ComandasAbertasFrame(self.content, self)
        elif name == "comanda_consulta":
            from ui.comandas_window import ConsultaComandaFrame
            page = ConsultaComandaFrame(self.content, self)
        elif name == "comanda_detalhe":
            from ui.comanda_detalhe_window import ComandaDetalheFrame
            page = ComandaDetalheFrame(self.content, self, kwargs["command_id"], kwargs.get("return_page", "comandas_abertas"))
        elif name == "produtos":
            from ui.produtos_window import ProdutosFrame
            page = ProdutosFrame(self.content, self)
        elif name == "caixa":
            from ui.caixa_window import CaixaFrame
            page = CaixaFrame(self.content, self)
        elif name == "fechamento":
            from ui.fechamento_window import FechamentoFrame
            page = FechamentoFrame(self.content, self, kwargs.get("cash_session_id"))
        elif name == "relatorios":
            from ui.relatorios_window import RelatoriosFrame
            page = RelatoriosFrame(self.content, self)
        elif name == "configuracoes":
            from ui.configuracoes_window import ConfiguracoesFrame
            page = ConfiguracoesFrame(self.content, self)
        else:
            raise ValueError(f"Pagina desconhecida: {name}")

        page.pack(fill="both", expand=True)
        self.current_page_widget = page
        self._refresh_cash_status()
