#!/usr/bin/env bash
set -e

# Переход в директорию скрипта
cd "$(dirname "$0")"

echo "=========================================="
echo " 🚀 Обновление Sentinel Music Server"
echo "=========================================="

echo ">> [1/3] 📥 Получение обновлений из репозитория..."
git pull origin main

echo ">> [2/3] 🐳 Применение изменений в Docker..."
if command -v docker &> /dev/null; then
    if docker compose version &> /dev/null; then
        COMPOSE_CMD="docker compose"
    elif command -v docker-compose &> /dev/null; then
        COMPOSE_CMD="docker-compose"
    else
        echo "⚠️ Docker Compose не найден. Репозиторий обновлен, перезапустите контейнеры вручную."
        exit 0
    fi

    # Пересборка с использованием кэша слоев и перезапуск
    $COMPOSE_CMD up -d --build

    echo ">> [3/3] 📊 Текущий статус контейнеров:"
    $COMPOSE_CMD ps
else
    echo "⚠️ Docker не найден. Файлы репозитория обновлены."
fi

echo "=========================================="
echo " ✅ Sentinel Music Server успешно обновлен!"
echo "=========================================="
