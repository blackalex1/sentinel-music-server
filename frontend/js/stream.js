/**
 * Модуль «Поток» (Sentinel Vibe Stream 2.0).
 * Персональный адаптивный поток с ранжированием по настроению, темпу,
 * сессионным кулдауном и управляемой частотой открытий новых треков.
 */

import { state, updateState, onStateChange } from './state.js';
import { fetchStreamNext, fetchAnalyticsStatus, startAnalytics, sendReaction } from './api.js';
import { API_BASE } from './config.js';
import { playTrack, togglePlay } from './player.js';
import { icon } from './icons.js';
import { toggleLikeAction, toggleDislikeAction } from './ui/reactions.js';

let isLoadingStreamTrack = false;
let analyticsPollingTimer = null;

export function initStream() {
  // Слушаем запрос следующего трека от плеера
  window.addEventListener('stream:request-next', () => {
    loadNextStreamTrack();
  });

  // Синхронизация состояния воспроизведения с анимацией сферы Потока
  onStateChange('isPlaying', (isPlaying) => {
    updateOrbUI(isPlaying);
  });

  onStateChange('currentTrack', (track) => {
    updateStreamCardTrackInfo(track);
  });

  // Привязка клика по сфере Потока
  const orbContainerLarge = document.getElementById('streamOrbContainerLarge');
  const streamOrbLargeBtn = document.getElementById('streamOrbLargeBtn');

  if (orbContainerLarge) {
    orbContainerLarge.addEventListener('click', () => {
      handleOrbClick();
    });
  }

  if (streamOrbLargeBtn) {
    streamOrbLargeBtn.addEventListener('click', (e) => {
      e.stopPropagation();
      handleOrbClick();
    });
  }

  // Привязка действий карточки текущего трека в Потоке
  const btnLike = document.getElementById('btnStreamLike');
  const btnDislike = document.getElementById('btnStreamDislike');
  const btnNext = document.getElementById('btnStreamNext');

  if (btnLike) {
    btnLike.addEventListener('click', (e) => {
      e.stopPropagation();
      if (!state.currentTrack) return;
      toggleLikeAction(state.currentTrack.id);
    });
  }

  if (btnDislike) {
    btnDislike.addEventListener('click', async (e) => {
      e.stopPropagation();
      if (!state.currentTrack) return;
      await toggleDislikeAction(state.currentTrack.id);
      loadNextStreamTrack();
    });
  }

  if (btnNext) {
    btnNext.addEventListener('click', (e) => {
      e.stopPropagation();
      loadNextStreamTrack();
    });
  }

  // Привязка чипов настроения
  initMoodChips();

  // Привязка селектора частоты новых треков
  initDiscoveryChips();

  // Инициализация виджета аналитики фонотеки
  initAnalyticsWidget();
}

/**
 * Запуск или пауза Потока по клику на сферу.
 */
export async function handleOrbClick() {
  if (!state.isStreamActive) {
    await startStream();
  } else {
    togglePlay();
  }
}

/**
 * Активирует режим «Поток» и запускает первый трек.
 */
export async function startStream() {
  updateState('isStreamActive', true);
  updateStreamButtonsUI(true);
  await loadNextStreamTrack();
}

/**
 * Останавливает режим «Поток».
 */
export function stopStream() {
  updateState('isStreamActive', false);
  updateStreamButtonsUI(false);
}

/**
 * Переключает активность режима Потока.
 */
export async function toggleStream() {
  if (state.isStreamActive) {
    stopStream();
  } else {
    await startStream();
  }
}

/**
 * Загрузка следующего трека Потока с учетом настроения, недавних треков и частоты открытий.
 */
export async function loadNextStreamTrack() {
  if (isLoadingStreamTrack) return;
  isLoadingStreamTrack = true;

  try {
    const curId = state.currentTrack ? state.currentTrack.id : null;
    const mood = state.streamMood || 'default';
    const discoveryRatio = typeof state.discoveryRatio === 'number' ? state.discoveryRatio : 0.2;
    const recentIds = Array.isArray(state.recentStreamIds) ? state.recentStreamIds : [];
    const consecutiveArtist = state.currentTrack ? state.currentTrack.artist : null;

    // Вычисляем сколько раз подряд играл этот артист
    let consecutiveCount = 1;
    if (state.history && state.history.length > 0 && consecutiveArtist) {
      for (let i = state.history.length - 1; i >= 0; i--) {
        if (state.history[i].artist === consecutiveArtist) {
          consecutiveCount++;
        } else {
          break;
        }
      }
    }

    const track = await fetchStreamNext({
      currentTrackId: curId,
      mood: mood,
      recentIds: recentIds,
      discoveryRatio: discoveryRatio,
      consecutiveArtist: consecutiveArtist,
      consecutiveCount: consecutiveCount
    });

    if (track) {
      playTrack(track, null, true);
    }
  } catch (err) {
    console.warn('Не удалось загрузить следующий трек Потока:', err);
  } finally {
    isLoadingStreamTrack = false;
  }
}

/**
 * Установка фильтра настроения для Потока.
 */
export function setStreamMood(mood) {
  updateState('streamMood', mood);

  // Обновляем визуальный активный чип на всех экранах
  document.querySelectorAll('.mood-chip, .stream-mood-chip').forEach(chip => {
    chip.classList.toggle('active', chip.dataset.mood === mood);
  });

  // Динамически меняем свечение ауры на экране Потока
  const streamContainer = document.getElementById('viewStream');
  if (streamContainer) {
    streamContainer.dataset.mood = mood;
  }

  // Оповещаем UI о смене настроения для фильтрации треков на главной
  window.dispatchEvent(new CustomEvent('stream:mood-changed', { detail: { mood } }));

  // Если Поток уже играет, плавно переключаем на трек в новом настроении
  if (state.isStreamActive) {
    loadNextStreamTrack();
  }
}

function initMoodChips() {
  const chips = document.querySelectorAll('.mood-chip, .stream-mood-chip');
  chips.forEach(chip => {
    chip.addEventListener('click', () => {
      const mood = chip.dataset.mood || 'default';
      setStreamMood(mood);
    });
  });
}

/**
 * Настройка селектора частоты новых треков (Discovery Ratio).
 */
function initDiscoveryChips() {
  const chips = document.querySelectorAll('.discovery-chip, .stream-discovery-chip');
  chips.forEach(chip => {
    chip.addEventListener('click', () => {
      const ratio = parseFloat(chip.dataset.ratio ?? '0.2');
      updateState('discoveryRatio', ratio);

      document.querySelectorAll('.discovery-chip, .stream-discovery-chip').forEach(c => {
        c.classList.toggle('active', parseFloat(c.dataset.ratio) === ratio);
      });

      const label = chip.querySelector('span') ? chip.querySelector('span').textContent.trim() : chip.textContent.trim();
      window.dispatchEvent(new CustomEvent('app:toast', {
        detail: `Частота новых треков: ${label}`
      }));
    });
  });
}

let isPollingAnalytics = false;
let analyticsInterval = null;

/**
 * Инициализация и динамическое обновление виджета психоакустической аналитики в реальном времени.
 */
export async function initAnalyticsWidget() {
  const btnStart = document.getElementById('btnStartAnalytics');
  if (btnStart) {
    btnStart.addEventListener('click', async () => {
      btnStart.disabled = true;
      btnStart.innerHTML = `${icon('loader', { size: 14, className: 'icon-spin' })} Запуск...`;
      try {
        await startAnalytics();
        window.dispatchEvent(new CustomEvent('app:toast', {
          detail: 'Психоакустический анализ фонотеки запущен в фоне'
        }));
        await pollAnalyticsStatus();
      } catch (err) {
        console.error('Ошибка старта аналитики:', err);
      }
    });
  }

  // Мгновенный первый запрос статуса (сам выставит адаптивный интервал)
  await pollAnalyticsStatus();
}

export async function pollAnalyticsStatus() {
  if (isPollingAnalytics) return;
  isPollingAnalytics = true;

  try {
    const data = await fetchAnalyticsStatus();
    if (data) {
      updateAnalyticsUI(data);
      // Если идет фоновый расчет — опрашиваем каждые 2.5с, иначе редко (каждые 30с)
      const nextDelay = data.is_running ? 2500 : 30000;
      if (analyticsInterval) clearInterval(analyticsInterval);
      analyticsInterval = setInterval(() => {
        pollAnalyticsStatus();
      }, nextDelay);
    }
  } catch (e) {
    console.warn('Не удалось обновить статус аналитики:', e);
  } finally {
    isPollingAnalytics = false;
  }
}

function updateAnalyticsUI(data) {
  const statusEl = document.getElementById('analyticsStatusText');
  const moodsEl = document.getElementById('analyticsMoodsText');
  const btnStart = document.getElementById('btnStartAnalytics');
  const progressFill = document.getElementById('analyticsProgressFill');

  if (progressFill) {
    progressFill.style.width = `${data.progress_percent}%`;
  }

  if (statusEl) {
    if (data.is_running) {
      const curr = data.current_track ? ` <span style="color: var(--text-secondary); font-size: 0.8rem; font-weight: normal;">• ${data.current_track}</span>` : '';
      statusEl.innerHTML = `<span class="analytics-live-badge"><span class="pulse-dot"></span> АНАЛИЗ</span> &nbsp; ${data.analyzed_tracks} / ${data.total_tracks} (${data.progress_percent}%)${curr}`;
    } else if (data.unanalyzed_tracks > 0) {
      statusEl.innerHTML = `Размечено: <strong>${data.analyzed_tracks} / ${data.total_tracks}</strong> (${data.progress_percent}%) • Не размечено: ${data.unanalyzed_tracks}`;
    } else {
      statusEl.innerHTML = `${icon('check', { size: 15, className: 'icon-success' })} <strong>Фонотека полностью проанализирована:</strong> ${data.total_tracks} треков (100%)`;
    }
  }

  if (moodsEl && data.moods) {
    moodsEl.innerHTML = `${icon('flame', { size: 14 })} ${data.moods.energy} &nbsp;•&nbsp; ${icon('moon', { size: 14 })} ${data.moods.chill} &nbsp;•&nbsp; ${icon('sun', { size: 14 })} ${data.moods.happy} &nbsp;•&nbsp; ${icon('cloudRain', { size: 14 })} ${data.moods.sad}`;
  }

  if (btnStart) {
    if (data.is_running) {
      btnStart.style.display = 'none';
    } else if (data.unanalyzed_tracks > 0) {
      btnStart.style.display = 'inline-flex';
      btnStart.disabled = false;
      btnStart.innerHTML = `${icon('zap', { size: 14 })} Запустить анализ`;
    } else {
      btnStart.style.display = 'none';
    }
  }
}

function updateOrbUI(isPlaying) {
  const isStreamPlaying = isPlaying && state.isStreamActive;

  const streamStage = document.getElementById('streamOrbStage');
  const streamLargeIcon = document.getElementById('streamOrbLargeIcon');
  const streamEq = document.getElementById('streamNpEq');

  if (streamStage) {
    streamStage.classList.toggle('playing', isStreamPlaying);
  }

  if (streamLargeIcon) {
    streamLargeIcon.innerHTML = isStreamPlaying ? icon('pause', { size: 38 }) : icon('play', { size: 38 });
  }

  if (streamEq) {
    streamEq.classList.toggle('active', isStreamPlaying);
  }
}

function updateStreamCardTrackInfo(track) {
  const npTitle = document.getElementById('streamNpTitle');
  const npArtist = document.getElementById('streamNpArtist');
  const npCover = document.getElementById('streamNpCover');
  const npPlaceholder = document.getElementById('streamNpPlaceholder');
  const btnLike = document.getElementById('btnStreamLike');
  const heroSubtitle = document.getElementById('streamHeroSubtitle');

  if (track) {
    if (npTitle) npTitle.textContent = track.title;
    if (npArtist) npArtist.textContent = track.artist;
    if (heroSubtitle) {
      const discoveryReason = track.discovery_reason ? ` • ${track.discovery_reason}` : '';
      heroSubtitle.textContent = `Сейчас играет: ${track.artist} — ${track.title}${discoveryReason}`;
    }

    const coverUrl = track.cover_url || (track.id ? `${API_BASE}/api/covers/${track.id}` : '');
    if (npCover) {
      if (coverUrl) {
        npCover.src = coverUrl;
        npCover.style.display = 'block';
        if (npPlaceholder) npPlaceholder.style.display = 'none';
      } else {
        npCover.style.display = 'none';
        if (npPlaceholder) npPlaceholder.style.display = 'flex';
      }
    }

    if (btnLike) {
      btnLike.classList.toggle('liked', !!track.is_liked);
      btnLike.innerHTML = track.is_liked ? icon('heartFilled', { size: 18 }) : icon('heart', { size: 18 });
    }
  }
}

function updateStreamButtonsUI(isActive) {
  const sidebarItem = document.getElementById('navItemStream');
  if (sidebarItem) {
    sidebarItem.classList.toggle('active', isActive);
  }
}
