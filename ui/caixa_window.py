"""Modulo de caixa: abertura, sangria, reforco e acesso ao fechamento."""
import customtkinter as ctk

from app import api_client as services
from app.api_client import ServiceError
from app.utils import format_currency, parse_currency_input, now_iso
from ui import theme
from ui.widgets import ModalDialog, SectionCard, show_error, show_success


class OpenCashDialog(ModalDialog):
    def __init__(self, parent, on_saved, operator_default=""):
        super().__init__(parent, title="Abrir caixa", width=420, height=420)
        self.on_saved = on_saved

        ctk.CTkLabel(self, text="Abertura de Caixa", font=theme.font(18, "bold"), text_color=theme.ORANGE).pack(
            pady=(20, 12)
        )
        ctk.CTkLabel(self, text="Fundo inicial em dinheiro (R$)", font=theme.font(12), text_color=theme.TEXT_MUTED).pack()
        self.amount_entry = ctk.CTkEntry(self, width=220, height=40, justify="center", font=theme.font(16, "bold"))
        self.amount_entry.pack(pady=6)
        self.amount_entry.insert(0, "0.00")

        ctk.CTkLabel(self, text="Operador (opcional)", font=theme.font(12), text_color=theme.TEXT_MUTED).pack(pady=(10, 0))
        self.operator_entry = ctk.CTkEntry(self, width=280, height=36)
        self.operator_entry.pack(pady=6)
        self.operator_entry.insert(0, operator_default)

        ctk.CTkLabel(self, text="Observacao (opcional)", font=theme.font(12), text_color=theme.TEXT_MUTED).pack(pady=(10, 0))
        self.notes_entry = ctk.CTkEntry(self, width=280, height=36)
        self.notes_entry.pack(pady=6)

        ctk.CTkButton(self, text="Abrir caixa", width=240, height=44, font=theme.font(14, "bold"),
                      command=self._save, **theme.SUCCESS_BUTTON).pack(pady=18)

    def _save(self):
        try:
            services.open_cash_session(
                parse_currency_input(self.amount_entry.get()), self.operator_entry.get(), self.notes_entry.get()
            )
        except ServiceError as exc:
            show_error(self, "Erro", str(exc))
            return
        self.destroy()
        self.on_saved()


class MovementDialog(ModalDialog):
    def __init__(self, parent, session_id, mtype, on_saved):
        title = "Registrar sangria (retirada)" if mtype == "sangria" else "Registrar reforco (entrada)"
        super().__init__(parent, title=title, width=420, height=340)
        self.session_id = session_id
        self.mtype = mtype
        self.on_saved = on_saved

        color = theme.RED if mtype == "sangria" else theme.GREEN
        ctk.CTkLabel(self, text=title, font=theme.font(17, "bold"), text_color=color).pack(pady=(20, 14))

        ctk.CTkLabel(self, text="Valor (R$)", font=theme.font(12), text_color=theme.TEXT_MUTED).pack()
        self.amount_entry = ctk.CTkEntry(self, width=200, height=40, justify="center", font=theme.font(16, "bold"))
        self.amount_entry.pack(pady=6)

        ctk.CTkLabel(self, text="Motivo", font=theme.font(12), text_color=theme.TEXT_MUTED).pack(pady=(10, 0))
        self.reason_entry = ctk.CTkEntry(self, width=280, height=36)
        self.reason_entry.pack(pady=6)

        ctk.CTkButton(self, text="Confirmar", width=220, height=44, font=theme.font(14, "bold"),
                      command=self._save, fg_color=color, hover_color=color, text_color="white").pack(pady=20)

    def _save(self):
        try:
            services.add_movement(self.session_id, self.mtype, parse_currency_input(self.amount_entry.get()),
                                   self.reason_entry.get())
        except ServiceError as exc:
            show_error(self, "Erro", str(exc))
            return
        self.destroy()
        self.on_saved()


class CaixaFrame(ctk.CTkFrame):
    def __init__(self, parent, app):
        super().__init__(parent, fg_color=theme.BG_DARK)
        self.app = app
        ctk.CTkLabel(self, text="Caixa", font=theme.font_title(26), text_color=theme.TEXT_LIGHT).pack(
            anchor="w", pady=(0, 14)
        )
        self.body = ctk.CTkFrame(self, fg_color="transparent")
        self.body.pack(fill="both", expand=True)
        self._reload()

    def _reload(self):
        for child in self.body.winfo_children():
            child.destroy()

        session = services.get_open_cash_session()
        if not session:
            self._render_closed_state()
        else:
            self._render_open_state(session)

    def _render_closed_state(self):
        card = SectionCard(self.body)
        card.pack(fill="x", pady=10)
        ctk.CTkLabel(card, text="🔴 O caixa esta FECHADO", font=theme.font(22, "bold"),
                     text_color=theme.TEXT_DANGER).pack(pady=(30, 6))
        ctk.CTkLabel(card, text="Nenhuma venda pode ser finalizada enquanto o caixa nao for aberto.",
                     font=theme.font(13), text_color=theme.TEXT_MUTED).pack(pady=(0, 20))
        ctk.CTkButton(card, text="🟢 Abrir caixa", width=240, height=54, font=theme.font(16, "bold"),
                      command=self._open_cash, **theme.SUCCESS_BUTTON).pack(pady=(0, 30))

    def _open_cash(self):
        OpenCashDialog(self, on_saved=self._reload, operator_default=self.app.user["username"])

    def _render_open_state(self, session):
        top = SectionCard(self.body)
        top.pack(fill="x", pady=(0, 10))
        row = ctk.CTkFrame(top, fg_color="transparent")
        row.pack(fill="x", padx=16, pady=16)
        ctk.CTkLabel(row, text="🟢 Caixa aberto", font=theme.font(18, "bold"), text_color=theme.TEXT_SUCCESS).pack(side="left")
        ctk.CTkLabel(row, text=f"desde {session['opened_at']}  •  operador: {session['operator_name'] or '-'}",
                     font=theme.font(12), text_color=theme.TEXT_MUTED).pack(side="left", padx=16)

        summary = services.get_cash_summary(session["id"])

        grid = ctk.CTkFrame(self.body, fg_color="transparent")
        grid.pack(fill="x", pady=10)
        for i in range(4):
            grid.grid_columnconfigure(i, weight=1)

        cards = [
            ("Fundo inicial", format_currency(summary["opening_amount"])),
            ("Total vendido", format_currency(summary["total_vendido"])),
            ("Reforcos", format_currency(summary["reforcos"])),
            ("Sangrias", format_currency(summary["sangrias"])),
            ("Dinheiro", format_currency(summary["por_forma"]["dinheiro"])),
            ("Pix", format_currency(summary["por_forma"]["pix"])),
            ("Cartao debito", format_currency(summary["por_forma"]["debito"])),
            ("Cartao credito", format_currency(summary["por_forma"]["credito"])),
        ]
        for idx, (label, value) in enumerate(cards):
            r, c = divmod(idx, 4)
            box = ctk.CTkFrame(grid, fg_color=theme.BG_PANEL_LIGHT, corner_radius=10)
            box.grid(row=r, column=c, sticky="nsew", padx=6, pady=6)
            ctk.CTkLabel(box, text=label, font=theme.font(11), text_color=theme.TEXT_MUTED).pack(anchor="w", padx=12, pady=(8, 0))
            ctk.CTkLabel(box, text=value, font=theme.font(17, "bold"), text_color=theme.TEXT_LIGHT).pack(anchor="w", padx=12, pady=(0, 10))

        actions = ctk.CTkFrame(self.body, fg_color="transparent")
        actions.pack(fill="x", pady=10)
        ctk.CTkButton(actions, text="🔻 Sangria (retirada)", width=200, height=50, font=theme.font(14, "bold"),
                      command=lambda: MovementDialog(self, session["id"], "sangria", self._reload),
                      **theme.DANGER_BUTTON).pack(side="left", padx=(0, 10))
        ctk.CTkButton(actions, text="🔺 Reforco (entrada)", width=200, height=50, font=theme.font(14, "bold"),
                      command=lambda: MovementDialog(self, session["id"], "reforco", self._reload),
                      **theme.SUCCESS_BUTTON).pack(side="left", padx=10)
        ctk.CTkButton(actions, text="🔄 Atualizar", width=140, height=50, command=self._reload,
                      **theme.NEUTRAL_BUTTON).pack(side="left", padx=10)
        if self.app.user["role"] == "admin":
            ctk.CTkButton(actions, text="🧾 Fechar caixa", width=200, height=50, font=theme.font(14, "bold"),
                          command=lambda: self.app.show_page("fechamento", cash_session_id=session["id"]),
                          **theme.GOLD_BUTTON).pack(side="right")

        moves = services.list_movements(session["id"])
        if moves:
            hist_card = SectionCard(self.body, title="Movimentacoes do caixa")
            hist_card.pack(fill="both", expand=True, pady=10)
            scroll = ctk.CTkScrollableFrame(hist_card, fg_color="transparent", height=160)
            scroll.pack(fill="both", expand=True, padx=12, pady=(0, 12))
            for m in moves:
                line = ctk.CTkFrame(scroll, fg_color=theme.BG_PANEL_LIGHT, corner_radius=8)
                line.pack(fill="x", pady=2)
                icon = "🔻" if m["type"] == "sangria" else "🔺"
                color = theme.TEXT_DANGER if m["type"] == "sangria" else theme.TEXT_SUCCESS
                ctk.CTkLabel(line, text=f"{icon} {m['created_at']}  -  {m['reason'] or 'Sem motivo informado'}",
                             font=theme.font(12), text_color=theme.TEXT_LIGHT).pack(side="left", padx=10, pady=6)
                ctk.CTkLabel(line, text=format_currency(m["amount"]), font=theme.font(13, "bold"),
                             text_color=color).pack(side="right", padx=10)
