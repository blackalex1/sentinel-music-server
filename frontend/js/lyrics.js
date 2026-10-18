/**
 * Sentinel Music — Модуль караоке-текстов песен (Lyrics Controller).
 * Управляет всплывающим окном текста с динамической фоновой обложкой,
 * плавной автопрокруткой и подсветкой активной строки без смены страницы.
 */

import { state, updateState, onStateChange } from './state.js';
import { API_BASE } from './config.js';
import { fetchLyrics } from './api.js';
import { seekTime } from './player.js';

let currentLyricsTrackId = null;

export function initLyrics() {
  const closeBtn = document.getElementById('btnCloseLyrics');
  if (closeBtn) {
    closeBtn.addEventListener('click', () => {
      toggleLyricsOverlay(false);
    });
  }

  // Закрытие всплывающего окна по Escape
  window.addEventListener('keydown', (e) => {
    const overlay = document.getElementById('lyricsOverlay');
    if (e.key === 'Escape' && overlay && overlay.classList.contains('active')) {
      toggleLyricsOverlay(false);
    }
  });

  // Слушаем смену трека для автоматической предзагрузки текстов и обновления фона
  window.addEventListener('track:changed', (e) => {
    const track = e.detail;
    if (track && track.id) {
      currentLyricsTrackId = null;
      updateState('activeLyricIndex', -1);
      const container = document.getElementById('lyricsContainer');
      if (container) {
        container.scrollTop = 0;
      }
      updateLyricsOverlayTrackInfo(track);
      loadTrackLyrics(track.id);
    }
  });

  onStateChange('currentTrack', (track) => {
    if (track) {
      updateLyricsOverlayTrackInfo(track);
    }
  });

  // Синхронизация времени воспроизведения со строками текста
  onStateChange('currentTime', (curTime) => {
    syncLyricsWithTime(curTime);
  });
}

/**
 * Открытие/закрытие всплывающего окна текстов песен.
 */
export function toggleLyricsOverlay(forceState = null) {
  const overlay = document.getElementById('lyricsOverlay');
  const btnLyrics = document.getElementById('btnPlayerLyrics');
  if (!overlay) return;

  const isOpen = overlay.classList.contains('active');
  const nextState = forceState !== null ? forceState : !isOpen;

  if (nextState) {
    overlay.classList.add('active');
    if (state.currentTrack) {
      updateLyricsOverlayTrackInfo(state.currentTrack);
      if (currentLyricsTrackId !== state.currentTrack.id) {
        loadTrackLyrics(state.currentTrack.id);
      }
    }

    const container = document.getElementById('lyricsContainer');
    // Если трек в самом начале или активная строка не определена — всегда открываем с самого начала (scrollTop = 0)
    if (!state.currentTime || state.currentTime <= 2 || state.activeLyricIndex <= 0) {
      if (container) {
        container.scrollTop = 0;
      }
    } else if (state.activeLyricIndex > 0 && container) {
      const activeLine = document.getElementById(`lyric-line-${state.activeLyricIndex}`);
      if (activeLine) {
        const targetScroll = Math.max(0, activeLine.offsetTop - (container.clientHeight / 2) + (activeLine.clientHeight / 2));
        container.scrollTo({ top: targetScroll, behavior: 'smooth' });
      }
    }
  } else {
    overlay.classList.remove('active');
  }

  if (btnLyrics) {
    btnLyrics.classList.toggle('active', nextState);
  }
}

/**
 * Обновление метаданных трека и обложки на фоне всплывающего окна текстов.
 */
function updateLyricsOverlayTrackInfo(track) {
  if (!track) return;

  const headerTitle = document.getElementById('lyricsHeaderTitle');
  const headerArtist = document.getElementById('lyricsHeaderArtist');
  const headerCover = document.getElementById('lyricsHeaderCover');
  const backdropCover = document.getElementById('lyricsBackdropCover');

  if (headerTitle) headerTitle.textContent = track.title || 'Трек не выбран';
  if (headerArtist) headerArtist.textContent = track.artist || 'Sentinel Music';

  const coverUrl = track.cover_url || (track.id ? `${API_BASE}/api/covers/${track.id}` : '');

  if (headerCover) {
    if (coverUrl) {
      headerCover.onerror = () => { headerCover.style.display = 'none'; };
      headerCover.src = coverUrl;
      headerCover.style.display = 'block';
    } else {
      headerCover.style.display = 'none';
    }
  }

  if (backdropCover) {
    if (coverUrl) {
      backdropCover.onerror = () => { backdropCover.style.display = 'none'; };
      backdropCover.onload = () => { backdropCover.style.display = 'block'; };
      backdropCover.src = coverUrl;
      backdropCover.style.display = 'block';
    } else {
      backdropCover.style.display = 'none';
    }
  }
}

/**
 * Загрузка текста песни для указанного трека.
 */
export async function loadTrackLyrics(trackId) {
  if (currentLyricsTrackId === trackId && state.lyrics && state.lyrics.length > 0) return;
  currentLyricsTrackId = trackId;

  const container = document.getElementById('lyricsContainer');
  if (container) {
    container.innerHTML = '<div class="lyrics-empty-state">Загрузка текста...</div>';
    container.scrollTop = 0;
  }

  updateState('lyrics', []);
  updateState('activeLyricIndex', -1);

  try {
    const data = await fetchLyrics(trackId);
    if (!data) {
      renderLyricsEmpty('Текст песни пока не найден в базе');
      return;
    }

    if (data.synced && Array.isArray(data.lines) && data.lines.length > 0) {
      updateState('lyrics', data.lines);
      renderSyncedLyrics(data.lines);
      // Если воспроизведение уже шло дальше начала, синхронизируем
      if (state.currentTime > 0) {
        syncLyricsWithTime(state.currentTime);
      }
    } else if (data.raw) {
      renderRawLyrics(data.raw);
    } else {
      renderLyricsEmpty('Для этого трека текст отсутствует');
    }
  } catch (err) {
    console.warn('Ошибка при получении текста песни:', err);
    renderLyricsEmpty('Не удалось загрузить текст песни');
  }
}

/**
 * Отрисовка синхронизированных караоке-строк.
 */
function renderSyncedLyrics(lines) {
  const container = document.getElementById('lyricsContainer');
  if (!container) return;

  container.innerHTML = '';
  container.scrollTop = 0;

  lines.forEach((line, index) => {
    const lineEl = document.createElement('div');
    lineEl.className = 'lyric-line-item';
    lineEl.id = `lyric-line-${index}`;
    lineEl.dataset.index = index;
    lineEl.dataset.time = line.time_sec ?? line.time ?? 0;
    lineEl.textContent = line.text;

    lineEl.addEventListener('click', () => {
      const targetTime = parseFloat(lineEl.dataset.time);
      if (!isNaN(targetTime)) {
        seekTime(targetTime);
      }
    });

    container.appendChild(lineEl);
  });
}

/**
 * Отрисовка несинхронизированного простого текста.
 */
function renderRawLyrics(rawText) {
  const container = document.getElementById('lyricsContainer');
  if (!container) return;

  container.innerHTML = `
    <div style="white-space: pre-line; line-height: 1.8; font-size: 1.25rem; color: rgba(255, 255, 255, 0.85); max-width: 680px; margin: 40px auto; text-shadow: 0 2px 10px rgba(0, 0, 0, 0.6);">
      ${escapeHtml(rawText)}
    </div>
  `;
  container.scrollTop = 0;
}

function renderLyricsEmpty(msg) {
  const container = document.getElementById('lyricsContainer');
  if (!container) return;
  container.innerHTML = `<div class="lyrics-empty-state">${escapeHtml(msg)}</div>`;
  container.scrollTop = 0;
}

/**
 * Синхронизация времени воспроизведения со строками текста.
 */
function syncLyricsWithTime(currentTime) {
  const lines = state.lyrics;
  if (!lines || lines.length === 0) return;

  let activeIdx = -1;
  for (let i = 0; i < lines.length; i++) {
    const lineTime = lines[i].time_sec ?? lines[i].time ?? 0;
    if (currentTime >= lineTime) {
      activeIdx = i;
    } else {
      break;
    }
  }

  if (activeIdx === state.activeLyricIndex) return;

  updateState('activeLyricIndex', activeIdx);

  const container = document.getElementById('lyricsContainer');

  // Если трек в самом начале (до первой строчки текста), сбрасываем активные классы и держим вверху
  if (activeIdx < 0) {
    document.querySelectorAll('.lyric-line-item').forEach((el) => {
      el.classList.remove('active', 'passed');
    });
    if (container && currentTime <= 1.5) {
      container.scrollTop = 0;
    }
    return;
  }

  // Обновляем визуальные классы строк
  document.querySelectorAll('.lyric-line-item').forEach((el, idx) => {
    if (idx === activeIdx) {
      el.classList.add('active');
      el.classList.remove('passed');

      // Плавная прокрутка внутри контейнера строк караоке
      if (container) {
        const targetScroll = Math.max(0, el.offsetTop - (container.clientHeight / 2) + (el.clientHeight / 2));
        container.scrollTo({ top: targetScroll, behavior: 'smooth' });
      }
    } else if (idx < activeIdx) {
      el.classList.remove('active');
      el.classList.add('passed');
    } else {
      el.classList.remove('active', 'passed');
    }
  });
}

function escapeHtml(text) {
  if (!text) return '';
  const map = { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#039;' };
  return String(text).replace(/[&<>"']/g, m => map[m]);
}
