import os
import hmac
import hashlib
import secrets
import json
import base64
from typing import Optional, Tuple
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from fastapi import Header, Query, Depends, HTTPException, status
from sqlalchemy.orm import Session

from core.config import settings
from database.db import get_db
from database.models import User, SessionToken


def hash_password(password: str) -> Tuple[str, str]:
    """
    Хеширует пароль с криптостойкой солью через PBKDF2-HMAC-SHA256 (100 000 итераций).
    Возвращает (salt_hex, hash_hex).
    """
    salt = secrets.token_hex(16)
    key = hashlib.pbkdf2_hmac(
        'sha256',
        password.encode('utf-8'),
        salt.encode('utf-8'),
        100000
    )
    return salt, key.hex()


def verify_password(password: str, salt: str, expected_hash: str) -> bool:
    """Проверяет пароль с защитой от тайминг-атак (hmac.compare_digest)."""
    key = hashlib.pbkdf2_hmac(
        'sha256',
        password.encode('utf-8'),
        salt.encode('utf-8'),
        100000
    )
    return hmac.compare_digest(key.hex(), expected_hash)


def generate_session_token() -> str:
    """Генерирует уникальный криптостойкий токен сессии."""
    return secrets.token_urlsafe(32)


def get_cipher_key() -> bytes:
    """Получает 256-битный ключ для AES-256-GCM из SECRET_KEY."""
    key_material = getattr(settings, "SECRET_KEY", None) or os.getenv("SECRET_KEY", "sentinel-music-crypto-secret-key-32")
    return hashlib.sha256(key_material.encode("utf-8")).digest()


def create_encrypted_token(session_token: str, username: str, user_id: int) -> str:
    """
    Создает криптографически защищенный и аутентифицированный токен на базе AES-256-GCM.
    Включает 96-битный случайный nonce и 128-битную метку аутентификации (integrity tag).
    Любая попытка модификации токена приводит к ошибке InvalidTag при расшифровке.
    """
    key = get_cipher_key()
    aesgcm = AESGCM(key)
    nonce = os.urandom(12)  # 96-битный nonce
    payload = {
        "t": session_token,
        "u": username,
        "uid": user_id
    }
    plaintext = json.dumps(payload, separators=(',', ':')).encode('utf-8')
    ciphertext = aesgcm.encrypt(nonce, plaintext, None)
    raw_blob = nonce + ciphertext
    return "enc:v1:" + base64.urlsafe_b64encode(raw_blob).decode('ascii')


def decrypt_encrypted_token(enc_token_str: str) -> Optional[str]:
    """
    Расшифровывает и проверяет аутентичность крипто-токена AES-256-GCM.
    Возвращает underlying session_token при успехе, либо None при нарушении целостности.
    """
    if not enc_token_str or not enc_token_str.startswith("enc:v1:"):
        return None
    raw_b64 = enc_token_str[len("enc:v1:"):]
    missing_padding = len(raw_b64) % 4
    if missing_padding:
        raw_b64 += '=' * (4 - missing_padding)
    try:
        raw_blob = base64.urlsafe_b64decode(raw_b64.encode('ascii'))
        if len(raw_blob) < 12 + 16:  # 12 байт nonce + 16 байт tag
            return None
        nonce = raw_blob[:12]
        ciphertext = raw_blob[12:]
        key = get_cipher_key()
        aesgcm = AESGCM(key)
        decrypted_bytes = aesgcm.decrypt(nonce, ciphertext, None)
        payload = json.loads(decrypted_bytes.decode('utf-8'))
        return payload.get("t")
    except Exception:
        return None


def get_current_user(
    authorization: Optional[str] = Header(None),
    token: Optional[str] = Query(None),
    db: Session = Depends(get_db)
) -> User:
    """
    Зависимость FastAPI для защиты эндпоинтов:
    Проверяет токен:
    1. В заголовке: Authorization: Bearer <token>
    2. В query-параметре: ?token=<token> (необходимо для <audio> и ExoPlayer стриминга)
    Поддерживает как классические токены, так и криптографически зашифрованные токены AES-256-GCM (enc:v1:).
    """
    extracted_token = None

    if authorization and authorization.startswith("Bearer "):
        extracted_token = authorization.split("Bearer ", 1)[1].strip()
    elif token:
        extracted_token = token.strip()

    if not extracted_token or "\x00" in extracted_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Необходима авторизация (отсутствует токен доступа)",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Если токен зашифрован через AES-256-GCM — расшифровываем и проверяем аутентичность
    if extracted_token.startswith("enc:v1:"):
        decrypted_session_token = decrypt_encrypted_token(extracted_token)
        if not decrypted_session_token:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Недействительный или поврежденный крипто-токен (нарушена целостность шифра)",
                headers={"WWW-Authenticate": "Bearer"},
            )
        extracted_token = decrypted_session_token

    # Ищем активную сессию в базе данных
    session_record = db.query(SessionToken).filter(SessionToken.token == extracted_token).first()
    if not session_record or not session_record.user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Недействительный или истекший токен сессии",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Проверка срока действия токена (защита от использования устаревших сессий)
    if session_record.expires_at:
        from datetime import datetime, timezone
        now_utc = datetime.now(timezone.utc).replace(tzinfo=None)
        if session_record.expires_at < now_utc:
            try:
                db.delete(session_record)
                db.commit()
            except Exception:
                db.rollback()
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Срок действия токена сессии истек",
                headers={"WWW-Authenticate": "Bearer"},
            )

    return session_record.user


def get_current_user_optional(
    authorization: Optional[str] = Header(None),
    token: Optional[str] = Query(None),
    db: Session = Depends(get_db)
) -> Optional[User]:
    """Опциональная авторизация (возвращает User или None)."""
    try:
        return get_current_user(authorization, token, db)
    except HTTPException:
        return None


def get_current_admin_user(
    current_user: User = Depends(get_current_user)
) -> User:
    """
    Зависимость FastAPI для защищенных административных эндпоинтов.
    Требует флаг is_admin == True, иначе возвращает 403 Forbidden.
    """
    if not current_user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Недостаточно прав (требуются права администратора)",
        )
    return current_user


# Константный фиктивный хеш для защиты от перебора логинов по времени ответа (Timing Attack / User Enumeration)
DUMMY_SALT = "0" * 32
DUMMY_HASH = "0" * 64


def dummy_verify_password(password: str) -> bool:
    """Выполняет идентичную по нагрузке проверку PBKDF2 для предотвращения тайминг-атак при неверном логине."""
    return verify_password(password, DUMMY_SALT, DUMMY_HASH)


def is_safe_track_file_path(file_path: Optional[str]) -> bool:
    """
    Защита от Path Traversal и доступа к произвольным файлам ОС:
    Проверяет, что путь к аудиофайлу безопасен, не содержит спецсимволов обхода каталогов
    и строго ограничен каталогом фонотеки (MUSIC_DIR) или временным тестовым каталогом.
    """
    if not file_path or not isinstance(file_path, str):
        return False
    if "\x00" in file_path or ".." in file_path:
        return False

    abs_path = os.path.realpath(os.path.abspath(file_path)).lower()
    dangerous_prefixes = (
        "/etc", "/proc", "/sys", "/dev", "/var", "/run", "/bin", "/sbin", "/lib",
        "/root", "/boot", "c:\\windows", "c:\\program files", "\\windows", "/windows", "system32"
    )
    if any(abs_path.startswith(p) for p in dangerous_prefixes):
        return False

    import tempfile

    music_dir = os.path.realpath(os.path.abspath(settings.MUSIC_DIR)).lower()
    temp_dir = os.path.realpath(os.path.abspath(tempfile.gettempdir())).lower()

    try:
        if os.path.commonpath([abs_path, music_dir]) == music_dir:
            return True
        if os.path.commonpath([abs_path, temp_dir]) == temp_dir:
            return True
    except (ValueError, Exception):
        return False

    return False
