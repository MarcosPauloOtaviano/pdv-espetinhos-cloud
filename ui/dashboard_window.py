"""Tela inicial: botoes grandes de acao + resumo do dia."""
import customtkinter as ctk

from app import api_client as services
from app.utils import format_currency
from ui import theme
from ui.widgets import SectionCard


class DashboardFrame(ctk.CTkFrame):
    def __init__(self, parent, app):
        super().__init__(parent, fg_color=theme.BG_DARK)
        self.app = app

        header = ctk.CTkFrame(self, fg_color="transparent")
        header.pack(fill="x", pady=(0, 14))
        ctk.CTkLabel(header, text="Painel do dia", font=theme.font_title(28), text_color=theme.TEXT_LIGHT).pack(
            side="left"
        )
        ctk.CTkButton(header, text="🔄 Atualizar", width=120, command=self._reload, **theme.NEUTRAL_BUTTON).pack(
            side="right"
        )

        self._build_big_buttons()
        self._build_summary()
        self._reload()

    def _build_big_buttons(self):
        is_admin = self.app.user["role"] == "admin"
        grid = ctk.CTkFrame(self, fg_color="transparent")
        grid.pack(fill="x", pady=(0, 18))
        for i in range(4):
            grid.grid_columnconfigure(i, weight=1)

        buttons = [
            ("🆕", "Nova Comanda", self.app.novo_comanda, theme.PRIMARY_BUTTON, True),
            ("🔍", "Consultar Comanda", lambda: self.app.show_page("comanda_consulta"), theme.NEUTRAL_BUTTON, True),
            ("📋", "Comandas Abertas", lambda: self.app.show_page("comandas_abertas"), theme.NEUTRAL_BUTTON, True),
            ("🍢", "Cadastrar Produtos", lambda: self.app.show_page("produtos"), theme.GOLD_BUTTON, True),
            ("💰", "Caixa", lambda: self.app.show_page("caixa"), theme.SUCCESS_BUTTON, True),
            ("📊", "Relatorios", lambda: self.app.show_page("relatorios"), theme.NEUTRAL_BUTTON, is_admin),
            ("⚙️", "Configuracoes", lambda: self.app.show_page("configuracoes"), theme.NEUTRAL_BUTTON, is_admin),
        ]
        for idx, (icon, label, cmd, style, enabled) in enumerate(buttons):
            r, c = divmod(idx, 4)
            btn = ctk.CTkButton(
                grid, text=f"{icon}\n{label}", command=cmd if enabled else None,
                state="normal" if enabled else "disabled",
                **{**theme.BIG_BUTTON(), **style},
            )
            btn.grid(row=r, column=c, sticky="nsew", padx=8, pady=8)

    def _build_summary(self):
        self.summary_card = SectionCard(self, title="Resumo de hoje")
        self.summary_card.pack(fill="both", expand=True)

        self.grid_labels = {}
        grid = ctk.CTkFrame(self.summary_card, fg_color="transparent")
        grid.pack(fill="both", expand=True, padx=16, pady=(4, 16))
        for i in range(4):
            grid.grid_columnconfigure(i, weight=1)

        specs = [
            ("cash_open", "Status do caixa"),
            ("total_vendido_hoje", "Total vendido hoje"),
            ("qtd_abertas", "Comandas abertas"),
            ("qtd_finalizadas_hoje", "Comandas finalizadas"),
            ("total_dinheiro", "Total em dinheiro"),
            ("total_pix", "Total em Pix"),
            ("total_cartao", "Total em cartao"),
            ("qtd_pendentes_hoje", "Comandas fiado/pendentes"),
        ]
        for idx, (key, label) in enumerate(specs):
            r, c = divmod(idx, 4)
            card = ctk.CTkFrame(grid, fg_color=theme.BG_PANEL_LIGHT, corner_radius=10)
            card.grid(row=r, column=c, sticky="nsew", padx=6, pady=6)
            ctk.CTkLabel(card, text=label, font=theme.font(12), text_color=theme.TEXT_MUTED).pack(
                anchor="w", padx=14, pady=(10, 0)
            )
            value_label = ctk.CTkLabel(card, text="-", font=theme.font(20, "bold"), text_color=theme.TEXT_LIGHT)
            value_label.pack(anchor="w", padx=14, pady=(0, 12))
            self.grid_labels[key] = value_label

    def _reload(self):
        data = services.get_dashboard_summary()
        self.grid_labels["cash_open"].configure(
            text="ABERTO" if data["cash_open"] else "FECHADO",
            text_color=theme.TEXT_SUCCESS if data["cash_open"] else theme.TEXT_DANGER,
        )
        self.grid_labels["total_vendido_hoje"].configure(text=format_currency(data["total_vendido_hoje"]))
        self.grid_labels["qtd_abertas"].configure(text=str(data["qtd_abertas"]))
        self.grid_labels["qtd_finalizadas_hoje"].configure(text=str(data["qtd_finalizadas_hoje"]))
        self.grid_labels["total_dinheiro"].configure(text=format_currency(data["total_dinheiro"]))
        self.grid_labels["total_pix"].configure(text=format_currency(data["total_pix"]))
        self.grid_labels["total_cartao"].configure(text=format_currency(data["total_cartao"]))
        self.grid_labels["qtd_pendentes_hoje"].configure(text=str(data["qtd_pendentes_hoje"]))
