/**
 * Модуль компонента верхней панели поиска и профиля (Header).
 * Оснащен векторными SVG-иконками Sentinel Design System.
 */

import { icon } from '../icons.js';

export function renderHeader() {
  return `
    <header class="top-header" data-tauri-drag-region>
      <div class="search-container">
        <span class="search-icon">${icon('search', { size: 17 })}</span>
        <input type="text" id="searchInput" class="search-input" placeholder="Трек, артист, альбом или слова из песни...">
        <button id="searchClear" class="search-clear" style="display: none;" title="Очистить поиск">${icon('close', { size: 15 })}</button>
      </div>

      <div class="header-actions">
        <button class="settings-btn" id="sentinelConnectBadge" title="Sentinel Connect (Управление с телефона)">
          ${icon('cast', { size: 19 })}
        </button>
        <button class="settings-btn" id="btnQrConnect" title="Подключить смартфон (QR-код)">
          ${icon('qr', { size: 19 })}
        </button>
        <button class="settings-btn" id="btnServerSettings" title="Настройки подключения к серверу">
          ${icon('settings', { size: 19 })}
        </button>
        <div class="user-badge" id="userBadge" title="Профиль пользователя">
          <div class="user-avatar" id="userAvatar">S</div>
          <span id="userName">Войти</span>
        </div>
      </div>
    </header>
  `;
}
