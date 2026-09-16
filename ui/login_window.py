"""Tela de login."""
import customtkinter as ctk

from app import api_client as services
from app.utils import resource_path
from ui import theme
from ui.widgets import show_error, show_info


class LoginFrame(ctk.CTkFrame):
    def __init__(self, parent, on_success):
        super().__init__(parent, fg_color=theme.BG_DARK)
        self.on_success = on_success

        card = ctk.CTkFrame(self, fg_color=theme.BG_PANEL, corner_radius=18, width=420, height=480)
        card.place(relx=0.5, rely=0.5, anchor="center")
        card.pack_propagate(False)

        establishment = services.get_setting("establishment_name", "Espetinho DU'DAIR")

        ctk.CTkLabel(card, text="🔥", font=ctk.CTkFont(size=46)).pack(pady=(36, 0))
        ctk.CTkLabel(card, text=establishment, font=theme.font_title(24), text_color=theme.ORANGE).pack(pady=(4, 2))
        ctk.CTkLabel(card, text="Sistema de Comandas e Caixa", font=theme.font(13), text_color=theme.TEXT_MUTED).pack(
            pady=(0, 24)
        )

        self.username_entry = ctk.CTkEntry(
            card, placeholder_text="Usuario", width=300, height=42, font=theme.font(15)
        )
        self.username_entry.pack(pady=8)
        self.username_entry.insert(0, "admin")

        self.password_entry = ctk.CTkEntry(
            card, placeholder_text="Senha", show="*", width=300, height=42, font=theme.font(15)
        )
        self.password_entry.pack(pady=8)

        self.error_label = ctk.CTkLabel(card, text="", text_color=theme.TEXT_DANGER, font=theme.font(12))
        self.error_label.pack(pady=(4, 0))

        ctk.CTkButton(
            card, text="ENTRAR", width=300, height=46, font=theme.font(16, "bold"),
            command=self._try_login, **theme.PRIMARY_BUTTON
        ).pack(pady=(16, 8))

        ctk.CTkLabel(
            card, text="Usuario padrao: admin / senha: admin123", font=theme.font(11), text_color=theme.TEXT_MUTED
        ).pack(pady=(18, 0))

        self.password_entry.bind("<Return>", lambda e: self._try_login())
        self.username_entry.bind("<Return>", lambda e: self.password_entry.focus())
        self.after(150, self.username_entry.focus)

    def _try_login(self):
        username = self.username_entry.get().strip()
        password = self.password_entry.get()
        if not username or not password:
            self.error_label.configure(text="Informe usuario e senha.")
            return
        user = services.authenticate(username, password)
        if not user:
            self.error_label.configure(text="Usuario ou senha invalidos.")
            return
        self.error_label.configure(text="")
        if user.get("must_change_password"):
            show_info(
                self, "Troque sua senha",
                "Este e o primeiro acesso com a senha padrao.\n"
                "Recomendamos trocar a senha em Configuracoes > Usuarios assim que possivel.",
            )
        self.on_success(user)
