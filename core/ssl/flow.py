import logging
from typing import Tuple, Optional
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives import serialization
from core.ssl.acme_client import AcmeClient
from core.ssl.challenge_server import TemporaryAcmeServer, ACME_CHALLENGES


def run_acme_flow(domain: str, email: str = "", use_staging: bool = False) -> Tuple[bool, str, Optional[str], Optional[str]]:
    """
    Запускает полный цикл получения сертификата Let's Encrypt через HTTP-01 challenge.
    Возвращает: (success: bool, message: str, cert_pem: Optional[str], key_pem: Optional[str])
    """
    # 1. Попытка запуска временного сервера на 80 порту для прямого ответа Let's Encrypt
    temp_server = TemporaryAcmeServer(port=80)
    server_started = temp_server.start()
    if not server_started:
        logging.info("[ACME Flow] Порт 80 недоступен для временного сервера (занят другим процессом или нет прав). Челлендж будет отдаваться через основной веб-сервер FastAPI.")

    try:
        client = AcmeClient(use_staging=use_staging)

        if not client.fetch_directory():
            return False, "Не удалось подключиться к директории Let's Encrypt ACME", None, None

        if not client.register_account(email):
            return False, "Не удалось зарегистрировать аккаунт в Let's Encrypt", None, None

        # 2. Создание заказа сертификата
        order_url, auths, finalize_url = client.create_order(domain)
        if not order_url or not auths or not finalize_url:
            return False, "Не удалось создать заказ в Let's Encrypt", None, None

        auth_url = auths[0]
        token, chal_url, auth_status = client.get_challenge_details(auth_url)
        if not token or not chal_url:
            return False, "Не удалось получить токен проверки HTTP-01", None, None

        if auth_status == "valid":
            logging.info("[ACME Client] Домен уже верифицирован.")
        else:
            # Генерация Key Authorization
            key_authorization = f"{token}.{client.thumbprint}"

            # Публикация токена для ответа
            ACME_CHALLENGES[token] = key_authorization
            logging.info(f"[ACME Client] Опубликован ключ авторизации для токена: {token}")

            # Инициация проверки Let's Encrypt
            if not client.trigger_challenge(chal_url):
                ACME_CHALLENGES.pop(token, None)
                return False, "Не удалось уведомить ACME о готовности проверки", None, None

            # Ожидание проверки
            success = client.poll_authorization(auth_url)
            ACME_CHALLENGES.pop(token, None)
            if not success:
                return False, "Проверка владения доменом не пройдена. Убедитесь, что DNS домена указывает на внешний IP вашего сервера и открыт порт 80.", None, None

        # 3. Финализация заказа и генерация ключа домена
        domain_key = ec.generate_private_key(ec.SECP256R1())
        cert_url = client.finalize_order(finalize_url, domain, domain_key)
        if not cert_url:
            return False, "Не удалось завершить заказ и подписать сертификат", None, None

        # 4. Скачивание цепочки сертификатов
        status, res_json, _ = client._send_request(cert_url, method="GET")
        if status != 200:
            return False, "Не удалось загрузить цепочку сертификатов", None, None

        cert_pem = res_json.get("raw")
        key_pem = domain_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.TraditionalOpenSSL,
            encryption_algorithm=serialization.NoEncryption()
        ).decode('utf-8')

        return True, "Сертификат Let's Encrypt успешно получен!", cert_pem, key_pem
    finally:
        if server_started and temp_server:
            temp_server.stop()
