"""
Потокобезопасный HTTP-клиент с ограничением частоты запросов (rate limiting)
и защитой внешних сервисов от блокировок и 429 Too Many Requests.
"""

import time
import threading
from typing import Optional, Dict
import requests


class PoliteSession:
    """
    Обертка над requests.Session с гарантированным интервалом между сетевыми вызовами
    и автоматическим восстановлением при получении 429 статуса.
    """

    def __init__(
        self,
        name: str,
        min_interval: float = 0.35,
        default_headers: Optional[Dict[str, str]] = None
    ):
        self.name = name
        self.min_interval = min_interval
        self.lock = threading.Lock()
        self.last_request_time = 0.0
        self.session = requests.Session()

        # Настраиваем пул соединений HTTP Keep-Alive
        adapter = requests.adapters.HTTPAdapter(pool_connections=10, pool_maxsize=20, max_retries=1)
        self.session.mount("http://", adapter)
        self.session.mount("https://", adapter)

        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept-Language": "ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7",
        }
        if default_headers:
            headers.update(default_headers)
        self.session.headers.update(headers)

    def request(self, method: str, url: str, **kwargs) -> Optional[requests.Response]:
        with self.lock:
            elapsed = time.time() - self.last_request_time
            if elapsed < self.min_interval:
                time.sleep(self.min_interval - elapsed)

            try:
                self.last_request_time = time.time()
                resp = self.session.request(method, url, **kwargs)
                if resp.status_code == 429:
                    print(f"[{self.name}] [!] 429 Too Many Requests: пауза 5 сек...")
                    time.sleep(5.0)
                    self.last_request_time = time.time()
                    resp = self.session.request(method, url, **kwargs)
                return resp
            except Exception as e:
                print(f"[{self.name}] Ошибка сети при запросе {url}: {e}")
                return None

    def get(self, url: str, **kwargs) -> Optional[requests.Response]:
        return self.request("GET", url, **kwargs)

    def post(self, url: str, **kwargs) -> Optional[requests.Response]:
        return self.request("POST", url, **kwargs)
