/**
 * Модуль «Поток» (Sentinel Vibe Stream 2.0).
 * Персональный адаптивный поток с ранжированием по настроению, темпу,
 * сессионным кулдауном и управляемой частотой открытий новых треков.
 */

import { state, updateState, onStateChange } from './state.js';
import { fetchStreamNext, fetchStreamCapability, fetchAnalyticsStatus, startAnalytics, sendReaction } from './api.js';
import { API_BASE } from './config.js';
import { playTrack, togglePlay } from './player.js';
import { icon } from './icons.js';
import { toggleLikeAction, toggleDislikeAction } from './ui/reactions.js';
import { showToast, escapeHtml } from './ui/toast.js';

let isLoadingStreamTrack = false;
let analyticsPollingTimer = null;
let streamCapability = null;

export async function checkStreamCapability() {
  try {
    const data = await fetchStreamCapability();
    if (data) {
      streamCapability = data;
      const warningEl = document.getElementById('streamPluginWarning');
      if (warningEl) {
        warningEl.style.display = !data.has_ingestion_plugins ? 'flex' : 'none';
      }
    }
  } catch (err) {
    console.warn('Не удалось проверить возможности Потока:', err);
  }
}

export function initStream() {
  // Слушаем запрос следующего трека от плеера
  window.addEventListener('stream:request-next', () => {
    loadNextStreamTrack();
  });

  // Синхронизация состояния воспроизведения с анимацией сферы Потока
  onStateChange('isPlaying', (isPlaying) => {
    updateOrbUI(isPlaying);
    updateStreamStatusUI();
  });

  onStateChange('currentTrack', () => {
    updateStreamStatusUI();
  });

  onStateChange('isStreamActive', (isActive) => {
    updateStreamStatusUI();
    updateOrbUI(state.isPlaying);
    updateStreamButtonsUI(isActive);
  });

  onStateChange('currentView', (view) => {
    if (view === 'stream') {
      updateStreamStatusUI();
      updateOrbUI(state.isPlaying);
      checkStreamCapability();
    }
  });

  // Кнопка запуска Потока на основе текущего трека
  const btnStartStreamFromTrack = document.getElementById('btnStartStreamFromTrack');
  if (btnStartStreamFromTrack) {
    btnStartStreamFromTrack.addEventListener('click', (e) => {
      e.stopPropagation();
      if (state.currentTrack) {
        startStreamFromCurrentTrack(state.currentTrack);
      } else {
        startStream();
      }
    });
  }

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

  // Первичная синхронизация состояния интерфейса
  updateStreamStatusUI();
  checkStreamCapability();
}

/**
 * Запуск или пауза Потока по клику на сферу.
 */
export async function handleOrbClick() {
  if (!state.isStreamActive) {
    if (state.currentTrack) {
      await startStreamFromCurrentTrack(state.currentTrack);
    } else {
      await startStream();
    }
  } else {
    togglePlay();
  }
}

/**
 * Запускает Поток на основе уже играющего трека (Seed Track).
 * Не прерывает воспроизведение текущего трека, но активирует алгоритмический поток
 * для всех последующих рекомендаций и обновляет визуальный статус.
 */
export async function startStreamFromCurrentTrack(track) {
  if (!track) {
    await startStream();
    return;
  }

  // 1. Активируем режим Потока
  updateState('isStreamActive', true);
  updateStreamButtonsUI(true);

  // 2. Добавляем трек в недавние ID потока, чтобы избежать повторов
  if (track.id > 0) {
    const recents = Array.isArray(state.recentStreamIds) ? [...state.recentStreamIds] : [];
    if (!recents.includes(track.id)) {
      recents.push(track.id);
      updateState('recentStreamIds', recents.slice(-50));
    }
  }

  // 3. Если трек стоял на паузе — запускаем
  if (!state.isPlaying) {
    togglePlay();
  }

  // 4. Мгновенно синхронизируем интерфейс
  updateStreamStatusUI();
  updateOrbUI(true);

  showToast(`✨ Поток запущен на основе «${track.artist} — ${track.title}»`, 'sparkles');
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
  const isStreamPlaying = isPlaying && !!state.isStreamActive;

  const streamStage = document.getElementById('streamOrbStage');
  const streamLargeIcon = document.getElementById('streamOrbLargeIcon');
  const streamOrbLargeBtn = document.getElementById('streamOrbLargeBtn');
  const streamEq = document.getElementById('streamNpEq');

  if (streamStage) {
    streamStage.classList.toggle('playing', isStreamPlaying);
  }

  if (streamLargeIcon) {
    streamLargeIcon.innerHTML = isStreamPlaying ? icon('pause', { size: 38 }) : icon('play', { size: 38 });
  }

  if (streamOrbLargeBtn) {
    if (isStreamPlaying) {
      streamOrbLargeBtn.title = 'Приостановить Поток (Пробел)';
    } else if (state.currentTrack) {
      streamOrbLargeBtn.title = `Запустить Поток на основе «${state.currentTrack.title}»`;
    } else {
      streamOrbLargeBtn.title = 'Включить Поток (Пробел)';
    }
  }

  if (streamEq) {
    streamEq.classList.toggle('active', isStreamPlaying);
  }
}

export function updateStreamStatusUI() {
  const isStream = !!state.isStreamActive;
  const track = state.currentTrack;

  const headerBadge = document.querySelector('.stream-header-badge');
  const badgeText = headerBadge ? headerBadge.querySelector('.stream-badge-text') : null;
  const badgePulse = headerBadge ? headerBadge.querySelector('.stream-badge-pulse') : null;
  const heroSubtitle = document.getElementById('streamHeroSubtitle');
  const seedWrapper = document.getElementById('streamSeedWrapper');
  const seedBtnLabel = document.getElementById('btnStartStreamFromTrackLabel');
  const nowPlayingCard = document.getElementById('streamNowPlaying');

  const npTitle = document.getElementById('streamNpTitle');
  const npArtist = document.getElementById('streamNpArtist');
  const npCover = document.getElementById('streamNpCover');
  const npPlaceholder = document.getElementById('streamNpPlaceholder');
  const npActions = document.querySelector('.stream-np-actions');
  const btnLike = document.getElementById('btnStreamLike');

  if (isStream) {
    // === РЕЖИМ: АКТИВНЫЙ ПОТОК ===
    if (headerBadge) {
      headerBadge.classList.remove('stream-idle');
    }
    if (badgeText) badgeText.textContent = 'УМНЫЙ AI ПОТОК АКТИВЕН';
    if (badgePulse) badgePulse.style.display = 'inline-block';

    if (seedWrapper) seedWrapper.style.display = 'none';
    if (nowPlayingCard) nowPlayingCard.style.display = 'flex';
    if (npActions) npActions.style.display = 'flex';

    if (track) {
      const isDemo = !!(track.is_preview || (track.id < 0) || (track.preview_url && (!track.file_path || track.file_path.startsWith('http'))));
      if (npTitle) {
        if (isDemo) {
          npTitle.innerHTML = `${escapeHtml(track.title)} <span class="stream-preview-badge" title="30-секундное демо Deezer">Демо 30с</span>`;
        } else {
          npTitle.textContent = track.title;
        }
      }
      if (npArtist) npArtist.textContent = track.artist;
      if (heroSubtitle) {
        const demoNote = isDemo ? ' [30с Демо]' : '';
        const discoveryReason = track.discovery_reason ? ` • ${track.discovery_reason}` : '';
        heroSubtitle.textContent = `В Потоке: ${track.artist} — ${track.title}${demoNote}${discoveryReason}`;
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
  } else {
    // === РЕЖИМ: ОБЫЧНОЕ ВОСПРОИЗВЕДЕНИЕ ИЛИ ОЖИДАНИЕ ===
    if (headerBadge) {
      headerBadge.classList.add('stream-idle');
    }
    if (badgeText) badgeText.textContent = 'УМНЫЙ AI ПОТОК (В ОЖИДАНИИ)';
    if (badgePulse) badgePulse.style.display = 'none';

    // В режиме ожидания скрываем карточку воспроизведения Потока, чтобы не путать с запущенным Потоком!
    if (nowPlayingCard) nowPlayingCard.style.display = 'none';

    if (track) {
      // Обычный трек из медиатеки
      if (heroSubtitle) {
        heroSubtitle.textContent = `Поток не запущен • В фонотеке играет: ${track.artist} — ${track.title}`;
      }
      if (seedWrapper) seedWrapper.style.display = 'flex';
      const seedBtn = document.getElementById('btnStartStreamFromTrack');
      if (seedBtn) {
        seedBtn.title = `Запустить Поток на основе «${track.artist} — ${track.title}»`;
      }
      if (seedBtnLabel) {
        seedBtnLabel.innerHTML = `Запустить Поток на основе <span class="seed-btn-track-name">«${escapeHtml(track.artist)} — ${escapeHtml(track.title)}»</span>`;
      }
    } else {
      // Ничего не играет
      if (heroSubtitle) {
        heroSubtitle.textContent = 'Музыка подстраивается под ваш ритм, вкусы и реакции в реальном времени';
      }
      if (seedWrapper) seedWrapper.style.display = 'none';
    }
  }
}

// Алиас для обратной совместимости
function updateStreamCardTrackInfo(track) {
  updateStreamStatusUI();
}

function updateStreamButtonsUI(isActive) {
  const sidebarItem = document.getElementById('navItemStream');
  if (sidebarItem) {
    sidebarItem.classList.toggle('active', isActive);
  }
}
