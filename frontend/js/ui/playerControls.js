/**
 * Модуль элементов управления плеером и профилем пользователя.
 */

import { state, updateState } from '../state.js';
import {
  playTrack,
  togglePlay,
  nextTrack,
  prevTrack,
  seekPercentage,
  setVolume,
  toggleMute,
  toggleShuffle,
  toggleRepeat,
  playShuffleTracks,
  toggleLoudnessNormalization
} from '../player.js';
import { sendReaction, apiLogout } from '../api.js';
import { clearAuthToken } from '../config.js';
import { showAuthModal } from './modals.js';
import { showToast } from './toast.js';
import { showConfirm } from './notifications.js';
import { icon } from '../icons.js';
import { getMainMoodTracks, getCurrentMainMood, getCurrentLibraryMood } from './trackList.js';
import { toggleLikeAction, toggleDislikeAction, syncTrackReactionUI } from './reactions.js';
import { toggleEqualizerModal } from './equalizer.js';
import { openTrackVersionModal } from './trackVersions.js';

export function setupPlayerControls() {
  const btnPlay = document.getElementById('ctrlPlayBtn');
  const btnNext = document.getElementById('ctrlNextBtn');
  const btnPrev = document.getElementById('ctrlPrevBtn');
  const btnShuffle = document.getElementById('btnShuffle');
  const btnRepeat = document.getElementById('btnRepeat');
  const timelineBar = document.getElementById('timelineBar');
  const volumeSlider = document.getElementById('volumeSlider');
  const btnVolumeIcon = document.getElementById('btnVolumeIcon');
  const btnLoudnessNorm = document.getElementById('btnLoudnessNorm');
  const btnPlayerEqualizer = document.getElementById('btnPlayerEqualizer');

  if (btnPlay) btnPlay.addEventListener('click', togglePlay);
  if (btnNext) btnNext.addEventListener('click', nextTrack);
  if (btnPrev) btnPrev.addEventListener('click', prevTrack);
  if (btnShuffle) btnShuffle.addEventListener('click', toggleShuffle);
  if (btnRepeat) btnRepeat.addEventListener('click', toggleRepeat);
  if (btnLoudnessNorm) btnLoudnessNorm.addEventListener('click', toggleLoudnessNormalization);
  if (btnPlayerEqualizer) btnPlayerEqualizer.addEventListener('click', toggleEqualizerModal);

  if (timelineBar) {
    timelineBar.addEventListener('click', (e) => {
      const rect = timelineBar.getBoundingClientRect();
      const pct = (e.clientX - rect.left) / rect.width;
      seekPercentage(pct);
    });
  }

  if (volumeSlider) {
    volumeSlider.addEventListener('click', (e) => {
      const rect = volumeSlider.getBoundingClientRect();
      const pct = (e.clientX - rect.left) / rect.width;
      setVolume(pct);
    });
  }

  if (btnVolumeIcon) {
    btnVolumeIcon.addEventListener('click', toggleMute);
  }

  // Лайк / Дизлайк в плеере со сквозной синхронизацией
  const btnLike = document.getElementById('btnPlayerLike');
  const btnDislike = document.getElementById('btnPlayerDislike');

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

  const btnReplace = document.getElementById('btnPlayerReplace');
  if (btnReplace) {
    btnReplace.addEventListener('click', () => {
      if (!state.currentTrack) {
        showToast('Сначала включите трек для замены', 'alert');
        return;
      }
      openTrackVersionModal(state.currentTrack);
    });
  }

  // Кнопки управления шапки коллекции треков
  const btnPlayAll = document.getElementById('btnPlayAllTracks');
  const btnShuffleAll = document.getElementById('btnShuffleAllTracks');

  if (btnPlayAll) {
    btnPlayAll.addEventListener('click', () => {
      if (state.tracks && state.tracks.length > 0) {
        playTrack(state.tracks[0], state.tracks, false);
      }
    });
  }

  if (btnShuffleAll) {
    btnShuffleAll.addEventListener('click', () => {
      const mood = getCurrentLibraryMood();
      playShuffleTracks(mood && mood !== 'all' ? mood : null);
    });
  }

  // Кнопки управления шапки подборки треков на Главной
  const btnPlayAllMain = document.getElementById('btnPlayAllMainTracks');
  const btnShuffleMain = document.getElementById('btnShuffleMainTracks');

  if (btnPlayAllMain) {
    btnPlayAllMain.addEventListener('click', () => {
      const tracks = getMainMoodTracks();
      if (tracks && tracks.length > 0) {
        playTrack(tracks[0], tracks, false);
      }
    });
  }

  if (btnShuffleMain) {
    btnShuffleMain.addEventListener('click', () => {
      const mood = getCurrentMainMood();
      playShuffleTracks(mood !== 'default' && mood !== 'all' ? mood : null);
    });
  }
}

export function updatePlayerReactionsUI(track) {
  if (!track) return;
  syncTrackReactionUI(track.id, !!track.is_liked, !!track.is_disliked);
}

export function setupUserPill() {
  const pill = document.getElementById('userBadge');
  if (!pill) return;

  pill.addEventListener('click', async () => {
    if (state.isAuthenticated && state.currentUser) {
      const ok = await showConfirm({
        title: 'Выход из аккаунта',
        message: `Вы действительно хотите выйти из профиля «${state.currentUser.username}»?`,
        confirmText: 'Выйти',
        cancelText: 'Отмена',
        type: 'warning',
        icon: 'alert'
      });
      if (ok) {
        apiLogout().finally(() => {
          clearAuthToken();
          updateState('isAuthenticated', false);
          updateState('currentUser', null);
          window.location.replace('login.html');
        });
      }
    } else {
      window.location.replace('login.html');
    }
  });
}

export function updateUserInfoUI(user) {
  const nameEl = document.getElementById('userName');
  const avatarEl = document.getElementById('userAvatar');

  if (nameEl) {
    nameEl.textContent = user ? user.username : 'Войти';
  }
  if (avatarEl && user) {
    avatarEl.textContent = user.username.charAt(0).toUpperCase();
  }
}
