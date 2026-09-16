"""Identidade visual do Espetinho DU'DAIR: paleta escura, vermelho/laranja/dourado."""
import customtkinter as ctk

# Paleta principal (churrasco / bar, tema escuro)
BG_DARK = "#1A1310"          # fundo principal (quase preto, tom cafe)
BG_PANEL = "#241A15"         # paineis / cards
BG_PANEL_LIGHT = "#2E2119"
BORDER = "#3D2A1F"

RED = "#C0392B"
RED_HOVER = "#A93226"
ORANGE = "#E67E22"
ORANGE_HOVER = "#CA6F1E"
GOLD = "#F1C40F"
GOLD_HOVER = "#D4AC0D"
GREEN = "#27AE60"
GREEN_HOVER = "#219150"
GRAY = "#5D4B3F"
GRAY_HOVER = "#4A3B31"

TEXT_LIGHT = "#F5EFE6"
TEXT_MUTED = "#B8A99A"
TEXT_DANGER = "#FF6B5E"
TEXT_SUCCESS = "#6EDC8C"
TEXT_WARNING = "#F1C40F"

FONT_FAMILY = "Segoe UI"


def font(size=14, weight="normal"):
    return ctk.CTkFont(family=FONT_FAMILY, size=size, weight=weight)


def font_title(size=26):
    return ctk.CTkFont(family=FONT_FAMILY, size=size, weight="bold")


def apply_appearance():
    ctk.set_appearance_mode("dark")
    ctk.set_default_color_theme("dark-blue")


def BIG_BUTTON():
    return dict(corner_radius=14, height=90, font=font(18, "bold"))


def NAV_BUTTON():
    return dict(corner_radius=8, height=44, font=font(14, "bold"), anchor="w")


PRIMARY_BUTTON = dict(fg_color=ORANGE, hover_color=ORANGE_HOVER, text_color="#1A1310")
DANGER_BUTTON = dict(fg_color=RED, hover_color=RED_HOVER, text_color="white")
SUCCESS_BUTTON = dict(fg_color=GREEN, hover_color=GREEN_HOVER, text_color="white")
GOLD_BUTTON = dict(fg_color=GOLD, hover_color=GOLD_HOVER, text_color="#1A1310")
NEUTRAL_BUTTON = dict(fg_color=GRAY, hover_color=GRAY_HOVER, text_color=TEXT_LIGHT)
