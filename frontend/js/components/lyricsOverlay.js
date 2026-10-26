/**
 * Sentinel Music — Модуль всплывающего окна текстов песен и караоке (Lyrics Overlay).
 * Отображает синхронизированный текст поверх текущего экрана с динамической обложкой на фоне.
 */

import { icon } from '../icons.js';

export function renderLyricsOverlay() {
  return `
    <div class="lyrics-overlay" id="lyricsOverlay">
      <!-- Динамический размытый фон обложки альбома -->
      <div class="lyrics-backdrop" id="lyricsBackdrop">
        <img id="lyricsBackdropCover" class="lyrics-backdrop-img" src="" alt="" style="display: none;" />
        <div class="lyrics-backdrop-gradient"></div>
      </div>

      <!-- Шапка окна текстов -->
      <header class="lyrics-overlay-header">
        <div class="lyrics-header-left">
          <img id="lyricsHeaderCover" class="lyrics-header-cover" src="" alt="" style="display: none;" />
          <div class="lyrics-header-meta">
            <div class="lyrics-badge-indicator">
              <span class="lyrics-badge-pulse"></span>
              <span>Текст песни • Караоке</span>
            </div>
            <h2 id="lyricsHeaderTitle" class="lyrics-header-title">Трек не выбран</h2>
            <div id="lyricsHeaderArtist" class="lyrics-header-artist">Sentinel Music</div>
          </div>
        </div>

        <div class="lyrics-header-actions">
          <button class="lyrics-btn-action" id="btnRefreshLyrics" title="Перезагрузить текст (если найден не тот или устарел)">
            ${icon('refresh', { size: 16 })}
          </button>
          <button class="lyrics-btn-close" id="btnCloseLyrics" title="Свернуть текст песни (L или Esc)">
            ${icon('close', { size: 18 })}
          </button>
        </div>
      </header>

      <!-- Контейнер караоке-строк с плавной прокруткой -->
      <div class="lyrics-content-scroll" id="lyricsContainer">
        <div class="lyrics-empty-state">Включите трек для отображения синхронизированного караоке-текста</div>
      </div>
    </div>
  `;
}
