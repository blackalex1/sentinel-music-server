/**
 * Sentinel Connect — Модуль удаленного управления и воспроизведения (Connect / Remote Control).
 * Поддерживает:
 * - Управление воспроизведением на других устройствах (Яндекс.Станция, Смартфон, другие ПК).
 * - Прием команд удаленного управления от других устройств.
 * - Двустороннюю синхронизацию состояний плееров через WebSocket / REST.
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
 * Определяет понятное имя устройства для отображения в домашней сети.
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
 * Отправляет удаленную команду конкретному целевому устройству (через WebSocket с фолбэком на REST).
 */
export function sendRemoteCommand(targetDeviceId, command, payload = {}) {
  if (!targetDeviceId) return false;

  const msg = {
    action: 'command',
    target_device_id: targetDeviceId,
    command: command.toUpperCase(),
    payload: payload || {}
  };

  if (ws && ws.readyState === WebSocket.OPEN) {
    try {
      ws.send(JSON.stringify(msg));
      return true;
    } catch (e) {
      console.warn('[Sentinel Connect] Ошибка отправки команды в WebSocket:', e);
    }
  }

  // Фолбэк на REST API
  const token = getAuthToken();
  if (token) {
    fetch(`${getApiBase()}/api/remote/command`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${token}`
      },
      body: JSON.stringify({
        target_device_id: targetDeviceId,
        command: command.toUpperCase(),
        payload: payload || {}
      })
    }).catch(err => console.warn('[Sentinel Connect] Ошибка отправки команды через REST:', err));
    return true;
  }

  return false;
}

/**
 * Запрашивает актуальный список устройств пользователя с сервера.
 */
export function requestDevices() {
  if (ws && ws.readyState === WebSocket.OPEN) {
    try {
      ws.send(JSON.stringify({ action: 'request_devices' }));
    } catch (_) {}
  }
  refreshDevicesHttp();
}

/**
 * HTTP-запрос списка онлайн-устройств.
 */
export async function refreshDevicesHttp() {
  const token = getAuthToken();
  if (!token) return;

  try {
    const res = await fetch(`${getApiBase()}/api/remote/devices`, {
      headers: { 'Authorization': `Bearer ${token}` }
    });
    if (res.ok) {
      const data = await res.json();
      const myId = getOrCreateDeviceId();
      const raw = Array.isArray(data.devices) ? data.devices : [];
      const filtered = raw.filter(d => d.id !== myId);
      updateState('availableDevices', filtered);
      window.dispatchEvent(new CustomEvent('sentinel:devices-changed', { detail: filtered }));
    }
  } catch (e) {
    console.warn('[Sentinel Connect] Ошибка HTTP-запроса списка устройств:', e);
  }
}

/**
 * Переключает активное целевое устройство для воспроизведения.
 * @param {Object|null} device - объект устройства из availableDevices или null для возврата на этот компьютер
 */
export function selectPlaybackDevice(device) {
  const audio = document.getElementById('audioElement');
  const previousRemote = state.selectedRemoteDevice;

  if (!device) {
    // Возврат на локальный компьютер
    if (previousRemote) {
      sendRemoteCommand(previousRemote.id, 'PAUSE');
    }
    updateState('selectedRemoteDevice', null);
    updateDeviceIndicatorsUI();
    window.dispatchEvent(new CustomEvent('sentinel:device-selected', { detail: null }));
    window.dispatchEvent(new CustomEvent('app:toast', { detail: '💻 Воспроизведение на этом компьютере' }));
    return;
  }

  // Переключение на удаленное устройство (колонку или телефон)
  const isLocalPlaying = audio && !audio.paused;
  const curTrack = state.currentTrack;
  const curPos = (audio && audio.currentTime > 0) ? audio.currentTime : (state.currentTime || 0);
  const curQueue = Array.isArray(state.queue) ? state.queue : [];

  // Останавливаем локальное воспроизведение на ПК
  if (audio && !audio.paused) {
    audio.pause();
  }

  updateState('selectedRemoteDevice', device);
  updateDeviceIndicatorsUI();
  window.dispatchEvent(new CustomEvent('sentinel:device-selected', { detail: device }));
  window.dispatchEvent(new CustomEvent('app:toast', { detail: `🎧 Воспроизведение переключено на: ${device.name}` }));

  // Если на ПК уже играл трек — передаем сессию на целевое устройство (TRANSFER_PLAYBACK)
  if (curTrack) {
    sendRemoteCommand(device.id, 'TRANSFER_PLAYBACK', {
      track: curTrack,
      queue: curQueue.slice(0, 50),
      position_seconds: curPos,
      position_ms: Math.round(curPos * 1000),
      auto_play: isLocalPlaying
    });
  } else if (device.current_track) {
    // Если на самом удаленном устройстве уже играет музыка — подтягиваем её в UI
    syncRemoteStateToPlayerUI(device);
  }
}

/**
 * Синхронизирует состояние удаленного устройства с UI локального плеера.
 */
export function syncRemoteStateToPlayerUI(dev) {
  if (!dev) return;

  if (dev.current_track) {
    updateState('currentTrack', dev.current_track);
    updateTrackInfoUI(dev.current_track);
  }
  if (typeof dev.is_playing === 'boolean') {
    updateState('isPlaying', dev.is_playing);
    updatePlayButtonsUI(dev.is_playing);
  }
  if (typeof dev.position_ms === 'number') {
    updateState('currentTime', dev.position_ms / 1000.0);
  }
  if (typeof dev.duration_ms === 'number' && dev.duration_ms > 0) {
    updateState('duration', dev.duration_ms / 1000.0);
  }
  updateTimelineUI();

  if (typeof dev.is_shuffle === 'boolean') {
    updateState('isShuffle', dev.is_shuffle);
    const btnShuffle = document.getElementById('btnShuffle');
    if (btnShuffle) btnShuffle.classList.toggle('active', dev.is_shuffle);
  }
  if (dev.repeat_mode) {
    updateState('repeatMode', dev.repeat_mode);
    const btnRepeat = document.getElementById('btnRepeat');
    if (btnRepeat) btnRepeat.classList.toggle('active', dev.repeat_mode !== 'off');
  }

  // Обновляем плашку и индикаторы
  updateDeviceIndicatorsUI();
}

/**
 * Обновляет иконку и плашку выбранного устройства в плеере.
 */
export function updateDeviceIndicatorsUI() {
  const dev = state.selectedRemoteDevice;
  const btn = document.getElementById('btnPlayerConnect');
  const pill = document.getElementById('playerDevicePill');
  const pillName = document.getElementById('playerDevicePillName');

  if (btn) {
    btn.classList.toggle('active', Boolean(dev));
    btn.title = dev ? `Воспроизведение на: ${dev.name} (нажмите для выбора)` : 'Устройства Sentinel Connect (D)';
  }
  if (pill && pillName) {
    if (dev) {
      pill.style.display = 'inline-flex';
      pillName.textContent = dev.name;
    } else {
      pill.style.display = 'none';
    }
  }
}

/**
 * Инициализирует WebSocket-подключение Sentinel Connect.
 */
export function initRemoteConnect() {
  const token = getAuthToken();
  if (!token) return;

  if (ws && (ws.readyState === WebSocket.OPEN || ws.readyState === WebSocket.CONNECTING)) {
    return;
  }

  const deviceId = getOrCreateDeviceId();
  const deviceName = getDeviceName();

  const base = getApiBase().replace(/\/+$/, '');
  let wsUrl = base.replace(/^http:/, 'ws:').replace(/^https:/, 'wss:');
  wsUrl += `/api/remote/ws?token=${encodeURIComponent(token)}&device_id=${encodeURIComponent(deviceId)}&device_name=${encodeURIComponent(deviceName)}&device_type=hybrid`;

  try {
    ws = new WebSocket(wsUrl);

    ws.onopen = () => {
      isConnected = true;
      console.log(`[Sentinel Connect] Подключено к серверу как hybrid (плеер + пульт): ${deviceName} (${deviceId})`);
      updateConnectIndicatorUI(true);
      updateDeviceIndicatorsUI();

      if (pingIntervalTimer) clearInterval(pingIntervalTimer);
      pingIntervalTimer = setInterval(() => {
        if (ws && ws.readyState === WebSocket.OPEN) {
          try {
            ws.send(JSON.stringify({ action: 'ping' }));
          } catch (_) {}
        }
      }, 15000);

      // Запрашиваем устройства сразу после подключения
      requestDevices();

      const audio = document.getElementById('audioElement');
      if (audio && !audio._remoteListenersAttached) {
        audio._remoteListenersAttached = true;
        audio.addEventListener('play', () => {
          if (!isApplyingRemoteState && !state.selectedRemoteDevice) broadcastCurrentState(true);
        });
        audio.addEventListener('pause', () => {
          if (!isApplyingRemoteState && !state.selectedRemoteDevice) broadcastCurrentState(true);
        });
        audio.addEventListener('seeked', () => {
          if (!isApplyingRemoteState && !state.selectedRemoteDevice) broadcastCurrentState(true);
        });
        audio.addEventListener('timeupdate', () => {
          if (!isApplyingRemoteState && !state.selectedRemoteDevice) broadcastCurrentState(false);
        });
      }
      if (!window._remoteTrackListenerAttached) {
        window._remoteTrackListenerAttached = true;
        window.addEventListener('track:changed', () => {
          if (!isApplyingRemoteState && !state.selectedRemoteDevice) broadcastCurrentState(true);
        });
      }

      if (!state.selectedRemoteDevice) {
        broadcastCurrentState(true);
      }
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

function scheduleReconnect() {
  if (reconnectTimer) return;
  reconnectTimer = setTimeout(() => {
    reconnectTimer = null;
    initRemoteConnect();
  }, 4000);
}

function handleIncomingMessage(msg) {
  if (!msg || !msg.type) return;

  switch (msg.type) {
    case 'welcome':
    case 'devices_update': {
      const myId = getOrCreateDeviceId();
      const raw = Array.isArray(msg.devices) ? msg.devices : [];
      const filtered = raw.filter(d => d.id !== myId);
      updateState('availableDevices', filtered);
      window.dispatchEvent(new CustomEvent('sentinel:devices-changed', { detail: filtered }));

      if (state.selectedRemoteDevice) {
        const stillOnline = filtered.find(d => d.id === state.selectedRemoteDevice.id);
        if (!stillOnline) {
          const devName = state.selectedRemoteDevice.name;
          updateState('selectedRemoteDevice', null);
          updateDeviceIndicatorsUI();
          window.dispatchEvent(new CustomEvent('sentinel:device-selected', { detail: null }));
          window.dispatchEvent(new CustomEvent('app:toast', {
            detail: `⚠️ Устройство «${devName}» отключилось. Воспроизведение переключено на этот компьютер.`
          }));
        } else {
          updateState('selectedRemoteDevice', stillOnline);
        }
      }
      break;
    }

    case 'command':
      executeRemoteCommand(msg.command, msg.payload, msg.from_device_id);
      break;

    case 'device_state': {
      const devId = msg.device_id;
      const dev = msg.device;
      if (!devId || !dev) break;

      const curList = state.availableDevices || [];
      const updatedList = curList.map(d => d.id === devId ? { ...d, ...dev } : d);
      updateState('availableDevices', updatedList);
      window.dispatchEvent(new CustomEvent('sentinel:devices-changed', { detail: updatedList }));

      // Если это активное выбранное устройство — синхронизируем UI плеера
      if (state.selectedRemoteDevice && state.selectedRemoteDevice.id === devId) {
        updateState('selectedRemoteDevice', { ...state.selectedRemoteDevice, ...dev });
        syncRemoteStateToPlayerUI(dev);
      }
      break;
    }

    case 'pong':
      break;
  }
}

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
        toastText = 'Воспроизведение запущено удаленно';
        break;
      }

      case 'PAUSE': {
        if (audio && !audio.paused) {
          audio.pause();
        }
        updateState('isPlaying', false);
        updatePlayButtonsUI(false);
        toastText = 'Пауза (удаленно)';
        break;
      }

      case 'TOGGLE_PLAY': {
        if (audio && !audio.paused) {
          audio.pause();
          updateState('isPlaying', false);
          updatePlayButtonsUI(false);
          toastText = 'Пауза (удаленно)';
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
          toastText = 'Воспроизведение запущено удаленно';
        }
        break;
      }

      case 'NEXT': {
        nextTrack();
        toastText = 'Следующий трек (удаленно)';
        break;
      }

      case 'PREV': {
        prevTrack();
        toastText = 'Предыдущий трек (удаленно)';
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
            : `Передано на ПК: ${payload.track.artist} - ${payload.track.title}`;
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
        break;
      }
    }
  } catch (err) {
    console.error('[Sentinel Connect] Ошибка обработки команды:', err);
  } finally {
    if (toastText) {
      window.dispatchEvent(new CustomEvent('app:toast', { detail: `📱 ${toastText}` }));
    }
    setTimeout(() => {
      isApplyingRemoteState = false;
      if (!state.selectedRemoteDevice) {
        broadcastCurrentState(true);
      }
    }, 80);
  }
}

/**
 * Отправляет актуальное состояние воспроизведения ПК всем клиентам в сети.
 */
export function broadcastCurrentState(force = false) {
  if (isApplyingRemoteState) return;
  if (state.selectedRemoteDevice) return; // Не перезаписываем статус удаленного устройства
  if (!ws || ws.readyState !== WebSocket.OPEN) return;

  const audio = document.getElementById('audioElement');
  const now = Date.now();

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
      current_track: state.currentTrack ? { ...state.currentTrack, audio_format: state.currentTrack.audio_format || state.currentTrack.format || 'mp3' } : null,
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

function updateConnectIndicatorUI(online) {
  const indicator = document.getElementById('sentinelConnectBadge');
  if (indicator) {
    indicator.classList.toggle('active', online);
    indicator.title = online
      ? `Sentinel Connect активен`
      : `Sentinel Connect подключается...`;
  }
}

// Слушатели событий плеера для автоматической синхронизации
if (typeof window !== 'undefined') {
  window.addEventListener('player:state-change', () => broadcastCurrentState(true));
  window.addEventListener('player:track-change', () => broadcastCurrentState(true));
  window.addEventListener('loudness:changed', () => broadcastCurrentState(true));
  window.addEventListener('online', () => initRemoteConnect());

  try {
    audioFx.subscribe(() => broadcastCurrentState(true));
  } catch (_) {}

  setInterval(() => {
    const audio = document.getElementById('audioElement');
    if (audio && !audio.paused && isConnected && !state.selectedRemoteDevice) {
      broadcastCurrentState(false);
    }
  }, 3000);
}
