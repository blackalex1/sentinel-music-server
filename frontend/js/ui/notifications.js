/**
 * Sentinel Music — Универсальный модуль диалоговых уведомлений и подтверждений.
 * Заменяет системные браузерные окна confirm/alert на современные модальные окна
 * в фирменном стиле Sentinel Design System с векторными SVG-пиктограммами.
 */

import { icon } from '../icons.js';
import { escapeHtml } from './toast.js';

let activeDialogResolve = null;
let activeDialogKeyHandler = null;

/**
 * Универсальное диалоговое окно подтверждения (замена window.confirm).
 * @param {string|Object} options Текст сообщения или конфигурация диалога
 * @returns {Promise<boolean>} true, если пользователь нажал подтвердить; false, если отменил или закрыл
 */
export function showConfirm(options = {}) {
  const config = normalizeConfig(options, 'confirm');

  return new Promise((resolve) => {
    closeActiveDialog(false);
    activeDialogResolve = resolve;

    const overlay = createDialogDOM(config, {
      showCancel: true,
      onConfirm: () => {
        closeActiveDialog(true);
      },
      onCancel: () => {
        closeActiveDialog(false);
      }
    });

    document.body.appendChild(overlay);
    requestAnimationFrame(() => {
      overlay.classList.add('active');
      const confirmBtn = overlay.querySelector('.sentinel-dialog-btn.btn-confirm');
      const cancelBtn = overlay.querySelector('.sentinel-dialog-btn.btn-cancel');
      // Для деструктивных действий (danger) фокусируемся на Отмене для защиты от случайного нажатия Enter
      if (config.type === 'danger' && cancelBtn) {
        cancelBtn.focus();
      } else if (confirmBtn) {
        confirmBtn.focus();
      }
    });

    setupKeyListeners(config.onConfirm, config.onCancel);
  });
}

/**
 * Универсальное информационное модальное окно (замена window.alert).
 * @param {string|Object} options Текст сообщения или конфигурация
 * @returns {Promise<void>}
 */
export function showAlert(options = {}) {
  const config = normalizeConfig(options, 'alert');

  return new Promise((resolve) => {
    closeActiveDialog();
    activeDialogResolve = resolve;

    const overlay = createDialogDOM(config, {
      showCancel: false,
      onConfirm: () => {
        closeActiveDialog(true);
      }
    });

    document.body.appendChild(overlay);
    requestAnimationFrame(() => {
      overlay.classList.add('active');
      const confirmBtn = overlay.querySelector('.sentinel-dialog-btn.btn-confirm');
      if (confirmBtn) confirmBtn.focus();
    });

    setupKeyListeners(() => closeActiveDialog(true), () => closeActiveDialog(true));
  });
}

/**
 * Диалоговое окно ввода текста (замена window.prompt).
 * @param {string|Object} options
 * @returns {Promise<string|null>} Введенная строка или null при отмене
 */
export function showPrompt(options = {}) {
  const config = normalizeConfig(options, 'prompt');

  return new Promise((resolve) => {
    closeActiveDialog(null);
    activeDialogResolve = resolve;

    const overlay = createDialogDOM(config, {
      showCancel: true,
      hasInput: true,
      onConfirm: () => {
        const inputEl = overlay.querySelector('.sentinel-dialog-input');
        const val = inputEl ? inputEl.value : '';
        closeActiveDialog(val);
      },
      onCancel: () => {
        closeActiveDialog(null);
      }
    });

    document.body.appendChild(overlay);
    requestAnimationFrame(() => {
      overlay.classList.add('active');
      const inputEl = overlay.querySelector('.sentinel-dialog-input');
      if (inputEl) {
        inputEl.focus();
        inputEl.select();
      }
    });

    setupKeyListeners(
      () => {
        const inputEl = overlay.querySelector('.sentinel-dialog-input');
        closeActiveDialog(inputEl ? inputEl.value : '');
      },
      () => closeActiveDialog(null)
    );
  });
}

// Экспорт в глобальный контекст для универсального доступа
window.showConfirm = showConfirm;
window.showAlert = showAlert;
window.showPrompt = showPrompt;

function normalizeConfig(options, kind) {
  if (typeof options === 'string') {
    return {
      title: kind === 'confirm' ? 'Подтверждение действия' : (kind === 'alert' ? 'Уведомление' : 'Ввод данных'),
      message: options,
      confirmText: kind === 'confirm' ? 'Подтвердить' : (kind === 'alert' ? 'Понятно' : 'Сохранить'),
      cancelText: 'Отмена',
      type: options.includes('удал') || options.includes('очист') || options.includes('безвозвратно') ? 'danger' : 'primary',
      icon: null,
      details: null
    };
  }

  const type = options.type || (options.confirmClass === 'btn-danger' ? 'danger' : 'primary');
  return {
    title: options.title || (kind === 'confirm' ? 'Подтверждение' : (kind === 'alert' ? 'Уведомление' : 'Ввод данных')),
    subtitle: options.subtitle || null,
    message: options.message || options.text || '',
    details: options.details || null,
    confirmText: options.confirmText || (kind === 'confirm' ? 'Подтвердить' : (kind === 'alert' ? 'Понятно' : 'Готово')),
    cancelText: options.cancelText || 'Отмена',
    type: type,
    icon: options.icon || getDefaultIconForType(type),
    placeholder: options.placeholder || '',
    defaultValue: options.defaultValue || ''
  };
}

function getDefaultIconForType(type) {
  switch (type) {
    case 'danger': return 'trash';
    case 'warning': return 'alert';
    case 'success': return 'checkCircle';
    case 'info':
    case 'primary':
    default:
      return 'sparkles';
  }
}

function createDialogDOM(config, handlers) {
  const overlay = document.createElement('div');
  overlay.className = 'sentinel-dialog-overlay';
  overlay.id = 'sentinelDialogOverlay';

  const typeClass = config.type || 'primary';
  const confirmBtnClass = `btn-confirm-${typeClass}`;

  overlay.innerHTML = `
    <div class="sentinel-dialog-card" role="dialog" aria-modal="true" aria-labelledby="sentinelDialogTitle">
      <div class="sentinel-dialog-header">
        <div class="sentinel-dialog-icon ${typeClass}">
          ${icon(config.icon, { size: 22 })}
        </div>
        <div class="sentinel-dialog-title-block">
          <h3 class="sentinel-dialog-title" id="sentinelDialogTitle">${escapeHtml(config.title)}</h3>
          ${config.subtitle ? `<div class="sentinel-dialog-subtitle">${escapeHtml(config.subtitle)}</div>` : ''}
        </div>
      </div>

      <div class="sentinel-dialog-body">
        <div>${escapeHtml(config.message)}</div>
        ${config.details ? `
          <div class="sentinel-dialog-details">
            <span style="display: flex; align-items: center; color: var(--text-muted);">${icon('alert', { size: 15 })}</span>
            <span>${escapeHtml(config.details)}</span>
          </div>
        ` : ''}
        ${handlers.hasInput ? `
          <div class="sentinel-dialog-input-wrapper">
            <input type="text" class="sentinel-dialog-input" value="${escapeHtml(config.defaultValue)}" placeholder="${escapeHtml(config.placeholder)}" />
          </div>
        ` : ''}
      </div>

      <div class="sentinel-dialog-actions">
        ${handlers.showCancel ? `
          <button type="button" class="sentinel-dialog-btn btn-cancel">
            ${escapeHtml(config.cancelText)}
          </button>
        ` : ''}
        <button type="button" class="sentinel-dialog-btn btn-confirm ${confirmBtnClass}">
          ${escapeHtml(config.confirmText)}
        </button>
      </div>
    </div>
  `;

  // Обработчики кнопок
  const confirmBtn = overlay.querySelector('.btn-confirm');
  if (confirmBtn) {
    confirmBtn.addEventListener('click', (e) => {
      e.stopPropagation();
      handlers.onConfirm();
    });
  }

  const cancelBtn = overlay.querySelector('.btn-cancel');
  if (cancelBtn) {
    cancelBtn.addEventListener('click', (e) => {
      e.stopPropagation();
      handlers.onCancel();
    });
  }

  // Клик вне карточки диалога закрывает его с отменой
  overlay.addEventListener('click', (e) => {
    if (e.target === overlay) {
      if (handlers.showCancel) {
        handlers.onCancel();
      } else {
        handlers.onConfirm();
      }
    }
  });

  return overlay;
}

function setupKeyListeners(onConfirm, onCancel) {
  removeKeyListeners();

  activeDialogKeyHandler = (e) => {
    if (e.key === 'Escape') {
      e.preventDefault();
      e.stopPropagation();
      if (onCancel) onCancel();
    } else if (e.key === 'Enter') {
      const activeEl = document.activeElement;
      if (activeEl && activeEl.classList.contains('btn-cancel')) {
        // Если фокус явно на кнопке "Отмена", срабатывает отмена
        e.preventDefault();
        if (onCancel) onCancel();
      } else {
        e.preventDefault();
        if (onConfirm) onConfirm();
      }
    }
  };

  window.addEventListener('keydown', activeDialogKeyHandler, true);
}

function removeKeyListeners() {
  if (activeDialogKeyHandler) {
    window.removeEventListener('keydown', activeDialogKeyHandler, true);
    activeDialogKeyHandler = null;
  }
}

function closeActiveDialog(resultVal) {
  removeKeyListeners();

  const overlay = document.getElementById('sentinelDialogOverlay');
  if (overlay) {
    overlay.classList.remove('active');
    setTimeout(() => {
      overlay.remove();
    }, 220);
  }

  if (activeDialogResolve) {
    const fn = activeDialogResolve;
    activeDialogResolve = null;
    fn(resultVal);
  }
}
