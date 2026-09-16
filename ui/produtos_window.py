"""Cadastro de produtos e categorias."""
import customtkinter as ctk

from app import api_client as services
from app.api_client import ServiceError
from app.utils import format_currency, parse_currency_input
from ui import theme
from ui.widgets import ModalDialog, show_error, show_success, confirm


class CategoryDialog(ModalDialog):
    def __init__(self, parent, on_saved):
        super().__init__(parent, title="Nova categoria", width=380, height=220)
        self.on_saved = on_saved
        ctk.CTkLabel(self, text="Nome da categoria", font=theme.font(14, "bold")).pack(pady=(24, 6))
        self.name_entry = ctk.CTkEntry(self, width=280, height=38)
        self.name_entry.pack(pady=6)
        ctk.CTkButton(self, text="Salvar", width=200, command=self._save, **theme.PRIMARY_BUTTON).pack(pady=18)

    def _save(self):
        try:
            services.create_category(self.name_entry.get())
        except ServiceError as exc:
            show_error(self, "Erro", str(exc))
            return
        self.destroy()
        self.on_saved()


class ProductDialog(ModalDialog):
    def __init__(self, parent, on_saved, product=None):
        title = "Editar produto" if product else "Novo produto"
        super().__init__(parent, title=title, width=460, height=560)
        self.on_saved = on_saved
        self.product = product

        form = ctk.CTkFrame(self, fg_color="transparent")
        form.pack(fill="both", expand=True, padx=24, pady=20)

        ctk.CTkLabel(form, text="Nome do produto", font=theme.font(12), text_color=theme.TEXT_MUTED).pack(anchor="w")
        self.name_entry = ctk.CTkEntry(form, height=38)
        self.name_entry.pack(fill="x", pady=(2, 12))

        ctk.CTkLabel(form, text="Categoria", font=theme.font(12), text_color=theme.TEXT_MUTED).pack(anchor="w")
        categories = services.list_categories()
        self.category_map = {c["name"]: c["id"] for c in categories}
        self.category_combo = ctk.CTkComboBox(form, values=list(self.category_map.keys()) or ["Sem categoria"], height=38)
        self.category_combo.pack(fill="x", pady=(2, 12))

        price_row = ctk.CTkFrame(form, fg_color="transparent")
        price_row.pack(fill="x", pady=(0, 12))
        left = ctk.CTkFrame(price_row, fg_color="transparent")
        left.pack(side="left", fill="x", expand=True)
        ctk.CTkLabel(left, text="Preco de venda (R$)", font=theme.font(12), text_color=theme.TEXT_MUTED).pack(anchor="w")
        self.price_entry = ctk.CTkEntry(left, height=38)
        self.price_entry.pack(fill="x", pady=2)
        right = ctk.CTkFrame(price_row, fg_color="transparent")
        right.pack(side="left", fill="x", expand=True, padx=(12, 0))
        ctk.CTkLabel(right, text="Custo (opcional)", font=theme.font(12), text_color=theme.TEXT_MUTED).pack(anchor="w")
        self.cost_entry = ctk.CTkEntry(right, height=38)
        self.cost_entry.pack(fill="x", pady=2)

        self.track_stock_var = ctk.BooleanVar(value=False)
        ctk.CTkCheckBox(form, text="Controlar estoque deste produto", variable=self.track_stock_var,
                         command=self._toggle_stock_fields).pack(anchor="w", pady=(4, 8))

        self.stock_frame = ctk.CTkFrame(form, fg_color="transparent")
        self.stock_frame.pack(fill="x", pady=(0, 12))
        stock_left = ctk.CTkFrame(self.stock_frame, fg_color="transparent")
        stock_left.pack(side="left", fill="x", expand=True)
        ctk.CTkLabel(stock_left, text="Estoque atual", font=theme.font(12), text_color=theme.TEXT_MUTED).pack(anchor="w")
        self.stock_entry = ctk.CTkEntry(stock_left, height=38)
        self.stock_entry.pack(fill="x", pady=2)
        stock_right = ctk.CTkFrame(self.stock_frame, fg_color="transparent")
        stock_right.pack(side="left", fill="x", expand=True, padx=(12, 0))
        ctk.CTkLabel(stock_right, text="Alerta de estoque baixo", font=theme.font(12), text_color=theme.TEXT_MUTED).pack(anchor="w")
        self.low_stock_entry = ctk.CTkEntry(stock_right, height=38)
        self.low_stock_entry.pack(fill="x", pady=2)

        ctk.CTkLabel(form, text="Observacao", font=theme.font(12), text_color=theme.TEXT_MUTED).pack(anchor="w")
        self.notes_entry = ctk.CTkEntry(form, height=38)
        self.notes_entry.pack(fill="x", pady=(2, 12))

        self.active_var = ctk.BooleanVar(value=True)
        ctk.CTkCheckBox(form, text="Produto ativo", variable=self.active_var).pack(anchor="w", pady=(0, 12))

        ctk.CTkButton(form, text="Salvar produto", height=44, font=theme.font(14, "bold"),
                      command=self._save, **theme.PRIMARY_BUTTON).pack(fill="x", pady=(6, 0))

        if product:
            self._fill_from_product(product, categories)
        else:
            self.stock_entry.insert(0, "0")
            self.low_stock_entry.insert(0, "5")
            self._toggle_stock_fields()

    def _fill_from_product(self, product, categories):
        self.name_entry.insert(0, product["name"])
        cat_name = next((c["name"] for c in categories if c["id"] == product["category_id"]), "")
        if cat_name:
            self.category_combo.set(cat_name)
        self.price_entry.insert(0, f"{product['price']:.2f}")
        self.cost_entry.insert(0, f"{product['cost']:.2f}")
        self.track_stock_var.set(bool(product["track_stock"]))
        self.stock_entry.insert(0, f"{product['stock']:g}")
        self.low_stock_entry.insert(0, f"{product['low_stock_threshold']:g}")
        self.notes_entry.insert(0, product.get("notes") or "")
        self.active_var.set(bool(product["active"]))
        self._toggle_stock_fields()

    def _toggle_stock_fields(self):
        state = "normal" if self.track_stock_var.get() else "disabled"
        self.stock_entry.configure(state=state)
        self.low_stock_entry.configure(state=state)

    def _save(self):
        name = self.name_entry.get()
        category_id = self.category_map.get(self.category_combo.get())
        price = parse_currency_input(self.price_entry.get())
        cost = parse_currency_input(self.cost_entry.get())
        track_stock = self.track_stock_var.get()
        stock = parse_currency_input(self.stock_entry.get()) if track_stock else 0
        low_stock = parse_currency_input(self.low_stock_entry.get()) if track_stock else 5
        notes = self.notes_entry.get()
        active = self.active_var.get()

        try:
            if self.product:
                services.update_product(self.product["id"], name, category_id, price, cost, track_stock,
                                         stock, low_stock, notes, active)
            else:
                services.create_product(name, category_id, price, cost, track_stock, stock, low_stock, notes, active)
        except ServiceError as exc:
            show_error(self, "Erro", str(exc))
            return
        self.destroy()
        self.on_saved()


class ProdutosFrame(ctk.CTkFrame):
    def __init__(self, parent, app):
        super().__init__(parent, fg_color=theme.BG_DARK)
        self.app = app
        self.is_admin = app.user["role"] == "admin"
        self.show_inactive = False

        header = ctk.CTkFrame(self, fg_color="transparent")
        header.pack(fill="x", pady=(0, 12))
        ctk.CTkLabel(header, text="Produtos", font=theme.font_title(26), text_color=theme.TEXT_LIGHT).pack(side="left")
        if self.is_admin:
            ctk.CTkButton(header, text="+ Nova categoria", width=160, command=self._new_category,
                          **theme.NEUTRAL_BUTTON).pack(side="right", padx=(8, 0))
            ctk.CTkButton(header, text="+ Novo produto", width=160, command=self._new_product,
                          **theme.PRIMARY_BUTTON).pack(side="right")

        filters = ctk.CTkFrame(self, fg_color=theme.BG_PANEL, corner_radius=12)
        filters.pack(fill="x", pady=(0, 12))
        row = ctk.CTkFrame(filters, fg_color="transparent")
        row.pack(fill="x", padx=14, pady=12)
        self.search_entry = ctk.CTkEntry(row, placeholder_text="Pesquisar produto", width=260, height=36)
        self.search_entry.pack(side="left", padx=(0, 8))
        self.search_entry.bind("<KeyRelease>", lambda e: self._reload())
        categories = services.list_categories()
        self.category_combo = ctk.CTkComboBox(row, values=["Todas"] + [c["name"] for c in categories], width=200,
                                               height=36, command=lambda v: self._reload())
        self.category_combo.set("Todas")
        self.category_combo.pack(side="left", padx=8)
        self.inactive_var = ctk.BooleanVar(value=False)
        ctk.CTkCheckBox(row, text="Mostrar inativos", variable=self.inactive_var,
                         command=self._reload).pack(side="left", padx=12)

        self.scroll = ctk.CTkScrollableFrame(self, fg_color="transparent")
        self.scroll.pack(fill="both", expand=True)

        self._reload()

    def _new_category(self):
        CategoryDialog(self, on_saved=self._reload)

    def _new_product(self):
        ProductDialog(self, on_saved=self._reload)

    def _edit_product(self, product):
        ProductDialog(self, on_saved=self._reload, product=product)

    def _toggle_active(self, product):
        services.set_product_active(product["id"], not product["active"])
        self._reload()

    def _delete_product(self, product):
        if not confirm(self, "Excluir produto", f"Tem certeza que deseja excluir '{product['name']}'?"):
            return
        services.delete_product(product["id"])
        show_success(self, "Produto removido", "Produto excluido ou desativado (caso ja tenha vendas registradas).")
        self._reload()

    def _reload(self):
        for child in self.scroll.winfo_children():
            child.destroy()

        category_id = None
        cat_label = self.category_combo.get()
        if cat_label != "Todas":
            for c in services.list_categories():
                if c["name"] == cat_label:
                    category_id = c["id"]
                    break

        products = services.list_products(search=self.search_entry.get().strip() or None,
                                           category_id=category_id, only_active=not self.inactive_var.get())
        if not products:
            ctk.CTkLabel(self.scroll, text="Nenhum produto cadastrado.", font=theme.font(14),
                         text_color=theme.TEXT_MUTED).pack(pady=30)
            return

        for p in products:
            row = ctk.CTkFrame(self.scroll, fg_color=theme.BG_PANEL, corner_radius=10)
            row.pack(fill="x", pady=4)

            info = ctk.CTkFrame(row, fg_color="transparent")
            info.pack(side="left", fill="x", expand=True, padx=14, pady=10)
            name_color = theme.TEXT_LIGHT if p["active"] else theme.TEXT_MUTED
            ctk.CTkLabel(info, text=p["name"] + ("" if p["active"] else "  (inativo)"),
                         font=theme.font(14, "bold"), text_color=name_color).pack(anchor="w")
            sub = p.get("category_name") or "Sem categoria"
            if p["track_stock"]:
                sub += f"  •  Estoque: {p['stock']:g}"
                if p["stock"] <= p["low_stock_threshold"]:
                    sub += "  ⚠ ESTOQUE BAIXO"
            ctk.CTkLabel(info, text=sub, font=theme.font(11), text_color=theme.TEXT_MUTED).pack(anchor="w")

            ctk.CTkLabel(row, text=format_currency(p["price"]), font=theme.font(15, "bold"),
                         text_color=theme.GOLD, width=100).pack(side="left", padx=10)

            if self.is_admin:
                actions = ctk.CTkFrame(row, fg_color="transparent")
                actions.pack(side="right", padx=10)
                ctk.CTkButton(actions, text="Editar", width=80, height=32, command=lambda p=p: self._edit_product(p),
                              **theme.NEUTRAL_BUTTON).pack(side="left", padx=4)
                toggle_text = "Desativar" if p["active"] else "Ativar"
                ctk.CTkButton(actions, text=toggle_text, width=90, height=32,
                              command=lambda p=p: self._toggle_active(p), **theme.GOLD_BUTTON).pack(side="left", padx=4)
                ctk.CTkButton(actions, text="Excluir", width=80, height=32, command=lambda p=p: self._delete_product(p),
                              **theme.DANGER_BUTTON).pack(side="left", padx=4)
