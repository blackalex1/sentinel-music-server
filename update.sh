#!/usr/bin/env bash
set -e

# Переход в директорию скрипта
cd "$(dirname "$0")"

echo "=========================================="
echo " 🚀 Обновление Sentinel Music Server"
echo "=========================================="

run_with_timeout() {
    local seconds="$1"
    shift
    if command -v timeout &>/dev/null; then
        timeout "$seconds" "$@"
    else
        "$@"
    fi
}

pull_updates() {
    local branch="${1:-main}"
    local origin_url
    origin_url=$(git remote get-url origin 2>/dev/null || echo "https://github.com/blackalex1/sentinel-music-server.git")

    # Извлекаем путь owner/repo (работает и для HTTPS, и для SSH)
    local repo_path="blackalex1/sentinel-music-server"
    if [[ "$origin_url" =~ github\.com[:/]([^/]+/[^/.]+)(\.git)? ]]; then
        repo_path="${BASH_REMATCH[1]}"
    fi

    echo ">> [1/3] 📥 Проверка доступности репозитория (ветка $branch)..."

    # 1. Проверяем доступность официального GitHub (таймаут 4 сек)
    if run_with_timeout 4 git ls-remote "$origin_url" HEAD &>/dev/null; then
        echo "✅ Связь с GitHub стабильна. Скачивание обновлений..."
        git fetch origin "$branch"
        git reset --hard "origin/$branch"
        return 0
    fi

    echo "⚠️ Официальный GitHub недоступен (таймаут или сетевая блокировка)."
    echo "🔄 Подключение через резервные зеркала GitHub..."

    # Проверенные высокоскоростные зеркала GitHub
    local mirrors=(
        "https://ghfast.top/https://github.com/${repo_path}.git"
        "https://gh-proxy.com/https://github.com/${repo_path}.git"
        "https://githubproxy.cc/https://github.com/${repo_path}.git"
    )

    local success=0
    for mirror in "${mirrors[@]}"; do
        local host
        host=$(echo "$mirror" | sed -E 's#https?://([^/]+)/.*#\1#')
        echo "   -> Проверка зеркала: $host ..."
        if run_with_timeout 4 git ls-remote "$mirror" HEAD &>/dev/null; then
            echo "   ✅ Зеркало $host доступно! Загрузка обновлений..."
            if git fetch "$mirror" "$branch" && git reset --hard FETCH_HEAD; then
                success=1
                break
            fi
        fi
    done

    if [ "$success" -ne 1 ]; then
        echo "❌ Ошибка: ни официальный GitHub, ни резервные зеркала не ответили на запрос."
        echo "Пожалуйста, проверьте интернет-соединение или настройки DNS."
        exit 1
    fi
}

# Режим фонового демона для 1-Click Update из веб-интерфейса
if [[ "$*" == *"--watch"* ]] || [[ "$*" == *"-w"* ]]; then
    echo "=========================================="
    echo " 👀 Режим фонового отслеживания 1-Click Update"
    echo "=========================================="
    echo " Ожидание триггера обновления из веб-интерфейса (data/update.trigger)..."
    TRIGGER_FILE="data/update.trigger"
    while true; do
        if [ -f "$TRIGGER_FILE" ]; then
            echo ""
            echo "⚡ [$(date '+%Y-%m-%d %H:%M:%S')] Обнаружен триггер обновления из веб-интерфейса!"
            rm -f "$TRIGGER_FILE"
            pull_updates "main"
            if command -v docker &> /dev/null; then
                if docker compose version &> /dev/null; then
                    COMPOSE_CMD="docker compose"
                elif command -v docker-compose &> /dev/null; then
                    COMPOSE_CMD="docker-compose"
                fi
                echo "🐳 Пересборка и перезапуск контейнера..."
                $COMPOSE_CMD up -d --build
            fi
            echo "✅ Контейнер успешно обновлен и перезапущен!"
            echo "👀 Возврат в режим отслеживания..."
        fi
        sleep 3
    done
    exit 0
fi

pull_updates "main"

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

    echo "=========================================="
    echo " ✅ Sentinel Music Server успешно запущен!"
    if [[ "$*" == *"--no-logs"* ]] || [[ "$*" == *"-n"* ]]; then
        echo " 📊 Логи контейнера:"
        $COMPOSE_CMD logs --tail=20 music-server
    elif [ -t 1 ]; then
        echo " 📡 Потоковый вывод логов в реальном времени (Ctrl+C для выхода):"
        echo "=========================================="
        $COMPOSE_CMD logs -f --tail=30 music-server
    else
        echo " 📊 Последние логи сервиса:"
        echo "=========================================="
        $COMPOSE_CMD logs --tail=30 music-server
    fi
else
    echo "⚠️ Docker не найден. Файлы репозитория обновлены."
fi
