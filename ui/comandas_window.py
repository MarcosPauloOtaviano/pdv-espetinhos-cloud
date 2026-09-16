"""Telas de comandas abertas e consulta/busca de comandas."""
import customtkinter as ctk

from app import api_client as services
from app.utils import format_currency
from ui import theme
from ui.widgets import StatusBadge


class ComandaCard(ctk.CTkFrame):
    def __init__(self, parent, cmd: dict, on_open):
        super().__init__(parent, fg_color=theme.BG_PANEL, corner_radius=12, height=120)
        self.pack_propagate(False)

        top = ctk.CTkFrame(self, fg_color="transparent")
        top.pack(fill="x", padx=14, pady=(12, 0))
        ctk.CTkLabel(top, text=f"Comanda #{cmd['number']:04d}", font=theme.font(16, "bold"),
                     text_color=theme.ORANGE).pack(side="left")
        StatusBadge(top, cmd["status"], services.STATUS_LABELS.get(cmd["status"], cmd["status"])).pack(side="right")

        who = cmd.get("customer_name") or "Cliente nao informado"
        if cmd.get("table_ref"):
            who += f"  •  Mesa/Id: {cmd['table_ref']}"
        ctk.CTkLabel(self, text=who, font=theme.font(13), text_color=theme.TEXT_MUTED).pack(
            anchor="w", padx=14, pady=(4, 0)
        )

        bottom = ctk.CTkFrame(self, fg_color="transparent")
        bottom.pack(fill="x", padx=14, pady=(8, 12), side="bottom")
        opened = (cmd.get("opened_at") or "")[11:16]
        item_count = cmd.get("item_count")
        info = f"Aberta as {opened}"
        if item_count is not None:
            info += f"  •  {item_count} item(ns)"
        ctk.CTkLabel(bottom, text=info, font=theme.font(12), text_color=theme.TEXT_MUTED).pack(side="left")
        ctk.CTkLabel(bottom, text=format_currency(cmd["total"]), font=theme.font(18, "bold"),
                     text_color=theme.GOLD).pack(side="right")

        self._bind_open_to_tree(self, on_open, cmd["id"])

    def _bind_open_to_tree(self, widget, on_open, command_id):
        try:
            widget.configure(cursor="hand2")
        except Exception:
            pass
        widget.bind("<Button-1>", lambda e, cid=command_id: on_open(cid))
        for child in widget.winfo_children():
            self._bind_open_to_tree(child, on_open, command_id)


class ComandasAbertasFrame(ctk.CTkFrame):
    def __init__(self, parent, app):
        super().__init__(parent, fg_color=theme.BG_DARK)
        self.app = app

        header = ctk.CTkFrame(self, fg_color="transparent")
        header.pack(fill="x", pady=(0, 14))
        ctk.CTkLabel(header, text="Comandas abertas", font=theme.font_title(26), text_color=theme.TEXT_LIGHT).pack(
            side="left"
        )
        ctk.CTkButton(header, text="🆕 Nova comanda", width=160, command=app.novo_comanda, **theme.PRIMARY_BUTTON).pack(
            side="right", padx=(8, 0)
        )
        ctk.CTkButton(header, text="🔄 Atualizar", width=120, command=self._reload, **theme.NEUTRAL_BUTTON).pack(
            side="right"
        )

        self.scroll = ctk.CTkScrollableFrame(self, fg_color="transparent")
        self.scroll.pack(fill="both", expand=True)
        for i in range(3):
            self.scroll.grid_columnconfigure(i, weight=1)

        self._reload()

    def _open(self, command_id):
        self.app.show_page("comanda_detalhe", command_id=command_id, return_page="comandas_abertas")

    def _reload(self):
        for child in self.scroll.winfo_children():
            child.destroy()
        commands = services.list_open_commands()
        if not commands:
            ctk.CTkLabel(self.scroll, text="Nenhuma comanda em aberto no momento.",
                         font=theme.font(15), text_color=theme.TEXT_MUTED).grid(row=0, column=0, pady=40)
            return
        for idx, cmd in enumerate(commands):
            r, c = divmod(idx, 3)
            card = ComandaCard(self.scroll, cmd, self._open)
            card.grid(row=r, column=c, sticky="nsew", padx=8, pady=8)


class ConsultaComandaFrame(ctk.CTkFrame):
    STATUS_OPTIONS = ["Todos"] + list(services.STATUS_LABELS.values())

    def __init__(self, parent, app):
        super().__init__(parent, fg_color=theme.BG_DARK)
        self.app = app

        ctk.CTkLabel(self, text="Consultar comanda", font=theme.font_title(26), text_color=theme.TEXT_LIGHT).pack(
            anchor="w", pady=(0, 14)
        )

        filters = ctk.CTkFrame(self, fg_color=theme.BG_PANEL, corner_radius=12)
        filters.pack(fill="x", pady=(0, 14))

        row = ctk.CTkFrame(filters, fg_color="transparent")
        row.pack(fill="x", padx=14, pady=14)

        self.query_entry = ctk.CTkEntry(row, placeholder_text="Numero, nome do cliente ou mesa", width=280,
                                         height=38, font=theme.font(13))
        self.query_entry.pack(side="left", padx=(0, 8))
        self.query_entry.bind("<Return>", lambda e: self._search())
        self.after(150, self.query_entry.focus)

        self.status_combo = ctk.CTkComboBox(row, values=self.STATUS_OPTIONS, width=200, height=38,
                                             font=theme.font(13))
        self.status_combo.set("Todos")
        self.status_combo.pack(side="left", padx=8)

        ctk.CTkButton(row, text="Buscar", width=120, height=38, command=self._search,
                      **theme.PRIMARY_BUTTON).pack(side="left", padx=8)
        ctk.CTkButton(row, text="Limpar", width=100, height=38, command=self._clear,
                      **theme.NEUTRAL_BUTTON).pack(side="left")

        self.scroll = ctk.CTkScrollableFrame(self, fg_color="transparent")
        self.scroll.pack(fill="both", expand=True)
        for i in range(3):
            self.scroll.grid_columnconfigure(i, weight=1)

        self._search()

    def _clear(self):
        self.query_entry.delete(0, "end")
        self.status_combo.set("Todos")
        self._search()

    def _status_value(self):
        label = self.status_combo.get()
        if label == "Todos":
            return None
        for key, value in services.STATUS_LABELS.items():
            if value == label:
                return key
        return None

    def _search(self):
        for child in self.scroll.winfo_children():
            child.destroy()
        results = services.search_commands(query=self.query_entry.get().strip(), status=self._status_value())
        if not results:
            ctk.CTkLabel(self.scroll, text="Nenhuma comanda encontrada.", font=theme.font(15),
                         text_color=theme.TEXT_MUTED).grid(row=0, column=0, pady=40)
            return
        for idx, cmd in enumerate(results):
            r, c = divmod(idx, 3)
            card = ComandaCard(
                self.scroll,
                cmd,
                lambda cid: self.app.show_page("comanda_detalhe", command_id=cid, return_page="comanda_consulta"),
            )
            card.grid(row=r, column=c, sticky="nsew", padx=8, pady=8)
