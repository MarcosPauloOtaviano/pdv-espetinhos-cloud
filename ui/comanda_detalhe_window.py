"""Tela de detalhe da comanda: itens, busca de produto, desconto, observacao, finalizar."""
import customtkinter as ctk

from app import api_client as services
from app.api_client import ServiceError
from app.pix import generate_qr_image
from app.utils import format_currency, parse_currency_input
from ui import theme
from ui.widgets import ModalDialog, StatusBadge, show_error, show_success, confirm
from ui.payment_dialog import PaymentDialog

CANCELABLE_STATUSES = ("aberto", "aguardando_pagamento", "fiado")
EDITABLE_STATUSES = ("aberto", "aguardando_pagamento")


class CommandAccessDialog(ModalDialog):
    def __init__(self, parent, command_id: int):
        super().__init__(parent, title="Acesso do cliente", width=580, height=720, resizable=True)
        self.command_id = command_id
        self._qr_image = None
        self._render()

    def _render(self):
        for child in self.winfo_children():
            child.destroy()
        try:
            access = services.get_command_access(self.command_id)
        except ServiceError as exc:
            show_error(self, "Erro", str(exc))
            self.destroy()
            return

        labels = {"sem_acesso": "Nao gerado", "ativo": "Ativo", "revogado": "Revogado"}
        active = access["status"] == "ativo"
        ctk.CTkLabel(self, text="📱 Acesso digital da comanda", font=theme.font(20, "bold"),
                     text_color=theme.ORANGE).pack(pady=(18, 4))
        ctk.CTkLabel(self, text=f"Status: {labels.get(access['status'], access['status'])}",
                     font=theme.font(14, "bold"),
                     text_color=theme.TEXT_SUCCESS if active else theme.TEXT_MUTED).pack(pady=(0, 6))

        if access.get("created_at"):
            details = f"Criado em: {access['created_at']}"
            if access.get("last_regenerated_at"):
                details += f"\nUltima regeneracao: {access['last_regenerated_at']}"
            if access.get("revoked_at"):
                details += f"\nRevogado em: {access['revoked_at']}"
            ctk.CTkLabel(self, text=details, font=theme.font(11), text_color=theme.TEXT_MUTED,
                         justify="center").pack(pady=(0, 8))

        if active:
            image = generate_qr_image(access["access_url"])
            self._qr_image = ctk.CTkImage(light_image=image, dark_image=image, size=(280, 280))
            ctk.CTkLabel(self, text="", image=self._qr_image).pack(pady=8)
            ctk.CTkLabel(self, text="Escaneie para abrir esta mesma comanda.", font=theme.font(12),
                         text_color=theme.TEXT_MUTED).pack(pady=(0, 8))
            link = ctk.CTkEntry(self, width=510, height=36)
            link.insert(0, access["access_url"])
            link.configure(state="readonly")
            link.pack(padx=24, pady=4)
            ctk.CTkButton(self, text="Copiar link", width=150,
                          command=lambda: self._copy_link(access["access_url"]),
                          **theme.NEUTRAL_BUTTON).pack(pady=4)

        actions = ctk.CTkFrame(self, fg_color="transparent")
        actions.pack(pady=12)
        ctk.CTkButton(actions, text="Gerar novo QR Code" if active else "Gerar QR Code", width=180,
                      command=lambda: self._regenerate(active), **theme.GOLD_BUTTON).pack(side="left", padx=6)
        if active:
            ctk.CTkButton(actions, text="Revogar acesso", width=150, command=self._revoke,
                          **theme.DANGER_BUTTON).pack(side="left", padx=6)
        ctk.CTkButton(self, text="Fechar", width=150, command=self.destroy,
                      **theme.NEUTRAL_BUTTON).pack(pady=(0, 14))

    def _copy_link(self, access_url):
        self.clipboard_clear()
        self.clipboard_append(access_url)
        show_success(self, "Link copiado", "O link da comanda foi copiado.")

    def _regenerate(self, has_active_access):
        if has_active_access and not confirm(
            self, "Gerar novo QR Code",
            "O QR Code anterior deixara de funcionar imediatamente. A comanda e os pedidos serao mantidos.",
            confirm_text="Gerar novo", cancel_text="Manter atual",
        ):
            return
        try:
            services.regenerate_command_access(self.command_id)
        except ServiceError as exc:
            show_error(self, "Erro", str(exc))
            return
        self._render()

    def _revoke(self):
        if not confirm(
            self, "Revogar acesso",
            "O cliente perdera o acesso digital, mas a comanda e todos os pedidos continuarao intactos.",
            confirm_text="Revogar", cancel_text="Manter acesso",
        ):
            return
        try:
            services.revoke_command_access(self.command_id)
        except ServiceError as exc:
            show_error(self, "Erro", str(exc))
            return
        self._render()


class ComandaDetalheFrame(ctk.CTkFrame):
    def __init__(self, parent, app, command_id: int, return_page: str = "comandas_abertas"):
        super().__init__(parent, fg_color=theme.BG_DARK)
        self.app = app
        self.command_id = command_id
        self.return_page = return_page
        self.selected_category = None

        root = self.winfo_toplevel()
        self._f4_binding = root.bind("<F4>", lambda e: self._focus_search())
        self._f8_binding = root.bind("<F8>", lambda e: self._finalizar())
        self.bind("<Destroy>", lambda e: self._unbind_shortcuts(root))

        self.grid_columnconfigure(0, weight=2)
        self.grid_columnconfigure(1, weight=3)
        self.grid_rowconfigure(1, weight=1)

        self._build_header()
        self._build_catalog()
        self._build_items_panel()
        self._reload()

    def _unbind_shortcuts(self, root):
        try:
            root.unbind("<F4>", self._f4_binding)
            root.unbind("<F8>", self._f8_binding)
        except Exception:
            pass

    # ------------------------------------------------------------------ HEADER
    def _build_header(self):
        header = ctk.CTkFrame(self, fg_color=theme.BG_PANEL, corner_radius=12)
        header.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, 12))

        left = ctk.CTkFrame(header, fg_color="transparent")
        left.pack(side="left", padx=16, pady=12)
        self.title_label = ctk.CTkLabel(left, text="", font=theme.font(20, "bold"), text_color=theme.ORANGE)
        self.title_label.pack(side="left")
        self.status_holder = ctk.CTkFrame(left, fg_color="transparent")
        self.status_holder.pack(side="left", padx=12)

        mid = ctk.CTkFrame(header, fg_color="transparent")
        mid.pack(side="left", padx=20, pady=12, fill="x", expand=True)
        ctk.CTkLabel(mid, text="Cliente:", font=theme.font(12), text_color=theme.TEXT_MUTED).grid(row=0, column=0, sticky="w")
        self.customer_entry = ctk.CTkEntry(mid, width=180, height=32)
        self.customer_entry.grid(row=0, column=1, padx=(6, 16))
        ctk.CTkLabel(mid, text="Mesa/Id:", font=theme.font(12), text_color=theme.TEXT_MUTED).grid(row=0, column=2, sticky="w")
        self.table_entry = ctk.CTkEntry(mid, width=100, height=32)
        self.table_entry.grid(row=0, column=3, padx=6)
        ctk.CTkButton(mid, text="Salvar", width=90, height=32, command=self._save_customer_info,
                      **theme.NEUTRAL_BUTTON).grid(row=0, column=4, padx=6)

        ctk.CTkButton(header, text="⬅ Voltar", width=110, command=self._go_back,
                      **theme.NEUTRAL_BUTTON).pack(side="right", padx=16)
        if self.app.user.get("role") in ("admin", "garcom"):
            ctk.CTkButton(header, text="📱 Acesso do cliente", width=170,
                          command=lambda: CommandAccessDialog(self, self.command_id),
                          **theme.GOLD_BUTTON).pack(side="right", padx=(0, 4))

    def _go_back(self):
        self.app.show_page(self.return_page)

    def _save_customer_info(self):
        try:
            services.set_customer_info(self.command_id, self.customer_entry.get(), self.table_entry.get())
        except ServiceError as exc:
            show_error(self, "Erro", str(exc))
            return
        self._reload(keep_focus=False)

    # ------------------------------------------------------------------ CATALOGO (esquerda)
    def _build_catalog(self):
        panel = ctk.CTkFrame(self, fg_color=theme.BG_PANEL, corner_radius=12)
        panel.grid(row=1, column=0, sticky="nsew", padx=(0, 8))

        ctk.CTkLabel(panel, text="Produtos", font=theme.font(15, "bold"), text_color=theme.TEXT_LIGHT).pack(
            anchor="w", padx=14, pady=(12, 4)
        )

        self.search_entry = ctk.CTkEntry(panel, placeholder_text="Pesquisar produto... (F4)", height=36)
        self.search_entry.pack(fill="x", padx=14, pady=(0, 6))
        self.search_entry.bind("<KeyRelease>", lambda e: self._reload_catalog())

        categories = services.list_categories()
        cat_names = ["Todas"] + [c["name"] for c in categories]
        self.category_combo = ctk.CTkComboBox(panel, values=cat_names, height=34, command=lambda v: self._reload_catalog())
        self.category_combo.set("Todas")
        self.category_combo.pack(fill="x", padx=14, pady=(0, 8))

        self.catalog_scroll = ctk.CTkScrollableFrame(panel, fg_color="transparent")
        self.catalog_scroll.pack(fill="both", expand=True, padx=8, pady=(0, 10))

        self._reload_catalog()

    def _focus_search(self):
        self.search_entry.focus()

    def _reload_catalog(self):
        for child in self.catalog_scroll.winfo_children():
            child.destroy()

        cat_label = self.category_combo.get()
        category_id = None
        if cat_label != "Todas":
            for c in services.list_categories():
                if c["name"] == cat_label:
                    category_id = c["id"]
                    break

        products = services.list_products(search=self.search_entry.get().strip() or None, category_id=category_id)
        if not products:
            ctk.CTkLabel(self.catalog_scroll, text="Nenhum produto encontrado.", font=theme.font(13),
                         text_color=theme.TEXT_MUTED).pack(pady=20)
            return

        editable = self._is_editable()
        for p in products:
            row = ctk.CTkFrame(self.catalog_scroll, fg_color=theme.BG_PANEL_LIGHT, corner_radius=8)
            row.pack(fill="x", pady=3)
            info = ctk.CTkFrame(row, fg_color="transparent")
            info.pack(side="left", fill="x", expand=True, padx=10, pady=8)
            ctk.CTkLabel(info, text=p["name"], font=theme.font(13, "bold"), text_color=theme.TEXT_LIGHT).pack(anchor="w")
            stock_txt = ""
            if p["track_stock"]:
                low = p["stock"] <= p["low_stock_threshold"]
                stock_txt = f"  •  Estoque: {p['stock']:g}" + ("  ⚠ BAIXO" if low else "")
            ctk.CTkLabel(info, text=format_currency(p["price"]) + stock_txt, font=theme.font(11),
                         text_color=theme.TEXT_DANGER if p["track_stock"] and p["stock"] <= p["low_stock_threshold"] else theme.TEXT_MUTED
                         ).pack(anchor="w")
            add_btn = ctk.CTkButton(row, text="+ Adicionar", width=100, height=32,
                                     command=lambda pid=p["id"]: self._add_product(pid),
                                     state="normal" if editable else "disabled", **theme.PRIMARY_BUTTON)
            add_btn.pack(side="right", padx=10)

    def _add_product(self, product_id):
        try:
            services.add_item(self.command_id, product_id, 1)
        except ServiceError as exc:
            show_error(self, "Nao foi possivel adicionar", str(exc))
            return
        self._reload()

    # ------------------------------------------------------------------ ITENS (direita)
    def _build_items_panel(self):
        panel = ctk.CTkFrame(self, fg_color=theme.BG_PANEL, corner_radius=12)
        panel.grid(row=1, column=1, sticky="nsew")
        panel.grid_rowconfigure(0, weight=1)
        panel.grid_columnconfigure(0, weight=1)

        self.items_scroll = ctk.CTkScrollableFrame(panel, fg_color="transparent", label_text="Itens da comanda")
        self.items_scroll.grid(row=0, column=0, sticky="nsew", padx=10, pady=(10, 4))

        bottom = ctk.CTkFrame(panel, fg_color=theme.BG_PANEL_LIGHT, corner_radius=10)
        bottom.grid(row=1, column=0, sticky="ew", padx=10, pady=10)

        obs_row = ctk.CTkFrame(bottom, fg_color="transparent")
        obs_row.pack(fill="x", padx=12, pady=(12, 4))
        ctk.CTkLabel(obs_row, text="Observacao:", font=theme.font(12), text_color=theme.TEXT_MUTED).pack(anchor="w")
        self.notes_entry = ctk.CTkEntry(obs_row, height=32)
        self.notes_entry.pack(side="left", fill="x", expand=True, padx=(0, 8))
        ctk.CTkButton(obs_row, text="Salvar", width=90, height=32, command=self._save_notes,
                      **theme.NEUTRAL_BUTTON).pack(side="left")

        disc_row = ctk.CTkFrame(bottom, fg_color="transparent")
        disc_row.pack(fill="x", padx=12, pady=4)
        ctk.CTkLabel(disc_row, text="Desconto (R$):", font=theme.font(12), text_color=theme.TEXT_MUTED).pack(side="left")
        self.discount_entry = ctk.CTkEntry(disc_row, width=100, height=32)
        self.discount_entry.pack(side="left", padx=8)
        ctk.CTkButton(disc_row, text="Aplicar", width=90, height=32, command=self._save_discount,
                      **theme.NEUTRAL_BUTTON).pack(side="left")

        totals_row = ctk.CTkFrame(bottom, fg_color="transparent")
        totals_row.pack(fill="x", padx=12, pady=(8, 4))
        self.subtotal_label = ctk.CTkLabel(totals_row, text="Subtotal: R$ 0,00", font=theme.font(13),
                                            text_color=theme.TEXT_MUTED)
        self.subtotal_label.pack(side="left")
        self.discount_label = ctk.CTkLabel(totals_row, text="", font=theme.font(13), text_color=theme.TEXT_DANGER)
        self.discount_label.pack(side="left", padx=16)

        total_row = ctk.CTkFrame(bottom, fg_color="transparent")
        total_row.pack(fill="x", padx=12, pady=(0, 12))
        ctk.CTkLabel(total_row, text="TOTAL", font=theme.font(16, "bold"), text_color=theme.TEXT_LIGHT).pack(side="left")
        self.total_label = ctk.CTkLabel(total_row, text="R$ 0,00", font=theme.font(30, "bold"), text_color=theme.GOLD)
        self.total_label.pack(side="right")

        actions = ctk.CTkFrame(panel, fg_color="transparent")
        actions.grid(row=2, column=0, sticky="ew", padx=10, pady=(0, 10))
        self.cancel_btn = ctk.CTkButton(actions, text="Cancelar comanda", width=150, command=self._cancelar,
                                         **theme.DANGER_BUTTON)
        self.cancel_btn.pack(side="left", padx=(0, 8))
        self.fiado_btn = ctk.CTkButton(actions, text="Marcar fiado/pendente", width=180, command=self._marcar_fiado,
                                        **theme.GOLD_BUTTON)
        self.fiado_btn.pack(side="left", padx=8)
        self.finalize_btn = ctk.CTkButton(actions, text="Finalizar comanda (F8)", width=220, height=44,
                                           font=theme.font(15, "bold"), command=self._finalizar,
                                           **theme.SUCCESS_BUTTON)
        self.finalize_btn.pack(side="right")

    def _save_notes(self):
        services.set_notes(self.command_id, self.notes_entry.get())
        show_success(self, "Salvo", "Observacao atualizada.")

    def _save_discount(self):
        try:
            services.set_discount(self.command_id, parse_currency_input(self.discount_entry.get()))
        except ServiceError as exc:
            show_error(self, "Erro", str(exc))
            return
        self._reload(keep_focus=False)

    def _is_editable(self):
        cmd = services.get_command(self.command_id)
        return cmd and cmd["status"] in EDITABLE_STATUSES

    def _cancelar(self):
        cmd = services.get_command(self.command_id)
        if not cmd:
            show_error(self, "Erro", "Comanda nao encontrada.")
            self._go_back()
            return
        extra = "\n\nComo esta comanda esta fiado/pendente, o estoque dos itens sera devolvido." if cmd["status"] == "fiado" else ""
        if not confirm(
            self,
            "Cancelar comanda",
            f"Tem certeza que deseja cancelar esta comanda? Essa acao nao pode ser desfeita.{extra}",
            confirm_text="Sim, cancelar",
            cancel_text="Manter comanda",
        ):
            return
        try:
            services.cancel_command(self.command_id)
        except ServiceError as exc:
            show_error(self, "Erro", str(exc))
            return
        show_success(self, "Comanda cancelada", "A comanda foi cancelada.")
        self._go_back()

    def _marcar_fiado(self):
        if not confirm(
            self,
            "Marcar como fiado",
            "Confirma marcar esta comanda como fiado/pendente? O estoque sera baixado normalmente.",
            confirm_text="Sim, marcar fiado",
            cancel_text="Voltar",
        ):
            return
        try:
            services.mark_as_pending(self.command_id)
        except ServiceError as exc:
            show_error(self, "Erro", str(exc))
            return
        show_success(self, "Comanda pendente", "A comanda foi marcada como fiado/pendente.")
        self._go_back()

    def _finalizar(self):
        cmd = services.get_command(self.command_id)
        if not cmd:
            return
        if not cmd["items"]:
            show_error(self, "Comanda vazia", "Adicione ao menos um item antes de finalizar.")
            return
        if cmd["status"] not in ("aberto", "aguardando_pagamento", "fiado"):
            show_error(self, "Nao permitido", f"Comanda ja esta '{services.STATUS_LABELS.get(cmd['status'])}'.")
            return
        PaymentDialog(self, self.app, cmd, on_finished=self._go_back)

    # ------------------------------------------------------------------ RELOAD
    def _reload(self, keep_focus=True):
        cmd = services.get_command(self.command_id)
        if not cmd:
            show_error(self, "Erro", "Comanda nao encontrada.")
            self._go_back()
            return

        self.title_label.configure(text=f"Comanda #{cmd['number']:04d}")
        for child in self.status_holder.winfo_children():
            child.destroy()
        StatusBadge(self.status_holder, cmd["status"], services.STATUS_LABELS.get(cmd["status"], cmd["status"])).pack()

        if not self.customer_entry.get():
            self.customer_entry.insert(0, cmd.get("customer_name") or "")
        if not self.table_entry.get():
            self.table_entry.insert(0, cmd.get("table_ref") or "")
        if not self.notes_entry.get():
            self.notes_entry.insert(0, cmd.get("notes") or "")
        if not self.discount_entry.get():
            self.discount_entry.insert(0, f"{cmd['discount']:.2f}" if cmd["discount"] else "0.00")

        editable = cmd["status"] in EDITABLE_STATUSES

        for child in self.items_scroll.winfo_children():
            child.destroy()

        if not cmd["items"]:
            ctk.CTkLabel(self.items_scroll, text="Nenhum item adicionado ainda.\nUse o painel a esquerda para adicionar produtos.",
                         font=theme.font(13), text_color=theme.TEXT_MUTED, justify="center").pack(pady=30)
        else:
            for item in cmd["items"]:
                self._build_item_row(item, editable)

        self.subtotal_label.configure(text=f"Subtotal: {format_currency(cmd['subtotal'])}")
        if cmd["discount"]:
            self.discount_label.configure(text=f"Desconto: -{format_currency(cmd['discount'])}")
        else:
            self.discount_label.configure(text="")
        self.total_label.configure(text=format_currency(cmd["total"]))

        for payment in cmd.get("payments", []):
            self._render_payment_summary(payment)

        state = "normal" if editable else "disabled"
        self.cancel_btn.configure(state="normal" if cmd["status"] in CANCELABLE_STATUSES else "disabled")
        self.fiado_btn.configure(state=state if cmd["status"] == "aberto" else "disabled")
        self.finalize_btn.configure(state="normal" if cmd["status"] in ("aberto", "aguardando_pagamento", "fiado") else "disabled")

        self._reload_catalog()

    def _render_payment_summary(self, payment):
        line = ctk.CTkFrame(self.items_scroll, fg_color=theme.BG_PANEL_LIGHT, corner_radius=8)
        line.pack(fill="x", pady=2)
        label = services.PAYMENT_METHOD_LABELS.get(payment["method"], payment["method"])
        text = f"Pagamento: {label} - {format_currency(payment['amount'])}"
        if payment.get("change_amount"):
            text += f" (troco {format_currency(payment['change_amount'])})"
        ctk.CTkLabel(line, text=text, font=theme.font(12), text_color=theme.TEXT_SUCCESS).pack(anchor="w", padx=10, pady=6)

    def _build_item_row(self, item, editable):
        row = ctk.CTkFrame(self.items_scroll, fg_color=theme.BG_PANEL_LIGHT, corner_radius=8)
        row.pack(fill="x", pady=3)

        info = ctk.CTkFrame(row, fg_color="transparent")
        info.pack(side="left", fill="x", expand=True, padx=10, pady=8)
        ctk.CTkLabel(info, text=item["product_name"], font=theme.font(13, "bold"),
                     text_color=theme.TEXT_LIGHT).pack(anchor="w")
        ctk.CTkLabel(info, text=f"{format_currency(item['unit_price'])} / un", font=theme.font(11),
                     text_color=theme.TEXT_MUTED).pack(anchor="w")

        qty_frame = ctk.CTkFrame(row, fg_color="transparent")
        qty_frame.pack(side="left", padx=10)
        ctk.CTkButton(qty_frame, text="-", width=30, height=30,
                      command=lambda: self._change_qty(item, -1), state="normal" if editable else "disabled",
                      **theme.NEUTRAL_BUTTON).pack(side="left")
        ctk.CTkLabel(qty_frame, text=f"{item['quantity']:g}", width=40, font=theme.font(13, "bold")).pack(side="left")
        ctk.CTkButton(qty_frame, text="+", width=30, height=30,
                      command=lambda: self._change_qty(item, 1), state="normal" if editable else "disabled",
                      **theme.NEUTRAL_BUTTON).pack(side="left")

        ctk.CTkLabel(row, text=format_currency(item["subtotal"]), font=theme.font(14, "bold"),
                     text_color=theme.GOLD, width=100).pack(side="left", padx=10)

        ctk.CTkButton(row, text="✕", width=32, height=32, command=lambda: self._remove_item(item),
                      state="normal" if editable else "disabled", **theme.DANGER_BUTTON).pack(side="right", padx=10)

    def _change_qty(self, item, delta):
        new_qty = item["quantity"] + delta
        try:
            if new_qty <= 0:
                services.remove_item(item["id"])
            else:
                services.update_item_quantity(item["id"], new_qty)
        except ServiceError as exc:
            show_error(self, "Erro", str(exc))
            return
        self._reload()

    def _remove_item(self, item):
        try:
            services.remove_item(item["id"])
        except ServiceError as exc:
            show_error(self, "Erro", str(exc))
            return
        self._reload()
