import logging
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Dict

# Глобальное хранилище активных ACME HTTP-01 челленджей (token -> key_authorization)
ACME_CHALLENGES: Dict[str, str] = {}


class AcmeChallengeHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        # Подавление стандартного логгирования
        pass

    def do_GET(self):
        # Путь: /.well-known/acme-challenge/<token>
        prefix = "/.well-known/acme-challenge/"
        clean_path = self.path.split("?")[0]
        if clean_path.startswith(prefix):
            token = clean_path[len(prefix):]
            if token in ACME_CHALLENGES:
                self.send_response(200)
                self.send_header("Content-Type", "text/plain")
                self.end_headers()
                self.wfile.write(ACME_CHALLENGES[token].encode("utf-8"))
                return
        self.send_response(404)
        self.end_headers()
        self.wfile.write(b"Not Found")


class TemporaryAcmeServer:
    def __init__(self, port=80):
        self.port = port
        self.server = None
        self.thread = None

    def start(self):
        try:
            self.server = HTTPServer(("0.0.0.0", self.port), AcmeChallengeHandler)
            self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
            self.thread.start()
            logging.info(f"[ACME Server] Временный HTTP сервер запущен на порту {self.port}")
            return True
        except Exception as e:
            logging.warning(f"[ACME Server] Не удалось запустить HTTP сервер на порту {self.port}: {e}")
            return False

    def stop(self):
        if self.server:
            logging.info(f"[ACME Server] Остановка временного HTTP сервера на порту {self.port}")
            self.server.shutdown()
            self.server.server_close()
            self.server = None
        if self.thread:
            self.thread.join(timeout=2)
            self.thread = None
