import io
import re
import json
import base64
import socket
import urllib.parse
import qrcode
from typing import Optional, List, Dict, Any
from pydantic import BaseModel
from fastapi import APIRouter, Depends, HTTPException, Header, Query, Request, Response
from sqlalchemy.orm import Session

import time
from collections import defaultdict
from threading import Lock

import os
from core.config import settings
from database.db import get_db
from database.models import User, SessionToken, UserDevice
from core.security import (
    hash_password,
    verify_password,
    dummy_verify_password,
    generate_session_token,
    get_current_user,
    get_current_admin_user,
    get_current_user_optional,
    create_encrypted_token,
    decrypt_encrypted_token
)

router = APIRouter(prefix="/auth", tags=["Аутентификация"])

# Защита от перебора паролей (Brute-Force & DoS rate limiting)
_LOGIN_ATTEMPTS: dict[str, list[float]] = defaultdict(list)
_LOGIN_LOCK = Lock()
_MAX_FAILED_ATTEMPTS = 5
_LOCKOUT_SECONDS = 60


def check_login_rate_limit(client_ip: str):
    """Проверяет превышение лимита неудачных попыток входа с данного IP."""
    now = time.time()
    with _LOGIN_LOCK:
        attempts = [t for t in _LOGIN_ATTEMPTS[client_ip] if now - t < _LOCKOUT_SECONDS]
        _LOGIN_ATTEMPTS[client_ip] = attempts
        if len(attempts) >= _MAX_FAILED_ATTEMPTS:
            retry_after = int(_LOCKOUT_SECONDS - (now - attempts[0]))
            raise HTTPException(
                status_code=429,
                detail=f"Слишком много неудачных попыток входа. Повторите попытку через {max(1, retry_after)} сек.",
                headers={"Retry-After": str(max(1, retry_after))}
            )


def record_failed_login(client_ip: str):
    """Фиксирует неудачную попытку входа."""
    now = time.time()
    with _LOGIN_LOCK:
        _LOGIN_ATTEMPTS[client_ip].append(now)


def clear_failed_logins(client_ip: str | None = None):
    """Сбрасывает счетчик неудачных попыток после успешного входа или в тестах."""
    with _LOGIN_LOCK:
        if client_ip is None:
            _LOGIN_ATTEMPTS.clear()
        else:
            _LOGIN_ATTEMPTS.pop(client_ip, None)




def is_docker_or_loopback_ip(ip: str | None) -> bool:
    """Проверяет, является ли IP петлевым (loopback) или Docker-подсетью (172.16.0.0/12)."""
    if not ip:
        return True
    ip = ip.strip()
    if ip in ("127.0.0.1", "localhost", "0.0.0.0", "::1"):
        return True
    parts = ip.split(".")
    if len(parts) == 4:
        try:
            p0, p1 = int(parts[0]), int(parts[1])
            # Docker default bridge subnets: 172.16.0.0 - 172.31.255.255
            if p0 == 172 and 16 <= p1 <= 31:
                return True
        except ValueError:
            pass
    return False


def get_local_ip() -> str:
    """Определяет локальный IP-адрес хоста в локальной сети (LAN)."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"


def get_effective_lan_ip(request: Request | None = None) -> str:
    """
    Определяет реальный LAN IP-адрес сервера для подключения мобильных устройств:
    1. Если задана переменная SERVER_LAN_IP в settings или .env — используем её в первую очередь.
    2. Если запрос пришел с клиентского хоста (request.headers / request.url), который не является loopback/Docker — берем его.
    3. Если локальный сокетный IP не относится к Docker bridge (172.16-31.x.x) и loopback — берем его.
    4. При отсутствии внешних адресов возвращаем локальный IP или 127.0.0.1.
    """
    # 1. Явная конфигурация сервера
    configured_ip = getattr(settings, "SERVER_LAN_IP", None) or os.getenv("SERVER_LAN_IP")
    if configured_ip and configured_ip.strip():
        return configured_ip.strip()

    # 2. Определение из входящего HTTP-запроса пользователя
    if request:
        req_host = None
        x_forwarded = request.headers.get("x-forwarded-host")
        if x_forwarded:
            req_host = x_forwarded.split(",")[0].strip().split(":")[0]
        if not req_host:
            host_header = request.headers.get("host")
            if host_header:
                req_host = host_header.split(":")[0].strip()
        if not req_host and request.url.hostname:
            req_host = request.url.hostname

        if req_host and not is_docker_or_loopback_ip(req_host):
            return req_host

    # 3. Сокетный IP машины
    local_ip = get_local_ip()
    if not is_docker_or_loopback_ip(local_ip):
        return local_ip

    return local_ip


def build_qr_png_bytes(data: str) -> bytes:
    """Генерирует PNG-изображение QR-кода."""
    qr = qrcode.QRCode(
        version=None,
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=8,
        border=2,
    )
    qr.add_data(data)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


class RegisterRequest(BaseModel):
    username: str
    password: str


class LoginRequest(BaseModel):
    username: str
    password: str
    device_name: str | None = "Web / App"


@router.get("/status")
def get_auth_status(db: Session = Depends(get_db)):
    """Проверяет, зарегистрирован ли хотя бы один пользователь (для первого старта)."""
    count = db.query(User).count()
    return {"initialized": count > 0}


class CreateUserAdminRequest(BaseModel):
    username: str
    password: str
    is_admin: bool = False


def validate_username(username: str) -> str:
    """Проверяет валидность имени пользователя (длина 3-50, допустимые символы без управляющих)."""
    uname = (username or "").strip()
    if len(uname) < 3 or len(uname) > 50:
        raise HTTPException(status_code=400, detail="Имя пользователя должно содержать от 3 до 50 символов")
    if not re.match(r"^[\w\.\-@а-яА-ЯёЁ]+$", uname, re.UNICODE):
        raise HTTPException(status_code=400, detail="Имя пользователя содержит недопустимые символы")
    return uname


@router.post("/register")
def register_user(
    payload: RegisterRequest,
    current_user: Optional[User] = Depends(get_current_user_optional),
    db: Session = Depends(get_db)
):
    """
    Регистрация пользователя:
    1. Если в системе еще нет пользователей (первый запуск) — разрешено создание первого администратора.
    2. Если пользователи уже есть — регистрацию может производить ТОЛЬКО действующий администратор.
    """
    user_count = db.query(User).count()
    if user_count > 0:
        if not current_user or not current_user.is_admin:
            raise HTTPException(
                status_code=403,
                detail="Публичная регистрация отключена. Создавать новых пользователей может только администратор в настройках аккаунта."
            )

    username = validate_username(payload.username)
    if len(payload.password) < 4:
        raise HTTPException(status_code=400, detail="Пароль должен содержать от 4 символов")

    existing = db.query(User).filter(User.username == username).first()
    if existing:
        raise HTTPException(status_code=400, detail="Пользователь с таким логином уже существует")

    salt, p_hash = hash_password(payload.password)
    user = User(
        username=username,
        password_hash=p_hash,
        salt=salt,
        is_admin=(user_count == 0)
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    token_str = generate_session_token()
    session = SessionToken(token=token_str, user_id=user.id, device_name="Initial Registration")
    db.add(session)
    db.commit()

    return {"status": "ok", "token": token_str, "username": user.username, "is_admin": user.is_admin}


@router.get("/users")
def list_users(
    admin_user: User = Depends(get_current_admin_user),
    db: Session = Depends(get_db)
):
    """Список всех пользователей системы (доступно только администратору)."""
    users = db.query(User).order_by(User.id.asc()).all()
    return [
        {
            "id": u.id,
            "username": u.username,
            "is_admin": u.is_admin,
            "created_at": getattr(u, "created_at", None)
        }
        for u in users
    ]


@router.post("/users")
def admin_create_user(
    payload: CreateUserAdminRequest,
    admin_user: User = Depends(get_current_admin_user),
    db: Session = Depends(get_db)
):
    """Создание нового пользователя администратором в настройках."""
    username = validate_username(payload.username)
    if len(payload.password) < 4:
        raise HTTPException(status_code=400, detail="Пароль должен содержать от 4 символов")

    existing = db.query(User).filter(User.username == username).first()
    if existing:
        raise HTTPException(status_code=400, detail="Пользователь с таким логином уже существует")

    salt, p_hash = hash_password(payload.password)
    user = User(
        username=username,
        password_hash=p_hash,
        salt=salt,
        is_admin=payload.is_admin
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    return {
        "status": "success",
        "message": f"Пользователь «{user.username}» успешно создан",
        "user": {
            "id": user.id,
            "username": user.username,
            "is_admin": user.is_admin
        }
    }


@router.delete("/users/{user_id}")
async def admin_delete_user(
    user_id: int,
    admin_user: User = Depends(get_current_admin_user),
    db: Session = Depends(get_db)
):
    """
    Полное удаление пользователя администратором.
    Удаляет пользователя из базы данных и очищает всю связанную с ним информацию:
    - Активные и сохранённые сессии (SessionToken)
    - Зарегистрированные устройства (UserDevice)
    - Закрывает живые WebSocket-соединения Sentinel Connect
    """
    if admin_user.id == user_id:
        raise HTTPException(status_code=400, detail="Нельзя удалить собственный аккаунт администратора")

    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="Пользователь не найден")

    username = user.username

    # 1. Принудительное отключение активных подключений в Remote Connect
    try:
        from api.remote import remote_manager
        conn_dict = remote_manager._connections.get(user_id, {})
        for dev in list(conn_dict.values()):
            try:
                await dev.websocket.close(code=1008)
            except Exception:
                pass
            dev_id = getattr(dev, "device_id", None)
            if dev_id:
                await remote_manager.disconnect(user_id, dev_id)

        if user_id in remote_manager._connections:
            del remote_manager._connections[user_id]
        if user_id in remote_manager._last_playback_session:
            del remote_manager._last_playback_session[user_id]
    except Exception as e:
        print(f"[Admin] Ошибка при сбросе Remote Connect для user {user_id}: {e}")

    # 2. Удаление всех связанных записей: сессий и устройств пользователя
    db.query(SessionToken).filter(SessionToken.user_id == user_id).delete(synchronize_session=False)
    db.query(UserDevice).filter(UserDevice.user_id == user_id).delete(synchronize_session=False)

    # 3. Удаление самого пользователя
    db.delete(user)
    db.commit()

    return {"status": "success", "message": f"Пользователь «{username}» и вся связанная с ним информация удалены"}


@router.post("/login")
def login_user(
    payload: LoginRequest,
    request: Request,
    db: Session = Depends(get_db)
):
    """Вход с выдачей постоянного токена сессии с защитой от тайминг-атак и брутфорса."""
    client_ip = request.client.host if request.client else "unknown"
    check_login_rate_limit(client_ip)

    user = db.query(User).filter(User.username == payload.username.strip()).first()
    if not user:
        # Идентичная нагрузка PBKDF2 для предотвращения перебора логинов (User Enumeration)
        dummy_verify_password(payload.password)
        record_failed_login(client_ip)
        raise HTTPException(status_code=401, detail="Неверное имя пользователя или пароль")

    if not verify_password(payload.password, user.salt, user.password_hash):
        record_failed_login(client_ip)
        raise HTTPException(status_code=401, detail="Неверное имя пользователя или пароль")

    # Сбрасываем счетчик неудач при успешном логине
    clear_failed_logins(client_ip)

    token_str = generate_session_token()
    session = SessionToken(
        token=token_str,
        user_id=user.id,
        device_name=payload.device_name or "Web / Desktop"
    )
    db.add(session)
    db.commit()

    return {"status": "ok", "token": token_str, "username": user.username, "is_admin": user.is_admin}



class UpdateProfileRequest(BaseModel):
    current_password: str
    new_username: Optional[str] = None
    new_password: Optional[str] = None


@router.get("/me")
def get_current_user_profile(current_user: User = Depends(get_current_user)):
    """Проверка активности и профиля текущей сессии."""
    return {"id": current_user.id, "username": current_user.username, "is_admin": current_user.is_admin}


@router.patch("/profile")
@router.post("/profile")
def update_user_profile(
    payload: UpdateProfileRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Изменение имени пользователя и/или пароля.
    Требует обязательного ввода текущего пароля (защита от несанкционированного изменения).
    """
    # 1. Проверяем текущий пароль
    if not verify_password(payload.current_password, current_user.salt, current_user.password_hash):
        raise HTTPException(status_code=400, detail="Неверный текущий пароль")

    updated = False

    # 2. Обновление имени пользователя
    if payload.new_username is not None:
        new_uname = payload.new_username.strip()
        if new_uname and new_uname != current_user.username:
            new_uname = validate_username(new_uname)
            # Проверяем уникальность
            existing = db.query(User).filter(User.username == new_uname, User.id != current_user.id).first()
            if existing:
                raise HTTPException(status_code=400, detail="Пользователь с таким именем уже существует")
            current_user.username = new_uname
            updated = True

    # 3. Обновление пароля
    if payload.new_password is not None and payload.new_password.strip():
        new_pwd = payload.new_password.strip()
        if len(new_pwd) < 4:
            raise HTTPException(status_code=400, detail="Новый пароль должен содержать минимум 4 символа")
        salt, p_hash = hash_password(new_pwd)
        current_user.salt = salt
        current_user.password_hash = p_hash
        updated = True

    if not updated:
        raise HTTPException(status_code=400, detail="Не указаны данные для изменения")

    db.commit()
    db.refresh(current_user)

    return {
        "status": "success",
        "message": "Данные профиля успешно обновлены",
        "user": {
            "id": current_user.id,
            "username": current_user.username,
            "is_admin": current_user.is_admin
        }
    }


@router.post("/logout")
def logout_user(
    authorization: str | None = Header(None),
    token: str | None = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Выход и аннулирование текущего токена сессии."""
    raw_token = None
    if authorization and authorization.startswith("Bearer "):
        raw_token = authorization.split("Bearer ", 1)[1].strip()
    elif token:
        raw_token = token.strip()

    if raw_token:
        lookup_token = raw_token
        if raw_token.startswith("enc:v1:"):
            decrypted = decrypt_encrypted_token(raw_token)
            if decrypted:
                lookup_token = decrypted
        s = db.query(SessionToken).filter(SessionToken.token == lookup_token).first()
        if s:
            db.delete(s)
            db.commit()

    return {"status": "logged_out"}


@router.get("/qr/hosts")
def get_qr_available_hosts(request: Request):
    """
    Возвращает локальный адрес сервера (LAN) для подключения мобильного устройства.
    Все остальные тестовые IP (эмулятор 10.0.2.2, localhost) исключены.
    """
    lan_ip = get_effective_lan_ip(request)
    port = request.url.port or getattr(settings, "PORT", 8000)
    scheme = request.url.scheme or "http"
    return {
        "lan_url": f"{scheme}://{lan_ip}:{port}"
    }


@router.get("/qr/code")
def get_qr_code(
    request: Request,
    host: str | None = Query(None, description="Пользовательский адрес сервера (например http://192.168.1.100:8000)"),
    device_name: str = Query("Android Mobile (QR)", description="Имя подключаемого устройства"),
    create_new_session: bool = Query(True, description="Создать новый токен сессии для мобильного устройства"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Генерирует QR-код сопряжения для мобильного приложения Sentinel Music.
    Содержит сетевой адрес сервера, токен сессии и данные пользователя.
    """
    port = request.url.port or getattr(settings, "PORT", 8000)
    lan_ip = get_effective_lan_ip(request)
    scheme = request.url.scheme or "http"

    if host and host.strip():
        h = host.strip().rstrip("/")
        # Если передан Docker IP (172.16-31.x.x) или loopback, автоматически заменяем на реальный LAN IP
        try:
            parsed = urllib.parse.urlparse(h)
            if is_docker_or_loopback_ip(parsed.hostname):
                h = f"{parsed.scheme or scheme}://{lan_ip}:{parsed.port or port}"
        except Exception:
            pass
        server_url = h
    else:
        server_url = f"{scheme}://{lan_ip}:{port}"

    if create_new_session:
        token_str = generate_session_token()
        session = SessionToken(token=token_str, user_id=current_user.id, device_name=device_name)
        db.add(session)
        db.commit()
    else:
        s = db.query(SessionToken).filter(SessionToken.user_id == current_user.id).first()
        token_str = s.token if s else generate_session_token()

    # Защита сопряжения через современный аутентифицированный шифр AES-256-GCM
    enc_token = create_encrypted_token(
        session_token=token_str,
        username=current_user.username,
        user_id=current_user.id
    )

    payload_data = {
        "url": server_url,
        "token": enc_token,
        "username": current_user.username
    }
    payload_json = json.dumps(payload_data, separators=(",", ":"))

    png_bytes = build_qr_png_bytes(payload_json)
    b64_img = f"data:image/png;base64,{base64.b64encode(png_bytes).decode('utf-8')}"

    encoded_data = urllib.parse.quote(payload_json)
    image_url = f"/api/auth/qr/image?data={encoded_data}"

    return {
        "status": "ok",
        "server_url": server_url,
        "token": token_str,
        "encrypted_token": enc_token,
        "username": current_user.username,
        "payload": payload_data,
        "payload_json": payload_json,
        "qr_image": b64_img,
        "image_url": image_url
    }


@router.get("/qr/image")
def get_qr_image(
    data: str | None = Query(None, description="Строка данных для кодирования в QR-код"),
    token: str | None = Query(None, description="Токен сессии для кодирования сопряжения"),
    host: str | None = Query(None, description="Пользовательский адрес сервера"),
    authorization: str | None = Header(None),
    db: Session = Depends(get_db)
):
    """
    Генерирует бинарное PNG-изображение QR-кода.
    """
    if data:
        if len(data) > 2048:
            raise HTTPException(status_code=400, detail="Превышен максимальный размер данных для QR-кода (максимум 2048 символов)")
        payload_str = data
    else:
        raw_token = token
        if not raw_token and authorization and authorization.startswith("Bearer "):
            raw_token = authorization.split("Bearer ", 1)[1].strip()

        if not raw_token:
            raise HTTPException(status_code=400, detail="Укажите параметр 'data' или 'token'")

        lookup_token = raw_token
        if lookup_token.startswith("enc:v1:"):
            decrypted = decrypt_encrypted_token(lookup_token)
            if decrypted:
                lookup_token = decrypted

        session = db.query(SessionToken).filter(SessionToken.token == lookup_token).first()
        if not session or not session.user:
            raise HTTPException(status_code=401, detail="Недействительный токен сессии")

        server_url = host.rstrip("/") if host else f"http://{get_local_ip()}:8000"
        payload_dict = {
            "url": server_url,
            "token": session.token,
            "username": session.user.username,
            "is_admin": session.user.is_admin
        }
        payload_str = json.dumps(payload_dict, separators=(",", ":"))

    png_bytes = build_qr_png_bytes(payload_str)
    return Response(content=png_bytes, media_type="image/png")
