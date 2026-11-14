#!/usr/bin/env bash
# ==============================================================================
# 🚀 Sentinel Music Server - Zero-Downtime Rebuild & Update Manager
# ==============================================================================
# Возможности:
# - Проверка и применение обновлений из GitHub или проверенных зеркал
# - Отображение списка коммитов и статистики изменений файлов (+/- строк)
# - Построчный просмотр измененных строк (--diff)
# - Безопасный stash локальных изменений перед обновлением
# - Самообновление скрипта update.sh при его изменении в репозитории
# - Бесшовный перезапуск: пересборка Docker-образа БЕЗ остановки работающего сервиса
# - Проверка состояния контейнера после перезапуска
# - Очистка неиспользуемых висячих слоев сборщика и образов Docker
# - Фоновый режим отслеживания 1-Click Update (--watch)
# ==============================================================================

set -e

# Переход в директорию скрипта
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Цветовое оформление ANSI
BOLD="\033[1m"
DIM="\033[2m"
CYAN="\033[0;36m"
GREEN="\033[0;32m"
YELLOW="\033[1;33m"
RED="\033[0;31m"
WHITE="\033[1;37m"
RESET="\033[0m"

# Отключаем цветовые коды, если вывод перенаправлен в файл или не является tty
if [ ! -t 1 ]; then
    BOLD=""
    DIM=""
    CYAN=""
    GREEN=""
    YELLOW=""
    RED=""
    WHITE=""
    RESET=""
fi

# Настройка безопасной рабочей директории Git и неинтерактивной аутентификации
git config --global --add safe.directory "$SCRIPT_DIR" 2>/dev/null || true
git config --global --add safe.directory "*" 2>/dev/null || true
export GIT_TERMINAL_PROMPT=0
export GIT_ASKPASS=""

# Разбор параметров командной строки
SHOW_DIFF=0
WATCH_MODE=0
NO_LOGS=0

for arg in "$@"; do
    case "$arg" in
        --diff|-d)
            SHOW_DIFF=1
            ;;
        --watch|-w)
            WATCH_MODE=1
            ;;
        --no-logs|-n)
            NO_LOGS=1
            ;;
    esac
done

echo -e "=========================================="
echo -e " ${BOLD}🚀 Обновление Sentinel Music Server${RESET}"
echo -e "=========================================="

run_with_timeout() {
    local seconds="$1"
    shift
    if command -v timeout &>/dev/null; then
        timeout "$seconds" "$@"
    else
        "$@"
    fi
}

get_compose_cmd() {
    if [ -n "$COMPOSE_CMD" ]; then
        return 0
    fi
    if docker compose version &>/dev/null; then
        COMPOSE_CMD="docker compose"
    elif command -v docker-compose &>/dev/null; then
        COMPOSE_CMD="docker-compose"
    else
        COMPOSE_CMD=""
    fi
}

display_changelog() {
    local from_commit="$1"
    local to_commit="$2"
    local force_diff="$3"

    if ! command -v git &>/dev/null || [ ! -d ".git" ]; then
        return 0
    fi

    local current_head
    current_head=$(git -c "safe.directory=*" rev-parse --short HEAD 2>/dev/null || echo "unknown")

    if [ -n "$from_commit" ] && [ -n "$to_commit" ] && [ "$from_commit" != "$to_commit" ]; then
        echo -e "\n  ${CYAN}📝 Список коммитов (${BOLD}${from_commit:0:7} → ${to_commit:0:7}${RESET}${CYAN}):${RESET}"
        git -c "safe.directory=*" log --pretty=format:"    • ${YELLOW}${BOLD}%h${RESET} %s ${DIM}(%cr)${RESET}" "${from_commit}..${to_commit}"
        echo ""

        echo -e "\n  ${WHITE}${BOLD}📊 Статистика изменений файлов (${GREEN}+${RESET}/${RED}-${RESET}):${RESET}"
        local diff_stat
        diff_stat=$(git -c "safe.directory=*" diff --stat --color=always "${from_commit}..${to_commit}" 2>/dev/null || true)
        if [ -n "$diff_stat" ]; then
            echo "$diff_stat" | sed 's/^/    /'
        else
            echo "    (Изменения файлов отсутствуют)"
        fi
        echo ""

        # Детализированный diff измененных строк
        local total_diff_lines=0
        if [ "$force_diff" -eq 1 ]; then
            echo -e "  ${CYAN}📄 Детализированный diff измененных строк:${RESET}"
            git -c "safe.directory=*" diff -U2 --color=always "${from_commit}..${to_commit}" | sed 's/^/    /'
            echo ""
        else
            total_diff_lines=$(git -c "safe.directory=*" diff --numstat "${from_commit}..${to_commit}" 2>/dev/null | awk '{s+=$1+$2} END {print s+0}')
            if [ "$total_diff_lines" -gt 0 ] && [ "$total_diff_lines" -le 100 ]; then
                echo -e "  ${CYAN}📄 Детализированный diff строк (до 100 измененных строк):${RESET}"
                git -c "safe.directory=*" diff -U1 --color=always "${from_commit}..${to_commit}" | sed 's/^/    /'
                echo ""
            elif [ "$total_diff_lines" -gt 100 ]; then
                echo -e "  ${DIM}💡 Изменено строк: $total_diff_lines. Чтобы увидеть полный построчный diff, запустите: ./update.sh --diff${RESET}\n"
            fi
        fi
    else
        echo -e "\n  ${CYAN}📝 Недавние коммиты (текущая версия: ${BOLD}${current_head}${RESET}${CYAN}):${RESET}"
        git -c "safe.directory=*" log -n 3 --pretty=format:"    • ${YELLOW}${BOLD}%h${RESET} %s ${DIM}(%cr)${RESET}"
        echo ""
        echo -e "\n  ${WHITE}${BOLD}📊 Статистика последнего коммита (${GREEN}+${RESET}/${RED}-${RESET}):${RESET}"
        local last_stat
        last_stat=$(git -c "safe.directory=*" show --stat --color=always --format= HEAD 2>/dev/null || true)
        if [ -n "$last_stat" ]; then
            echo "$last_stat" | sed 's/^/    /'
        fi
        echo ""
        if [ "$force_diff" -eq 1 ]; then
            echo -e "  ${CYAN}📄 Построчный diff последнего коммита:${RESET}"
            git -c "safe.directory=*" show -U2 --color=always --format= HEAD 2>/dev/null | sed 's/^/    /'
            echo ""
        fi
    fi
}

pull_updates() {
    local branch="${1:-main}"
    local origin_url
    origin_url=$(git remote get-url origin 2>/dev/null || echo "https://github.com/blackalex1/sentinel-music-server.git")

    local repo_path="blackalex1/sentinel-music-server"
    if [[ "$origin_url" =~ github\.com[:/]([^/]+/[^/.]+)(\.git)? ]]; then
        repo_path="${BASH_REMATCH[1]}"
    fi

    # Фиксируем исходный коммит для подсчета changelog
    OLD_HEAD=$(git rev-parse HEAD 2>/dev/null || true)

    # 1. Защита локальных правок: сохранение в stash
    local stashed=0
    if [ -n "$(git status --porcelain 2>/dev/null)" ]; then
        echo -e "  ${YELLOW}⚠️ Обнаружены локальные изменения. Сохранение во временный stash...${RESET}"
        git stash push -m "sentinel-music-autostash-$(date +%s)" 2>/dev/null || true
        stashed=1
    fi

    echo -e ">> [1/4] 📥 Проверка доступности репозитория (ветка $branch)..."

    local fetch_success=0

    # Проверяем официальный GitHub
    if run_with_timeout 4 git ls-remote "$origin_url" HEAD &>/dev/null; then
        echo -e "  ${GREEN}✅ Связь с GitHub стабильна. Скачивание обновлений...${RESET}"
        if git fetch origin "$branch" && git reset --hard "origin/$branch"; then
            fetch_success=1
        fi
    fi

    # Резервные проверенные зеркала при сбоях
    if [ "$fetch_success" -ne 1 ]; then
        echo -e "  ${YELLOW}⚠️ Официальный GitHub недоступен (таймаут или сетевая блокировка).${RESET}"
        echo -e "  ${CYAN}🔄 Подключение через проверенные зеркала...${RESET}"

        local mirrors=(
            "https://ghfast.top/https://github.com/${repo_path}.git"
            "https://gh-proxy.com/https://github.com/${repo_path}.git"
            "https://githubproxy.cc/https://github.com/${repo_path}.git"
        )

        for mirror in "${mirrors[@]}"; do
            local host
            host=$(echo "$mirror" | sed -E 's#https?://([^/]+)/.*#\1#')
            echo "   -> Проверка зеркала: $host ..."
            if run_with_timeout 4 git ls-remote "$mirror" HEAD &>/dev/null; then
                echo -e "   ${GREEN}✅ Зеркало $host доступно! Загрузка обновлений...${RESET}"
                if git fetch "$mirror" "$branch" && git reset --hard FETCH_HEAD; then
                    fetch_success=1
                    break
                fi
            fi
        done
    fi

    # Восстановление локальных изменений из stash при наличии
    if [ "$stashed" -eq 1 ]; then
        echo -e "  ${CYAN}🔄 Восстановление локальных изменений из stash...${RESET}"
        git stash pop 2>/dev/null || true
    fi

    if [ "$fetch_success" -ne 1 ]; then
        echo -e "  ${RED}❌ Ошибка: ни официальный GitHub, ни резервные зеркала не ответили на запрос.${RESET}"
        echo "Пожалуйста, проверьте интернет-соединение или настройки DNS."
        exit 1
    fi

    NEW_HEAD=$(git rev-parse HEAD 2>/dev/null || true)

    if [ -n "$OLD_HEAD" ] && [ -n "$NEW_HEAD" ] && [ "$OLD_HEAD" != "$NEW_HEAD" ]; then
        echo -e "  ${GREEN}✔ Кодовая база успешно обновлена:${RESET} ${BOLD}${OLD_HEAD:0:7} → ${NEW_HEAD:0:7}${RESET}"
        display_changelog "$OLD_HEAD" "$NEW_HEAD" "$SHOW_DIFF"

        # Самообновление: если обновился сам update.sh, перезапускаем его
        if [ -z "${SENTINEL_RELOADED:-}" ]; then
            if git diff --name-only "$OLD_HEAD" "$NEW_HEAD" 2>/dev/null | grep -q "update.sh"; then
                echo -e "  ${CYAN}🔄 Скрипт update.sh был обновлен. Перезапуск обновленного скрипта...${RESET}\n"
                export SENTINEL_RELOADED=1
                exec bash "$0" "$@"
            fi
        fi
    else
        echo -e "  ${GREEN}✔ Кодовая база уже актуальна (Up to date).${RESET}"
        display_changelog "$OLD_HEAD" "$NEW_HEAD" "$SHOW_DIFF"
    fi
}

build_and_restart_containers() {
    get_compose_cmd
    if [ -z "$COMPOSE_CMD" ]; then
        echo -e "  ${YELLOW}⚠️ Docker Compose не найден. Код обновлен, перезапустите контейнеры вручную.${RESET}"
        return 0
    fi

    # 1. Zero-Downtime пересборка: сервис продолжает отвечать клиентам во время сборки
    echo -e ">> [2/4] 🔨 Сборка обновленного Docker-образа (сервис продолжает работать)..."
    if ! $COMPOSE_CMD build music-server; then
        echo -e "  ${RED}❌ Ошибка: сбой сборки Docker-образа!${RESET}"
        echo -e "  ${YELLOW}⚠️ Предыдущая версия контейнера продолжает работать без сбоев.${RESET}"
        return 1
    fi
    echo -e "  ${GREEN}✔ Docker-образ успешно собран без простоя сервиса.${RESET}"

    # 2. Быстрый перезапуск (~1-2 сек) только после успешного завершения сборки
    echo -e ">> [3/4] 🔄 Быстрый перезапуск контейнеров с новым образом..."
    if ! $COMPOSE_CMD up -d --no-build; then
        echo -e "  ${RED}❌ Ошибка запуска контейнеров через Docker Compose!${RESET}"
        return 1
    fi

    # 3. Верификация запуска контейнера
    echo -e ">> [4/4] 🏥 Проверка состояния сервиса..."
    sleep 3
    local container_status
    container_status=$(docker inspect --format='{{.State.Status}}' music-server 2>/dev/null || true)
    if [ "$container_status" = "running" ]; then
        echo -e "  ${GREEN}✅ Сервис music-server успешно запущен и работает!${RESET}"
    else
        echo -e "  ${RED}❌ Внимание: контейнер music-server имеет статус '${container_status:-не найден}'!${RESET}"
        echo "  📊 Последние логи аварийного завершения:"
        $COMPOSE_CMD logs --tail=40 music-server 2>/dev/null || true
        return 1
    fi

    # 4. Очистка неиспользуемых висячих слоев сборщика и образов
    echo -e "🧹 Очистка неиспользуемых слоев и висячих образов Docker..."
    docker image prune -f 2>/dev/null || true
    docker builder prune -f 2>/dev/null || true

    echo -e "\n>> 📊 Текущий статус контейнеров:"
    $COMPOSE_CMD ps
    return 0
}

# Режим фонового демона для 1-Click Update из веб-интерфейса
if [ "$WATCH_MODE" -eq 1 ]; then
    echo -e "=========================================="
    echo -e " ${BOLD}👀 Режим фонового отслеживания 1-Click Update${RESET}"
    echo -e "=========================================="
    echo " Ожидание триггера обновления из веб-интерфейса (data/update.trigger)..."
    TRIGGER_FILE="data/update.trigger"
    while true; do
        if [ -f "$TRIGGER_FILE" ]; then
            echo ""
            echo -e "⚡ [$(date '+%Y-%m-%d %H:%M:%S')] ${CYAN}Обнаружен триггер обновления из веб-интерфейса!${RESET}"
            rm -f "$TRIGGER_FILE"
            pull_updates "main"
            if command -v docker &> /dev/null; then
                get_compose_cmd
                echo "🔨 Сборка обновленного образа (сервер продолжает работать)..."
                if $COMPOSE_CMD build music-server; then
                    echo "🔄 Быстрый перезапуск контейнера..."
                    $COMPOSE_CMD up -d --no-build
                    echo "🧹 Очистка кэша сборки Docker..."
                    docker image prune -f 2>/dev/null || true
                    docker builder prune -f 2>/dev/null || true
                    echo -e "  ${GREEN}✅ Контейнер успешно обновлен и перезапущен!${RESET}"
                else
                    echo -e "  ${RED}❌ Ошибка сборки Docker-образа. Предыдущий контейнер продолжает работу.${RESET}"
                fi
            fi
            echo "👀 Возврат в режим отслеживания..."
        fi
        sleep 3
    done
    exit 0
fi

# Нормализация прав на тома данных для non-root контейнера (UID 1000)
if [ -d "data" ] || [ -d "plugins" ]; then
    sudo chmod -R a+rwX data plugins 2>/dev/null || chmod -R a+rwX data plugins 2>/dev/null || true
fi

# Скачивание и применение изменений из репозитория
pull_updates "main"

# Повторная нормализация прав на тома после обновления файлов
if [ -d "data" ] || [ -d "plugins" ]; then
    sudo chmod -R a+rwX data plugins 2>/dev/null || chmod -R a+rwX data plugins 2>/dev/null || true
fi

# Бесшовная пересборка и запуск контейнеров
if command -v docker &> /dev/null; then
    build_and_restart_containers

    echo "=========================================="
    echo -e " ${GREEN}✅ Sentinel Music Server успешно запущен!${RESET}"
    if [ "$NO_LOGS" -eq 1 ]; then
        echo " 📊 Логи контейнера:"
        $COMPOSE_CMD logs --tail=20 music-server
    elif [ -t 1 ]; then
        echo -e " 📡 Потоковый вывод логов в реальном времени (Ctrl+C для выхода):"
        echo "=========================================="
        $COMPOSE_CMD logs -f --tail=30 music-server
    else
        echo " 📊 Последние логи сервиса:"
        echo "=========================================="
        $COMPOSE_CMD logs --tail=30 music-server
    fi
else
    echo -e "  ${YELLOW}⚠️ Docker не найден. Файлы репозитория обновлены.${RESET}"
fi
