/**
 * Модуль предпрослушивания треков-кандидатов из подключенных плагинов и внешних источников.
 * Воспроизводит треки через центральный плеер приложения (player.js), гарантируя:
 * - Единый аудиопоток без наложения звука на треки медиатеки
 * - Отображение названия, исполнителя, обложки и таймлайна в основном плеере
 * - Полный контроль над воспроизведением (пауза, перемотка, громкость, эквалайзер)
 *   даже при закрытии окна поиска
 * - Синхронизацию статуса (Слушать / Пауза) на карточках кандидатов
 */

import { API_BASE, getServerHost, getAuthToken } from './config.js';
import { icon } from './icons.js';
import { state } from './state.js';
import { playTrack, togglePlay, pauseTrack, resumeTrack } from './player.js';

let currentPreviewCandidateId = null;
let currentPreviewButton = null;
let currentPreviewCard = null;

/**
 * Проверяет, поддерживает ли данный кандидат предпрослушивание.
 * @param {Object} candidate
 * @returns {boolean}
 */
export function isCandidatePreviewSupported(candidate) {
  if (!candidate) return false;
  if (candidate.can_preview === false) return false;
  return Boolean(candidate.candidate_id || candidate.id);
}

/**
 * Формирует потоковый URL предпрослушивания трека-кандидата.
 * @param {Object} candidate
 * @returns {string}
 */
export function getCandidateStreamUrl(candidate) {
  if (!candidate) return '';
  const candId = candidate.candidate_id || candidate.id;
  if (!candId) return '';
  const token = getAuthToken();
  const base = (typeof getServerHost === 'function' ? getServerHost() : null) || API_BASE;
  return `${base}/api/tracks/candidates/preview?candidate_id=${encodeURIComponent(candId)}${token ? `&token=${encodeURIComponent(token)}` : ''}`;
}

/**
 * Парсит длительность кандидата (в секундах или строке "MM:SS").
 * @param {number|string} dur
 * @returns {number}
 */
export function parseCandidateDuration(dur) {
  if (typeof dur === 'number' && !isNaN(dur) && dur > 0) return dur;
  if (typeof dur === 'string') {
    const trimmed = dur.trim();
    if (trimmed.includes(':')) {
      const parts = trimmed.split(':').map((p) => parseFloat(p));
      if (parts.length === 2 && !isNaN(parts[0]) && !isNaN(parts[1])) {
        return parts[0] * 60 + parts[1];
      }
      if (parts.length === 3 && !isNaN(parts[0]) && !isNaN(parts[1]) && !isNaN(parts[2])) {
        return parts[0] * 3600 + parts[1] * 60 + parts[2];
      }
    }
    const val = parseFloat(trimmed);
    if (!isNaN(val) && val > 0) return val;
  }
  return 0;
}

/**
 * Преобразует кандидата от внешнего источника в стандартную модель трека Sentinel Music.
 * @param {Object} candidate
 * @returns {Object|null}
 */
export function candidateToTrack(candidate) {
  if (!candidate) return null;
  const candId = candidate.candidate_id || candidate.id;
  const streamUrl = getCandidateStreamUrl(candidate);
  const durSec = parseCandidateDuration(candidate.duration);

  return {
    id: `candidate_${candId}`,
    candidate_id: candId,
    title: candidate.title || 'Без названия',
    artist: candidate.artist || 'Неизвестный исполнитель',
    album: candidate.album || candidate.source_name || (candidate.source ? `Источник: ${candidate.source}` : 'Онлайн поиск'),
    duration: durSec || null,
    cover_url: candidate.cover_url || null,
    preview_url: streamUrl,
    file_path: streamUrl,
    format: candidate.format || 'mp3',
    bitrate: candidate.bitrate || 320,
    is_preview: true,
    is_candidate: true,
    can_preview: candidate.can_preview !== false,
    source: candidate.source || null,
    source_name: candidate.source_name || null
  };
}

/**
 * Проверяет, является ли кандидат текущим активным треком в плеере.
 * @param {Object} candidate
 * @returns {boolean}
 */
export function isCandidateActive(candidate) {
  if (!candidate || !state.currentTrack) return false;
  const candId = candidate.candidate_id || candidate.id;
  if (!candId) return false;
  return state.currentTrack.candidate_id === candId || state.currentTrack.id === `candidate_${candId}`;
}

/**
 * Проверяет, воспроизводится ли данный кандидат прямо сейчас в основном плеере.
 * @param {Object} candidate
 * @returns {boolean}
 */
export function isCandidatePlaying(candidate) {
  return isCandidateActive(candidate) && Boolean(state.isPlaying);
}

/**
 * Синхронизирует состояние всех кнопок предпрослушивания в DOM с текущим состоянием плеера.
 */
export function syncAllCandidateButtonsUI() {
  const currentCand = state.currentTrack;
  const currentCandId = currentCand?.candidate_id || (currentCand?.is_candidate ? String(currentCand.id).replace(/^candidate_/, '') : null);
  const isPlaying = Boolean(state.isPlaying) && Boolean(currentCandId);

  // Обновляем все кнопки предпрослушивания в интерфейсе
  const buttons = document.querySelectorAll('.hybrid-preview-btn, .candidate-preview-btn, .cand-btn-preview');
  buttons.forEach((btn) => {
    const candId = btn.dataset.candidateId;
    const card = btn.closest('.hybrid-candidate-card, .candidate-card, .version-card');
    const isThisCandidate = candId && candId === currentCandId;

    btn.classList.remove('btn-preview-loading');
    if (isThisCandidate && isPlaying) {
      btn.classList.add('btn-preview-playing');
      const labelSpan = btn.querySelector('span');
      if (labelSpan) {
        labelSpan.textContent = 'Пауза';
      } else {
        btn.innerHTML = `${icon('pause', { size: 14 })} Пауза`;
      }
      if (card) card.classList.add('preview-playing');
    } else {
      btn.classList.remove('btn-preview-playing');
      const labelSpan = btn.querySelector('span');
      if (labelSpan) {
        labelSpan.textContent = 'Слушать';
      } else {
        btn.innerHTML = `${icon('play', { size: 14 })} Слушать`;
      }
      if (card && (!isThisCandidate || !isPlaying)) {
        card.classList.remove('preview-playing');
      }
    }
  });

  // Также обновляем запомненную кнопку (на случай если data-candidate-id не была прописана в разметке)
  if (currentPreviewButton && (!currentPreviewButton.dataset.candidateId || currentPreviewButton.dataset.candidateId === currentCandId)) {
    if (isPlaying) {
      currentPreviewButton.classList.remove('btn-preview-loading');
      currentPreviewButton.classList.add('btn-preview-playing');
      const labelSpan = currentPreviewButton.querySelector('span');
      if (labelSpan) {
        labelSpan.textContent = 'Пауза';
      } else {
        currentPreviewButton.innerHTML = `${icon('pause', { size: 14 })} Пауза`;
      }
      if (currentPreviewCard) currentPreviewCard.classList.add('preview-playing');
    } else {
      currentPreviewButton.classList.remove('btn-preview-loading', 'btn-preview-playing');
      const labelSpan = currentPreviewButton.querySelector('span');
      if (labelSpan) {
        labelSpan.textContent = 'Слушать';
      } else {
        currentPreviewButton.innerHTML = `${icon('play', { size: 14 })} Слушать`;
      }
      if (currentPreviewCard) currentPreviewCard.classList.remove('preview-playing');
    }
  }
}

/**
 * Остановка или очистка предпрослушивания.
 * @param {boolean} [forcePause=false] - Приостановить ли воспроизведение в плеере
 */
export function stopCandidatePreview(forcePause = false) {
  if (forcePause && state.currentTrack && (state.currentTrack.is_preview || state.currentTrack.is_candidate)) {
    pauseTrack();
  }

  currentPreviewCandidateId = null;
  currentPreviewButton = null;
  currentPreviewCard = null;

  syncAllCandidateButtonsUI();
}

/**
 * Переключает предпрослушивание выбранного кандидата в центральном плеере (Play / Pause).
 * @param {Object} candidate
 * @param {HTMLElement} [buttonEl]
 * @param {HTMLElement} [cardEl]
 */
export function toggleCandidatePreview(candidate, buttonEl = null, cardEl = null) {
  if (!candidate) return;
  const candId = candidate.candidate_id || candidate.id;
  if (!candId) return;

  // Если этот же кандидат уже в плеере — просто переключаем воспроизведение (Play / Pause)
  if (isCandidateActive(candidate)) {
    togglePlay();
    return;
  }

  // Запоминаем текущие элементы для UI
  currentPreviewCandidateId = candId;
  currentPreviewButton = buttonEl;
  currentPreviewCard = cardEl;

  if (buttonEl) {
    buttonEl.disabled = false;
    buttonEl.classList.remove('btn-preview-playing');
    buttonEl.classList.add('btn-preview-loading');
    const labelSpan = buttonEl.querySelector('span');
    if (labelSpan) {
      labelSpan.textContent = 'Загрузка...';
    } else {
      buttonEl.innerHTML = `${icon('loader', { size: 14, className: 'icon-spin' })} Загрузка...`;
    }
  }

  // Преобразуем кандидата в модель трека Sentinel и запускаем в основном плеере
  const previewTrack = candidateToTrack(candidate);
  playTrack(previewTrack, null, false, true, 0);
}

// Подписываемся на события жизненного цикла плеера для синхронизации UI
if (typeof window !== 'undefined') {
  window.addEventListener('track:changed', () => {
    syncAllCandidateButtonsUI();
  });
  window.addEventListener('playback:state', () => {
    syncAllCandidateButtonsUI();
  });
  window.addEventListener('playback:play', () => {
    syncAllCandidateButtonsUI();
  });
  window.addEventListener('playback:pause', () => {
    syncAllCandidateButtonsUI();
  });
}
