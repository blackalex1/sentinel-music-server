/**
 * Корневой модуль сборки разметки приложения Sentinel Music.
 * Объединяет боковую панель, шапку, экраны, очередь, плеер и модальные окна.
 */

import { renderSidebar } from './sidebar.js';
import { renderHeader } from './header.js';
import { renderContentViews } from './views/index.js';
import { renderQueueDrawer } from './queueDrawer.js';
import { renderPlayerBar } from './playerBar.js';
import { renderModals } from './modals/index.js';
import { renderLyricsOverlay } from './lyricsOverlay.js';
import { renderExpandedPlayer } from './expandedPlayer.js';

export function renderAppLayout() {
  return `
    <!-- Основная сетка приложения -->
    <div class="app-container">
      ${renderSidebar()}

      <!-- Главная рабочая область -->
      <main class="main-view">
        ${renderHeader()}
        ${renderContentViews()}
      </main>

      <!-- БОКОВАЯ ПАНЕЛЬ: Очередь воспроизведения (Playback Queue & History) -->
      ${renderQueueDrawer()}
    </div>

    <!-- Всплывающее окно караоке-текста песни (Lyrics Overlay) -->
    ${renderLyricsOverlay()}

    <!-- Полноэкранный развернутый плеер (Expanded Full Player) -->
    ${renderExpandedPlayer()}

    <!-- Нижняя панель плеера -->
    ${renderPlayerBar()}

    <!-- Скрытый аудиоплеер -->
    <audio id="audioElement"></audio>

    <!-- Модальные окна -->
    ${renderModals()}
  `;
}

export function mountLayout(target = document.getElementById('app')) {
  if (!target) {
    target = document.createElement('div');
    target.id = 'app';
    document.body.prepend(target);
  }
  target.innerHTML = renderAppLayout();
}
