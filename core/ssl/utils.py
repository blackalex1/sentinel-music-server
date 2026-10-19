import os
import shutil
import logging
from pathlib import Path
from core.config import settings
from core.ssl.flow import run_acme_flow

SSL_CERT_PATH = Path(settings.DATA_DIR) / "cert.pem"
SSL_KEY_PATH = Path(settings.DATA_DIR) / "key.pem"


def generate_self_signed_cert(domain: str = "localhost") -> tuple[bool, str]:
    """Генерирует самоподписанный SSL-сертификат для локальной разработки или LAN."""
    try:
        import ipaddress, datetime
        from cryptography import x509
        from cryptography.x509.oid import NameOID
        from cryptography.hazmat.primitives import hashes, serialization
        from cryptography.hazmat.primitives.asymmetric import rsa

        key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        subject = issuer = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, domain)])
        
        san_list = []
        is_ip = False
        try:
            parsed_ip = ipaddress.ip_address(domain)
            san_list.append(x509.IPAddress(parsed_ip))
            is_ip = True
        except ValueError:
            san_list.append(x509.DNSName(domain))

        if not is_ip and domain != "localhost":
            san_list.append(x509.DNSName("localhost"))

        try:
            san_list.append(x509.IPAddress(ipaddress.ip_address("127.0.0.1")))
        except Exception:
            pass

        san = x509.SubjectAlternativeName(san_list)
        now = datetime.datetime.now(datetime.timezone.utc)
        cert = (
            x509.CertificateBuilder()
            .subject_name(subject)
            .issuer_name(issuer)
            .public_key(key.public_key())
            .serial_number(x509.random_serial_number())
            .not_valid_before(now)
            .not_valid_after(now + datetime.timedelta(days=365))
            .add_extension(san, critical=False)
            .sign(key, hashes.SHA256())
        )

        SSL_CERT_PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(SSL_KEY_PATH, "wb") as f:
            f.write(key.private_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PrivateFormat.TraditionalOpenSSL,
                encryption_algorithm=serialization.NoEncryption()
            ))
        with open(SSL_CERT_PATH, "wb") as f:
            f.write(cert.public_bytes(serialization.Encoding.PEM))

        return True, "Самоподписанный сертификат успешно создан."
    except Exception as e:
        return False, f"Ошибка создания сертификата: {e}"


def request_ssl_cert(domain: str, email: str = "") -> tuple[bool, str]:
    """
    Выпускает SSL-сертификат Let's Encrypt через встроенный ACME HTTP-01 клиент.
    Сохраняет cert.pem и key.pem в директорию данных DATA_DIR.
    """
    try:
        success, msg, cert_pem, key_pem = run_acme_flow(domain, email)
        if not success:
            return False, msg

        SSL_CERT_PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(SSL_CERT_PATH, "w", encoding="utf-8") as f:
            f.write(cert_pem)
        with open(SSL_KEY_PATH, "w", encoding="utf-8") as f:
            f.write(key_pem)

        try:
            os.chmod(SSL_CERT_PATH, 0o644)
            os.chmod(SSL_KEY_PATH, 0o600)
        except Exception:
            pass

        return True, "SSL-сертификат Let's Encrypt успешно получен и установлен!"
    except Exception as e:
        return False, f"Ошибка при получении сертификата: {e}"


def get_ssl_status() -> dict:
    """Возвращает информацию о текущем SSL-сертификате."""
    has_cert = SSL_CERT_PATH.exists() and SSL_KEY_PATH.exists()
    details = {
        "installed": has_cert,
        "cert_path": str(SSL_CERT_PATH),
        "key_path": str(SSL_KEY_PATH),
        "common_name": None,
        "expires_at": None,
        "is_self_signed": False
    }

    if has_cert:
        try:
            from cryptography import x509
            with open(SSL_CERT_PATH, "rb") as f:
                cert = x509.load_pem_x509_certificate(f.read())
            cn = cert.subject.get_attributes_for_oid(x509.oid.NameOID.COMMON_NAME)
            details["common_name"] = cn[0].value if cn else "Unknown"
            details["expires_at"] = cert.not_valid_after_utc.strftime("%Y-%m-%d %H:%M:%S UTC")
            details["is_self_signed"] = (cert.issuer == cert.subject)
        except Exception:
            pass

    return details
