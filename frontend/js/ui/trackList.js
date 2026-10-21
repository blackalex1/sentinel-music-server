/**
 * Модуль отрисовки списков треков, бесконечной подгрузки (Infinite Scroll) и эквалайзеров строк.
 */

import { state, updateState } from '../state.js';
import { fetchTracks, fetchTracksCount, fetchRecentTracks, sendReaction } from '../api.js';
import { playTrack, formatTime, playShuffleTracks } from '../player.js';
import { getApiBase } from '../config.js';
import { showToast, escapeHtml } from './toast.js';
import { openTrackContextMenu } from './contextMenu.js';
import { updatePlayerReactionsUI } from './playerControls.js';
import { toggleLikeAction } from './reactions.js';
import { icon } from '../icons.js';

const PAGE_SIZE = 50;
let libraryOffset = 0;
let totalTracksCount = 0;
let hasMoreLibraryTracks = true;
let isLoadingMoreTracks = false;
let tracksScrollObserver = null;
let currentLibraryMood = 'all';

let mainMoodTracks = [];
let mainTracksOffset = 0;
let totalMainTracksCount = 0;
let hasMoreMainTracks = true;
let isLoadingMoreMainTracks = false;
let currentMainMood = 'default';
let mainTracksScrollObserver = null;

const MOOD_TITLES = {
  default: 'Недавно добавленные треки',
  all: 'Недавно добавленные треки',
  energy: 'Бодрые треки',
  chill: 'Спокойные треки',
  happy: 'Радостные треки',
  sad: 'Грустные треки'
};

export function getCurrentLibraryMood() {
  return currentLibraryMood;
}

export function syncLibraryMoodChips(mood) {
  currentLibraryMood = mood || 'all';
  const chips = document.querySelectorAll('.tracks-mood-chip');
  chips.forEach(chip => {
    chip.classList.toggle('active', chip.dataset.mood === currentLibraryMood);
  });
}

export function initLibraryMoodChips() {
  const bar = document.getElementById('tracksMoodBar');
  if (!bar) return;

  bar.addEventListener('click', (e) => {
    const chip = e.target.closest('.tracks-mood-chip');
    if (!chip) return;
    const mood = chip.dataset.mood || 'all';
    if (mood === currentLibraryMood) return;
    syncLibraryMoodChips(mood);
    loadLibraryTracks(true, false, mood);
  });
}

export function getMainMoodTracks() {
  return mainMoodTracks;
}

export function getCurrentMainMood() {
  return currentMainMood;
}

export function disconnectMainTracksScrollObserver() {
  if (mainTracksScrollObserver) {
    mainTracksScrollObserver.disconnect();
    mainTracksScrollObserver = null;
  }
}

export function getTotalTracksCount() {
  return totalTracksCount;
}

export function setTotalTracksCount(count) {
  totalTracksCount = count;
}

export function disconnectTracksScrollObserver() {
  if (tracksScrollObserver) {
    tracksScrollObserver.disconnect();
    tracksScrollObserver = null;
  }
}

export function setHasMoreLibraryTracks(val) {
  hasMoreLibraryTracks = val;
}

export function syncMoodCardsActiveState(mood) {
  const cards = document.querySelectorAll('.mood-collection-card');
  const btnAll = document.getElementById('btnMoodAll');
  const isDefault = !mood || mood === 'default' || mood === 'all';

  if (btnAll) {
    btnAll.classList.toggle('active', isDefault);
  }

  cards.forEach(card => {
    card.classList.toggle('active', !isDefault && card.dataset.mood === mood);
  });
}

function formatTrackCount(count) {
  const n = Math.abs(count) % 100;
  const n1 = n % 10;
  if (n > 10 && n < 20) return `${count.toLocaleString('ru-RU')} треков`;
  if (n1 > 1 && n1 < 5) return `${count.toLocaleString('ru-RU')} трека`;
  if (n1 === 1) return `${count.toLocaleString('ru-RU')} трек`;
  return `${count.toLocaleString('ru-RU')} треков`;
}

export async function loadMoodCollectionCounts() {
  const moods = ['energy', 'chill', 'happy', 'sad'];
  const countEls = {
    energy: document.getElementById('countMoodEnergy'),
    chill: document.getElementById('countMoodChill'),
    happy: document.getElementById('countMoodHappy'),
    sad: document.getElementById('countMoodSad')
  };

  try {
    const results = await Promise.allSettled(
      moods.map(m => fetchTracksCount(m))
    );

    moods.forEach((m, idx) => {
      const res = results[idx];
      const el = countEls[m];
      if (el) {
        if (res.status === 'fulfilled' && res.value && typeof res.value.count === 'number') {
          el.textContent = formatTrackCount(res.value.count);
        } else {
          el.textContent = '0 треков';
        }
      }
    });
  } catch (err) {
    console.warn('[MoodCollections] Не удалось загрузить счетчики настроений:', err);
  }
}

export function initMoodCollectionsUI() {
  const cards = document.querySelectorAll('.mood-collection-card');
  const btnAll = document.getElementById('btnMoodAll');

  cards.forEach(card => {
    card.addEventListener('click', (e) => {
      if (e.target.closest('.mood-quick-play-btn')) return;
      const mood = card.dataset.mood;
      if (mood) {
        syncMoodCardsActiveState(mood);
        loadMainViewTracks(mood);
      }
    });

    const playBtn = card.querySelector('.mood-quick-play-btn');
    if (playBtn) {
      playBtn.addEventListener('click', (e) => {
        e.stopPropagation();
        const mood = playBtn.dataset.mood;
        if (mood) {
          syncMoodCardsActiveState(mood);
          loadMainViewTracks(mood);
          playShuffleTracks(mood);
        }
      });
    }
  });

  if (btnAll) {
    btnAll.addEventListener('click', () => {
      syncMoodCardsActiveState('default');
      loadMainViewTracks('default');
    });
  }

  loadMoodCollectionCounts();
}

export async function loadMainViewTracks(mood = 'default') {
  currentMainMood = mood;
  mainTracksOffset = 0;
  hasMoreMainTracks = true;
  isLoadingMoreMainTracks = false;
  mainMoodTracks = [];
  disconnectMainTracksScrollObserver();
  syncMoodCardsActiveState(mood);

  const container = document.getElementById('mainTracksContainer');
  const titleEl = document.getElementById('mainTracksTitle');
  const actionsEl = document.getElementById('mainTracksActions');
  const sentinel = document.getElementById('mainTracksScrollSentinel');
  if (!container) return;

  const baseTitle = MOOD_TITLES[mood] || 'Недавно добавленные треки';
  if (titleEl) {
    titleEl.textContent = baseTitle;
  }
  if (actionsEl) {
    actionsEl.style.display = 'none';
  }
  if (sentinel) {
    sentinel.style.display = 'none';
  }

  container.innerHTML = '<div style="color: var(--text-muted); padding: 30px; text-align: center;"><div class="spinner" style="margin: 0 auto 10px;"></div>Загрузка категории...</div>';

  try {
    const [countData, tracks] = await Promise.all([
      fetchTracksCount(mood),
      fetchRecentTracks(PAGE_SIZE, mood, 0)
    ]);

    totalMainTracksCount = countData && typeof countData.count === 'number' ? countData.count : (tracks ? tracks.length : 0);

    if (titleEl) {
      titleEl.textContent = `${baseTitle} (${totalMainTracksCount.toLocaleString('ru-RU')} треков)`;
    }

    if (!tracks || tracks.length === 0) {
      container.innerHTML = '<div style="color: var(--text-muted); padding: 40px; text-align: center;">В этой категории пока нет треков</div>';
      return;
    }

    mainMoodTracks = [...tracks];
    if (actionsEl) {
      actionsEl.style.display = 'flex';
    }

    if (tracks.length < PAGE_SIZE || tracks.length >= totalMainTracksCount) {
      hasMoreMainTracks = false;
    }

    renderTracksTable(mainMoodTracks, 'mainTracksContainer');
    setupMainInfiniteScroll();
  } catch (err) {
    console.error('Ошибка загрузки треков категории:', err);
    container.innerHTML = '<div style="color: var(--text-muted); padding: 30px; text-align: center;">Не удалось загрузить треки</div>';
  }
}

export const loadRecentTracks = () => loadMainViewTracks(state.streamMood || 'default');

export async function loadLibraryTracks(reset = true, soft = false, mood = currentLibraryMood) {
  const container = document.getElementById('tracksTableContainer');
  if (!container) return;

  currentLibraryMood = mood || 'all';
  syncLibraryMoodChips(currentLibraryMood);

  const effectiveMood = (currentLibraryMood && currentLibraryMood !== 'all') ? currentLibraryMood : null;

  if (reset) {
    libraryOffset = 0;
    hasMoreLibraryTracks = true;
    isLoadingMoreTracks = false;
    disconnectTracksScrollObserver();
    if (!soft) {
      container.innerHTML = '<div style="color: var(--text-muted); padding: 40px; text-align: center;"><div class="spinner" style="margin: 0 auto 12px;"></div>Загрузка фонотеки...</div>';
    }
  }

  try {
    const [countData, tracks] = await Promise.all([
      fetchTracksCount(effectiveMood),
      fetchTracks('', PAGE_SIZE, 0, 'recent', effectiveMood)
    ]);

    totalTracksCount = countData && typeof countData.count === 'number' ? countData.count : tracks.length;
    updateState('tracks', tracks);

    const titleEl = document.getElementById('tracksViewTitle');
    const moodNames = {
      energy: 'Бодрое',
      chill: 'Спокойное',
      happy: 'Радостное',
      sad: 'Грустное'
    };
    const titleSuffix = moodNames[currentLibraryMood] ? ` · ${moodNames[currentLibraryMood]}` : '';
    if (titleEl) {
      titleEl.textContent = `Коллекция треков${titleSuffix} (${totalTracksCount.toLocaleString('ru-RU')} треков)`;
    }

    if (tracks.length < PAGE_SIZE || tracks.length >= totalTracksCount) {
      hasMoreLibraryTracks = false;
    }

    renderTracksTable(tracks, 'tracksTableContainer');
    setupInfiniteScroll();

    loadMainViewTracks(state.streamMood || 'default');
    loadMoodCollectionCounts();
  } catch (err) {
    console.error('Ошибка загрузки фонотеки:', err);
    if (container && !soft) {
      container.innerHTML = '<div style="color: var(--text-muted); padding: 40px; text-align: center;">Не удалось загрузить коллекцию треков</div>';
    }
  }
}

export function renderTracksTable(tracks, containerId) {
  const container = document.getElementById(containerId);
  if (!container) return;

  if (!tracks || tracks.length === 0) {
    const isPlaylist = state.activePlaylist !== null;
    const emptyMsg = isPlaylist
      ? 'В этом плейлисте пока нет треков. Добавьте треки из коллекции через меню ⋮'
      : 'Треки не найдены';
    container.innerHTML = `<div style="color: var(--text-muted); padding: 40px; text-align: center;">${emptyMsg}</div>`;
    return;
  }

  const isMainLibrary = containerId === 'tracksTableContainer' && !state.activePlaylist && !state.searchQuery;

  container.innerHTML = `
    <div class="table-header">
      <div>#</div>
      <div></div>
      <div>Название</div>
      <div>Альбом</div>
      <div></div>
      <div style="text-align: right;">Время</div>
      <div></div>
    </div>
    <div class="track-rows-list"></div>
  `;

  const sentinel = document.getElementById('tracksScrollSentinel');
  if (sentinel) {
    if (isMainLibrary) {
      sentinel.style.display = 'flex';
      if (!hasMoreLibraryTracks) {
        sentinel.innerHTML = `<span style="opacity: 0.6;">Все треки коллекции загружены (${totalTracksCount.toLocaleString('ru-RU')})</span>`;
      } else {
        sentinel.innerHTML = '<div class="spinner" style="opacity: 0.4;"></div>';
      }
    } else {
      sentinel.style.display = 'none';
    }
  }

  const rowsList = container.querySelector('.track-rows-list');
  appendTrackRowsElements(tracks, rowsList, 0, tracks);
}

export function appendTrackRowsElements(tracks, rowsList, startIndex = 0, fullList = null) {
  if (!rowsList || !tracks) return;

  tracks.forEach((track, idx) => {
    const index = startIndex + idx;
    const isCurrent = state.currentTrack && state.currentTrack.id === track.id;
    const isPlaying = isCurrent && state.isPlaying;

    const row = document.createElement('div');
    row.className = `track-row ${isCurrent ? 'active' : ''}`;
    row.dataset.id = track.id;

    const isFlac = (track.audio_format || '').toLowerCase() === 'flac';

    row.innerHTML = `
      <div class="track-cell-index">
        <span class="track-index-num" style="${isCurrent ? 'display: none;' : ''}">${index + 1}</span>
        <span class="track-index-play" style="${isCurrent ? 'display: none;' : ''}">▶</span>
        <div class="now-playing-bars" style="${isCurrent ? 'display: flex;' : 'display: none;'}">
          <div class="playing-bar" style="${isPlaying ? '' : 'animation-play-state: paused;'}"></div>
          <div class="playing-bar" style="${isPlaying ? '' : 'animation-play-state: paused;'}"></div>
          <div class="playing-bar" style="${isPlaying ? '' : 'animation-play-state: paused;'}"></div>
        </div>
      </div>
      <img class="track-cell-cover" src="${getApiBase()}/api/covers/${track.id}" alt="" onerror="this.style.opacity='0.2'" />
      <div class="track-cell-info">
        <div class="track-title-line">
          <span class="track-cell-title">${escapeHtml(track.title)}</span>
          ${isFlac ? '<span class="flac-badge">FLAC</span>' : ''}
        </div>
        <span class="track-cell-artist">${escapeHtml(track.artist)}</span>
      </div>
      <div class="track-cell-album">${escapeHtml(track.album || '—')}</div>
      <button class="btn-like ${track.is_liked ? 'liked' : ''}" title="Нравится">
        ${track.is_liked ? icon('heartFilled', { size: 16, className: 'icon-liked' }) : icon('heart', { size: 16 })}
      </button>
      <div class="track-cell-duration">${formatTime(track.duration)}</div>
      <button class="btn-track-menu" title="Действия">⋮</button>
    `;

    row.addEventListener('click', (e) => {
      if (e.target.closest('.btn-like') || e.target.closest('.btn-track-menu')) return;
      playTrack(track, fullList || state.tracks, false);
    });

    const likeBtn = row.querySelector('.btn-like');
    likeBtn.addEventListener('click', (e) => {
      e.stopPropagation();
      toggleLikeAction(track.id);
    });

    const menuBtn = row.querySelector('.btn-track-menu');
    menuBtn.addEventListener('click', (e) => {
      e.stopPropagation();
      openTrackContextMenu(track, menuBtn);
    });

    rowsList.appendChild(row);
  });
}

let scrollListenerBound = false;

function handleContentScroll() {
  const scrollArea = document.getElementById('contentArea');
  if (!scrollArea) return;

  // Если прокручено до нижних 500px - подгружаем следующую порцию
  if (scrollArea.scrollTop + scrollArea.clientHeight >= scrollArea.scrollHeight - 500) {
    if (state.currentView === 'tracks' && !state.searchQuery && !state.activePlaylist) {
      if (!isLoadingMoreTracks && hasMoreLibraryTracks) {
        loadMoreTracks();
      }
    } else if (state.currentView === 'main') {
      if (!isLoadingMoreMainTracks && hasMoreMainTracks) {
        loadMoreMainTracks();
      }
    }
  }
}

export async function loadMoreTracks() {
  if (isLoadingMoreTracks || !hasMoreLibraryTracks) return;
  if (state.currentView !== 'tracks' || state.searchQuery || state.activePlaylist) return;

  const rowsList = document.querySelector('#tracksTableContainer .track-rows-list');
  const sentinel = document.getElementById('tracksScrollSentinel');
  if (!rowsList) return;

  isLoadingMoreTracks = true;
  if (sentinel) {
    sentinel.style.display = 'flex';
    sentinel.innerHTML = '<div class="spinner"></div><span>Загрузка следующих треков...</span>';
  }

  try {
    const nextOffset = libraryOffset + PAGE_SIZE;
    const effectiveMood = (currentLibraryMood && currentLibraryMood !== 'all') ? currentLibraryMood : null;
    const nextTracks = await fetchTracks('', PAGE_SIZE, nextOffset, 'recent', effectiveMood);

    if (!nextTracks || nextTracks.length === 0) {
      hasMoreLibraryTracks = false;
      if (sentinel) {
        sentinel.innerHTML = `<span style="opacity: 0.6;">Все треки коллекции загружены (${totalTracksCount.toLocaleString('ru-RU')})</span>`;
      }
    } else {
      libraryOffset = nextOffset;
      const currentCount = state.tracks.length;
      updateState('tracks', [...state.tracks, ...nextTracks]);

      appendTrackRowsElements(nextTracks, rowsList, currentCount, state.tracks);

      if (nextTracks.length < PAGE_SIZE || state.tracks.length >= totalTracksCount) {
        hasMoreLibraryTracks = false;
        if (sentinel) {
          sentinel.innerHTML = `<span style="opacity: 0.6;">Все треки коллекции загружены (${totalTracksCount.toLocaleString('ru-RU')})</span>`;
        }
      } else {
        if (sentinel) {
          sentinel.innerHTML = '<div class="spinner" style="opacity: 0.4;"></div>';
        }
      }
    }
  } catch (err) {
    console.error('Ошибка подгрузки следующей пачки треков:', err);
    if (sentinel) {
      sentinel.innerHTML = `<span style="color: var(--accent-rose); cursor: pointer; display: inline-flex; align-items: center; gap: 6px;" id="retryScrollLoadBtn">${icon('alert', { size: 14 })} Ошибка подгрузки треков. Нажмите для повтора</span>`;
      document.getElementById('retryScrollLoadBtn')?.addEventListener('click', () => loadMoreTracks());
    }
  } finally {
    isLoadingMoreTracks = false;
  }
}

export function setupInfiniteScroll() {
  disconnectTracksScrollObserver();

  const sentinel = document.getElementById('tracksScrollSentinel');
  const scrollArea = document.getElementById('contentArea');
  if (!scrollArea) return;

  // 1. Устанавливаем гарантированный слушатель скролла на контейнер контента
  if (!scrollListenerBound) {
    scrollArea.addEventListener('scroll', handleContentScroll, { passive: true });
    scrollListenerBound = true;
  }

  if (!sentinel) return;

  if (!hasMoreLibraryTracks) {
    sentinel.style.display = 'flex';
    sentinel.innerHTML = `<span style="opacity: 0.6;">Все треки коллекции загружены (${totalTracksCount.toLocaleString('ru-RU')})</span>`;
    return;
  }

  sentinel.style.display = 'flex';
  sentinel.innerHTML = '<div class="spinner" style="opacity: 0.4;"></div>';

  // 2. IntersectionObserver в качестве упреждающего триггера (pre-fetch)
  try {
    tracksScrollObserver = new IntersectionObserver((entries) => {
      const entry = entries[0];
      if (entry && entry.isIntersecting) {
        loadMoreTracks();
      }
    }, {
      root: null,
      rootMargin: '400px',
      threshold: 0
    });

    tracksScrollObserver.observe(sentinel);
  } catch (err) {
    console.warn('IntersectionObserver недоступен, используется fallback на scroll-событие:', err);
  }
}

export async function loadMoreMainTracks() {
  if (isLoadingMoreMainTracks || !hasMoreMainTracks) return;
  if (state.currentView !== 'main') return;

  const rowsList = document.querySelector('#mainTracksContainer .track-rows-list');
  const sentinel = document.getElementById('mainTracksScrollSentinel');
  if (!rowsList) return;

  isLoadingMoreMainTracks = true;
  if (sentinel) {
    sentinel.style.display = 'flex';
    sentinel.innerHTML = '<div class="spinner"></div><span>Загрузка следующих треков...</span>';
  }

  try {
    const nextOffset = mainTracksOffset + PAGE_SIZE;
    const nextTracks = await fetchRecentTracks(PAGE_SIZE, currentMainMood, nextOffset);

    if (!nextTracks || nextTracks.length === 0) {
      hasMoreMainTracks = false;
      if (sentinel) {
        sentinel.innerHTML = `<span style="opacity: 0.6;">Все треки категории загружены (${totalMainTracksCount.toLocaleString('ru-RU')})</span>`;
      }
    } else {
      mainTracksOffset = nextOffset;
      const currentCount = mainMoodTracks.length;
      mainMoodTracks.push(...nextTracks);

      appendTrackRowsElements(nextTracks, rowsList, currentCount, mainMoodTracks);

      if (nextTracks.length < PAGE_SIZE || mainMoodTracks.length >= totalMainTracksCount) {
        hasMoreMainTracks = false;
        if (sentinel) {
          sentinel.innerHTML = `<span style="opacity: 0.6;">Все треки категории загружены (${totalMainTracksCount.toLocaleString('ru-RU')})</span>`;
        }
      } else {
        if (sentinel) {
          sentinel.innerHTML = '<div class="spinner" style="opacity: 0.4;"></div>';
        }
      }
    }
  } catch (err) {
    console.error('Ошибка подгрузки следующих треков подборки:', err);
    if (sentinel) {
      sentinel.innerHTML = `<span style="color: var(--accent-rose); cursor: pointer; display: inline-flex; align-items: center; gap: 6px;" id="retryMainScrollLoadBtn">${icon('alert', { size: 14 })} Ошибка подгрузки треков. Нажмите для повтора</span>`;
      document.getElementById('retryMainScrollLoadBtn')?.addEventListener('click', () => loadMoreMainTracks());
    }
  } finally {
    isLoadingMoreMainTracks = false;
  }
}

export function setupMainInfiniteScroll() {
  disconnectMainTracksScrollObserver();

  const sentinel = document.getElementById('mainTracksScrollSentinel');
  const scrollArea = document.getElementById('contentArea');
  if (!scrollArea || !sentinel) return;

  if (!scrollListenerBound) {
    scrollArea.addEventListener('scroll', handleContentScroll, { passive: true });
    scrollListenerBound = true;
  }

  if (!hasMoreMainTracks) {
    sentinel.style.display = 'flex';
    sentinel.innerHTML = `<span style="opacity: 0.6;">Все треки категории загружены (${totalMainTracksCount.toLocaleString('ru-RU')})</span>`;
    return;
  }

  sentinel.style.display = 'flex';
  sentinel.innerHTML = '<div class="spinner" style="opacity: 0.4;"></div>';

  try {
    mainTracksScrollObserver = new IntersectionObserver((entries) => {
      const entry = entries[0];
      if (entry && entry.isIntersecting) {
        loadMoreMainTracks();
      }
    }, {
      root: null,
      rootMargin: '400px',
      threshold: 0
    });

    mainTracksScrollObserver.observe(sentinel);
  } catch (err) {
    console.warn('IntersectionObserver недоступен для главной, используется fallback на scroll:', err);
  }
}

export function updateActiveRowEqualizers() {
  const currentId = state.currentTrack ? state.currentTrack.id : null;
  const isPlaying = state.isPlaying;

  document.querySelectorAll('.track-row').forEach(row => {
    const isThisTrack = currentId && parseInt(row.dataset.id, 10) === currentId;
    row.classList.toggle('active', isThisTrack);

    const numSpan = row.querySelector('.track-index-num');
    const eqBars = row.querySelector('.now-playing-bars');

    if (numSpan && eqBars) {
      if (isThisTrack) {
        numSpan.style.display = 'none';
        eqBars.style.display = 'flex';
        eqBars.querySelectorAll('.playing-bar').forEach(b => {
          b.style.animationPlayState = isPlaying ? 'running' : 'paused';
        });
      } else {
        numSpan.style.display = 'block';
        eqBars.style.display = 'none';
      }
    }
  });
}

// Слушатель глобального удаления трека из фонотеки
window.addEventListener('track:deleted', (e) => {
  const trackId = e.detail?.trackId;
  if (!trackId) return;

  // 1. Анимация плавного удаления строк трека
  document.querySelectorAll(`.track-row[data-id="${trackId}"]`).forEach(row => {
    row.style.transition = 'all 0.25s ease';
    row.style.opacity = '0';
    row.style.transform = 'translateX(-20px)';
    setTimeout(() => {
      row.remove();
    }, 250);
  });

  // 2. Обновление локального массива треков
  if (Array.isArray(state.tracks)) {
    updateState('tracks', state.tracks.filter(t => t.id !== trackId));
  }

  // 3. Обновление счетчиков коллекции
  if (!state.activePlaylist) {
    totalTracksCount = Math.max(0, totalTracksCount - 1);
    const titleEl = document.getElementById('tracksViewTitle');
    if (titleEl && !state.searchQuery) {
      titleEl.textContent = `Коллекция треков (${totalTracksCount.toLocaleString('ru-RU')} треков)`;
    }
  } else if (state.activePlaylist) {
    if (Array.isArray(state.activePlaylist.tracks)) {
      state.activePlaylist.tracks = state.activePlaylist.tracks.filter(t => t.id !== trackId);
      const titleEl = document.getElementById('tracksViewTitle');
      if (titleEl) {
        titleEl.innerHTML = `${icon('folder', { size: 18 })} ${escapeHtml(state.activePlaylist.title)} <span style="font-size: 0.88rem; font-weight: 500; color: var(--text-secondary); margin-left: 10px;">${state.activePlaylist.tracks.length} треков</span>`;
      }
    }
  }
});

// Слушатель исключения трека из текущего плейлиста
window.addEventListener('track:removed-from-playlist', (e) => {
  const trackId = e.detail?.trackId;
  if (!trackId) return;

  document.querySelectorAll(`#tracksTableContainer .track-row[data-id="${trackId}"]`).forEach(row => {
    row.style.transition = 'all 0.25s ease';
    row.style.opacity = '0';
    row.style.transform = 'translateX(-20px)';
    setTimeout(() => {
      row.remove();
    }, 250);
  });

  if (state.activePlaylist && Array.isArray(state.activePlaylist.tracks)) {
    state.activePlaylist.tracks = state.activePlaylist.tracks.filter(t => t.id !== trackId);
    updateState('tracks', state.activePlaylist.tracks);
    const titleEl = document.getElementById('tracksViewTitle');
    if (titleEl) {
      titleEl.innerHTML = `${icon('folder', { size: 18 })} ${escapeHtml(state.activePlaylist.title)} <span style="font-size: 0.88rem; font-weight: 500; color: var(--text-secondary); margin-left: 10px;">${state.activePlaylist.tracks.length} треков</span>`;
    }
  }
});

window.addEventListener('library:reload', () => {
  loadLibraryTracks();
});


