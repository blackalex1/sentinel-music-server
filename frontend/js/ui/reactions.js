/**
 * Sentinel Music — Единый модуль управления реакциями (лайки и дизлайки).
 * Обеспечивает 100% сквозную реактивную синхронизацию состояния во всех компонентах:
 * - Нижняя панель плеера (#btnPlayerLike, #btnPlayerDislike)
 * - Развернутый полноэкранный плеер (#btnExpandedLike, #btnExpandedDislike)
 * - Интерактивный экран «Поток» (#btnStreamLike, #btnStreamDislike)
 * - Строки таблиц треков (в фонотеке, плейлистах, поиске, недавних)
 * - Элементы очереди воспроизведения
 * - Глобальное состояние state.currentTrack, state.tracks, state.queue, state.history
 */

import { state } from '../state.js';
import { sendReaction } from '../api.js';
import { icon } from '../icons.js';
import { showToast } from './toast.js';

/**
 * Синхронизирует визуальное и внутреннее состояние лайка/дизлайка трека во всем приложении.
 */
export function syncTrackReactionUI(trackId, isLiked, isDisliked = false) {
  if (trackId === null || trackId === undefined) return;
  const tId = Number(trackId);
  const likedBool = Boolean(isLiked);
  const dislikedBool = Boolean(isDisliked);

  // 1. Обновляем текущий играющий трек в глобальном state
  if (state.currentTrack && Number(state.currentTrack.id) === tId) {
    state.currentTrack.is_liked = likedBool;
    state.currentTrack.is_disliked = dislikedBool;
  }

  // 2. Обновляем объекты трека в массивах фонотеки, очереди и истории
  if (Array.isArray(state.tracks)) {
    const t = state.tracks.find(x => Number(x.id) === tId);
    if (t) {
      t.is_liked = likedBool;
      t.is_disliked = dislikedBool;
    }
  }

  if (Array.isArray(state.queue)) {
    state.queue.forEach(x => {
      if (Number(x.id) === tId) {
        x.is_liked = likedBool;
        x.is_disliked = dislikedBool;
      }
    });
  }

  if (Array.isArray(state.history)) {
    state.history.forEach(x => {
      if (Number(x.id) === tId) {
        x.is_liked = likedBool;
        x.is_disliked = dislikedBool;
      }
    });
  }

  // 3. Нижняя панель плеера (Bottom Player Bar)
  if (state.currentTrack && Number(state.currentTrack.id) === tId) {
    const btnPlayerLike = document.getElementById('btnPlayerLike');
    if (btnPlayerLike) {
      btnPlayerLike.classList.toggle('liked', likedBool);
      btnPlayerLike.innerHTML = likedBool
        ? icon('heartFilled', { size: 18, className: 'icon-liked' })
        : icon('heart', { size: 18 });
    }
    const btnPlayerDislike = document.getElementById('btnPlayerDislike');
    if (btnPlayerDislike) {
      btnPlayerDislike.classList.toggle('disliked', dislikedBool);
    }
  }

  // 4. Полноэкранный плеер (Expanded Player)
  if (state.currentTrack && Number(state.currentTrack.id) === tId) {
    const btnExpandedLike = document.getElementById('btnExpandedLike');
    if (btnExpandedLike) {
      btnExpandedLike.classList.toggle('liked', likedBool);
      btnExpandedLike.innerHTML = likedBool
        ? icon('heartFilled', { size: 22, className: 'icon-liked' })
        : icon('heart', { size: 22 });
    }
    const btnExpandedDislike = document.getElementById('btnExpandedDislike');
    if (btnExpandedDislike) {
      btnExpandedDislike.classList.toggle('disliked', dislikedBool);
    }
  }

  // 5. Карточка текущего трека в «Потоке»
  if (state.currentTrack && Number(state.currentTrack.id) === tId) {
    const btnStreamLike = document.getElementById('btnStreamLike');
    if (btnStreamLike) {
      btnStreamLike.classList.toggle('liked', likedBool);
      btnStreamLike.innerHTML = likedBool
        ? icon('heartFilled', { size: 18, className: 'icon-liked' })
        : icon('heart', { size: 18 });
    }
  }

  // 6. Строки в таблицах треков (все совпадения по data-id в DOM)
  const tableButtons = document.querySelectorAll(`tr[data-id="${tId}"] .btn-like, .track-row[data-id="${tId}"] .btn-like, .track-card[data-id="${tId}"] .btn-like`);
  tableButtons.forEach(btn => {
    btn.classList.toggle('liked', likedBool);
    btn.innerHTML = likedBool
      ? icon('heartFilled', { size: 16, className: 'icon-liked' })
      : icon('heart', { size: 16 });
  });

  // 7. Элементы очереди (Queue Drawer)
  const queueButtons = document.querySelectorAll(`.queue-item[data-id="${tId}"] .btn-like`);
  queueButtons.forEach(btn => {
    btn.classList.toggle('liked', likedBool);
    btn.innerHTML = likedBool
      ? icon('heartFilled', { size: 14, className: 'icon-liked' })
      : icon('heart', { size: 14 });
  });

  // 8. Оповещаем подписчиков через шину событий
  window.dispatchEvent(new CustomEvent('track:reaction-updated', {
    detail: { trackId: tId, isLiked: likedBool, isDisliked: dislikedBool }
  }));
}

/**
 * Единый переключатель отметки «Нравится» с мгновенной синхронизацией всех элементов.
 */
export async function toggleLikeAction(trackId) {
  if (trackId === null || trackId === undefined) return null;
  const tId = Number(trackId);

  // Оптимистичное переключение для мгновенного отклика интерфейса
  const currentLiked = (state.currentTrack && Number(state.currentTrack.id) === tId)
    ? Boolean(state.currentTrack.is_liked)
    : Boolean(state.tracks.find(x => Number(x.id) === tId)?.is_liked);

  const optimisticLiked = !currentLiked;
  syncTrackReactionUI(tId, optimisticLiked, false);

  try {
    const res = await sendReaction(tId, true);
    if (res) {
      syncTrackReactionUI(tId, res.is_liked, res.is_disliked);
      if (res.saved_permanent) {
        showToast('Новинка навсегда сохранена в вашу фонотеку!', 'heartFilled');
      } else {
        showToast(res.is_liked ? 'Добавлено в Мою коллекцию' : 'Удалено из Моей коллекции', res.is_liked ? 'heartFilled' : 'heart');
      }
      return res;
    } else {
      // Откатываем в случае ошибки сети
      syncTrackReactionUI(tId, currentLiked, false);
    }
  } catch (err) {
    console.error('Ошибка отправки реакции лайка:', err);
    syncTrackReactionUI(tId, currentLiked, false);
  }
  return null;
}

/**
 * Единый переключатель отметки «Не нравится» с синхронизацией интерфейса.
 */
export async function toggleDislikeAction(trackId) {
  if (trackId === null || trackId === undefined) return null;
  const tId = Number(trackId);

  try {
    const res = await sendReaction(tId, false);
    if (res) {
      syncTrackReactionUI(tId, res.is_liked, res.is_disliked);
      showToast('Меньше такого в Потоке');
      return res;
    }
  } catch (err) {
    console.error('Ошибка отправки реакции дизлайка:', err);
  }
  return null;
}
