/**
 * Модуль предпрослушивания треков-кандидатов из плагинов (SourceA, SourceAs, SourceC, SourceD).
 * Исключает P2P (p2p) в соответствии с системными требованиями.
 */

import { API_BASE, getAuthToken } from './config.js';
import { icon } from './icons.js';

let previewAudio = null;
let currentPreviewCandidateId = null;
let currentPreviewButton = null;
let currentPreviewCard = null;

// При смене трека в основном плеере останавливаем предпрослушивание
if (typeof window !== 'undefined') {
  window.addEventListener('track:changed', () => {
    stopCandidatePreview();
  });
}

/**
 * Проверяет, поддерживает ли данный кандидат предпрослушивание.
 * Возвращает false для P2P (p2p).
 */
export function isCandidatePreviewSupported(candidate) {
  if (!candidate) return false;
  const src = (candidate.source || '').toLowerCase();
  if (src === 'p2p') return false;
  if (candidate.can_preview === false) return false;
  return true;
}

/**
 * Полная остановка текущего предпрослушивания и возврат UI в исходное состояние.
 */
export function stopCandidatePreview() {
  if (previewAudio) {
    try {
      previewAudio.pause();
      previewAudio.removeAttribute('src');
      previewAudio.load();
    } catch (_) {}
    previewAudio = null;
  }

  if (currentPreviewButton) {
    currentPreviewButton.innerHTML = `${icon('play', { size: 14 })} Слушать`;
    currentPreviewButton.classList.remove('btn-preview-playing', 'btn-preview-loading');
  }

  if (currentPreviewCard) {
    currentPreviewCard.classList.remove('preview-playing');
  }

  currentPreviewCandidateId = null;
  currentPreviewButton = null;
  currentPreviewCard = null;
}

/**
 * Переключает предпрослушивание выбранного кандидата (Play / Pause).
 */
export function toggleCandidatePreview(candidate, buttonEl, cardEl) {
  if (!candidate || !candidate.candidate_id) return;

  // Если этот же кандидат сейчас воспроизводится — ставим на паузу
  if (currentPreviewCandidateId === candidate.candidate_id && previewAudio && !previewAudio.paused) {
    stopCandidatePreview();
    return;
  }

  // Останавливаем предыдущее воспроизведение
  stopCandidatePreview();

  // Приостанавливаем воспроизведение основного плеера приложения
  try {
    const mainAudio = document.getElementById('audioElement');
    if (mainAudio && !mainAudio.paused) {
      mainAudio.pause();
    }
  } catch (_) {}

  const token = getAuthToken();
  const streamUrl = `${API_BASE}/api/tracks/candidates/preview?candidate_id=${encodeURIComponent(candidate.candidate_id)}${token ? `&token=${encodeURIComponent(token)}` : ''}`;

  currentPreviewCandidateId = candidate.candidate_id;
  currentPreviewButton = buttonEl;
  currentPreviewCard = cardEl;

  buttonEl.disabled = false;
  buttonEl.classList.add('btn-preview-loading');
  buttonEl.innerHTML = `${icon('loader', { size: 14, className: 'icon-spin' })} Загрузка...`;

  previewAudio = new Audio();
  previewAudio.src = streamUrl;

  const thisCandId = candidate.candidate_id;

  previewAudio.oncanplay = () => {
    if (currentPreviewCandidateId === thisCandId && previewAudio) {
      previewAudio.play().then(() => {
        if (currentPreviewCandidateId === thisCandId && buttonEl) {
          buttonEl.classList.remove('btn-preview-loading');
          buttonEl.classList.add('btn-preview-playing');
          buttonEl.innerHTML = `${icon('pause', { size: 14 })} Пауза`;
          if (cardEl) cardEl.classList.add('preview-playing');
        }
      }).catch(err => {
        console.warn('[CandidatePreview] Ошибка запуска воспроизведения:', err);
        stopCandidatePreview();
      });
    }
  };

  previewAudio.onerror = (e) => {
    console.warn('[CandidatePreview] Ошибка загрузки аудиопотока:', e);
    stopCandidatePreview();
  };

  previewAudio.onended = () => {
    stopCandidatePreview();
  };

  previewAudio.load();
}
