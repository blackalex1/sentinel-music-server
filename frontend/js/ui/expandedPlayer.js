/**
 * Sentinel Music — Контроллер развернутого полноэкранного плеера (Expanded Full Player).
 * Управляет отображением крупной обложки, расширенного таймлайна, метаданных и контролов
 * при клике на миниатюру альбома в левом нижнем углу интерфейса.
 */

import { state, updateState, onStateChange } from '../state.js';
import { getApiBase } from '../config.js';
import {
  togglePlay,
  nextTrack,
  prevTrack,
  seekPercentage,
  setVolume,
  toggleMute,
  toggleShuffle,
  toggleRepeat,
  formatTime,
  toggleLoudnessNormalization
} from '../player.js';
import { sendReaction } from '../api.js';
import { icon } from '../icons.js';
import { showToast } from './toast.js';
import { toggleLyricsOverlay } from '../lyrics.js';
import { toggleQueueDrawer } from '../queue.js';
import { toggleLikeAction, toggleDislikeAction, syncTrackReactionUI } from './reactions.js';
import { toggleEqualizerModal } from './equalizer.js';
import { openTrackVersionModal } from './trackVersions.js';

let isExpandedOpen = false;

export function initExpandedPlayer() {
  const miniCover = document.getElementById('playerTrackCover');
  const btnCollapse = document.getElementById('btnCollapsePlayer');
  const overlay = document.getElementById('expandedPlayerOverlay');

  // Клик на миниатюру обложки в нижнем левом углу раскрывает плеер
  if (miniCover) {
    miniCover.style.cursor = 'pointer';
    miniCover.title = 'Развернуть плеер (клик)';
    miniCover.addEventListener('click', () => {
      toggleExpandedPlayer(true);
    });
  }

  // Кнопка сворачивания
  if (btnCollapse) {
    btnCollapse.addEventListener('click', () => {
      toggleExpandedPlayer(false);
    });
  }

  // Клик вне контейнера на оверлей сворачивает плеер
  if (overlay) {
    overlay.addEventListener('click', (e) => {
      if (e.target === overlay) {
        toggleExpandedPlayer(false);
      }
    });
  }

  // Закрытие по Escape
  window.addEventListener('keydown', (e) => {
    if (e.key === 'Escape' && isExpandedOpen) {
      toggleExpandedPlayer(false);
    }
  });

  // Элементы управления
  const btnPlay = document.getElementById('btnExpandedPlay');
  const btnNext = document.getElementById('btnExpandedNext');
  const btnPrev = document.getElementById('btnExpandedPrev');
  const btnShuffle = document.getElementById('btnExpandedShuffle');
  const btnRepeat = document.getElementById('btnExpandedRepeat');
  const btnLyrics = document.getElementById('btnExpandedLyrics');
  const btnQueue = document.getElementById('btnExpandedQueue');

  if (btnPlay) btnPlay.addEventListener('click', togglePlay);
  if (btnNext) btnNext.addEventListener('click', nextTrack);
  if (btnPrev) btnPrev.addEventListener('click', prevTrack);
  if (btnShuffle) btnShuffle.addEventListener('click', toggleShuffle);
  if (btnRepeat) btnRepeat.addEventListener('click', toggleRepeat);

  if (btnLyrics) {
    btnLyrics.addEventListener('click', (e) => {
      e.stopPropagation();
      toggleExpandedPlayer(false);
      toggleLyricsOverlay(true);
    });
  }

  if (btnQueue) {
    btnQueue.addEventListener('click', (e) => {
      e.stopPropagation();
      toggleExpandedPlayer(false);
      toggleQueueDrawer(true);
    });
  }

  // Замена трека (Не та версия / поиск другой версии)
  const handleReplaceTrack = (e) => {
    e.stopPropagation();
    if (!state.currentTrack) {
      showToast('Сначала включите трек для замены', 'alert');
      return;
    }
    openTrackVersionModal(state.currentTrack);
  };

  const btnReplace = document.getElementById('btnExpandedReplace');
  const btnReplaceHeader = document.getElementById('btnExpandedReplaceHeader');
  if (btnReplace) btnReplace.addEventListener('click', handleReplaceTrack);
  if (btnReplaceHeader) btnReplaceHeader.addEventListener('click', handleReplaceTrack);

  // Таймлайн
  const timelineBar = document.getElementById('expandedTimelineBar');
  if (timelineBar) {
    timelineBar.addEventListener('click', (e) => {
      const rect = timelineBar.getBoundingClientRect();
      const pct = (e.clientX - rect.left) / rect.width;
      seekPercentage(pct);
    });
  }

  // Громкость
  const volumeBar = document.getElementById('expandedVolumeBar');
  const btnVolumeIcon = document.getElementById('btnExpandedVolumeIcon');

  if (volumeBar) {
    volumeBar.addEventListener('click', (e) => {
      const rect = volumeBar.getBoundingClientRect();
      const pct = (e.clientX - rect.left) / rect.width;
      setVolume(pct);
    });
  }

  if (btnVolumeIcon) {
    btnVolumeIcon.addEventListener('click', toggleMute);
  }

  const btnLoudness = document.getElementById('btnExpandedLoudnessNorm');
  if (btnLoudness) {
    btnLoudness.addEventListener('click', toggleLoudnessNormalization);
  }

  const btnEq = document.getElementById('btnExpandedEqualizer');
  if (btnEq) {
    btnEq.addEventListener('click', toggleEqualizerModal);
  }

  // Лайк / Дизлайк со сквозной синхронизацией всех компонентов
  const btnLike = document.getElementById('btnExpandedLike');
  const btnDislike = document.getElementById('btnExpandedDislike');

  if (btnLike) {
    btnLike.addEventListener('click', () => {
      if (!state.currentTrack) return;
      toggleLikeAction(state.currentTrack.id);
    });
  }

  if (btnDislike) {
    btnDislike.addEventListener('click', async () => {
      if (!state.currentTrack) return;
      await toggleDislikeAction(state.currentTrack.id);
      nextTrack();
    });
  }

  // Реактивные слушатели состояния
  onStateChange('currentTrack', (track) => {
    updateExpandedTrackInfo(track);
  });

  onStateChange('isPlaying', (isPlaying) => {
    updateExpandedPlayButton(isPlaying);
  });

  onStateChange('currentTime', (curTime) => {
    updateExpandedTimeline(curTime, state.duration);
  });

  onStateChange('duration', (dur) => {
    updateExpandedTimeline(state.currentTime, dur);
  });

  onStateChange('volume', (vol) => {
    updateExpandedVolume(vol);
  });

  onStateChange('isShuffle', (isShuffle) => {
    if (btnShuffle) btnShuffle.classList.toggle('active', isShuffle);
  });

  onStateChange('repeatMode', (repeatMode) => {
    if (btnRepeat) {
      btnRepeat.classList.toggle('active', repeatMode !== 'off');
      btnRepeat.innerHTML = repeatMode === 'one' ? icon('repeatOne', { size: 20 }) : icon('repeat', { size: 20 });
    }
  });

  // Инициализация текущим состоянием
  if (state.currentTrack) {
    updateExpandedTrackInfo(state.currentTrack);
  }
}

/**
 * Открытие/закрытие развернутого плеера.
 */
export function toggleExpandedPlayer(forceOpen = null) {
  const overlay = document.getElementById('expandedPlayerOverlay');
  if (!overlay) return;

  isExpandedOpen = forceOpen !== null ? forceOpen : !isExpandedOpen;
  overlay.classList.toggle('active', isExpandedOpen);

  if (isExpandedOpen) {
    toggleLyricsOverlay(false);
    toggleQueueDrawer(false);

    if (state.currentTrack) {
      updateExpandedTrackInfo(state.currentTrack);
      updateExpandedPlayButton(state.isPlaying);
      updateExpandedTimeline(state.currentTime, state.duration);
      updateExpandedVolume(state.volume);
    }
  }
}

function updateExpandedTrackInfo(track) {
  if (!track) return;

  const titleEl = document.getElementById('expandedTitle');
  const artistEl = document.getElementById('expandedArtist');
  const albumEl = document.getElementById('expandedAlbum');
  const coverImg = document.getElementById('expandedCoverImg');
  const placeholder = document.getElementById('expandedCoverPlaceholder');
  const backdropCover = document.getElementById('expandedBackdropCover');
  const badgesRow = document.getElementById('expandedBadgesRow');

  if (titleEl) titleEl.textContent = track.title || 'Трек не выбран';
  if (artistEl) artistEl.textContent = track.artist || 'Sentinel Music';
  if (albumEl) albumEl.textContent = track.album ? `Альбом: ${track.album}` : '';

  const coverUrl = track.cover_url || (track.id && typeof track.id === 'number' && track.id > 0 ? `${getApiBase()}/api/covers/${track.id}` : '');

  if (coverImg) {
    if (coverUrl) {
      coverImg.src = coverUrl;
      coverImg.style.display = 'block';
      if (placeholder) placeholder.style.display = 'none';
    } else {
      coverImg.style.display = 'none';
      if (placeholder) placeholder.style.display = 'flex';
    }
  }

  if (backdropCover) {
    if (coverUrl) {
      backdropCover.src = coverUrl;
      backdropCover.style.display = 'block';
    } else {
      backdropCover.style.display = 'none';
    }
  }

  // Обновляем бейджи качества
  if (badgesRow) {
    const fmt = (track.format || track.audio_format || 'mp3').toLowerCase();
    const isFlac = fmt === 'flac' || fmt === 'wav';
    const badgeClass = isFlac ? 'badge-flac' : 'badge-mp3';
    const bitrateText = isFlac ? 'FLAC • Lossless' : `${track.bitrate || 320} kbps • ${fmt.toUpperCase()}`;
    const yearText = track.year ? `<span class="hybrid-badge badge-neutral">${track.year}</span>` : '';
    const loudnessText = typeof track.loudness_lufs === 'number'
      ? `<span class="hybrid-badge badge-neutral" title="Громкость EBU R128: ${track.loudness_lufs} LUFS (Поправка: ${track.gain_db >= 0 ? '+' : ''}${track.gain_db} дБ)">${track.loudness_lufs} LUFS</span>`
      : '';

    badgesRow.innerHTML = `
      <span class="hybrid-badge ${badgeClass}">${bitrateText}</span>
      ${yearText}
      ${loudnessText}
    `;
  }

  updateExpandedReactions(track);
}

function updateExpandedReactions(track) {
  const btnLike = document.getElementById('btnExpandedLike');
  if (btnLike && track) {
    btnLike.classList.toggle('liked', !!track.is_liked);
    btnLike.innerHTML = track.is_liked
      ? icon('heartFilled', { size: 22, className: 'icon-liked' })
      : icon('heart', { size: 22 });
  }
}

function updateExpandedPlayButton(isPlaying) {
  const btnPlay = document.getElementById('btnExpandedPlay');
  if (btnPlay) {
    btnPlay.innerHTML = isPlaying ? icon('pause', { size: 26 }) : icon('play', { size: 26 });
    btnPlay.title = isPlaying ? 'Пауза (Пробел)' : 'Воспроизведение (Пробел)';
  }
}

function updateExpandedTimeline(currentTime, duration) {
  const curEl = document.getElementById('expandedTimeCurrent');
  const totalEl = document.getElementById('expandedTimeTotal');
  const fillEl = document.getElementById('expandedTimelineFill');

  if (curEl) curEl.textContent = formatTime(currentTime);
  if (totalEl && duration) totalEl.textContent = formatTime(duration);

  if (fillEl && duration) {
    const pct = Math.max(0, Math.min(100, (currentTime / duration) * 100));
    fillEl.style.width = `${pct}%`;
  }
}

function updateExpandedVolume(vol) {
  const fillEl = document.getElementById('expandedVolumeFill');
  if (fillEl) fillEl.style.width = `${vol * 100}%`;
}
