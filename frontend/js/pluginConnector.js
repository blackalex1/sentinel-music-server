/**
 * Универсальный коннектор и SDK подключаемых плагинов Sentinel Music (Sentinel SDK).
 * Предоставляет полный интерфейс для расширения возможностей системы:
 * - Регистрация собственных вкладок в боковом меню и экранов контента
 * - Вызов системных модальных окон, подтверждений и всплывающих уведомлений
 * - Точки расширения UI (Extension Points) в экранах настроек, модалок и поиска
 * - Подписка на системные события ядра через Event Bus
 * - Выполнение авторизованных API-запросов к серверу
 */

import { apiFetch } from './api.js';
import { API_BASE } from './config.js';
import { state } from './state.js';
import { icon } from './icons.js';
import { showToast } from './ui/toast.js';
import { showConfirm, showAlert } from './ui/notifications.js';
import { switchView, registerPluginNavigation } from './ui/navigation.js';

// Карта зарегистрированных точек расширения (location -> Set<renderFn>)
const extensionPoints = new Map();

export const Sentinel = {
  version: '2.0.0',

  ui: {
    /**
     * Показывает всплывающее уведомление в стиле Sentinel Design System.
     * @param {string} message - Текст уведомления
     * @param {string} [iconName='checkCircle'] - Имя векторной иконки
     */
    showToast(message, iconName = 'checkCircle') {
      showToast(message, iconName);
    },

    /**
     * Показывает фирменное модальное окно подтверждения (Confirm Dialog).
     * @param {Object} options - { title, message, confirmText, cancelText, danger }
     * @returns {Promise<boolean>} - true если подтверждено, false если отменено
     */
    showConfirm(options) {
      return showConfirm(options);
    },

    /**
     * Показывает фирменное модальное информационное окно (Alert Dialog).
     * @param {Object} options - { title, message, okText }
     * @returns {Promise<void>}
     */
    showAlert(options) {
      return showAlert(options);
    },

    /**
     * Возвращает SVG-разметку векторной иконки Sentinel Design System.
     * @param {string} name - Имя иконки (напр. 'download', 'settings', 'folder')
     * @param {Object} [options={}] - { size, strokeWidth, className }
     * @returns {string} - SVG разметка
     */
    icon(name, options = {}) {
      return icon(name, options);
    },

    /**
     * Регистрирует полноценный автономный экран и вкладку в боковом меню сайдбара.
     * @param {Object} config
     * @param {string} config.id - Уникальный идентификатор экрана (напр. 'batchImport')
     * @param {string} config.title - Заголовок в боковом меню
     * @param {string} [config.icon='folder'] - Имя иконки
     * @param {boolean} [config.isHidden=false] - Скрыт ли пункт в меню при старте
     * @param {Function} config.render - function(containerEl) рендеринг разметки экрана
     * @param {Function} [config.onShow] - Вызывается при переключении на этот экран
     * @param {Function} [config.onHide] - Вызывается при уходе с экрана
     * @returns {Object} Контроллер навигационного элемента { setVisible, setBadge, setWarning, onClose, setTitle }
     */
    registerView({
      id,
      title,
      icon: iconName = 'folder',
      isHidden = false,
      render,
      onShow,
      onHide
    }) {
      const containerId = `view_${id}`;

      // 1. Создаем контейнер страницы в основном контейнере #mainContent
      let pageContainer = document.getElementById(containerId);
      if (!pageContainer) {
        pageContainer = document.createElement('div');
        pageContainer.id = containerId;
        pageContainer.className = 'view-page plugin-view-page';
        pageContainer.style.setProperty('display', 'none', 'important');

        const mainContent = document.getElementById('mainContent') || document.querySelector('.main-content');
        if (mainContent) {
          mainContent.appendChild(pageContainer);
        } else {
          document.body.appendChild(pageContainer);
        }

        if (typeof render === 'function') {
          try {
            render(pageContainer);
          } catch (err) {
            console.error(`[SentinelSDK] Ошибка рендеринга страницы плагина «${id}»:`, err);
          }
        }
      }

      // 2. Регистрируем в ядре переключения экранов
      registerPluginNavigation(id, containerId, { onShow, onHide });

      // 3. Создаем пункт навигации в сайдбаре
      const navGroup = document.querySelector('.nav-group');
      let navItem = document.querySelector(`.nav-item[data-view="${id}"]`);

      if (!navItem && navGroup) {
        navItem = document.createElement('a');
        navItem.className = 'nav-item';
        navItem.dataset.view = id;
        navItem.title = title;
        if (isHidden) {
          navItem.style.display = 'none';
        }

        navItem.innerHTML = `
          <span class="nav-icon">${icon(iconName, { size: 18 })}</span>
          <span class="nav-item-label" style="white-space: nowrap; overflow: hidden; text-overflow: ellipsis;">${title}</span>
          <div class="nav-item-actions">
            <span class="nav-badge" style="display: none;"></span>
            <span class="nav-badge-warning" style="display: none;" title="Внимание">!</span>
            <button type="button" class="nav-item-close-btn" style="display: none;" title="Скрыть">
              ${icon('close', { size: 13 })}
            </button>
          </div>
        `;

        navItem.addEventListener('click', (e) => {
          // Если клик по кнопке закрытия плашки — не переключаем экран
          if (e.target.closest('.nav-item-close-btn')) return;
          e.preventDefault();
          switchView(id);
        });

        // Вставляем пункт перед настройками, если они есть в сайдбаре, иначе в конец
        const settingsItem = document.querySelector('.nav-item[data-view="settings"]');
        if (settingsItem && settingsItem.parentNode === navGroup) {
          navGroup.insertBefore(navItem, settingsItem);
        } else {
          navGroup.appendChild(navItem);
        }
      }

      const badgeEl = navItem ? navItem.querySelector('.nav-badge') : null;
      const warningEl = navItem ? navItem.querySelector('.nav-badge-warning') : null;
      const closeBtn = navItem ? navItem.querySelector('.nav-item-close-btn') : null;
      const labelEl = navItem ? navItem.querySelector('.nav-item-label') : null;

      let closeCallback = null;
      if (closeBtn) {
        closeBtn.addEventListener('click', (e) => {
          e.stopPropagation();
          e.preventDefault();
          if (typeof closeCallback === 'function') {
            closeCallback();
          } else {
            navItem.style.display = 'none';
            switchView('tracks');
          }
        });
      }

      // Контроллер управления созданным пунктом навигации
      return {
        id,
        navItem,
        pageContainer,

        setVisible(visible) {
          if (navItem) {
            navItem.style.display = visible ? 'flex' : 'none';
          }
        },

        setTitle(newTitle) {
          if (labelEl) labelEl.textContent = newTitle;
          if (navItem) navItem.title = newTitle;
        },

        setBadge(text, isVisible = true) {
          if (!badgeEl) return;
          if (isVisible && text !== null && text !== undefined && text !== '') {
            badgeEl.textContent = text;
            badgeEl.style.display = 'inline-flex';
          } else {
            badgeEl.style.display = 'none';
          }
        },

        setWarning(isVisible, tooltip = '') {
          if (!warningEl) return;
          if (isVisible) {
            warningEl.classList.add('visible');
            warningEl.style.display = 'inline-flex';
            if (tooltip) warningEl.title = tooltip;
          } else {
            warningEl.classList.remove('visible');
            warningEl.style.display = 'none';
          }
        },

        setCanClose(canClose) {
          if (closeBtn) {
            closeBtn.style.display = canClose ? 'inline-flex' : 'none';
          }
        },

        onClose(fn) {
          closeCallback = fn;
          if (closeBtn) {
            closeBtn.style.display = 'inline-flex';
          }
        }
      };
    },

    /**
     * Регистрирует функцию внедрения UI в определенную точку расширения системы (Extension Point).
     * @param {string} location - Имя точки расширения ('settings:view', 'upload:modal', 'tracks:search')
     * @param {Function} renderFn - function(containerElement, context)
     */
    registerExtensionPoint(location, renderFn) {
      if (!extensionPoints.has(location)) {
        extensionPoints.set(location, new Set());
      }
      extensionPoints.get(location).add(renderFn);
    },

    /**
     * Вызывает все зарегистрированные функции для указанной точки расширения и рендерит их в container.
     * @param {string} location - Имя точки расширения
     * @param {HTMLElement} container - DOM-контейнер для внедрения
     * @param {Object} [context={}] - Контекст вызова
     */
    renderExtensionPoints(location, container, context = {}) {
      if (!container) return;
      const fns = extensionPoints.get(location);
      if (!fns || fns.size === 0) return;

      fns.forEach((fn) => {
        try {
          fn(container, context);
        } catch (err) {
          console.error(`[SentinelSDK] Ошибка в расширении точки «${location}»:`, err);
        }
      });
    }
  },

  navigation: {
    /**
     * Переключает текущий активный экран приложения.
     * @param {string} viewName - Имя экрана ('main', 'tracks', 'settings', либо ID плагина)
     * @param {boolean} [shouldReload=true]
     */
    switchView(viewName, shouldReload = true) {
      switchView(viewName, shouldReload);
    },

    /**
     * Возвращает имя текущего открытого экрана.
     */
    getCurrentView() {
      return state.currentView;
    }
  },

  library: {
    /**
     * Запрашивает обновление списка плейлистов в интерфейсе (сайдбар и карточки).
     */
    reloadPlaylists() {
      window.dispatchEvent(new CustomEvent('playlists:reload'));
    },

    /**
     * Запрашивает обновление списка треков локальной фонотеки в интерфейсе.
     */
    reloadTracks() {
      window.dispatchEvent(new CustomEvent('library:reload'));
    }
  },

  api: {
    /**
     * Выполняет авторизованный сетевой запрос к бэкенду.
     * @param {string} url - Путь к API
     * @param {Object} [options={}] - Опции fetch
     * @returns {Promise<Response>}
     */
    fetch(url, options = {}) {
      return apiFetch(url, options);
    },

    /**
     * Возвращает базовый URL API сервера.
     */
    getBaseUrl() {
      return API_BASE;
    }
  },

  events: {
    /**
     * Подписывается на системное событие ядра.
     * @param {string} eventName
     * @param {Function} handler - function(detail, event)
     */
    on(eventName, handler) {
      const listener = (e) => handler(e.detail, e);
      window.addEventListener(eventName, listener);
      return () => window.removeEventListener(eventName, listener);
    },

    /**
     * Отправляет системное событие через Event Bus.
     * @param {string} eventName
     * @param {*} [detail=null]
     */
    emit(eventName, detail = null) {
      window.dispatchEvent(new CustomEvent(eventName, { detail }));
    }
  }
};

// Экспортируем также глобально на window для свободного использования любыми динамическими скриптами
window.Sentinel = Sentinel;
window.apiFetch = apiFetch;
window.showToast = showToast;
window.showConfirm = showConfirm;
window.showAlert = showAlert;
window.switchView = switchView;
