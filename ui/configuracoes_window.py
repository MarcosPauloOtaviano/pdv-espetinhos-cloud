"""Configuracoes: estabelecimento, Pix, backup/restauracao e usuarios."""
from tkinter import filedialog

import customtkinter as ctk

from app import api_client as services, backup as backup_module
from app.api_client import ServiceError
from ui import theme
from ui.widgets import ModalDialog, show_error, show_success, confirm


class UserDialog(ModalDialog):
    def __init__(self, parent, on_saved):
        super().__init__(parent, title="Novo usuario", width=400, height=420)
        self.on_saved = on_saved

        ctk.CTkLabel(self, text="Novo usuario", font=theme.font(17, "bold"), text_color=theme.ORANGE).pack(pady=(20, 14))
        ctk.CTkLabel(self, text="Usuario", font=theme.font(12), text_color=theme.TEXT_MUTED).pack()
        self.username_entry = ctk.CTkEntry(self, width=260, height=38)
        self.username_entry.pack(pady=6)

        ctk.CTkLabel(self, text="Senha", font=theme.font(12), text_color=theme.TEXT_MUTED).pack(pady=(10, 0))
        self.password_entry = ctk.CTkEntry(self, width=260, height=38, show="*")
        self.password_entry.pack(pady=6)

        ctk.CTkLabel(self, text="Perfil", font=theme.font(12), text_color=theme.TEXT_MUTED).pack(pady=(10, 0))
        self.role_combo = ctk.CTkComboBox(self, values=["caixa", "garcom", "cozinha", "admin"], width=260)
        self.role_combo.set("caixa")
        self.role_combo.pack(pady=6)

        ctk.CTkButton(self, text="Criar usuario", width=240, height=42, command=self._save,
                      **theme.PRIMARY_BUTTON).pack(pady=20)

    def _save(self):
        try:
            services.create_user(self.username_entry.get(), self.password_entry.get(), self.role_combo.get())
        except ServiceError as exc:
            show_error(self, "Erro", str(exc))
            return
        self.destroy()
        self.on_saved()


class ChangePasswordDialog(ModalDialog):
    def __init__(self, parent, user_id, username):
        super().__init__(parent, title=f"Trocar senha - {username}", width=380, height=260)
        ctk.CTkLabel(self, text=f"Nova senha para {username}", font=theme.font(15, "bold"),
                     text_color=theme.ORANGE).pack(pady=(24, 14))
        self.password_entry = ctk.CTkEntry(self, width=240, height=38, show="*")
        self.password_entry.pack(pady=6)
        ctk.CTkButton(self, text="Salvar nova senha", width=220, height=40,
                      command=lambda: self._save(user_id), **theme.PRIMARY_BUTTON).pack(pady=20)

    def _save(self, user_id):
        try:
            services.change_password(user_id, self.password_entry.get())
        except ServiceError as exc:
            show_error(self, "Erro", str(exc))
            return
        self.destroy()
        show_success(self, "Senha alterada", "A senha foi atualizada com sucesso.")


class ConfiguracoesFrame(ctk.CTkFrame):
    def __init__(self, parent, app):
        super().__init__(parent, fg_color=theme.BG_DARK)
        self.app = app

        ctk.CTkLabel(self, text="Configuracoes", font=theme.font_title(26), text_color=theme.TEXT_LIGHT).pack(
            anchor="w", pady=(0, 14)
        )

        self.tabs = ctk.CTkTabview(self, fg_color=theme.BG_PANEL,
                                    segmented_button_selected_color=theme.ORANGE,
                                    segmented_button_selected_hover_color=theme.ORANGE_HOVER)
        self.tabs.pack(fill="both", expand=True)
        self.tabs.add("Estabelecimento")
        self.tabs.add("Rede / Celular")
        self.tabs.add("Pix")
        self.tabs.add("Backup")
        self.tabs.add("Usuarios")

        self._build_estabelecimento_tab()
        self._build_rede_tab()
        self._build_pix_tab()
        self._build_backup_tab()
        self._build_usuarios_tab()

    # ------------------------------------------------------------------
    def _build_rede_tab(self):
        tab = self.tabs.tab("Rede / Celular")
        from app.utils import get_lan_ip, DEFAULT_PORT

        url = f"http://{get_lan_ip()}:{DEFAULT_PORT}/app/"

        ctk.CTkLabel(tab, text="Acesso pelo celular (garcom / cozinha)", font=theme.font(15, "bold"),
                     text_color=theme.ORANGE).pack(anchor="w", padx=20, pady=(20, 6))
        ctk.CTkLabel(
            tab, text="Conecte o celular na MESMA rede Wi-Fi deste computador e abra o endereco abaixo\n"
                      "no navegador. Depois use o menu do navegador para \"Adicionar a tela inicial\"\n"
                      "e instalar como aplicativo.",
            font=theme.font(12), text_color=theme.TEXT_MUTED, justify="left"
        ).pack(anchor="w", padx=20, pady=(0, 14))

        url_box = ctk.CTkEntry(tab, width=420, height=42, font=theme.font(15, "bold"), justify="center")
        url_box.pack(anchor="w", padx=20)
        url_box.insert(0, url)
        url_box.configure(state="readonly")

        def _copy():
            self.clipboard_clear()
            self.clipboard_append(url)
            show_success(self, "Copiado", "Endereco copiado para a area de transferencia.")

        ctk.CTkButton(tab, text="📋 Copiar endereco", width=200, height=38, command=_copy,
                      **theme.NEUTRAL_BUTTON).pack(anchor="w", padx=20, pady=12)

        ctk.CTkLabel(
            tab, text="Se o celular nao conseguir acessar, confira se o Firewall do Windows esta\n"
                      "liberando o Python/DUDAIR-PDV para redes privadas (veja o README).",
            font=theme.font(11), text_color=theme.TEXT_MUTED, justify="left"
        ).pack(anchor="w", padx=20, pady=(6, 0))

    # ------------------------------------------------------------------
    def _build_estabelecimento_tab(self):
        tab = self.tabs.tab("Estabelecimento")
        ctk.CTkLabel(tab, text="Nome do estabelecimento", font=theme.font(13), text_color=theme.TEXT_MUTED).pack(
            anchor="w", padx=20, pady=(20, 4)
        )
        self.establishment_entry = ctk.CTkEntry(tab, width=400, height=40)
        self.establishment_entry.pack(anchor="w", padx=20)
        self.establishment_entry.insert(0, services.get_setting("establishment_name", "Espetinho DU'DAIR"))

        ctk.CTkButton(tab, text="Salvar", width=160, height=40, command=self._save_establishment,
                      **theme.PRIMARY_BUTTON).pack(anchor="w", padx=20, pady=16)

    def _save_establishment(self):
        services.set_setting("establishment_name", self.establishment_entry.get().strip() or "Espetinho DU'DAIR")
        show_success(self, "Salvo", "Nome do estabelecimento atualizado. Reabra as telas para ver o efeito completo.")

    # ------------------------------------------------------------------
    def _build_pix_tab(self):
        tab = self.tabs.tab("Pix")
        ctk.CTkLabel(
            tab, text="Configure a chave Pix estatica usada para gerar o QR Code de cobranca.\n"
                      "Estrutura pronta para futura integracao com Mercado Pago, Asaas, Gerencianet ou PagSeguro.",
            font=theme.font(12), text_color=theme.TEXT_MUTED, justify="left"
        ).pack(anchor="w", padx=20, pady=(20, 14))

        fields = [
            ("pix_key", "Chave Pix (CPF, CNPJ, e-mail, telefone ou aleatoria)"),
            ("pix_receiver_name", "Nome do recebedor (max. 25 caracteres, sem acentos)"),
            ("pix_city", "Cidade do recebedor (max. 15 caracteres, sem acentos)"),
            ("pix_description", "Descricao padrao da cobranca"),
        ]
        self.pix_entries = {}
        for key, label in fields:
            ctk.CTkLabel(tab, text=label, font=theme.font(12), text_color=theme.TEXT_MUTED).pack(anchor="w", padx=20)
            entry = ctk.CTkEntry(tab, width=400, height=38)
            entry.pack(anchor="w", padx=20, pady=(2, 12))
            entry.insert(0, services.get_setting(key, ""))
            self.pix_entries[key] = entry

        ctk.CTkButton(tab, text="Salvar configuracoes Pix", width=220, height=42, command=self._save_pix,
                      **theme.PRIMARY_BUTTON).pack(anchor="w", padx=20, pady=10)

    def _save_pix(self):
        values = {key: entry.get().strip() for key, entry in self.pix_entries.items()}
        services.set_settings_bulk(values)
        show_success(self, "Salvo", "Configuracoes do Pix atualizadas.")

    # ------------------------------------------------------------------
    def _build_backup_tab(self):
        tab = self.tabs.tab("Backup")
        ctk.CTkLabel(
            tab, text="Faca backup regularmente. O arquivo pode ser copiado para um pendrive\n"
                      "e restaurado em outro computador com o DUDAIR-PDV instalado.",
            font=theme.font(12), text_color=theme.TEXT_MUTED, justify="left"
        ).pack(anchor="w", padx=20, pady=(20, 16))

        ctk.CTkButton(tab, text="💾 Fazer backup agora", width=260, height=48, font=theme.font(14, "bold"),
                      command=self._do_backup, **theme.SUCCESS_BUTTON).pack(anchor="w", padx=20, pady=8)

        ctk.CTkButton(tab, text="♻ Restaurar backup", width=260, height=48, font=theme.font(14, "bold"),
                      command=self._do_restore, **theme.DANGER_BUTTON).pack(anchor="w", padx=20, pady=8)

        self.backup_status = ctk.CTkLabel(tab, text="", font=theme.font(12), text_color=theme.TEXT_MUTED,
                                           wraplength=500, justify="left")
        self.backup_status.pack(anchor="w", padx=20, pady=16)

    def _do_backup(self):
        folder = filedialog.askdirectory(title="Escolha a pasta para salvar o backup")
        if not folder:
            return
        try:
            path = backup_module.backup_database(folder)
        except Exception as exc:
            show_error(self, "Erro ao gerar backup", str(exc))
            return
        self.backup_status.configure(text=f"Ultimo backup salvo em:\n{path}")
        show_success(self, "Backup concluido", f"Backup salvo em:\n{path}")

    def _do_restore(self):
        path = filedialog.askopenfilename(title="Selecione o arquivo de backup (.db)", filetypes=[("Banco de dados", "*.db")])
        if not path:
            return
        if not confirm(
            self, "Restaurar backup",
            "Isso vai SUBSTITUIR todos os dados atuais pelos dados do backup selecionado.\n"
            "Uma copia de seguranca do banco atual sera criada antes. Deseja continuar?",
        ):
            return
        try:
            backup_module.restore_database(path)
        except Exception as exc:
            show_error(self, "Erro ao restaurar", str(exc))
            return
        show_success(self, "Backup restaurado",
                     "Dados restaurados com sucesso. Feche e abra o sistema novamente para garantir consistencia.")

    # ------------------------------------------------------------------
    def _build_usuarios_tab(self):
        tab = self.tabs.tab("Usuarios")
        header = ctk.CTkFrame(tab, fg_color="transparent")
        header.pack(fill="x", padx=20, pady=(16, 8))
        ctk.CTkLabel(header, text="Usuarios do sistema", font=theme.font(14, "bold"),
                     text_color=theme.TEXT_LIGHT).pack(side="left")
        ctk.CTkButton(header, text="+ Novo usuario", width=150, command=lambda: UserDialog(self, self._reload_users),
                      **theme.PRIMARY_BUTTON).pack(side="right")

        self.users_scroll = ctk.CTkScrollableFrame(tab, fg_color="transparent")
        self.users_scroll.pack(fill="both", expand=True, padx=20, pady=(0, 16))
        self._reload_users()

    def _reload_users(self):
        for child in self.users_scroll.winfo_children():
            child.destroy()
        for u in services.list_users():
            row = ctk.CTkFrame(self.users_scroll, fg_color=theme.BG_PANEL_LIGHT, corner_radius=8)
            row.pack(fill="x", pady=3)
            status = "ativo" if u["active"] else "inativo"
            ctk.CTkLabel(row, text=f"{u['username']}  ({u['role']}, {status})", font=theme.font(13),
                         text_color=theme.TEXT_LIGHT).pack(side="left", padx=12, pady=8)
            ctk.CTkButton(row, text="Trocar senha", width=110, height=30,
                          command=lambda uid=u["id"], name=u["username"]: ChangePasswordDialog(self, uid, name),
                          **theme.NEUTRAL_BUTTON).pack(side="right", padx=6, pady=6)
            toggle_text = "Desativar" if u["active"] else "Ativar"
            ctk.CTkButton(row, text=toggle_text, width=90, height=30,
                          command=lambda uid=u["id"], act=u["active"]: self._toggle_user(uid, act),
                          **theme.GOLD_BUTTON).pack(side="right", padx=6, pady=6)

    def _toggle_user(self, user_id, active):
        services.set_user_active(user_id, not active)
        self._reload_users()
