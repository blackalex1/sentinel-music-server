/**
 * Модуль экрана «Плейлисты» (Сетка плейлистов пользователя).
 */

import { icon } from '../../icons.js';

export function renderPlaylistsView() {
  return `
    <section id="viewPlaylists" style="display: none;">
      <!-- Каталог плейлистов пользователя -->
      <div id="playlistsCatalogSection">
        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 24px; flex-wrap: wrap; gap: 16px;">
          <div>
            <h2 style="font-size: 1.5rem; font-weight: 800; margin: 0;">Плейлисты</h2>
            <p style="font-size: 0.88rem; color: var(--text-muted); margin-top: 4px; margin-bottom: 0;">Ваши персональные плейлисты</p>
          </div>
          <button class="btn-primary" onclick="window.showPlaylistModal && window.showPlaylistModal()">+ Создать плейлист</button>
        </div>
        <div id="playlistsGridContainer" style="display: grid; grid-template-columns: repeat(auto-fill, minmax(180px, 1fr)); gap: 20px;">
          <!-- Карточки плейлистов -->
        </div>
      </div>

      <!-- Детальный просмотр треков открытого плейлиста -->
      <div id="playlistDetailSection" style="display: none;">
        <div style="display: flex; align-items: center; justify-content: space-between; margin-bottom: 20px; flex-wrap: wrap; gap: 16px;">
          <div style="display: flex; align-items: center; gap: 14px;">
            <button class="btn-secondary" id="btnBackToPlaylists" style="display: inline-flex; align-items: center; gap: 6px; padding: 8px 14px;">
              ${icon('chevronLeft', { size: 16 })} <span>Назад к плейлистам</span>
            </button>
            <h2 id="playlistDetailTitle" style="font-size: 1.4rem; font-weight: 800; margin: 0;"></h2>
          </div>
          <div style="display: flex; gap: 8px;">
            <button class="btn-primary" id="btnPlayAllPlaylist">
              ${icon('play', { size: 16 })} <span>Слушать всё</span>
            </button>
            <button class="btn-secondary" id="btnShufflePlaylist">
              ${icon('shuffle', { size: 16 })} <span>Перемешать</span>
            </button>
          </div>
        </div>
        <div class="track-table-container" id="playlistTracksContainer">
          <!-- Таблица треков плейлиста -->
        </div>
      </div>
    </section>
  `;
}
