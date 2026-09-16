"""Widgets e dialogos reutilizaveis em todo o app."""
import customtkinter as ctk

from ui import theme


class ModalDialog(ctk.CTkToplevel):
    """Base para janelas modais: centraliza sobre o parent e trava foco."""

    def __init__(self, parent, title="", width=480, height=360, resizable=False):
        super().__init__(parent)
        self.title(title)
        self.configure(fg_color=theme.BG_DARK)
        self.geometry(f"{width}x{height}")
        self.resizable(resizable, resizable)
        self.transient(parent)
        self.grab_set()
        self.bind("<Escape>", lambda e: self.destroy())
        self.after(50, self._center(parent, width, height))

    def _center(self, parent, width, height):
        def _do():
            try:
                parent.update_idletasks()
                px, py = parent.winfo_rootx(), parent.winfo_rooty()
                pw, ph = parent.winfo_width(), parent.winfo_height()
                x = px + (pw - width) // 2
                y = py + (ph - height) // 2
                self.geometry(f"{width}x{height}+{max(x,0)}+{max(y,0)}")
            except Exception:
                pass
        return _do


def show_info(parent, title, message, kind="info"):
    color = {"info": theme.GOLD, "success": theme.GREEN, "error": theme.RED}.get(kind, theme.GOLD)
    dialog = ModalDialog(parent, title=title, width=420, height=220)
    ctk.CTkLabel(dialog, text=title, font=theme.font(18, "bold"), text_color=color).pack(pady=(24, 8))
    ctk.CTkLabel(
        dialog, text=message, font=theme.font(14), text_color=theme.TEXT_LIGHT,
        wraplength=360, justify="center",
    ).pack(pady=8, padx=20)
    ctk.CTkButton(
        dialog, text="OK", width=140, command=dialog.destroy, **theme.PRIMARY_BUTTON
    ).pack(pady=18)
    dialog.wait_window()


def show_error(parent, title, message):
    show_info(parent, title, message, kind="error")


def show_success(parent, title, message):
    show_info(parent, title, message, kind="success")


def confirm(parent, title, message, confirm_text="Confirmar", cancel_text="Voltar") -> bool:
    result = {"ok": False}
    dialog = ModalDialog(parent, title=title, width=440, height=230)
    ctk.CTkLabel(dialog, text=title, font=theme.font(18, "bold"), text_color=theme.ORANGE).pack(pady=(24, 8))
    ctk.CTkLabel(
        dialog, text=message, font=theme.font(14), text_color=theme.TEXT_LIGHT,
        wraplength=380, justify="center",
    ).pack(pady=8, padx=20)

    btn_row = ctk.CTkFrame(dialog, fg_color="transparent")
    btn_row.pack(pady=18)

    def _yes():
        result["ok"] = True
        dialog.destroy()

    ctk.CTkButton(btn_row, text=cancel_text, width=160, command=dialog.destroy, **theme.NEUTRAL_BUTTON).pack(
        side="left", padx=8
    )
    ctk.CTkButton(btn_row, text=confirm_text, width=170, command=_yes, **theme.DANGER_BUTTON).pack(side="left", padx=8)

    dialog.wait_window()
    return result["ok"]


class StatusBadge(ctk.CTkLabel):
    STATUS_COLORS = {
        "aberto": theme.GOLD,
        "aguardando_pagamento": theme.ORANGE,
        "paga": theme.GREEN,
        "cancelada": theme.RED,
        "fiado": theme.TEXT_DANGER,
    }

    def __init__(self, parent, status: str, label: str):
        color = self.STATUS_COLORS.get(status, theme.GRAY)
        super().__init__(
            parent, text=f"  {label}  ", font=theme.font(12, "bold"), text_color="#1A1310",
            fg_color=color, corner_radius=6,
        )


class SectionCard(ctk.CTkFrame):
    def __init__(self, parent, title=None, **kwargs):
        kwargs.setdefault("fg_color", theme.BG_PANEL)
        kwargs.setdefault("corner_radius", 12)
        super().__init__(parent, **kwargs)
        if title:
            ctk.CTkLabel(self, text=title, font=theme.font(16, "bold"), text_color=theme.ORANGE).pack(
                anchor="w", padx=16, pady=(14, 4)
            )
