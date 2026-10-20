"""
Sentinel Connect — Модуль удаленного управления воспроизведением (Remote Control / Connect).
Позволяет устройствам пользователя (Android, PC Desktop, Web) обнаруживать друг друга
и синхронизировать воспроизведение через двусторонний WebSocket-канал.
"""

import time
import asyncio
import logging
from typing import Optional, Dict, Any, List
from collections import defaultdict
from pydantic import BaseModel
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from database.db import get_db, SessionLocal
from database.models import User, SessionToken, UserDevice, utc_now
from core.security import get_current_user, decrypt_encrypted_token

logger = logging.getLogger("sentinel.remote")

router = APIRouter(prefix="/remote", tags=["Sentinel Connect (Remote Control)"])


class ConnectedDevice:
    """Представление подключенного устройства в сессии пользователя."""
    def __init__(
        self,
        websocket: WebSocket,
        device_id: str,
        name: str,
        device_type: str,
        user_id: int
    ):
        self.websocket = websocket
        self.device_id = device_id
        self.name = name
        self.device_type = device_type  # "player", "remote", "hybrid"
        self.user_id = user_id
        self.connected_at = time.time()
        self.last_seen = time.time()
        self.state: Dict[str, Any] = {
            "is_playing": False,
            "current_track": None,
            "position_ms": 0,
            "duration_ms": 0,
            "queue": [],
            "volume": 1.0,
            "is_muted": False,
            "repeat_mode": "off",
            "is_shuffle": False,
            "equalizer": None,
            "limiter": None,
        }

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.device_id,
            "name": self.name,
            "type": self.device_type,
            "connected_at": self.connected_at,
            "last_seen": self.last_seen,
            "can_play": self.device_type in ("player", "hybrid"),
            **self.state
        }


class RemoteConnectionManager:
    """Менеджер активных подключений Sentinel Connect, сгруппированных по пользователям."""
    def __init__(self):
        # user_id -> dict[device_id, ConnectedDevice]
        self._connections: Dict[int, Dict[str, ConnectedDevice]] = defaultdict(dict)
        self._last_playback_session: Dict[int, Dict[str, Any]] = {}
        self._lock = asyncio.Lock()

    async def connect(self, device: ConnectedDevice):
        async with self._lock:
            # Если уже было устройство с таким же device_id (например, переподключение вкладки) — закрываем старый сокет
            existing = self._connections[device.user_id].get(device.device_id)
            if existing:
                try:
                    await existing.websocket.close(code=status.WS_1000_NORMAL_CLOSURE)
                except Exception:
                    pass
            self._connections[device.user_id][device.device_id] = device

        logger.info(f"[Remote] Устройство подключено: {device.name} ({device.device_id}) для пользователя {device.user_id}")

        # Отправляем вновь подключенному устройству список всех устройств и его подтверждение
        await self._send_json_safe(device.websocket, {
            "type": "welcome",
            "device_id": device.device_id,
            "devices": self.get_user_devices(device.user_id)
        })

        # Уведомляем все остальные устройства пользователя о появлении нового
        await self.broadcast_devices(device.user_id, exclude_device_id=device.device_id)

    async def disconnect(self, user_id: int, device_id: str, websocket: Optional[WebSocket] = None):
        async with self._lock:
            user_devs = self._connections.get(user_id)
            if user_devs and device_id in user_devs:
                dev = user_devs[device_id]
                # Защита от race condition: если устройство уже переподключилось с новым сокетом,
                # закрытие старого соединения не должно сбрасывать активное новое.
                if websocket is not None and dev.websocket != websocket:
                    return

                if dev.state.get("current_track"):
                    self._last_playback_session[user_id] = {
                        "current_track": dev.state.get("current_track"),
                        "position_ms": dev.state.get("position_ms", 0),
                        "duration_ms": dev.state.get("duration_ms", 0),
                        "queue": dev.state.get("queue", []),
                        "device_name": dev.name,
                        "saved_at": time.time()
                    }
                del user_devs[device_id]
                if not user_devs:
                    del self._connections[user_id]
                logger.info(f"[Remote] Устройство отключено: {device_id} (user {user_id})")

        # Оповещаем оставшиеся устройства
        await self.broadcast_devices(user_id)

    def get_last_playback_session(self, user_id: int) -> Optional[Dict[str, Any]]:
        return self._last_playback_session.get(user_id)

    def get_user_devices(self, user_id: int) -> List[Dict[str, Any]]:
        user_devs = self._connections.get(user_id, {})
        return [dev.to_dict() for dev in user_devs.values()]

    async def broadcast_devices(self, user_id: int, exclude_device_id: Optional[str] = None):
        """Отправляет обновленный список устройств всем подключенным клиентам пользователя."""
        devices_list = self.get_user_devices(user_id)
        msg = {
            "type": "devices_update",
            "devices": devices_list
        }
        await self._broadcast_to_user(user_id, msg, exclude_device_id=exclude_device_id)

    async def update_device_state(self, user_id: int, device_id: str, new_state: Dict[str, Any]):
        """Обновляет состояние плеера устройства и транслирует его всем остальным устройствам."""
        user_devs = self._connections.get(user_id, {})
        device = user_devs.get(device_id)
        if not device:
            return

        device.last_seen = time.time()
        for k, v in new_state.items():
            if k in device.state:
                device.state[k] = v

        if device.state.get("current_track"):
            self._last_playback_session[user_id] = {
                "current_track": device.state.get("current_track"),
                "position_ms": device.state.get("position_ms", 0),
                "duration_ms": device.state.get("duration_ms", 0),
                "queue": device.state.get("queue", []),
                "device_name": device.name,
                "saved_at": time.time()
            }

        msg = {
            "type": "device_state",
            "device_id": device_id,
            "device": device.to_dict()
        }
        await self._broadcast_to_user(user_id, msg, exclude_device_id=device_id)

    async def send_command(
        self,
        user_id: int,
        from_device_id: str,
        target_device_id: str,
        command: str,
        payload: Optional[Dict[str, Any]] = None
    ) -> bool:
        """Пересылает команду управления целевому плееру."""
        user_devs = self._connections.get(user_id, {})
        target = user_devs.get(target_device_id)
        if not target:
            logger.warning(f"[Remote] Целевое устройство {target_device_id} не найдено в сети")
            return False

        msg = {
            "type": "command",
            "from_device_id": from_device_id,
            "command": command.upper(),
            "payload": payload or {}
        }
        return await self._send_json_safe(target.websocket, msg)

    async def _broadcast_to_user(self, user_id: int, message: Dict[str, Any], exclude_device_id: Optional[str] = None):
        user_devs = [
            dev for dev in list(self._connections.get(user_id, {}).values())
            if not (exclude_device_id and dev.device_id == exclude_device_id)
        ]
        if not user_devs:
            return
        tasks = [self._send_json_safe(dev.websocket, message) for dev in user_devs]
        await asyncio.gather(*tasks, return_exceptions=True)

    async def _send_json_safe(self, ws: WebSocket, data: Dict[str, Any]) -> bool:
        try:
            await ws.send_json(data)
            return True
        except Exception as e:
            logger.debug(f"[Remote] Ошибка отправки в сокет: {e}")
            return False


# Глобальный инстанс менеджера удаленных подключений
remote_manager = RemoteConnectionManager()


# --- Pydantic Схемы для REST API ---

class RemoteCommandRequest(BaseModel):
    target_device_id: str
    command: str  # PLAY, PAUSE, TOGGLE_PLAY, NEXT, PREV, SEEK, SET_VOLUME, PLAY_TRACK, SHUFFLE, REPEAT
    payload: Optional[Dict[str, Any]] = None


# --- REST Эндпоинты ---

@router.get("/status")
async def get_remote_status(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Проверяет:
    1. Существует ли вообще ПК у пользователя (в базе известных устройств или истории сессий).
    2. Находится ли ПК прямо сейчас в сети (активен ли сокет Sentinel Connect).
    3. Возвращает данные об устройстве для предложения выбора воспроизведения на клиенте.
    """
    online_devices = remote_manager.get_user_devices(current_user.id)
    # Находим онлайн-плеер (ПК / Desktop / Браузер)
    online_pc = next((d for d in online_devices if d.get("can_play")), None)

    # Ищем в базе сохраненных устройств
    known_pcs = db.query(UserDevice).filter(
        UserDevice.user_id == current_user.id,
        UserDevice.device_type.in_(["player", "hybrid"])
    ).all()

    # Проверяем токены сессий (если ПК входил ранее, но сокет еще не регистрировался)
    has_pc_in_sessions = False
    session_pc_name = "Windows ПК (Desktop)"
    sessions = db.query(SessionToken).filter(SessionToken.user_id == current_user.id).all()
    for s in sessions:
        d_name = (s.device_name or "").lower()
        if any(keyword in d_name for keyword in ["desktop", "web", "pc", "пк", "windows", "linux", "mac"]):
            has_pc_in_sessions = True
            session_pc_name = s.device_name
            break

    has_pc = bool(online_pc) or bool(known_pcs) or has_pc_in_sessions
    is_pc_online = bool(online_pc)

    pc_info = None
    if online_pc:
        pc_info = {
            "id": online_pc["id"],
            "name": online_pc["name"],
            "type": online_pc.get("type", "player"),
            "can_play": True,
            "is_online": True,
            "is_playing": online_pc.get("is_playing", False),
            "current_track": online_pc.get("current_track"),
            "position_ms": online_pc.get("position_ms", 0),
            "duration_ms": online_pc.get("duration_ms", 0),
            "queue": online_pc.get("queue", []),
            "equalizer": online_pc.get("equalizer"),
            "limiter": online_pc.get("limiter")
        }
    elif known_pcs:
        last_pc = sorted(known_pcs, key=lambda x: str(x.last_seen_at or ""), reverse=True)[0]
        pc_info = {
            "id": last_pc.device_id,
            "name": last_pc.name,
            "type": last_pc.device_type,
            "can_play": True,
            "is_online": False,
            "is_playing": False,
            "current_track": None,
            "position_ms": 0,
            "duration_ms": 0,
            "queue": []
        }
    elif has_pc_in_sessions:
        pc_info = {
            "id": "known_pc_session",
            "name": session_pc_name,
            "type": "player",
            "can_play": True,
            "is_online": False,
            "is_playing": False,
            "current_track": None,
            "position_ms": 0,
            "duration_ms": 0,
            "queue": []
        }

    last_session = remote_manager.get_last_playback_session(current_user.id)
    # Если есть активное онлайн-устройство с треком (например, мобильный телефон), используем его сессию, если она новее
    active_device = next((d for d in online_devices if d.get("current_track")), None)
    if active_device:
        dev_time = active_device.get("last_seen", time.time())
        if not last_session or dev_time >= last_session.get("saved_at", 0):
            last_session = {
                "current_track": active_device.get("current_track"),
                "position_ms": active_device.get("position_ms", 0),
                "duration_ms": active_device.get("duration_ms", 0),
                "queue": active_device.get("queue", []),
                "device_name": active_device.get("name"),
                "saved_at": dev_time
            }

    return {
        "has_pc": has_pc,
        "is_pc_online": is_pc_online,
        "pc_device": pc_info,
        "online_devices": online_devices,
        "last_playback_session": last_session
    }


@router.get("/devices")
async def get_online_devices(current_user: User = Depends(get_current_user)):
    """Возвращает список всех активных устройств текущего пользователя."""
    return {"devices": remote_manager.get_user_devices(current_user.id)}


@router.post("/command")
async def send_remote_command(
    req: RemoteCommandRequest,
    current_user: User = Depends(get_current_user)
):
    """Отправляет команду воспроизведения целевому устройству через REST (альтернатива сокету)."""
    success = await remote_manager.send_command(
        user_id=current_user.id,
        from_device_id="rest_api",
        target_device_id=req.target_device_id,
        command=req.command,
        payload=req.payload
    )
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Устройство не найдено или офлайн"
        )
    return {"status": "ok", "delivered": True}


# --- WebSocket Эндпоинт ---

@router.websocket("/ws")
async def remote_websocket_endpoint(
    websocket: WebSocket,
    token: str = Query(...),
    device_id: str = Query(...),
    device_name: str = Query("Устройство"),
    device_type: str = Query("hybrid")  # "player", "remote", "hybrid"
):
    """
    Полнодуплексный WebSocket шлюз Sentinel Connect.
    Служит шиной обмена состояниями и командами между устройствами одного аккаунта.
    """
    clean_device_id = str(device_id).strip()[:128]
    clean_device_name = str(device_name).strip()[:128] or "Устройство"
    clean_device_type = str(device_type).strip()[:32]
    if clean_device_type not in ("player", "remote", "hybrid"):
        clean_device_type = "hybrid"

    origin = websocket.headers.get("origin")
    if origin:
        import re
        from main import cors_origins
        is_allowed = (origin in cors_origins) or bool(
            re.match(r"^https?://(localhost|127\.0\.0\.1|192\.168\.\d+\.\d+|10\.\d+\.\d+\.\d+)(:\d+)?$", origin)
        )
        if not is_allowed:
            await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
            return

    await websocket.accept()

    # Аутентификация пользователя по сессионному токену
    user_id: Optional[int] = None
    if "\x00" not in token:
        lookup_token = token.strip()
        if lookup_token.startswith("enc:v1:"):
            decrypted = decrypt_encrypted_token(lookup_token)
            lookup_token = decrypted

        if lookup_token:
            with SessionLocal() as db:
                session_record = db.query(SessionToken).filter(SessionToken.token == lookup_token).first()
            if session_record:
                if session_record.expires_at and session_record.expires_at < utc_now():
                    session_record = None
                else:
                    user_id = session_record.user_id

                # Фиксируем устройство в базе известных устройств пользователя
                if user_id:
                    try:
                        known = db.query(UserDevice).filter(
                            UserDevice.user_id == user_id,
                            UserDevice.device_id == clean_device_id
                        ).first()
                        if known:
                            known.name = clean_device_name
                            known.device_type = clean_device_type
                            known.last_seen_at = utc_now()
                        else:
                            known = UserDevice(
                                user_id=user_id,
                                device_id=clean_device_id,
                                name=clean_device_name,
                                device_type=clean_device_type,
                                last_seen_at=utc_now()
                            )
                            db.add(known)
                        db.commit()
                    except Exception as e:
                        db.rollback()
                        logger.warning(f"[Remote] Ошибка регистрации устройства: {e}")

    if not user_id:
        await websocket.send_json({
            "type": "error",
            "message": "Недействительный или истекший токен авторизации"
        })
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    device = ConnectedDevice(
        websocket=websocket,
        device_id=clean_device_id,
        name=clean_device_name,
        device_type=clean_device_type,
        user_id=user_id
    )

    await remote_manager.connect(device)

    try:
        while True:
            data = await websocket.receive_json()
            if not isinstance(data, dict):
                continue
            action = str(data.get("action") or "").lower()

            if action == "state_update":
                # Обновление состояния текущего плеера (прогресс, трек, статус)
                state_data = data.get("state")
                if isinstance(state_data, dict):
                    await remote_manager.update_device_state(user_id, device.device_id, state_data)

            elif action == "command":
                # Отправка команды конкретному устройству
                target_id = data.get("target_device_id")
                cmd = data.get("command")
                payload = data.get("payload")
                if target_id and cmd and isinstance(target_id, str) and isinstance(cmd, str):
                    clean_payload = payload if isinstance(payload, dict) else {}
                    await remote_manager.send_command(
                        user_id=user_id,
                        from_device_id=device.device_id,
                        target_device_id=target_id.strip(),
                        command=cmd.strip(),
                        payload=clean_payload
                    )

            elif action == "ping":
                await websocket.send_json({"type": "pong", "time": time.time()})

            elif action == "request_devices":
                await websocket.send_json({
                    "type": "devices_update",
                    "devices": remote_manager.get_user_devices(user_id)
                })

    except WebSocketDisconnect:
        await remote_manager.disconnect(user_id, device.device_id, websocket)
    except Exception as e:
        logger.warning(f"[Remote] Ошибка соединения {device.device_id}: {e}")
        await remote_manager.disconnect(user_id, device.device_id, websocket)
