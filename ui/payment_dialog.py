"""Modal de finalizacao de pagamento: dinheiro (troco), Pix (QR EMV), cartao e misto."""
import customtkinter as ctk
from PIL import Image

from app import api_client as services, pix as pix_module
from app.api_client import ServiceError
from app.utils import format_currency, parse_currency_input
from ui import theme
from ui.widgets import ModalDialog, show_error, show_success


class PaymentDialog(ModalDialog):
    def __init__(self, parent, app, command: dict, on_finished):
        super().__init__(parent, title=f"Finalizar Comanda #{command['number']:04d}", width=680, height=650, resizable=True)
        self.app = app
        self.command = command
        self.total = command["total"]
        self.on_finished = on_finished
        self.misto_rows = []  # list of dicts {method, amount, received}

        header = ctk.CTkFrame(self, fg_color=theme.BG_PANEL, corner_radius=12)
        header.pack(fill="x", padx=16, pady=(16, 8))
        ctk.CTkLabel(header, text=f"Comanda #{command['number']:04d}", font=theme.font(15, "bold"),
                     text_color=theme.TEXT_LIGHT).pack(side="left", padx=16, pady=12)
        ctk.CTkLabel(header, text="TOTAL A PAGAR", font=theme.font(12), text_color=theme.TEXT_MUTED).pack(
            side="left", padx=(30, 6)
        )
        ctk.CTkLabel(header, text=format_currency(self.total), font=theme.font(26, "bold"),
                     text_color=theme.GOLD).pack(side="left")

        self.tabs = ctk.CTkTabview(self, fg_color=theme.BG_PANEL,
                                    segmented_button_selected_color=theme.ORANGE,
                                    segmented_button_selected_hover_color=theme.ORANGE_HOVER)
        self.tabs.pack(fill="both", expand=True, padx=16, pady=8)
        self.tabs.add("Dinheiro")
        self.tabs.add("Pix")
        self.tabs.add("Cartao")
        self.tabs.add("Misto")

        self._build_dinheiro_tab()
        self._build_pix_tab()
        self._build_cartao_tab()
        self._build_misto_tab()

    # ------------------------------------------------------------------ DINHEIRO
    def _build_dinheiro_tab(self):
        tab = self.tabs.tab("Dinheiro")
        ctk.CTkLabel(tab, text=f"Total da comanda: {format_currency(self.total)}", font=theme.font(16, "bold"),
                     text_color=theme.TEXT_LIGHT).pack(pady=(20, 10))

        ctk.CTkLabel(tab, text="Valor recebido do cliente", font=theme.font(13), text_color=theme.TEXT_MUTED).pack()
        self.recebido_entry = ctk.CTkEntry(tab, width=220, height=44, font=theme.font(18, "bold"), justify="center")
        self.recebido_entry.pack(pady=8)
        self.recebido_entry.insert(0, f"{self.total:.2f}")
        self.recebido_entry.bind("<KeyRelease>", lambda e: self._update_troco())

        ctk.CTkLabel(tab, text="TROCO", font=theme.font(13, "bold"), text_color=theme.TEXT_MUTED).pack(pady=(18, 0))
        self.troco_label = ctk.CTkLabel(tab, text=format_currency(0), font=theme.font(36, "bold"),
                                         text_color=theme.GREEN)
        self.troco_label.pack(pady=(0, 20))

        ctk.CTkButton(tab, text="Confirmar pagamento em dinheiro", height=48, width=320,
                      font=theme.font(15, "bold"), command=self._confirm_dinheiro,
                      **theme.SUCCESS_BUTTON).pack(pady=8)
        self._update_troco()

    def _update_troco(self):
        received = parse_currency_input(self.recebido_entry.get())
        troco = round(received - self.total, 2)
        color = theme.GREEN if troco >= 0 else theme.TEXT_DANGER
        self.troco_label.configure(text=format_currency(troco), text_color=color)

    def _confirm_dinheiro(self):
        received = parse_currency_input(self.recebido_entry.get())
        if received < self.total:
            show_error(self, "Valor insuficiente", "O valor recebido nao pode ser menor que o total da comanda.")
            return
        self._finalize([{"method": "dinheiro", "amount": self.total, "received_amount": received}])

    # ------------------------------------------------------------------ PIX
    def _build_pix_tab(self):
        tab = self.tabs.tab("Pix")
        pix_key = services.get_setting("pix_key", "")

        if not pix_key:
            ctk.CTkLabel(
                tab, text="Chave Pix nao configurada.\nVa em Configuracoes > Pix para cadastrar.",
                font=theme.font(14), text_color=theme.TEXT_DANGER, justify="center"
            ).pack(pady=60)
            return

        try:
            payload = pix_module.build_pix_payload(
                pix_key=pix_key,
                merchant_name=services.get_setting("pix_receiver_name", "ESPETINHO DUDAIR"),
                merchant_city=services.get_setting("pix_city", "SAO PAULO"),
                amount=self.total,
                description=services.get_setting("pix_description", ""),
                txid=f"CMD{self.command['number']}",
            )
            qr_image = pix_module.generate_qr_image(payload)
        except Exception as exc:
            ctk.CTkLabel(tab, text=f"Erro ao gerar Pix: {exc}", font=theme.font(13),
                         text_color=theme.TEXT_DANGER).pack(pady=40)
            return

        content = ctk.CTkFrame(tab, fg_color="transparent")
        content.pack(fill="both", expand=True, pady=10)

        left = ctk.CTkFrame(content, fg_color="transparent")
        left.pack(side="left", padx=20)
        ctk_image = ctk.CTkImage(light_image=qr_image, dark_image=qr_image, size=(220, 220))
        ctk.CTkLabel(left, text="", image=ctk_image).pack()
        ctk.CTkLabel(left, text=format_currency(self.total), font=theme.font(18, "bold"),
                     text_color=theme.GOLD).pack(pady=(8, 0))

        right = ctk.CTkFrame(content, fg_color="transparent")
        right.pack(side="left", fill="both", expand=True, padx=10)
        ctk.CTkLabel(right, text="Codigo Pix copia e cola:", font=theme.font(13), text_color=theme.TEXT_MUTED).pack(
            anchor="w"
        )
        code_box = ctk.CTkTextbox(right, height=110, font=theme.font(11), wrap="char")
        code_box.pack(fill="x", pady=6)
        code_box.insert("1.0", payload)
        code_box.configure(state="disabled")

        def _copy():
            self.clipboard_clear()
            self.clipboard_append(payload)
            show_success(self, "Copiado", "Codigo Pix copiado para a area de transferencia.")

        ctk.CTkButton(right, text="📋 Copiar codigo", height=36, command=_copy, **theme.NEUTRAL_BUTTON).pack(
            fill="x", pady=(0, 10)
        )

        ctk.CTkLabel(
            right, text="1. Cliente escaneia o QR ou cola o codigo no app do banco.\n"
                        "2. Cliente paga o valor exato.\n"
                        "3. Atendente confere o recebimento e confirma abaixo.",
            font=theme.font(11), text_color=theme.TEXT_MUTED, justify="left"
        ).pack(anchor="w", pady=(4, 10))

        ctk.CTkButton(right, text="✅ Confirmar pagamento Pix", height=44, font=theme.font(14, "bold"),
                      command=lambda: self._confirm_pix(), **theme.SUCCESS_BUTTON).pack(fill="x")

    def _confirm_pix(self):
        self._finalize([{"method": "pix", "amount": self.total, "pix_confirmed": True}])

    # ------------------------------------------------------------------ CARTAO
    def _build_cartao_tab(self):
        tab = self.tabs.tab("Cartao")
        ctk.CTkLabel(tab, text=f"Total da comanda: {format_currency(self.total)}", font=theme.font(16, "bold"),
                     text_color=theme.TEXT_LIGHT).pack(pady=(30, 20))

        ctk.CTkLabel(tab, text="Selecione o tipo de cartao:", font=theme.font(13),
                     text_color=theme.TEXT_MUTED).pack()

        row = ctk.CTkFrame(tab, fg_color="transparent")
        row.pack(pady=20)
        ctk.CTkButton(row, text="💳 Cartao de Debito", width=220, height=60, font=theme.font(15, "bold"),
                      command=lambda: self._confirm_cartao("debito"), **theme.PRIMARY_BUTTON).pack(
            side="left", padx=10
        )
        ctk.CTkButton(row, text="💳 Cartao de Credito", width=220, height=60, font=theme.font(15, "bold"),
                      command=lambda: self._confirm_cartao("credito"), **theme.GOLD_BUTTON).pack(
            side="left", padx=10
        )

    def _confirm_cartao(self, card_type):
        self._finalize([{"method": card_type, "amount": self.total}])

    # ------------------------------------------------------------------ MISTO
    def _build_misto_tab(self):
        tab = self.tabs.tab("Misto")

        form = ctk.CTkFrame(tab, fg_color=theme.BG_PANEL_LIGHT, corner_radius=10)
        form.pack(fill="x", padx=10, pady=(14, 8))

        ctk.CTkLabel(form, text="Forma:", font=theme.font(12)).grid(row=0, column=0, padx=(12, 4), pady=12)
        self.misto_method_combo = ctk.CTkComboBox(
            form, values=["Dinheiro", "Pix", "Cartao de Debito", "Cartao de Credito"], width=170
        )
        self.misto_method_combo.set("Dinheiro")
        self.misto_method_combo.grid(row=0, column=1, padx=4)

        ctk.CTkLabel(form, text="Valor:", font=theme.font(12)).grid(row=0, column=2, padx=(12, 4))
        self.misto_amount_entry = ctk.CTkEntry(form, width=110)
        self.misto_amount_entry.grid(row=0, column=3, padx=4)

        ctk.CTkButton(form, text="+ Adicionar", width=110, command=self._add_misto_row,
                      **theme.PRIMARY_BUTTON).grid(row=0, column=4, padx=12)

        self.misto_list_frame = ctk.CTkScrollableFrame(tab, fg_color="transparent", height=180)
        self.misto_list_frame.pack(fill="both", expand=True, padx=10, pady=8)

        totals = ctk.CTkFrame(tab, fg_color="transparent")
        totals.pack(fill="x", padx=10)
        self.misto_atribuido_label = ctk.CTkLabel(totals, text="Atribuido: R$ 0,00", font=theme.font(13, "bold"))
        self.misto_atribuido_label.pack(side="left", padx=10)
        self.misto_restante_label = ctk.CTkLabel(totals, text="Restante: R$ 0,00", font=theme.font(13, "bold"),
                                                  text_color=theme.GOLD)
        self.misto_restante_label.pack(side="left", padx=10)

        ctk.CTkButton(tab, text="✅ Finalizar pagamento misto", height=46, font=theme.font(14, "bold"),
                      command=self._confirm_misto, **theme.SUCCESS_BUTTON).pack(pady=12)

        self._refresh_misto_list()

    def _add_misto_row(self):
        label_to_method = {
            "Dinheiro": "dinheiro", "Pix": "pix", "Cartao de Debito": "debito", "Cartao de Credito": "credito"
        }
        method = label_to_method[self.misto_method_combo.get()]
        amount = parse_currency_input(self.misto_amount_entry.get())
        if amount <= 0:
            show_error(self, "Valor invalido", "Informe um valor maior que zero.")
            return
        row = {"method": method, "amount": amount}
        if method == "dinheiro":
            row["received_amount"] = amount
        self.misto_rows.append(row)
        self.misto_amount_entry.delete(0, "end")
        self._refresh_misto_list()

    def _remove_misto_row(self, index):
        del self.misto_rows[index]
        self._refresh_misto_list()

    def _refresh_misto_list(self):
        for child in self.misto_list_frame.winfo_children():
            child.destroy()
        for idx, row in enumerate(self.misto_rows):
            line = ctk.CTkFrame(self.misto_list_frame, fg_color=theme.BG_PANEL, corner_radius=8)
            line.pack(fill="x", pady=3)
            label = services.PAYMENT_METHOD_LABELS.get(row["method"], row["method"])
            ctk.CTkLabel(line, text=f"{label}", font=theme.font(12)).pack(side="left", padx=12, pady=8)
            ctk.CTkLabel(line, text=format_currency(row["amount"]), font=theme.font(12, "bold"),
                         text_color=theme.GOLD).pack(side="left", padx=12)
            ctk.CTkButton(line, text="Remover", width=80, height=26, command=lambda i=idx: self._remove_misto_row(i),
                          **theme.DANGER_BUTTON).pack(side="right", padx=8, pady=6)

        atribuido = sum(r["amount"] for r in self.misto_rows)
        restante = round(self.total - atribuido, 2)
        self.misto_atribuido_label.configure(text=f"Atribuido: {format_currency(atribuido)}")
        self.misto_restante_label.configure(
            text=f"Restante: {format_currency(restante)}",
            text_color=theme.GREEN if abs(restante) < 0.01 else theme.GOLD,
        )

    def _confirm_misto(self):
        if len(self.misto_rows) < 2:
            show_error(self, "Pagamento misto", "Adicione ao menos duas formas de pagamento diferentes.")
            return
        self._finalize(list(self.misto_rows))

    # ------------------------------------------------------------------
    def _finalize(self, payments):
        try:
            result = services.finalize_command(self.command["id"], payments)
        except ServiceError as exc:
            show_error(self, "Nao foi possivel finalizar", str(exc))
            return
        self.destroy()
        troco_msg = ""
        for p in result["payments"]:
            if p.get("method") == "dinheiro" and p.get("received_amount"):
                troco = round(p["received_amount"] - p["amount"], 2)
                if troco > 0:
                    troco_msg = f"\nTroco entregue: {format_currency(troco)}"
        show_success(self.app, "Pagamento confirmado",
                     f"Comanda #{self.command['number']:04d} finalizada com sucesso.{troco_msg}")
        self.on_finished()
