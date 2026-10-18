/**
 * Главный модуль входа музыкального сервиса Sentinel Music.
 * Инициализирует аудио-движок, UI, Поток, караоке и горячие клавиши.
 */

import { state, updateState } from './state.js';
import { getAuthToken } from './config.js';
import { apiFetch, checkAuthStatus } from './api.js';
import { initPlayer, togglePlay, nextTrack, prevTrack, seekTime, setVolume, toggleMute, toggleShuffle, toggleRepeat, restorePlaybackSession, restorePlaybackFromRemote } from './player.js';
import { initStream } from './stream.js';
import { initLyrics, toggleLyricsOverlay } from './lyrics.js';
import { initQueueUI, toggleQueueDrawer } from './queue.js';
import { initUI, switchView, loadLibraryTracks, loadPlaylistsData, showAuthModal, updateUserInfoUI, loadDuplicates, toggleEqualizerModal } from './ui.js';
import { toggleExpandedPlayer } from './ui/expandedPlayer.js';
import { mountLayout } from './components/layout.js';
import { loadFrontendPlugins } from './pluginLoader.js';
import { initRemoteConnect } from './remote.js';

document.addEventListener('DOMContentLoaded', async () => {
  // 0. Модульная сборка и монтирование интерфейса из компонентов
  mountLayout(document.getElementById('app'));

  // 1. Инициализация всех подсистем
  initPlayer();
  initStream();
  initLyrics();
  initQueueUI();
  initUI();
  await loadFrontendPlugins();

  // 1.1 Мгновенное восстановление сохраненной сессии воспроизведения (трек, очередь, позиция)
  restorePlaybackSession();

  // 2. Регистрация глобальных горячих клавиш
  setupGlobalHotkeys();

  // 3. Авторизация и первичная загрузка данных
  await bootstrapApp();
});

async function bootstrapApp() {
  const token = getAuthToken();

  if (token) {
    try {
      const res = await apiFetch('/api/auth/me');
      if (res.ok) {
        const user = await res.json();
        updateState('isAuthenticated', true);
        updateState('currentUser', user);
        updateUserInfoUI(user);

        // Инициализация удаленного управления Sentinel Connect
        initRemoteConnect();

        // Загрузка начальной фонотеки
        await loadLibraryTracks();
        await loadPlaylistsData();
        loadDuplicates();

        // Проверяем актуальность сессии воспроизведения с сервера (например, слушали на телефоне)
        try {
          const statusRes = await apiFetch('/api/remote/status');
          if (statusRes.ok) {
            const statusData = await statusRes.json();
            const remoteSession = statusData?.last_playback_session;
            if (remoteSession && remoteSession.current_track) {
              const serverTimestamp = remoteSession.saved_at ? (remoteSession.saved_at * 1000) : 0;
              let localTimestamp = 0;
              try {
                const rawLocal = localStorage.getItem('sentinel_playback_session');
                if (rawLocal) {
                  const parsed = JSON.parse(rawLocal);
                  localTimestamp = parsed.timestamp || 0;
                }
              } catch (_) {}

              // Если на сервере сессия новее, чем в localStorage на ПК, или на ПК вообще не было трека,
              // или если трек отличается и время сервера больше или равно локальному
              const isDiffTrack = !state.currentTrack || state.currentTrack.id !== remoteSession.current_track.id;
              if (isDiffTrack && (serverTimestamp >= localTimestamp || localTimestamp === 0)) {
                console.log('[Remote] Найдена более свежая сессия воспроизведения с другого устройства:', remoteSession.current_track.title);
                restorePlaybackFromRemote(remoteSession);
              }
            }
          }
        } catch (e) {
          console.warn('[Remote] Ошибка запроса серверной сессии:', e);
        }
        return;
      }
    } catch (e) {
      console.warn('Токен сессии недействителен, требуется повторный вход');
    }
  }

  // Проверяем статус сервера (первичная настройка или стандартный вход)
  try {
    const status = await checkAuthStatus();
    if (!status.initialized) {
      showAuthModal(true); // Первый запуск — регистрация администратора
    } else {
      showAuthModal(false); // Стандартный вход
    }
  } catch (err) {
    console.error('Ошибка проверки состояния сервера:', err);
    showAuthModal(false);
  }
}

/**
 * Глобальные горячие клавиши управления плеером (Space, стрелки, M, L).
 */
function setupGlobalHotkeys() {
  window.addEventListener('keydown', (e) => {
    // Игнорируем горячие клавиши, если фокус в поле ввода (поиск, логин и т.д.)
    const tag = document.activeElement ? document.activeElement.tagName.toLowerCase() : '';
    if (tag === 'input' || tag === 'textarea') return;

    switch (e.code) {
      case 'Space':
        e.preventDefault();
        togglePlay();
        break;

      case 'ArrowLeft':
        e.preventDefault();
        if (e.shiftKey) {
          prevTrack();
        } else {
          seekRelative(-5);
        }
        break;

      case 'ArrowRight':
        e.preventDefault();
        if (e.shiftKey) {
          nextTrack();
        } else {
          seekRelative(5);
        }
        break;

      case 'ArrowUp':
        e.preventDefault();
        setVolume(Math.min(1, state.volume + 0.05));
        break;

      case 'ArrowDown':
        e.preventDefault();
        setVolume(Math.max(0, state.volume - 0.05));
        break;

      case 'KeyM':
        toggleMute();
        break;

      case 'KeyL':
        // Переключение всплывающего окна текстов песен
        if (document.getElementById('expandedPlayerOverlay')?.classList.contains('active')) {
          toggleExpandedPlayer(false);
          toggleLyricsOverlay(true);
        } else {
          toggleLyricsOverlay();
        }
        break;

      case 'KeyQ':
        // Переключение панели Очереди воспроизведения
        if (document.getElementById('expandedPlayerOverlay')?.classList.contains('active')) {
          toggleExpandedPlayer(false);
          toggleQueueDrawer(true);
        } else {
          toggleQueueDrawer();
        }
        break;

      case 'KeyS':
        toggleShuffle();
        break;

      case 'KeyR':
        toggleRepeat();
        break;

      case 'KeyE':
        toggleEqualizerModal();
        break;
    }
  });
}

function seekRelative(deltaSeconds) {
  const audio = document.getElementById('audioElement');
  if (audio && audio.duration) {
    seekTime(Math.max(0, Math.min(audio.duration, audio.currentTime + deltaSeconds)));
  }
}
