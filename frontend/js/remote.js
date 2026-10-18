/**
 * Sentinel Connect — Модуль удаленного управления (Remote Control / Connect) на стороне ПК.
 * Регистрирует ПК как активный плеер в шине WebSocket сервера,
 * слушает команды от Android-приложения и отсылает текущее состояние воспроизведения.
 */

import { state, updateState } from './state.js';
import { API_BASE, getAuthToken, isTauri } from './config.js';
import {
  playTrack,
  togglePlay,
  nextTrack,
  prevTrack,
  seekTime,
  setVolume,
  toggleShuffle,
  toggleRepeat,
  toggleMute,
  toggleLoudnessNormalization,
  updatePlayButtonsUI,
  updateTrackInfoUI,
  updateTimelineUI,
  savePlaybackSession
} from './player.js';
import { audioFx } from './audioFx.js';
import { syncEqualizerUI } from './ui/equalizer.js';

let ws = null;
let reconnectTimer = null;
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

  // Преобразуем HTTP URL сервера в WS URL
  let wsUrl = API_BASE.replace(/^http:/, 'ws:').replace(/^https:/, 'wss:');
  wsUrl += `/api/remote/ws?token=${encodeURIComponent(token)}&device_id=${encodeURIComponent(deviceId)}&device_name=${encodeURIComponent(deviceName)}&device_type=player`;

  try {
    ws = new WebSocket(wsUrl);

    ws.onopen = () => {
      isConnected = true;
      console.log(`[Sentinel Connect] Подключено к серверу как плеер: ${deviceName} (${deviceId})`);
      updateConnectIndicatorUI(true);

      const audio = document.getElementById('audioElement');
      if (audio && !audio._remoteListenersAttached) {
        audio._remoteListenersAttached = true;
        audio.addEventListener('play', () => broadcastCurrentState(true));
        audio.addEventListener('pause', () => {
          if (!isApplyingRemoteState) {
            broadcastCurrentState(true);
          }
        });
        audio.addEventListener('seeked', () => broadcastCurrentState(true));
        audio.addEventListener('timeupdate', () => broadcastCurrentState(false));
      }
      if (!window._remoteTrackListenerAttached) {
        window._remoteTrackListenerAttached = true;
        window.addEventListener('track:changed', () => broadcastCurrentState(true));
      }

      // Сразу отправляем текущее состояние
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
      updateConnectIndicatorUI(false);
      scheduleReconnect();
    };

    ws.onerror = (err) => {
      console.warn('[Sentinel Connect] Ошибка сокета:', err);
      ws.close();
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
        const activePlayingDevice = msg.devices.find(d => d.id !== getOrCreateDeviceId() && (d.is_playing || d.current_track));
        if (activePlayingDevice && activePlayingDevice.current_track) {
          const audio = document.getElementById('audioElement');
          if (audio && audio.paused) {
            console.log(`[Sentinel Connect] Найдено активное устройство (${activePlayingDevice.name}), синхронизируем состояние`);
            handleRemoteDeviceState(activePlayingDevice.id, activePlayingDevice);
          }
        }
      }
      break;

    case 'devices_update':
      window.dispatchEvent(new CustomEvent('sentinel:devices-changed', { detail: msg.devices || [] }));
      break;

    case 'command':
      executeRemoteCommand(msg.command, msg.payload, msg.from_device_id);
      break;

    case 'device_state':
      handleRemoteDeviceState(msg.device_id, msg.device);
      break;

    case 'pong':
      break;
  }
}

/**
 * Выполняет команду, пришедшую с телефона (Play, Pause, Next, Seek, Volume...).
 */
function executeRemoteCommand(command, payload = {}, fromDeviceId = '') {
  const audio = document.getElementById('audioElement');
  console.log(`[Sentinel Connect] Получена удаленная команда: ${command}`, payload);

  let toastText = null;

  switch (command) {
    case 'PLAY':
      if (audio && audio.paused) {
        audio.play().catch(() => {});
        toastText = 'Воспроизведение запущено с телефона';
      }
      break;

    case 'PAUSE':
      if (audio && !audio.paused) {
        audio.pause();
        toastText = 'Пауза с телефона';
      }
      break;

    case 'TOGGLE_PLAY':
      togglePlay();
      break;

    case 'NEXT':
      nextTrack();
      toastText = 'Следующий трек (с телефона)';
      break;

    case 'PREV':
      prevTrack();
      toastText = 'Предыдущий трек (с телефона)';
      break;

    case 'SEEK':
      if (payload.position_seconds !== undefined) {
        seekTime(Number(payload.position_seconds));
      } else if (payload.position_ms !== undefined) {
        seekTime(Number(payload.position_ms) / 1000.0);
      }
      break;

    case 'SET_VOLUME':
      if (payload.volume !== undefined) {
        setVolume(Number(payload.volume));
      }
      break;

    case 'MUTE':
      toggleMute();
      break;

    case 'PREPARE_TRACK':
    case 'TRANSFER_PLAYBACK':
    case 'PLAY_TRACK':
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

        setTimeout(() => {
          isApplyingRemoteState = false;
          broadcastCurrentState(true);
        }, 150);
      }
      break;

    case 'SHUFFLE':
      toggleShuffle();
      break;

    case 'REPEAT':
      toggleRepeat();
      break;

    case 'SET_EQUALIZER':
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

    case 'SET_LIMITER':
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

  if (toastText) {
    window.dispatchEvent(new CustomEvent('app:toast', { detail: `📱 ${toastText}` }));
  }

  // Немедленно синхронизируем новое состояние обратно
  setTimeout(broadcastCurrentState, 50);
}

/**
 * Обрабатывает обновление состояния воспроизведения с другого устройства (например, со смартфона).
 * Если на ПК в этот момент не играет звук, синхронизирует отображение активного трека,
 * прогресса, обложки и очереди без автовоспроизведения на ПК.
 */
function handleRemoteDeviceState(deviceId, device) {
  if (!device || !device.current_track) return;
  if (deviceId === getOrCreateDeviceId()) return;

  const audio = document.getElementById('audioElement');
  // Если на ПК прямо сейчас активно воспроизводится локальный звук — не перебиваем его
  if (audio && !audio.paused) {
    return;
  }

  const remoteTrack = device.current_track;
  const posSec = (device.position_ms || 0) / 1000.0;
  const durSec = (device.duration_ms || (remoteTrack.duration ? remoteTrack.duration * 1000 : 0)) / 1000.0;

  const isDifferentTrack = !state.currentTrack || state.currentTrack.id !== remoteTrack.id;

  isApplyingRemoteState = true;
  try {
    if (isDifferentTrack) {
      console.log(`[Sentinel Connect] Синхронизация трека с ${device.name || 'устройства'}:`, remoteTrack.title);
      const remoteQueue = Array.isArray(device.queue) && device.queue.length > 0 ? device.queue : null;
      // Подготавливаем трек на ПК без автозапуска звука
      playTrack(remoteTrack, remoteQueue, false, false, posSec);
    } else {
      // Тот же трек — плавно обновляем позицию на шкале воспроизведения
      updateState('currentTime', posSec);
      if (durSec > 0) {
        updateState('duration', durSec);
      }
      updateTimelineUI();
      if (audio && Math.abs(audio.currentTime - posSec) > 2) {
        try {
          audio.currentTime = posSec;
        } catch (_) {}
      }
    }
  } catch (err) {
    console.warn('[Sentinel Connect] Ошибка применения удаленного состояния:', err);
  } finally {
    setTimeout(() => {
      isApplyingRemoteState = false;
    }, 300);
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
