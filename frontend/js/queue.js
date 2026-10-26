/**
 * Модуль интерфейса Очереди воспроизведения (Playback Queue & History).
 * Отображает:
 * 1. «Сейчас играет» (Now Playing) с анимацией и обложкой.
 * 2. «Далее в очереди» (Up Next) с возможностью удаления треков и кликом для перехода.
 * 3. «Что играло» (History / Недавно играли) с быстрым повторным запуском.
 */

import { state, updateState, onStateChange } from './state.js';
import { getApiBase } from './config.js';
import {
  formatTime,
  playQueueTrackAt,
  removeFromQueue,
  clearUpcomingQueue,
  clearHistory,
  playHistoryTrack
} from './player.js';
import { icon } from './icons.js';

let activeTab = 'queue'; // 'queue' | 'history'

export function initQueueUI() {
  const btnToggle = document.getElementById('btnPlayerQueue');
  const btnClose = document.getElementById('btnCloseQueue');
  const btnClearUpcoming = document.getElementById('btnClearQueue');
  const btnClearHist = document.getElementById('btnClearHistory');
  const drawer = document.getElementById('queueDrawer');

  if (btnToggle) {
    btnToggle.addEventListener('click', () => {
      toggleQueueDrawer();
    });
  }

  if (btnClose) {
    btnClose.addEventListener('click', () => {
      toggleQueueDrawer(false);
    });
  }

  if (btnClearUpcoming) {
    btnClearUpcoming.addEventListener('click', () => {
      clearUpcomingQueue();
    });
  }

  if (btnClearHist) {
    btnClearHist.addEventListener('click', () => {
      clearHistory();
    });
  }

  // Переключение вкладок «Очередь» / «История»
  document.querySelectorAll('.queue-tab').forEach(tab => {
    tab.addEventListener('click', () => {
      const target = tab.dataset.tab;
      switchQueueTab(target);
    });
  });

  // Закрытие по клику вне панели (если клик на затемнение/фон)
  document.addEventListener('click', (e) => {
    if (state.isQueueOpen && drawer && !drawer.contains(e.target) && btnToggle && !btnToggle.contains(e.target)) {
      // Закрываем только если клик не внутри плеера
      const isPlayer = e.target.closest('.bottom-player-bar');
      if (!isPlayer) {
        toggleQueueDrawer(false);
      }
    }
  });

  // Закрытие по Escape
  window.addEventListener('keydown', (e) => {
    if (e.key === 'Escape' && state.isQueueOpen) {
      toggleQueueDrawer(false);
    }
  });

  // Слушатели обновлений очереди и треков
  window.addEventListener('queue:updated', () => {
    if (state.isQueueOpen) {
      renderQueue();
    }
    updateQueueBadge();
  });

  onStateChange('currentTrack', () => {
    if (state.isQueueOpen) {
      renderQueue();
    }
    updateQueueBadge();
  });

  onStateChange('isPlaying', () => {
    if (state.isQueueOpen) {
      updateQueueNowPlayingStatus();
    }
  });

  if (state.isQueueOpen) {
    toggleQueueDrawer(true);
  }
}

/**
 * Открытие/закрытие боковой панели очереди.
 */
export function toggleQueueDrawer(forceOpen = null) {
  const drawer = document.getElementById('queueDrawer');
  const btnToggle = document.getElementById('btnPlayerQueue');
  if (!drawer) return;

  const nextState = forceOpen !== null ? forceOpen : !state.isQueueOpen;
  updateState('isQueueOpen', nextState);
  try {
    localStorage.setItem('sentinel_queue_open', nextState ? 'true' : 'false');
  } catch (_) {}

  drawer.classList.toggle('open', nextState);
  if (btnToggle) {
    btnToggle.classList.toggle('active', nextState);
  }

  if (nextState) {
    renderQueue();
  }
}

/**
 * Переключение между вкладками Очереди и Истории.
 */
function switchQueueTab(tabName) {
  activeTab = tabName;

  document.querySelectorAll('.queue-tab').forEach(tab => {
    tab.classList.toggle('active', tab.dataset.tab === tabName);
  });

  const tabUpcoming = document.getElementById('queueTabUpcoming');
  const tabHistory = document.getElementById('queueTabHistory');

  if (tabUpcoming) tabUpcoming.style.display = tabName === 'queue' ? 'block' : 'none';
  if (tabHistory) tabHistory.style.display = tabName === 'history' ? 'block' : 'none';
}

/**
 * Обновление счётчиков на кнопке и в заголовках.
 */
function updateQueueBadge() {
  const upcomingCount = (state.queue && state.queue.length > 0)
    ? Math.max(0, state.queue.length - 1 - state.queueIndex)
    : 0;

  const countBadge = document.getElementById('queueUpcomingCount');
  if (countBadge) {
    countBadge.textContent = upcomingCount;
  }
}

/**
 * Полная перерисовка содержимого панели очереди.
 */
export function renderQueue() {
  renderNowPlayingCard();
  renderUpcomingList();
  renderHistoryList();
  updateQueueBadge();
}

/**
 * Отрисовка карточки текущего играющего трека.
 */
function renderNowPlayingCard() {
  const container = document.getElementById('queueNowPlayingCard');
  if (!container) return;

  const track = state.currentTrack;
  if (!track) {
    container.innerHTML = `
      <div class="queue-empty-state">
        <span style="display: flex; justify-content: center; opacity: 0.5;">${icon('music', { size: 30 })}</span>
        <div style="font-size: 0.88rem; color: var(--text-muted); margin-top: 6px;">Ничего не воспроизводится</div>
      </div>
    `;
    return;
  }

  const isPlaying = state.isPlaying;
  const fmt = (track.format || track.audio_format || '').toLowerCase();
  const isFlac = fmt === 'flac' || fmt === 'wav';
  const coverUrl = track.cover_url || (typeof track.id === 'number' && track.id > 0 ? `${getApiBase()}/api/covers/${track.id}` : '');
  const coverHtml = coverUrl
    ? `<img class="queue-now-playing-cover" src="${coverUrl}" alt="" onerror="this.style.opacity='0.2'" />`
    : `<div class="queue-now-playing-cover" style="display:flex;align-items:center;justify-content:center;background:var(--bg-card);">${icon('music', { size: 20 })}</div>`;

  container.innerHTML = `
    ${coverHtml}
    <div class="queue-now-playing-info">
      <div class="queue-track-title-line">
        <span class="queue-track-title">${escapeHtml(track.title || 'Без названия')}</span>
        ${isFlac ? '<span class="flac-badge">FLAC</span>' : ''}
      </div>
      <div class="queue-track-artist">${escapeHtml(track.artist || 'Неизвестный исполнитель')}</div>
      <div class="queue-now-playing-meta">
        <span class="queue-track-album">${escapeHtml(track.album || track.source_name || 'Sentinel Music')}</span>
        <span class="queue-track-time">${formatTime(track.duration)}</span>
      </div>
    </div>`;
    <div class="now-playing-bars" style="display: flex;">
      <div class="playing-bar" style="${isPlaying ? '' : 'animation-play-state: paused;'}"></div>
      <div class="playing-bar" style="${isPlaying ? '' : 'animation-play-state: paused;'}"></div>
      <div class="playing-bar" style="${isPlaying ? '' : 'animation-play-state: paused;'}"></div>
    </div>
  `;
}

/**
 * Отрисовка списка предстоящих треков (Up Next).
 */
function renderUpcomingList() {
  const container = document.getElementById('queueUpcomingList');
  if (!container) return;

  const queue = state.queue || [];
  const currentIndex = state.queueIndex >= 0 ? state.queueIndex : 0;
  const upcomingTracks = queue.slice(currentIndex + 1);

  const countEl = document.getElementById('queueUpcomingCount');
  if (countEl) countEl.textContent = upcomingTracks.length;

  if (upcomingTracks.length === 0) {
    container.innerHTML = `
      <div class="queue-empty-state">
        <span style="display: flex; justify-content: center; opacity: 0.5;">${icon('sparkles', { size: 24 })}</span>
        <div style="font-size: 0.86rem; color: var(--text-muted); margin-top: 6px;">
          Список следующих треков пуст.<br>
          <span style="font-size: 0.78rem; opacity: 0.8;">Включите альбом, плейлист или добавьте треки через меню ⋮</span>
        </div>
      </div>
    `;
    return;
  }

  container.innerHTML = '';

  upcomingTracks.forEach((track, relIdx) => {
    const absIdx = currentIndex + 1 + relIdx;
    const isFlac = (track.audio_format || '').toLowerCase() === 'flac';

    const item = document.createElement('div');
    item.className = 'queue-item';
    item.innerHTML = `
      <span class="queue-item-index">${relIdx + 1}</span>
      ${track.cover_url || (typeof track.id === 'number' && track.id > 0) ? `<img class="queue-item-cover" src="${track.cover_url || `${getApiBase()}/api/covers/${track.id}`}" alt="" onerror="this.style.opacity='0.2'" />` : `<div class="queue-item-cover" style="display:flex;align-items:center;justify-content:center;background:var(--bg-card);">${icon('music', { size: 14 })}</div>`}
      <div class="queue-item-details">
        <div class="queue-track-title-line">
          <span class="queue-item-title">${escapeHtml(track.title)}</span>
          ${isFlac ? '<span class="flac-badge" style="font-size: 0.58rem; padding: 0 4px;">FLAC</span>' : ''}
        </div>
        <span class="queue-item-artist">${escapeHtml(track.artist)}</span>
      </div>
      <span class="queue-item-time">${formatTime(track.duration)}</span>
      <button class="queue-btn-remove" title="Удалить из очереди">${icon('close', { size: 14 })}</button>
    `;

    // Клик по строке — мгновенный переход к этому треку в очереди
    item.addEventListener('click', (e) => {
      if (e.target.closest('.queue-btn-remove')) return;
      playQueueTrackAt(absIdx);
    });

    // Удаление из очереди
    const removeBtn = item.querySelector('.queue-btn-remove');
    if (removeBtn) {
      removeBtn.addEventListener('click', (e) => {
        e.stopPropagation();
        removeFromQueue(relIdx);
      });
    }

    container.appendChild(item);
  });
}

/**
 * Отрисовка списка проигранных ранее треков (History).
 */
function renderHistoryList() {
  const container = document.getElementById('queueHistoryList');
  if (!container) return;

  const currentTrack = state.currentTrack;
  const queue = state.queue || [];
  const currentIndex = state.queueIndex >= 0 ? state.queueIndex : 0;

  // Треки, которые уже сыграли из текущей очереди
  const playedFromQueue = queue.slice(0, currentIndex).reverse();
  const globalHistory = Array.isArray(state.history) ? state.history : [];

  // Объединяем без дубликатов по ID и без текущего играющего трека
  const seenIds = new Set();
  const historyList = [];

  for (const t of [...playedFromQueue, ...globalHistory]) {
    if (t && t.id && !seenIds.has(t.id) && (!currentTrack || t.id !== currentTrack.id)) {
      seenIds.add(t.id);
      historyList.push(t);
    }
  }

  const countEl = document.getElementById('queueHistoryCount');
  if (countEl) countEl.textContent = historyList.length;

  if (historyList.length === 0) {
    container.innerHTML = `
      <div class="queue-empty-state">
        <span style="display: flex; justify-content: center; opacity: 0.5;">${icon('clock', { size: 24 })}</span>
        <div style="font-size: 0.86rem; color: var(--text-muted); margin-top: 6px;">
          История воспроизведения пуста.<br>
          <span style="font-size: 0.78rem; opacity: 0.8;">Здесь появятся треки, которые вы уже послушали.</span>
        </div>
      </div>
    `;
    return;
  }

  container.innerHTML = '';

  historyList.forEach((track) => {
    const isFlac = (track.audio_format || '').toLowerCase() === 'flac';

    const item = document.createElement('div');
    item.className = 'queue-item history-item';
    item.innerHTML = `
      <span class="queue-item-play-btn" title="Слушать повторно">${icon('play', { size: 14 })}</span>
      ${track.cover_url || (typeof track.id === 'number' && track.id > 0) ? `<img class="queue-item-cover" src="${track.cover_url || `${getApiBase()}/api/covers/${track.id}`}" alt="" onerror="this.style.opacity='0.2'" />` : `<div class="queue-item-cover" style="display:flex;align-items:center;justify-content:center;background:var(--bg-card);">${icon('music', { size: 14 })}</div>`}
      <div class="queue-item-details">
        <div class="queue-track-title-line">
          <span class="queue-item-title">${escapeHtml(track.title)}</span>
          ${isFlac ? '<span class="flac-badge" style="font-size: 0.58rem; padding: 0 4px;">FLAC</span>' : ''}
        </div>
        <span class="queue-item-artist">${escapeHtml(track.artist)}</span>
      </div>
      <span class="queue-item-time">${formatTime(track.duration)}</span>
    `;

    // Клик по треку из истории — запуск воспроизведения
    item.addEventListener('click', () => {
      playHistoryTrack(track);
    });

    container.appendChild(item);
  });
}

function updateQueueNowPlayingStatus() {
  const bars = document.querySelectorAll('#queueNowPlayingCard .playing-bar');
  const isPlaying = state.isPlaying;
  bars.forEach(bar => {
    bar.style.animationPlayState = isPlaying ? 'running' : 'paused';
  });
}

function escapeHtml(text) {
  if (!text) return '';
  const map = { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#039;' };
  return String(text).replace(/[&<>"']/g, m => map[m]);
}
