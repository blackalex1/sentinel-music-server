import ssl
import json
import base64
import hashlib
import urllib.request
import logging
from typing import Tuple, Optional
from cryptography import x509
from cryptography.x509.oid import NameOID
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.asymmetric.utils import decode_dss_signature


def b64url(data: bytes) -> str:
    """Кодирует байты в base64url без паддинга по RFC 7515."""
    return base64.urlsafe_b64encode(data).decode('utf-8').rstrip('=')


class AcmeClient:
    """Клиент ACME v2 протокола для взаимодействия с Let's Encrypt."""

    def __init__(self, use_staging: bool = False):
        if use_staging:
            self.directory_url = "https://acme-staging-v02.api.letsencrypt.org/directory"
        else:
            self.directory_url = "https://acme-v02.api.letsencrypt.org/directory"
        self.directory = {}
        self.account_url = None
        self.nonce = None

        # Генерация ключа аккаунта ES256 (SECP256R1)
        self.account_key = ec.generate_private_key(ec.SECP256R1())

        # Расчет JWK и thumbprint
        pub_numbers = self.account_key.public_key().public_numbers()
        x_bytes = pub_numbers.x.to_bytes(32, 'big')
        y_bytes = pub_numbers.y.to_bytes(32, 'big')
        self.jwk = {
            "crv": "P-256",
            "kty": "EC",
            "x": b64url(x_bytes),
            "y": b64url(y_bytes)
        }
        jwk_json = json.dumps(self.jwk, sort_keys=True, separators=(',', ':'))
        self.thumbprint = b64url(hashlib.sha256(jwk_json.encode('utf-8')).digest())

    def _send_request(self, url: str, data: bytes = None, headers: dict = None, method: str = "POST") -> Tuple[int, dict, dict]:
        """Отправляет HTTP-запрос к ACME-серверу."""
        if headers is None:
            headers = {}
        ctx = ssl.create_default_context()

        req = urllib.request.Request(url, data=data, headers=headers, method=method)
        try:
            with urllib.request.urlopen(req, context=ctx, timeout=15) as resp:
                res_headers = {k.lower(): v for k, v in resp.getheaders()}
                res_body = resp.read()
                try:
                    res_json = json.loads(res_body.decode('utf-8')) if res_body else {}
                except Exception:
                    res_json = {"raw": res_body.decode('utf-8', errors='ignore')}
                return resp.status, res_json, res_headers
        except urllib.request.HTTPError as e:
            res_headers = {k.lower(): v for k, v in e.headers.items()}
            res_body = e.read()
            try:
                res_json = json.loads(res_body.decode('utf-8')) if res_body else {}
            except Exception:
                res_json = {"raw": res_body.decode('utf-8', errors='ignore')}
            return e.code, res_json, res_headers
        except Exception as e:
            logging.error(f"[ACME Client] Ошибка сети при запросе к {url}: {e}")
            return 0, {}, {}

    def fetch_directory(self) -> bool:
        """Получает список эндпоинтов Let's Encrypt."""
        status, res_json, _ = self._send_request(self.directory_url, method="GET")
        if status == 200:
            self.directory = res_json
            return True
        return False

    def get_nonce(self) -> str:
        """Получает свежий анти-replay nonce."""
        new_nonce_url = self.directory.get("newNonce")
        if not new_nonce_url:
            return ""
        status, _, headers = self._send_request(new_nonce_url, method="HEAD")
        return headers.get("replay-nonce", "")

    def _sign_and_post(self, url: str, payload_dict: Optional[dict]) -> Tuple[int, dict, dict]:
        """Подписывает payload ключом ES256 и отправляет POST запрос."""
        if not self.nonce:
            self.nonce = self.get_nonce()

        protected = {
            "alg": "ES256",
            "nonce": self.nonce,
            "url": url
        }
        if self.account_url:
            protected["kid"] = self.account_url
        else:
            protected["jwk"] = self.jwk

        protected_b64 = b64url(json.dumps(protected).encode('utf-8'))
        payload_b64 = b64url(json.dumps(payload_dict).encode('utf-8')) if payload_dict is not None else ""

        signing_input = f"{protected_b64}.{payload_b64}".encode('utf-8')
        raw_sig = self.account_key.sign(signing_input, ec.ECDSA(hashes.SHA256()))

        # Преобразование DER сигнатуры в IEEE P1363 (r || s, 64 байта)
        r, s = decode_dss_signature(raw_sig)
        sig_bytes = r.to_bytes(32, 'big') + s.to_bytes(32, 'big')
        signature_b64 = b64url(sig_bytes)

        body = {
            "protected": protected_b64,
            "payload": payload_b64,
            "signature": signature_b64
        }
        data = json.dumps(body).encode('utf-8')
        headers = {"Content-Type": "application/jose+json"}

        status, res_json, res_headers = self._send_request(url, data=data, headers=headers, method="POST")
        self.nonce = res_headers.get("replay-nonce")
        return status, res_json, res_headers

    def register_account(self, email: str = "") -> bool:
        """Регистрирует новый аккаунт или находит существующий."""
        new_account_url = self.directory.get("newAccount")
        payload = {
            "termsOfServiceAgreed": True
        }
        if email:
            payload["contact"] = [f"mailto:{email}"]

        status, _, res_headers = self._sign_and_post(new_account_url, payload)
        if status in (200, 201):
            self.account_url = res_headers.get("location")
            return bool(self.account_url)
        return False

    def create_order(self, domain: str) -> Tuple[Optional[str], Optional[list], Optional[str]]:
        """Создает заказ на выпуск сертификата для домена."""
        new_order_url = self.directory.get("newOrder")
        payload = {
            "identifiers": [{"type": "dns", "value": domain}]
        }
        status, res_json, res_headers = self._sign_and_post(new_order_url, payload)
        if status == 201:
            order_url = res_headers.get("location")
            authorizations = res_json.get("authorizations", [])
            finalize_url = res_json.get("finalize")
            return order_url, authorizations, finalize_url
        return None, None, None

    def get_challenge_details(self, auth_url: str) -> Tuple[Optional[str], Optional[str], Optional[str]]:
        """Извлекает детали HTTP-01 челленджа."""
        status, res_json, _ = self._sign_and_post(auth_url, None)
        if status == 200:
            auth_status = res_json.get("status")
            challenges = res_json.get("challenges", [])
            for c in challenges:
                if c.get("type") == "http-01":
                    return c.get("token"), c.get("url"), auth_status
        return None, None, None

    def trigger_challenge(self, challenge_url: str) -> bool:
        """Сообщает Let's Encrypt, что файл челленджа размещен."""
        status, _, _ = self._sign_and_post(challenge_url, {})
        return status == 200

    def poll_authorization(self, auth_url: str, max_retries: int = 15) -> bool:
        """Опрашивает статус валидации авторизации домена."""
        import time
        for _ in range(max_retries):
            time.sleep(2)
            status, res_json, _ = self._sign_and_post(auth_url, None)
            if status == 200:
                current_status = res_json.get("status")
                if current_status == "valid":
                    return True
                elif current_status == "invalid":
                    logging.error(f"[ACME Client] Ошибка валидации: {res_json}")
                    return False
        return False

    def finalize_order(self, finalize_url: str, domain: str, domain_key) -> Optional[str]:
        """Генерирует CSR и отправляет на финализацию заказа."""
        csr = (
            x509.CertificateSigningRequestBuilder()
            .subject_name(x509.Name([
                x509.NameAttribute(NameOID.COMMON_NAME, domain),
            ]))
            .add_extension(
                x509.SubjectAlternativeName([x509.DNSName(domain)]),
                critical=False,
            )
            .sign(domain_key, hashes.SHA256())
        )
        csr_der = csr.public_bytes(serialization.Encoding.DER)
        payload = {"csr": b64url(csr_der)}

        import time
        status, res_json, _ = self._sign_and_post(finalize_url, payload)
        if status == 200:
            for _ in range(15):
                cert_url = res_json.get("certificate")
                if cert_url:
                    return cert_url
                if res_json.get("status") == "invalid":
                    return None
                time.sleep(2)
                status, res_json, _ = self._sign_and_post(finalize_url, None)
        return None
