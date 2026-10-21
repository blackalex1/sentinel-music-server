/**
 * Sentinel Connect — Модуль удаленного управления (Remote Control / Connect) на стороне ПК.
 * Регистрирует ПК как активный плеер в шине WebSocket сервера,
 * слушает команды от Android-приложения и отсылает текущее состояние воспроизведения.
 */

import { state, updateState } from './state.js';
import { getApiBase, getAuthToken, isTauri } from './config.js';
import {
  playTrack,
  togglePlay,
  nextTrack,
  prevTrack,
  seekTime,
  setVolume,
  toggleShuffle,
  setShuffle,
  toggleRepeat,
  setRepeatMode,
  toggleMute,
  toggleLoudnessNormalization,
  updatePlayButtonsUI,
  updateTrackInfoUI,
  updateTimelineUI,
  savePlaybackSession
} from './player.js';
import { syncTrackReactionUI } from './ui/reactions.js';
import { audioFx } from './audioFx.js';
import { syncEqualizerUI } from './ui/equalizer.js';

let ws = null;
let reconnectTimer = null;
let pingIntervalTimer = null;
let lastProgressBroadcast = 0;
let isConnected = false;
let isApplyingRemoteState = false;

/**
 * Получает или генерирует уникальный persistent ID текущего устройства.
 */
export function getOrCreateDeviceId() {
  let id = localStorage.getItem('sentinel_device_id');
  if (!id) {
    id = 'pc_' + Math.random().toString(36).substring(2, 9) + '_' + Date.now().toString(36);
    localStorage.setItem('sentinel_device_id', id);
  }
  return id;
}

/**
 * Определяет понятное имя устройства для отображения в списке на Android.
 */
export function getDeviceName() {
  if (isTauri) {
    return 'Windows ПК (Sentinel Desktop)';
  }
  const ua = navigator.userAgent;
  let browser = 'Web Браузер';
  if (ua.includes('Edg/')) browser = 'Edge';
  else if (ua.includes('Chrome/')) browser = 'Chrome';
  else if (ua.includes('Firefox/')) browser = 'Firefox';
  else if (ua.includes('Safari/')) browser = 'Safari';

  return `Компьютер (${browser})`;
}

/**
 * Инициализирует WebSocket-подключение Sentinel Connect.
 */
export function initRemoteConnect() {
  const token = getAuthToken();
  if (!token) {
    // Пользователь еще не авторизован, отложим подключение
    return;
  }

  if (ws && (ws.readyState === WebSocket.OPEN || ws.readyState === WebSocket.CONNECTING)) {
    return;
  }

  const deviceId = getOrCreateDeviceId();
  const deviceName = getDeviceName();

  // Преобразуем динамический HTTP URL сервера в WS URL
  const base = getApiBase().replace(/\/+$/, '');
  let wsUrl = base.replace(/^http:/, 'ws:').replace(/^https:/, 'wss:');
  wsUrl += `/api/remote/ws?token=${encodeURIComponent(token)}&device_id=${encodeURIComponent(deviceId)}&device_name=${encodeURIComponent(deviceName)}&device_type=player`;

  try {
    ws = new WebSocket(wsUrl);

    ws.onopen = () => {
      isConnected = true;
      console.log(`[Sentinel Connect] Подключено к серверу как плеер: ${deviceName} (${deviceId})`);
      updateConnectIndicatorUI(true);

      // Запуск периодического heartbeat ping раз в 15 секунд для удержания соединения
      if (pingIntervalTimer) clearInterval(pingIntervalTimer);
      pingIntervalTimer = setInterval(() => {
        if (ws && ws.readyState === WebSocket.OPEN) {
          try {
            ws.send(JSON.stringify({ action: 'ping' }));
          } catch (_) {}
        }
      }, 15000);

      const audio = document.getElementById('audioElement');
      if (audio && !audio._remoteListenersAttached) {
        audio._remoteListenersAttached = true;
        audio.addEventListener('play', () => {
          if (!isApplyingRemoteState) broadcastCurrentState(true);
        });
        audio.addEventListener('pause', () => {
          if (!isApplyingRemoteState) broadcastCurrentState(true);
        });
        audio.addEventListener('seeked', () => {
          if (!isApplyingRemoteState) broadcastCurrentState(true);
        });
        audio.addEventListener('timeupdate', () => {
          if (!isApplyingRemoteState) broadcastCurrentState(false);
        });
      }
      if (!window._remoteTrackListenerAttached) {
        window._remoteTrackListenerAttached = true;
        window.addEventListener('track:changed', () => {
          if (!isApplyingRemoteState) broadcastCurrentState(true);
        });
      }

      // Немедленно отправляем текущее состояние воспроизведения
      broadcastCurrentState(true);
    };

    ws.onmessage = (event) => {
      try {
        const msg = JSON.parse(event.data);
        handleIncomingMessage(msg);
      } catch (err) {
        console.warn('[Sentinel Connect] Ошибка разбора сообщения:', err);
      }
    };

    ws.onclose = () => {
      isConnected = false;
      if (pingIntervalTimer) {
        clearInterval(pingIntervalTimer);
        pingIntervalTimer = null;
      }
      updateConnectIndicatorUI(false);
      scheduleReconnect();
    };

    ws.onerror = (err) => {
      console.warn('[Sentinel Connect] Ошибка сокета:', err);
      try { ws.close(); } catch (_) {}
    };
  } catch (e) {
    console.error('[Sentinel Connect] Не удалось открыть WebSocket:', e);
    scheduleReconnect();
  }
}

/**
 * Планирует автоматическое переподключение с задержкой при обрыве связи.
 */
function scheduleReconnect() {
  if (reconnectTimer) return;
  reconnectTimer = setTimeout(() => {
    reconnectTimer = null;
    initRemoteConnect();
  }, 4000);
}

/**
 * Обрабатывает входящие события и команды от сервера и других устройств.
 */
function handleIncomingMessage(msg) {
  if (!msg || !msg.type) return;

  switch (msg.type) {
    case 'welcome':
      console.log(`[Sentinel Connect] Зарегистрирован в сети. Доступных устройств:`, msg.devices?.length || 0);
      if (Array.isArray(msg.devices)) {
        window.dispatchEvent(new CustomEvent('sentinel:devices-changed', { detail: msg.devices }));
      }
      break;

    case 'devices_update':
      window.dispatchEvent(new CustomEvent('sentinel:devices-changed', { detail: msg.devices || [] }));
      break;

    case 'command':
      executeRemoteCommand(msg.command, msg.payload, msg.from_device_id);
      break;

    case 'device_state':
      // ПК является конечным плеером (player), поэтому входящее состояние других устройств
      // не должно самовольно сбрасывать локальный трек и очередь.
      // Сохраняем информацию об устройствах для UI при необходимости.
      break;

    case 'pong':
      break;
  }
}

/**
 * Выполняет команду, пришедшую со смартфона (Play, Pause, Next, Prev, Seek, Volume...).
 */
function executeRemoteCommand(command, payload = {}, fromDeviceId = '') {
  const audio = document.getElementById('audioElement');
  console.log(`[Sentinel Connect] Получена удаленная команда: ${command}`, payload);

  let toastText = null;
  isApplyingRemoteState = true;

  try {
    switch (command) {
      case 'PLAY': {
        const hasValidSource = audio && audio.src && audio.src !== window.location.href && !audio.src.endsWith('/null');
        if (!hasValidSource) {
          if (state.currentTrack) {
            playTrack(state.currentTrack, state.queue, false, true, state.currentTime || 0);
          } else if (state.tracks && state.tracks.length > 0) {
            playTrack(state.tracks[0], state.tracks, false, true, 0);
          }
        } else if (audio.paused) {
          audio.play().catch(e => {
            console.warn('[Sentinel Connect] Ошибка запуска аудио:', e);
            if (state.currentTrack) {
              playTrack(state.currentTrack, state.queue, false, true, state.currentTime || 0);
            }
          });
        }
        updateState('isPlaying', true);
        updatePlayButtonsUI(true);
        toastText = 'Воспроизведение запущено с телефона';
        break;
      }

      case 'PAUSE': {
        if (audio && !audio.paused) {
          audio.pause();
        }
        updateState('isPlaying', false);
        updatePlayButtonsUI(false);
        toastText = 'Пауза с телефона';
        break;
      }

      case 'TOGGLE_PLAY': {
        if (audio && !audio.paused) {
          audio.pause();
          updateState('isPlaying', false);
          updatePlayButtonsUI(false);
          toastText = 'Пауза с телефона';
        } else {
          const hasValidSource = audio && audio.src && audio.src !== window.location.href && !audio.src.endsWith('/null');
          if (!hasValidSource) {
            if (state.currentTrack) {
              playTrack(state.currentTrack, state.queue, false, true, state.currentTime || 0);
            } else if (state.tracks && state.tracks.length > 0) {
              playTrack(state.tracks[0], state.tracks, false, true, 0);
            }
          } else {
            audio.play().catch(e => {
              console.warn('[Sentinel Connect] Ошибка запуска аудио при toggle:', e);
              if (state.currentTrack) {
                playTrack(state.currentTrack, state.queue, false, true, state.currentTime || 0);
              }
            });
          }
          updateState('isPlaying', true);
          updatePlayButtonsUI(true);
          toastText = 'Воспроизведение запущено с телефона';
        }
        break;
      }

      case 'NEXT': {
        nextTrack();
        toastText = 'Следующий трек (с телефона)';
        break;
      }

      case 'PREV': {
        prevTrack();
        toastText = 'Предыдущий трек (с телефона)';
        break;
      }

      case 'SEEK': {
        const posSec = (payload.position_seconds !== undefined)
          ? Number(payload.position_seconds)
          : ((payload.position_ms !== undefined) ? Number(payload.position_ms) / 1000.0 : 0);
        seekTime(posSec);
        break;
      }

      case 'SET_VOLUME': {
        if (payload.volume !== undefined) {
          setVolume(Number(payload.volume));
        }
        break;
      }

      case 'MUTE': {
        toggleMute();
        break;
      }

      case 'PREPARE_TRACK':
      case 'TRANSFER_PLAYBACK':
      case 'PLAY_TRACK': {
        if (payload.track) {
          const isTransfer = (command === 'PREPARE_TRACK' || command === 'TRANSFER_PLAYBACK');
          const autoPlay = payload.auto_play !== undefined 
            ? Boolean(payload.auto_play) 
            : !isTransfer;
          const posSec = (payload.position_seconds !== undefined)
            ? Number(payload.position_seconds)
            : ((payload.position_ms !== undefined) ? Number(payload.position_ms) / 1000.0 : 0);

          playTrack(payload.track, payload.queue || null, false, autoPlay, posSec);
          toastText = autoPlay
            ? `Удаленный запуск: ${payload.track.artist} - ${payload.track.title}`
            : `Передано с телефона: ${payload.track.artist} - ${payload.track.title}`;
        }
        break;
      }

      case 'SHUFFLE': {
        if (payload.is_shuffle !== undefined) {
          setShuffle(Boolean(payload.is_shuffle));
        } else {
          toggleShuffle();
        }
        break;
      }

      case 'REPEAT': {
        if (payload.repeat_mode) {
          setRepeatMode(payload.repeat_mode);
        } else {
          toggleRepeat();
        }
        break;
      }

      case 'SET_REACTION': {
        if (payload.track_id !== undefined) {
          syncTrackReactionUI(Number(payload.track_id), Boolean(payload.is_liked), Boolean(payload.is_disliked));
        }
        break;
      }

      case 'SET_EQUALIZER': {
        if (payload.enabled !== undefined) audioFx.setEnabled(Boolean(payload.enabled));
        if (payload.preset) audioFx.setPreset(payload.preset);
        if (payload.band_index !== undefined && payload.level_db !== undefined) {
          audioFx.setBandLevel(Number(payload.band_index), Number(payload.level_db));
        }
        if (Array.isArray(payload.bands)) {
          payload.bands.forEach((lvl, idx) => audioFx.setBandLevel(idx, Number(lvl)));
        }
        if (payload.bass_boost !== undefined) audioFx.setBassBoost(Number(payload.bass_boost));
        if (payload.reset) audioFx.resetToFlat();
        try { syncEqualizerUI(); } catch (_) {}
        toastText = 'Эквалайзер изменен с телефона';
        break;
      }

      case 'SET_LIMITER': {
        if (payload.mode) audioFx.setLimiterMode(payload.mode);
        if (payload.loudness_enabled !== undefined) {
          const targetState = Boolean(payload.loudness_enabled);
          if (targetState !== Boolean(state.isLoudnessNormalization)) {
            toggleLoudnessNormalization();
          }
        }
        try { syncEqualizerUI(); } catch (_) {}
        toastText = 'Лимитер изменен с телефона';
        break;
      }
    }
  } catch (err) {
    console.error('[Sentinel Connect] Ошибка обработки команды:', err);
  } finally {
    if (toastText) {
      window.dispatchEvent(new CustomEvent('app:toast', { detail: `📱 ${toastText}` }));
    }
    // Даем аудио-стеку применить изменения и отправляем обновленный статус с force = true
    setTimeout(() => {
      isApplyingRemoteState = false;
      broadcastCurrentState(true);
    }, 80);
  }
}

/**
 * Отправляет актуальное состояние воспроизведения ПК всем клиентам в сети.
 */
export function broadcastCurrentState(force = false) {
  if (isApplyingRemoteState) return;
  if (!ws || ws.readyState !== WebSocket.OPEN) return;

  const audio = document.getElementById('audioElement');
  const now = Date.now();

  // Троттлинг отправки тиков прогресса (не чаще раза в 1 секунду), если не форсировано
  if (!force && now - lastProgressBroadcast < 1000) {
    return;
  }
  lastProgressBroadcast = now;

  const isPlaying = (audio && !audio.paused) || Boolean(state.isPlaying);
  const posSec = (audio && audio.currentTime > 0) ? audio.currentTime : (state.currentTime || 0);
  const positionMs = Math.round(posSec * 1000);
  const durSec = (audio && audio.duration) ? audio.duration : (state.duration || (state.currentTrack ? state.currentTrack.duration : 0));
  const durationMs = Math.round(durSec * 1000);

  const upcomingQueue = (Array.isArray(state.queue) && state.queueIndex >= 0)
    ? state.queue.slice(state.queueIndex + 1)
    : (Array.isArray(state.queue) ? state.queue : []);

  const payload = {
    action: 'state_update',
    state: {
      is_playing: isPlaying,
      current_track: state.currentTrack,
      position_ms: positionMs,
      duration_ms: durationMs,
      queue: upcomingQueue.slice(0, 100),
      volume: state.volume,
      is_muted: Boolean(state.isMuted),
      repeat_mode: state.repeatMode || 'off',
      is_shuffle: Boolean(state.isShuffle),
      equalizer: audioFx.getState(),
      limiter: {
        mode: audioFx.getState().currentLimiterMode,
        is_loudness: Boolean(state.isLoudnessNormalization)
      }
    }
  };

  try {
    ws.send(JSON.stringify(payload));
  } catch (e) {
    console.warn('[Sentinel Connect] Не удалось отправить статус:', e);
  }
}

/**
 * Обновляет иконку / индикатор подключения Sentinel Connect в интерфейсе.
 */
function updateConnectIndicatorUI(online) {
  const indicator = document.getElementById('sentinelConnectBadge');
  if (indicator) {
    indicator.classList.toggle('active', online);
    indicator.title = online
      ? `Sentinel Connect активен: можно управлять воспроизведением с телефона`
      : `Sentinel Connect подключается...`;

    if (!indicator._hasClickListener) {
      indicator._hasClickListener = true;
      indicator.addEventListener('click', () => {
        const text = isConnected
          ? 'Sentinel Connect активен. Вы можете управлять этим ПК из приложения на Android!'
          : 'Sentinel Connect: подключение к серверу...';
        window.dispatchEvent(new CustomEvent('app:toast', { detail: `💻 ${text}` }));
      });
    }
  }
}

// Слушатели событий плеера для автоматической синхронизации
if (typeof window !== 'undefined') {
  window.addEventListener('player:state-change', () => broadcastCurrentState(true));
  window.addEventListener('player:track-change', () => broadcastCurrentState(true));
  window.addEventListener('loudness:changed', () => broadcastCurrentState(true));
  window.addEventListener('online', () => initRemoteConnect());

  // Слушаем изменения эквалайзера и лимитеров в реальном времени
  try {
    audioFx.subscribe(() => broadcastCurrentState(true));
  } catch (_) {}

  // Периодический пинг состояния раз в 3 секунды во время воспроизведения
  setInterval(() => {
    const audio = document.getElementById('audioElement');
    if (audio && !audio.paused && isConnected) {
      broadcastCurrentState(false);
    }
  }, 3000);
}
