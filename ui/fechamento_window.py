"""Fechamento de caixa: conferencia de dinheiro, diferenca e resumo final."""
import customtkinter as ctk

from app import api_client as services
from app.api_client import ServiceError
from app.utils import format_currency, parse_currency_input
from ui import theme
from ui.widgets import SectionCard, show_error, confirm


class FechamentoFrame(ctk.CTkFrame):
    def __init__(self, parent, app, cash_session_id):
        super().__init__(parent, fg_color=theme.BG_DARK)
        self.app = app

        session = services.get_cash_session(cash_session_id) if cash_session_id else services.get_open_cash_session()

        header = ctk.CTkFrame(self, fg_color="transparent")
        header.pack(fill="x", pady=(0, 14))
        ctk.CTkLabel(header, text="Fechamento de Caixa", font=theme.font_title(26), text_color=theme.TEXT_LIGHT).pack(
            side="left"
        )
        ctk.CTkButton(header, text="⬅ Voltar", width=110, command=lambda: app.show_page("caixa"),
                      **theme.NEUTRAL_BUTTON).pack(side="right")

        if not session:
            SectionCard(self).pack(fill="both", expand=True)
            ctk.CTkLabel(self, text="Nenhum caixa aberto no momento.", font=theme.font(16),
                         text_color=theme.TEXT_MUTED).pack(pady=60)
            return

        self.session = session
        self.scroll = ctk.CTkScrollableFrame(self, fg_color="transparent")
        self.scroll.pack(fill="both", expand=True)

        if session["status"] == "fechado":
            self._render_closed_report()
        else:
            self._render_closing_form()

    # ------------------------------------------------------------------
    def _summary_cards(self, parent, summary):
        grid = ctk.CTkFrame(parent, fg_color="transparent")
        grid.pack(fill="x", padx=16, pady=10)
        for i in range(4):
            grid.grid_columnconfigure(i, weight=1)
        cards = [
            ("Fundo inicial", format_currency(summary["opening_amount"])),
            ("Total vendido", format_currency(summary["total_vendido"])),
            ("Reforcos", format_currency(summary["reforcos"])),
            ("Sangrias", format_currency(summary["sangrias"])),
            ("Dinheiro (puro)", format_currency(summary["por_forma"]["dinheiro"])),
            ("Pix (puro)", format_currency(summary["por_forma"]["pix"])),
            ("Cartao debito", format_currency(summary["por_forma"]["debito"])),
            ("Cartao credito", format_currency(summary["por_forma"]["credito"])),
            ("Pagamento misto", format_currency(summary["por_forma"]["misto"])),
            ("Comandas pagas", str(summary["qtd_pagas"])),
            ("Comandas canceladas", str(summary["qtd_canceladas"])),
            ("Comandas em aberto", str(summary["qtd_abertas"])),
            ("Comandas fiado/pendente", str(summary["qtd_pendentes"])),
            ("Troco total pago", format_currency(summary["troco_total"])),
        ]
        for idx, (label, value) in enumerate(cards):
            r, c = divmod(idx, 4)
            box = ctk.CTkFrame(grid, fg_color=theme.BG_PANEL_LIGHT, corner_radius=10)
            box.grid(row=r, column=c, sticky="nsew", padx=6, pady=6)
            ctk.CTkLabel(box, text=label, font=theme.font(11), text_color=theme.TEXT_MUTED).pack(anchor="w", padx=12, pady=(8, 0))
            ctk.CTkLabel(box, text=value, font=theme.font(15, "bold"), text_color=theme.TEXT_LIGHT).pack(anchor="w", padx=12, pady=(0, 10))

        if summary["produtos_mais_vendidos"]:
            top_card = SectionCard(parent, title="Produtos mais vendidos")
            top_card.pack(fill="x", padx=16, pady=10)
            for name, qty in summary["produtos_mais_vendidos"]:
                line = ctk.CTkFrame(top_card, fg_color="transparent")
                line.pack(fill="x", padx=16, pady=2)
                ctk.CTkLabel(line, text=name, font=theme.font(12), text_color=theme.TEXT_LIGHT).pack(side="left")
                ctk.CTkLabel(line, text=f"{qty:g} un.", font=theme.font(12, "bold"), text_color=theme.GOLD).pack(side="right")
            ctk.CTkLabel(top_card, text="", height=1).pack(pady=4)

    def _render_closing_form(self):
        summary = services.get_cash_summary(self.session["id"])
        self._summary_cards(self.scroll, summary)

        if summary["qtd_abertas"] > 0:
            warn = ctk.CTkFrame(self.scroll, fg_color=theme.RED, corner_radius=10)
            warn.pack(fill="x", padx=16, pady=10)
            ctk.CTkLabel(warn, text=f"⚠ Existem {summary['qtd_abertas']} comanda(s) em aberto. "
                                     f"Finalize ou cancele antes de fechar, ou force o fechamento abaixo.",
                         font=theme.font(13, "bold"), text_color="white", wraplength=700).pack(padx=14, pady=10)
            self.force_var = ctk.BooleanVar(value=False)
            ctk.CTkCheckBox(self.scroll, text="Forcar fechamento mesmo com comandas em aberto",
                            variable=self.force_var, text_color=theme.TEXT_DANGER).pack(anchor="w", padx=20, pady=(0, 10))
        else:
            self.force_var = ctk.BooleanVar(value=False)

        conf_card = SectionCard(self.scroll, title="Conferencia de caixa")
        conf_card.pack(fill="x", padx=16, pady=10)

        row = ctk.CTkFrame(conf_card, fg_color="transparent")
        row.pack(fill="x", padx=16, pady=10)
        ctk.CTkLabel(row, text="Dinheiro esperado na gaveta:", font=theme.font(14), text_color=theme.TEXT_MUTED).pack(
            side="left"
        )
        ctk.CTkLabel(row, text=format_currency(summary["dinheiro_esperado"]), font=theme.font(20, "bold"),
                     text_color=theme.GOLD).pack(side="left", padx=10)

        row2 = ctk.CTkFrame(conf_card, fg_color="transparent")
        row2.pack(fill="x", padx=16, pady=(0, 6))
        ctk.CTkLabel(row2, text="Dinheiro contado (informe o valor fisico na gaveta):", font=theme.font(13),
                     text_color=theme.TEXT_MUTED).pack(anchor="w")
        self.counted_entry = ctk.CTkEntry(row2, width=200, height=42, font=theme.font(17, "bold"), justify="center")
        self.counted_entry.pack(anchor="w", pady=6)
        self.counted_entry.insert(0, f"{summary['dinheiro_esperado']:.2f}")
        self.counted_entry.bind("<KeyRelease>", lambda e: self._update_difference(summary["dinheiro_esperado"]))

        self.diff_label = ctk.CTkLabel(conf_card, text="", font=theme.font(22, "bold"))
        self.diff_label.pack(anchor="w", padx=16, pady=(6, 14))

        notes_row = ctk.CTkFrame(conf_card, fg_color="transparent")
        notes_row.pack(fill="x", padx=16, pady=(0, 14))
        ctk.CTkLabel(notes_row, text="Observacao do fechamento (opcional):", font=theme.font(12),
                     text_color=theme.TEXT_MUTED).pack(anchor="w")
        self.close_notes_entry = ctk.CTkEntry(notes_row, height=36)
        self.close_notes_entry.pack(fill="x", pady=4)

        ctk.CTkButton(self.scroll, text="🧾 Confirmar fechamento de caixa", height=52, font=theme.font(16, "bold"),
                      command=lambda: self._confirm_close(summary["dinheiro_esperado"]),
                      **theme.GOLD_BUTTON).pack(fill="x", padx=16, pady=(4, 20))

        self._update_difference(summary["dinheiro_esperado"])

    def _update_difference(self, expected):
        counted = parse_currency_input(self.counted_entry.get())
        diff = round(counted - expected, 2)
        if abs(diff) < 0.01:
            text, color = f"Diferenca: {format_currency(diff)} (confere certinho)", theme.TEXT_SUCCESS
        elif diff < 0:
            text, color = f"Diferenca: {format_currency(diff)} (faltando)", theme.TEXT_DANGER
        else:
            text, color = f"Diferenca: +{format_currency(diff)} (sobrando)", theme.TEXT_WARNING
        self.diff_label.configure(text=text, text_color=color)

    def _confirm_close(self, expected):
        counted = parse_currency_input(self.counted_entry.get())
        diff = round(counted - expected, 2)
        msg = f"Dinheiro esperado: {format_currency(expected)}\nDinheiro contado: {format_currency(counted)}\n" \
              f"Diferenca: {format_currency(diff)}\n\nDeseja confirmar o fechamento do caixa? Esta acao nao pode ser desfeita."
        if not confirm(self, "Confirmar fechamento", msg):
            return
        try:
            services.close_cash_session(
                self.session["id"], counted, self.close_notes_entry.get(), self.app.user["username"],
                force=self.force_var.get(),
            )
        except ServiceError as exc:
            show_error(self, "Nao foi possivel fechar", str(exc))
            return

        for child in self.scroll.winfo_children():
            child.destroy()
        self.session = services.get_cash_session(self.session["id"])
        self._render_closed_report()

    def _render_closed_report(self):
        summary = services.get_cash_summary(self.session["id"])
        banner = ctk.CTkFrame(self.scroll, fg_color=theme.BG_PANEL, corner_radius=12)
        banner.pack(fill="x", padx=16, pady=10)
        ctk.CTkLabel(banner, text="✅ Caixa fechado", font=theme.font(20, "bold"),
                     text_color=theme.TEXT_SUCCESS).pack(pady=(14, 4))
        ctk.CTkLabel(banner, text=f"Aberto em {self.session['opened_at']}  •  Fechado em {self.session['closed_at']}",
                     font=theme.font(12), text_color=theme.TEXT_MUTED).pack(pady=(0, 14))

        self._summary_cards(self.scroll, summary)

        conf_card = SectionCard(self.scroll, title="Conferencia final")
        conf_card.pack(fill="x", padx=16, pady=10)
        for label, value, color in [
            ("Dinheiro esperado", format_currency(self.session["expected_amount"]), theme.TEXT_LIGHT),
            ("Dinheiro contado", format_currency(self.session["counted_amount"]), theme.TEXT_LIGHT),
            ("Diferenca", format_currency(self.session["difference"]),
             theme.TEXT_SUCCESS if abs(self.session["difference"] or 0) < 0.01
             else (theme.TEXT_DANGER if (self.session["difference"] or 0) < 0 else theme.TEXT_WARNING)),
        ]:
            row = ctk.CTkFrame(conf_card, fg_color="transparent")
            row.pack(fill="x", padx=16, pady=6)
            ctk.CTkLabel(row, text=label, font=theme.font(14), text_color=theme.TEXT_MUTED).pack(side="left")
            ctk.CTkLabel(row, text=value, font=theme.font(20, "bold"), text_color=color).pack(side="right")
        if self.session.get("close_notes"):
            ctk.CTkLabel(conf_card, text=f"Obs: {self.session['close_notes']}", font=theme.font(12),
                         text_color=theme.TEXT_MUTED, wraplength=700).pack(anchor="w", padx=16, pady=(0, 14))
        else:
            ctk.CTkLabel(conf_card, text="", height=1).pack(pady=6)

        ctk.CTkButton(self.scroll, text="Ir para o Painel", height=44, command=lambda: self.app.show_page("dashboard"),
                      **theme.PRIMARY_BUTTON).pack(pady=16)
