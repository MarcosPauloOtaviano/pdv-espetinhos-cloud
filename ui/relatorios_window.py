"""Relatorios: vendas por periodo, formas de pagamento, produtos mais vendidos, historico de caixa."""
import csv
from datetime import date, timedelta
from tkinter import filedialog

import customtkinter as ctk

from app import api_client as services
from app.utils import format_currency, today_str
from ui import theme
from ui.widgets import SectionCard, show_success, show_error


class RelatoriosFrame(ctk.CTkFrame):
    def __init__(self, parent, app):
        super().__init__(parent, fg_color=theme.BG_DARK)
        self.app = app

        header = ctk.CTkFrame(self, fg_color="transparent")
        header.pack(fill="x", pady=(0, 12))
        ctk.CTkLabel(header, text="Relatorios", font=theme.font_title(26), text_color=theme.TEXT_LIGHT).pack(side="left")

        filters = ctk.CTkFrame(self, fg_color=theme.BG_PANEL, corner_radius=12)
        filters.pack(fill="x", pady=(0, 12))
        row = ctk.CTkFrame(filters, fg_color="transparent")
        row.pack(fill="x", padx=14, pady=12)

        ctk.CTkLabel(row, text="De:", font=theme.font(12)).pack(side="left")
        self.date_from_entry = ctk.CTkEntry(row, width=120, height=34)
        self.date_from_entry.pack(side="left", padx=(6, 14))
        self.date_from_entry.insert(0, today_str())

        ctk.CTkLabel(row, text="Ate:", font=theme.font(12)).pack(side="left")
        self.date_to_entry = ctk.CTkEntry(row, width=120, height=34)
        self.date_to_entry.pack(side="left", padx=(6, 14))
        self.date_to_entry.insert(0, today_str())

        ctk.CTkButton(row, text="Hoje", width=80, height=34, command=self._set_today,
                      **theme.NEUTRAL_BUTTON).pack(side="left", padx=4)
        ctk.CTkButton(row, text="7 dias", width=80, height=34, command=self._set_7_days,
                      **theme.NEUTRAL_BUTTON).pack(side="left", padx=4)
        ctk.CTkButton(row, text="Este mes", width=90, height=34, command=self._set_month,
                      **theme.NEUTRAL_BUTTON).pack(side="left", padx=4)
        ctk.CTkButton(row, text="Filtrar", width=100, height=34, command=self._reload,
                      **theme.PRIMARY_BUTTON).pack(side="left", padx=(14, 4))
        ctk.CTkButton(row, text="⬇ Exportar CSV", width=140, height=34, command=self._export_csv,
                      **theme.GOLD_BUTTON).pack(side="right")

        self.scroll = ctk.CTkScrollableFrame(self, fg_color="transparent")
        self.scroll.pack(fill="both", expand=True)

        self._reload()

    def _set_today(self):
        self._set_range(today_str(), today_str())

    def _set_7_days(self):
        self._set_range((date.today() - timedelta(days=6)).isoformat(), today_str())

    def _set_month(self):
        first = date.today().replace(day=1).isoformat()
        self._set_range(first, today_str())

    def _set_range(self, d_from, d_to):
        self.date_from_entry.delete(0, "end")
        self.date_from_entry.insert(0, d_from)
        self.date_to_entry.delete(0, "end")
        self.date_to_entry.insert(0, d_to)
        self._reload()

    def _range(self):
        return self.date_from_entry.get().strip(), self.date_to_entry.get().strip()

    def _export_csv(self):
        d_from, d_to = self._range()
        rows = services.sales_report(d_from, d_to)
        if not rows:
            show_error(self, "Sem dados", "Nao ha comandas no periodo selecionado.")
            return
        path = filedialog.asksaveasfilename(
            defaultextension=".csv", filetypes=[("CSV", "*.csv")],
            initialfile=f"relatorio-vendas-{d_from}-a-{d_to}.csv",
        )
        if not path:
            return
        try:
            with open(path, "w", newline="", encoding="utf-8-sig") as f:
                writer = csv.writer(f, delimiter=";")
                writer.writerow(["Numero", "Cliente", "Mesa/Id", "Status", "Total", "Aberta em", "Fechada em"])
                for r in rows:
                    writer.writerow([
                        r["number"], r.get("customer_name") or "", r.get("table_ref") or "",
                        services.STATUS_LABELS.get(r["status"], r["status"]), f"{r['total']:.2f}",
                        r["opened_at"], r.get("closed_at") or "",
                    ])
        except Exception as exc:
            show_error(self, "Erro ao exportar", str(exc))
            return
        show_success(self, "Exportado", f"Relatorio salvo em:\n{path}")

    def _reload(self):
        for child in self.scroll.winfo_children():
            child.destroy()

        d_from, d_to = self._range()
        commands = services.sales_report(d_from, d_to)
        payment_totals = {p["method"]: p for p in services.payment_totals_by_period(d_from, d_to)}
        top_products = services.top_products_by_period(d_from, d_to)

        pagas = [c for c in commands if c["status"] == "paga"]
        canceladas = [c for c in commands if c["status"] == "cancelada"]
        pendentes = [c for c in commands if c["status"] == "fiado"]
        total_vendido = sum(c["total"] for c in pagas)

        grid = ctk.CTkFrame(self.scroll, fg_color="transparent")
        grid.pack(fill="x", pady=(0, 10))
        for i in range(4):
            grid.grid_columnconfigure(i, weight=1)
        cards = [
            ("Total vendido no periodo", format_currency(total_vendido)),
            ("Comandas finalizadas", str(len(pagas))),
            ("Comandas canceladas", str(len(canceladas))),
            ("Comandas fiado/pendentes", str(len(pendentes))),
        ]
        for idx, (label, value) in enumerate(cards):
            box = ctk.CTkFrame(grid, fg_color=theme.BG_PANEL_LIGHT, corner_radius=10)
            box.grid(row=0, column=idx, sticky="nsew", padx=6, pady=6)
            ctk.CTkLabel(box, text=label, font=theme.font(11), text_color=theme.TEXT_MUTED).pack(anchor="w", padx=12, pady=(10, 0))
            ctk.CTkLabel(box, text=value, font=theme.font(18, "bold"), text_color=theme.GOLD).pack(anchor="w", padx=12, pady=(0, 12))

        pay_card = SectionCard(self.scroll, title="Total por forma de pagamento")
        pay_card.pack(fill="x", pady=10)
        for method, label in services.PAYMENT_METHOD_LABELS.items():
            info = payment_totals.get(method)
            row = ctk.CTkFrame(pay_card, fg_color="transparent")
            row.pack(fill="x", padx=16, pady=3)
            ctk.CTkLabel(row, text=label, font=theme.font(13), text_color=theme.TEXT_LIGHT).pack(side="left")
            qty = info["qtd"] if info else 0
            total = info["total"] if info else 0
            ctk.CTkLabel(row, text=f"{qty} pagamento(s)", font=theme.font(12), text_color=theme.TEXT_MUTED).pack(
                side="left", padx=12
            )
            ctk.CTkLabel(row, text=format_currency(total), font=theme.font(14, "bold"), text_color=theme.GOLD).pack(side="right")
        ctk.CTkLabel(pay_card, text="", height=1).pack(pady=4)

        top_card = SectionCard(self.scroll, title="Produtos mais vendidos")
        top_card.pack(fill="x", pady=10)
        if not top_products:
            ctk.CTkLabel(top_card, text="Sem vendas no periodo.", font=theme.font(12),
                         text_color=theme.TEXT_MUTED).pack(padx=16, pady=10)
        for p in top_products:
            row = ctk.CTkFrame(top_card, fg_color="transparent")
            row.pack(fill="x", padx=16, pady=3)
            ctk.CTkLabel(row, text=p["product_name"], font=theme.font(13), text_color=theme.TEXT_LIGHT).pack(side="left")
            ctk.CTkLabel(row, text=f"{p['qty']:g} un.", font=theme.font(12), text_color=theme.TEXT_MUTED).pack(
                side="left", padx=12
            )
            ctk.CTkLabel(row, text=format_currency(p["total"]), font=theme.font(14, "bold"),
                         text_color=theme.GOLD).pack(side="right")
        ctk.CTkLabel(top_card, text="", height=1).pack(pady=4)

        history_card = SectionCard(self.scroll, title="Historico de caixas fechados")
        history_card.pack(fill="x", pady=10)
        history = services.list_cash_sessions_history()
        if not history:
            ctk.CTkLabel(history_card, text="Nenhum caixa fechado ainda.", font=theme.font(12),
                         text_color=theme.TEXT_MUTED).pack(padx=16, pady=10)
        for h in history:
            row = ctk.CTkFrame(history_card, fg_color=theme.BG_PANEL_LIGHT, corner_radius=8)
            row.pack(fill="x", padx=12, pady=3)
            text = f"Aberto {h['opened_at']}  •  Fechado {h['closed_at']}  •  Operador: {h['operator_name'] or '-'}"
            ctk.CTkLabel(row, text=text, font=theme.font(11), text_color=theme.TEXT_LIGHT).pack(side="left", padx=10, pady=8)
            diff = h["difference"] or 0
            diff_color = theme.TEXT_SUCCESS if abs(diff) < 0.01 else (theme.TEXT_DANGER if diff < 0 else theme.TEXT_WARNING)
            btn = ctk.CTkButton(row, text=f"Diferenca {format_currency(diff)}", width=170, height=30,
                                 fg_color="transparent", hover_color=theme.BG_PANEL, text_color=diff_color,
                                 command=lambda sid=h["id"]: self.app.show_page("fechamento", cash_session_id=sid))
            btn.pack(side="right", padx=8, pady=6)
        ctk.CTkLabel(history_card, text="", height=1).pack(pady=4)
