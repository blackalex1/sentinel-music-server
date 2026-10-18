"""
Модуль безопасной инициализации учетных данных (Zero Hardcode).
Генерирует криптографически стойкий логин и пароль при первом старте сервиса,
сохраняет их в базе данных и выводит в консоль и защищенный файл.
"""

import os
import secrets
from typing import Optional, Dict
from sqlalchemy.orm import Session

from database.models import User
from core.security import hash_password


def generate_secure_credentials(prefix: str = "admin") -> tuple[str, str]:
    """Генерирует случайный уникальный логин и криптостойкий пароль."""
    random_suffix = secrets.token_hex(2)
    username = f"{prefix}_{random_suffix}"
    # 16-символьный URL-safe пароль высокой энтропии
    password = secrets.token_urlsafe(12)
    return username, password


def bootstrap_admin_user(db: Session, credentials_path: Optional[str] = None) -> Optional[Dict[str, str]]:
    """
    Проверяет наличие пользователей в базе данных.
    Если база пуста (первый запуск):
    1. Генерирует уникальный логин и стойкий пароль.
    2. Хеширует с уникальной солью PBKDF2 и создает администратора.
    3. Записывает данные в файл credentials_path (если указан).
    4. Выводит красивый защищенный баннер в консоль/логи.
    Если пользователи уже есть, ничего не меняет.
    """
    user_count = db.query(User).count()
    if user_count > 0:
        return None

    username, password = generate_secure_credentials()
    salt, p_hash = hash_password(password)

    admin_user = User(
        username=username,
        password_hash=p_hash,
        salt=salt,
        is_admin=True
    )
    db.add(admin_user)
    db.commit()
    db.refresh(admin_user)

    # Сохранение в локальный файл учетных данных
    if credentials_path:
        try:
            folder = os.path.dirname(os.path.abspath(credentials_path))
            if folder:
                os.makedirs(folder, exist_ok=True)
            with open(credentials_path, "w", encoding="utf-8") as f:
                f.write(f"LOGIN={username}\n")
                f.write(f"PASSWORD={password}\n")
            # На Linux/macOS ограничиваем права файла только владельцем (chmod 0600)
            if hasattr(os, "chmod") and os.name != "nt":
                os.chmod(credentials_path, 0o600)
        except Exception as e:
            print(f"[Bootstrap] Предупреждение при записи файла credentials: {e}")

    # Печать информационного баннера в логах сервера
    banner = f"""
================================================================================
🔐 [SECURITY] СГЕНЕРИРОВАНЫ УЧЕТНЫЕ ДАННЫЕ АДМИНИСТРАТОРА (ПЕРВЫЙ СТАРТ)
--------------------------------------------------------------------------------
   Логин:   {username}
   Пароль:  {password}
"""
    if credentials_path:
        banner += f"   Файл:    {credentials_path}\n"
    banner += """--------------------------------------------------------------------------------
   Используйте эти данные для входа в веб-плеер или мобильное приложение!
================================================================================
"""
    print(banner)

    return {"username": username, "password": password}
