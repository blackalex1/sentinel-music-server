/**
 * Модуль компонента боковой панели очереди воспроизведения и истории (Queue Drawer).
 * Оснащен векторными SVG-иконками Sentinel Design System.
 */

import { icon } from '../icons.js';

export function renderQueueDrawer() {
  return `
    <aside class="queue-drawer" id="queueDrawer">
      <div class="queue-header">
        <div class="queue-title-group">
          <span class="queue-icon">${icon('queue', { size: 18 })}</span>
          <h3 class="queue-title">Очередь воспроизведения</h3>
        </div>
        <div class="queue-actions">
          <button class="queue-btn-action" id="btnClearQueue" title="Очистить список следующих треков">Очистить</button>
          <button class="queue-btn-close" id="btnCloseQueue" title="Закрыть панель очереди">
            ${icon('close', { size: 16 })}
          </button>
        </div>
      </div>

      <div class="queue-nav-tabs">
        <button class="queue-tab active" data-tab="queue">Очередь (<span id="queueUpcomingCount">0</span>)</button>
        <button class="queue-tab" data-tab="history">История (<span id="queueHistoryCount">0</span>)</button>
      </div>

      <div class="queue-content-scroll" id="queueContentScroll">
        <!-- Секция: Сейчас играет -->
        <div class="queue-section" id="queueNowPlayingSection">
          <div class="queue-section-header">Сейчас играет</div>
          <div id="queueNowPlayingCard" class="queue-now-playing-card">
            <!-- Заполняется динамически -->
          </div>
        </div>

        <!-- Вкладка: Очередь (Далее в очереди) -->
        <div class="queue-tab-panel" id="queueTabUpcoming">
          <div class="queue-section-header">
            <span>Далее в очереди</span>
          </div>
          <div class="queue-list" id="queueUpcomingList">
            <!-- Список треков -->
          </div>
        </div>

        <!-- Вкладка: История (Недавно играли) -->
        <div class="queue-tab-panel" id="queueTabHistory" style="display: none;">
          <div class="queue-section-header">
            <span>Недавно играли</span>
            <button class="queue-btn-subaction" id="btnClearHistory">Очистить историю</button>
          </div>
          <div class="queue-list" id="queueHistoryList">
            <!-- Список истории -->
          </div>
        </div>
      </div>
    </aside>
  `;
}
