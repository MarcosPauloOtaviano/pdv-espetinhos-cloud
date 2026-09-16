"""
Ponto de entrada do DUDAIR-PDV.
Ao abrir, este programa faz DUAS coisas:
  1. Sobe um servidor local (FastAPI + WebSocket) em background, que e o
     unico dono do banco SQLite. Celulares na mesma rede Wi-Fi acessam esse
     servidor pela PWA em http://<ip-do-computador>:<porta>/app/.
  2. Abre a janela do caixa (CustomTkinter), que fala com esse servidor via
     HTTP/WebSocket em 127.0.0.1, exatamente como o celular faria.
Continua sendo "um programa so" no computador - o cliente nao precisa saber
que existe um servidor rodando por baixo.
"""
import sys
import ctypes
import threading
import time

import customtkinter as ctk
import requests
import uvicorn

from app.utils import resource_path, get_lan_ip, DEFAULT_PORT
from ui import theme
from ui.login_window import LoginFrame
from ui.main_window import MainWindow

HOST = "0.0.0.0"
PORT = DEFAULT_PORT
LOCAL_BASE_URL = f"http://127.0.0.1:{PORT}"


def _enable_windows_dpi_awareness():
    if sys.platform == "win32":
        try:
            ctypes.windll.shcore.SetProcessDpiAwareness(1)
        except Exception:
            try:
                ctypes.windll.user32.SetProcessDPIAware()
            except Exception:
                pass


def _start_embedded_server() -> uvicorn.Server:
    """Sobe o FastAPI/uvicorn em background thread, sem instalar signal handlers
    (que so funcionam na thread principal) e sem abrir terminal de log."""
    from app.server import app as fastapi_app

    config = uvicorn.Config(fastapi_app, host=HOST, port=PORT, log_level="warning")
    server = uvicorn.Server(config)
    server.install_signal_handlers = lambda: None

    thread = threading.Thread(target=server.run, daemon=True, name="dudair-server")
    thread.start()
    return server


def _wait_server_ready(timeout=15) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            r = requests.get(f"{LOCAL_BASE_URL}/", timeout=1)
            if r.status_code == 200:
                return True
        except Exception:
            pass
        time.sleep(0.2)
    return False


class App(ctk.CTk):
    def __init__(self, server: uvicorn.Server):
        super().__init__()
        self.server = server
        theme.apply_appearance()
        self.title("DUDAIR-PDV - Espetinho DU'DAIR")
        self.geometry("1280x800")
        self.minsize(1024, 680)
        self.configure(fg_color=theme.BG_DARK)

        try:
            icon_path = resource_path("assets/icons/app.ico")
            if icon_path.exists():
                self.iconbitmap(str(icon_path))
        except Exception:
            pass

        self.container = ctk.CTkFrame(self, fg_color=theme.BG_DARK)
        self.container.pack(fill="both", expand=True)

        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self.show_login()

    def show_login(self):
        for child in self.container.winfo_children():
            child.destroy()
        LoginFrame(self.container, on_success=self.show_main).pack(fill="both", expand=True)

    def show_main(self, user):
        for child in self.container.winfo_children():
            child.destroy()
        MainWindow(self.container, user, on_logout=self.show_login).pack(fill="both", expand=True)

    def _on_close(self):
        self.server.should_exit = True
        self.destroy()


def main():
    _enable_windows_dpi_awareness()

    server = _start_embedded_server()
    if not _wait_server_ready():
        print("AVISO: o servidor local nao respondeu a tempo. O app pode nao funcionar corretamente.")

    lan_ip = get_lan_ip()
    print(f"DUDAIR-PDV rodando. Acesso pelo celular (mesma rede Wi-Fi): http://{lan_ip}:{PORT}/app/")

    app = App(server)
    app.mainloop()


if __name__ == "__main__":
    main()
