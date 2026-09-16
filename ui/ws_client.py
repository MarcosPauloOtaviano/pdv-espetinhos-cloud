"""
Cliente WebSocket do app desktop: escuta os eventos que o servidor embutido
transmite (mudancas feitas pelo proprio computador OU por um celular na
rede) e entrega para a UI via uma fila thread-safe, para o Tkinter poder
atualizar a tela sem travar (nunca mexer em widgets fora da main thread).
"""
import json
import queue
import threading
import time

import websocket

from app import api_client
from app.utils import DEFAULT_PORT

WS_URL = f"ws://127.0.0.1:{DEFAULT_PORT}/ws"


class WsListener:
    def __init__(self):
        self.events = queue.Queue()
        self._stop = False
        self._thread = threading.Thread(target=self._run, daemon=True, name="dudair-ws-client")
        self._thread.start()

    def stop(self):
        self._stop = True

    def _run(self):
        while not self._stop:
            token = api_client.get_token()
            if not token:
                time.sleep(0.5)
                continue
            try:
                ws = websocket.create_connection(f"{WS_URL}?token={token}", timeout=5)
                while not self._stop:
                    msg = ws.recv()
                    if not msg:
                        break
                    try:
                        self.events.put(json.loads(msg))
                    except Exception:
                        pass
            except Exception:
                time.sleep(2)
            finally:
                try:
                    ws.close()
                except Exception:
                    pass

    def poll(self):
        """Retorna todos os eventos recebidos ate agora (lista, pode ser vazia)."""
        drained = []
        while True:
            try:
                drained.append(self.events.get_nowait())
            except queue.Empty:
                break
        return drained
