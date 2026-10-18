/**
 * Модуль компонента боковой панели навигации (Sidebar).
 * Оснащен векторными SVG-иконками Sentinel Design System.
 */

import { icon } from '../icons.js';

export function renderSidebar() {
  return `
    <aside class="sidebar">
      <div class="brand-logo">
        <img src="img/logo_mascot.png" alt="Sentinel Music Mascot" class="brand-logo-img" />
        <div class="brand-title">Sentinel <span>Music</span></div>
      </div>

      <nav class="nav-group">
        <a class="nav-item active" data-view="main">
          <span class="nav-icon">${icon('home', { size: 18 })}</span>
          <span>Главное</span>
        </a>
        <a class="nav-item" id="navItemStream" data-view="stream">
          <span class="nav-icon">${icon('stream', { size: 18 })}</span>
          <span>Поток</span>
          <span class="nav-badge">AI</span>
        </a>
        <a class="nav-item" data-view="tracks">
          <span class="nav-icon">${icon('music', { size: 18 })}</span>
          <span>Коллекция треков</span>
        </a>
        <a class="nav-item" data-view="playlists">
          <span class="nav-icon">${icon('folder', { size: 18 })}</span>
          <span>Плейлисты</span>
        </a>
        <a class="nav-item" data-view="duplicates" id="navItemDuplicates" title="Управление дубликатами треков" style="display: none;">
          <span class="nav-icon">${icon('copy', { size: 18 })}</span>
          <span>Дубликаты</span>
          <span class="nav-badge" id="duplicatesCountBadge" style="display: none;">0</span>
        </a>
      </nav>

      <div class="sidebar-divider"></div>

      <div class="playlists-header">
        <span>Мои плейлисты</span>
        <button class="btn-add-playlist" id="btnAddPlaylist" title="Создать плейлист">
          ${icon('plus', { size: 14 })}
        </button>
      </div>

      <div class="sidebar-playlists-list" id="sidebarPlaylistsList">
        <!-- Заполняется динамически -->
      </div>

      <div class="sidebar-footer">
        <div class="watcher-status-pill" title="Фоновое отслеживание новых FLAC/MP3 файлов">
          <div class="status-dot" id="watcherStatusDot"></div>
          <span id="watcherStatusLabel">Автосканирование активно</span>
        </div>
      </div>
    </aside>
  `;
}
