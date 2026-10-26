/**
 * Глобальное реактивное состояние музыкального сервиса.
 */

export const state = {
  // Авторизация
  currentUser: null,
  isAuthenticated: false,

  // Воспроизведение
  currentTrack: null,
  isPlaying: false,
  currentTime: 0,
  duration: 0,
  volume: !isNaN(parseFloat(localStorage.getItem('sentinel_volume'))) ? parseFloat(localStorage.getItem('sentinel_volume')) : 0.8,
  isMuted: localStorage.getItem('sentinel_muted') === 'true',
  isLoudnessNormalization: localStorage.getItem('sentinel_loudness_norm') !== 'false',
  currentTrackGain: 0.0,
  currentTrackLoudness: null,

  // Очередь и режимы
  queue: [],
  queueIndex: -1,
  history: [],
  isQueueOpen: localStorage.getItem('sentinel_queue_open') === 'true',
  isShuffle: false,
  repeatMode: localStorage.getItem('sentinel_repeat_mode') || 'off',
  isStreamActive: false,
  streamMood: 'default', // 'default', 'energy', 'chill', 'happy', 'sad'
  discoveryRatio: 0.2, // 0.0 (только своя), 0.1 (редко), 0.2 (умеренно), 0.33 (часто), 1.0 (только открытия)
  recentStreamIds: [],   // сессионный кулдаун прослушанных треков Потока

  // Фонотека
  tracks: [],
  playlists: [],
  activePlaylist: null,

  // Караоке
  lyrics: [], // Array<{ time: number, text: string }>
  activeLyricIndex: -1,

  // Sentinel Connect (Удаленное управление)
  availableDevices: [],
  selectedRemoteDevice: null, // null = этот ПК (локально); { id, name, ... } = удаленное устройство

  // Навигация
  currentView: 'main', // 'main', 'stream', 'tracks', 'playlists', 'lyrics'
  searchQuery: ''
};

// Простая шина событий состояния
const listeners = new Map();

export function onStateChange(key, callback) {
  if (!listeners.has(key)) {
    listeners.set(key, []);
  }
  listeners.get(key).push(callback);
}

export function updateState(key, value) {
  state[key] = value;
  if (listeners.has(key)) {
    listeners.get(key).forEach(cb => cb(value, state));
  }
}
