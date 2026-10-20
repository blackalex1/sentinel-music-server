/**
 * Модуль аудио-плеера и управления потоковым воспроизведением.
 */

import { state, updateState } from './state.js';
import { API_BASE, getAuthToken } from './config.js';
import { sendReaction, fetchShuffleTracks } from './api.js';
import { icon } from './icons.js';
import { syncTrackReactionUI } from './ui/reactions.js';
import { audioFx } from './audioFx.js';

let audio = null;
let audioCtx = null;
let audioSourceNode = null;
let trackGainNode = null;
let masterGainNode = null;
let isAudioGraphInitialized = false;

export function ensureAudioGraph() {
  if (!audio) return;
  if (!audioCtx) {
    const AudioContextClass = window.AudioContext || window.webkitAudioContext;
    if (!AudioContextClass) return;
    try {
      audioCtx = new AudioContextClass();
    } catch (e) {
      console.warn('Не удалось создать AudioContext:', e);
      return;
    }
  }

  if (audioCtx.state === 'suspended') {
    audioCtx.resume().catch(() => {});
  }

  if (!isAudioGraphInitialized && audioCtx) {
    try {
      audioSourceNode = audioCtx.createMediaElementSource(audio);
      trackGainNode = audioCtx.createGain();
      masterGainNode = audioCtx.createGain();

      audioSourceNode.connect(trackGainNode);

      // Полная DSP-цепочка: Bass Boost -> 5 полос эквалайзера -> Лимитер (DSP как в Android)
      audioFx.init(audioCtx, trackGainNode, masterGainNode);

      masterGainNode.connect(audioCtx.destination);

      audio.volume = 1.0;
      masterGainNode.gain.setValueAtTime(state.isMuted ? 0 : state.volume, audioCtx.currentTime);
      isAudioGraphInitialized = true;
    } catch (e) {
      console.warn('Ошибка инициализации Web Audio API графа:', e);
    }
  }
}

export function applyTrackLoudnessGain(track) {
  ensureAudioGraph();

  const gainDb = track && typeof track.gain_db === 'number' ? track.gain_db : 0.0;
  const loudnessLufs = track && typeof track.loudness_lufs === 'number' ? track.loudness_lufs : null;

  updateState('currentTrackGain', gainDb);
  updateState('currentTrackLoudness', loudnessLufs);

  const isEnabled = state.isLoudnessNormalization;
  const targetLinearGain = isEnabled ? Math.pow(10, gainDb / 20.0) : 1.0;

  if (trackGainNode && audioCtx) {
    try {
      trackGainNode.gain.setTargetAtTime(targetLinearGain, audioCtx.currentTime, 0.04);
    } catch (e) {
      trackGainNode.gain.value = targetLinearGain;
    }
  } else if (audio) {
    audio.volume = state.isMuted ? 0 : Math.min(1.0, state.volume * targetLinearGain);
  }

  updateLoudnessBadgeUI();
}

export function toggleLoudnessNormalization() {
  const next = !state.isLoudnessNormalization;
  updateState('isLoudnessNormalization', next);
  localStorage.setItem('sentinel_loudness_norm', next ? 'true' : 'false');
  applyTrackLoudnessGain(state.currentTrack);
  const msg = next
    ? 'Нормализация громкости (EBU R128) включена'
    : 'Нормализация громкости отключена (исходный мастер)';
  window.dispatchEvent(new CustomEvent('loudness:changed', { detail: next }));
  updateLoudnessBadgeUI();
}

export function updateLoudnessBadgeUI() {
  const isEnabled = state.isLoudnessNormalization;
  const gain = state.currentTrackGain;
  const lufs = state.currentTrackLoudness;

  const btnMain = document.getElementById('btnLoudnessNorm');
  const btnExp = document.getElementById('btnExpandedLoudnessNorm');

  let title = 'Нормализация громкости EBU R128 (-14 LUFS): ';
  if (isEnabled) {
    title += 'ВКЛЮЧЕНА';
    if (lufs !== null) {
      const sign = gain >= 0 ? '+' : '';
      title += ` (Громкость: ${lufs} LUFS, поправка: ${sign}${gain} дБ)`;
    } else {
      title += ' (Трек еще не размечен, активен защитный пик-лимитер)';
    }
  } else {
    title += 'ВЫКЛЮЧЕНА (оригинальная громкость файла)';
  }

  [btnMain, btnExp].forEach(btn => {
    if (btn) {
      btn.classList.toggle('active', isEnabled);
      btn.title = title;
    }
  });

  // Синхронизируем тумблер и бейдж в окне настроек звука/эквалайзера
  const loudnessToggle = document.getElementById('loudnessPowerToggle');
  const loudnessStatus = document.getElementById('loudnessPowerStatus');
  const loudnessBadge = document.getElementById('loudnessTrackBadge');

  if (loudnessToggle) loudnessToggle.checked = isEnabled;
  if (loudnessStatus) {
    loudnessStatus.textContent = isEnabled ? 'Включена' : 'Выключена';
    loudnessStatus.style.color = isEnabled ? 'var(--accent-cyan)' : 'var(--text-muted)';
  }
  if (loudnessBadge) {
    if (!isEnabled) {
      loudnessBadge.textContent = 'Режим: Оригинальный уровень громкости (без коррекции)';
      loudnessBadge.style.color = 'var(--text-muted)';
    } else if (lufs !== null && lufs !== undefined) {
      const sign = (gain || 0) >= 0 ? '+' : '';
      loudnessBadge.textContent = `Текущий трек: ${lufs} LUFS (коррекция: ${sign}${gain} дБ до -14 LUFS)`;
      loudnessBadge.style.color = 'var(--accent-cyan)';
    } else {
      loudnessBadge.textContent = 'Текущий трек: без EBU-разметки (активен защитный пик-лимитер)';
      loudnessBadge.style.color = 'var(--text-secondary)';
    }
  }

  // Обновляем состояние единой кнопки эквалайзера в панели плеера
  const btnPlayerEq = document.getElementById('btnPlayerEqualizer');
  const btnExpandedEq = document.getElementById('btnExpandedEqualizer');
  const fxState = audioFx.getState();
  const isActive = fxState.isEnabled || fxState.currentLimiterMode !== 'off' || isEnabled;
  [btnPlayerEq, btnExpandedEq].forEach(btn => {
    if (btn) btn.classList.toggle('active', isActive);
  });
}

export function initPlayer() {
  audio = document.getElementById('audioElement');
  if (!audio) {
    audio = new Audio();
    audio.id = 'audioElement';
    document.body.appendChild(audio);
  }

  audio.crossOrigin = 'anonymous';
  audio.volume = state.volume;

  let lastTimeUpdateSave = 0;
  audio.addEventListener('timeupdate', () => {
    updateState('currentTime', audio.currentTime);
    updateTimelineUI();
    const now = Date.now();
    if (now - lastTimeUpdateSave > 1200) {
      lastTimeUpdateSave = now;
      savePlaybackSession(false);
    }
  });

  audio.addEventListener('loadedmetadata', () => {
    updateState('duration', audio.duration);
    updateTimelineUI();
    savePlaybackSession(false);
  });

  audio.addEventListener('play', () => {
    ensureAudioGraph();
    updateState('isPlaying', true);
    updatePlayButtonsUI(true);
  });

  audio.addEventListener('pause', () => {
    updateState('isPlaying', false);
    updatePlayButtonsUI(false);
    savePlaybackSession(true);
  });

  audio.addEventListener('seeked', () => {
    updateTimelineUI();
    savePlaybackSession(true);
  });

  window.addEventListener('beforeunload', () => savePlaybackSession(true));
  window.addEventListener('pagehide', () => savePlaybackSession(true));

  audio.addEventListener('ended', onTrackEnded);

  audio.addEventListener('error', (e) => {
    const err = audio.error;
    const current = state.currentTrack;
    console.warn('[Player] Ошибка воспроизведения медиаресурса:', err, current);

    updateState('isPlaying', false);
    updatePlayButtonsUI(false);

    if (current) {
      const trackName = `${current.artist || ''} - ${current.title || 'Трек'}`.trim();
      window.dispatchEvent(new CustomEvent('app:toast', {
        detail: `Аудиофайл «${trackName}» отсутствует на сервере (404) и удален из фонотеки`
      }));

      // Удаляем фантомный трек из локального состояния медиатеки и очереди
      if (current.id) {
        const updatedTracks = (state.tracks || []).filter(t => t.id !== current.id);
        const updatedQueue = (state.queue || []).filter(t => t.id !== current.id);
        updateState('tracks', updatedTracks);
        updateState('queue', updatedQueue);

        window.dispatchEvent(new CustomEvent('track:deleted', { detail: { trackId: current.id } }));
        window.dispatchEvent(new CustomEvent('queue:updated'));

        // Затемняем строку трека в текущем списке результатов
        const row = document.querySelector(`.track-row[data-id="${current.id}"]`);
        if (row) {
          row.style.opacity = '0.35';
          row.style.filter = 'grayscale(1)';
          row.style.pointerEvents = 'none';
          const titleCell = row.querySelector('.track-cell-title');
          if (titleCell && !titleCell.innerHTML.includes('(файл удален)')) {
            titleCell.innerHTML += ' <span style="font-size: 0.72rem; color: #ef4444; font-weight: normal;">(файл отсутствует на диске)</span>';
          }
        }
      }
    }
  });

  updateLoudnessBadgeUI();
}

export function shuffleListWithFirst(firstTrack, list) {
  if (!Array.isArray(list) || list.length <= 1) return list ? [...list] : [];
  const others = list.filter(t => t.id !== firstTrack.id);
  for (let i = others.length - 1; i > 0; i--) {
    const j = Math.floor(Math.random() * (i + 1));
    [others[i], others[j]] = [others[j], others[i]];
  }
  return [firstTrack, ...others];
}

let isInitializingShuffle = false;

/**
 * Инициализирует очередь перемешивания случайными треками со всего сервера (всей фонотеки).
 * Запускается асинхронно при старте трека с включенным режимом Shuffle,
 * гарантируя, что перемешивается вся коллекция, а не только текущая порция на экране.
 */
export async function initServerShuffleQueue(seedTrack) {
  if (!seedTrack || !state.isShuffle || state.activePlaylist || state.isStreamActive) return;
  if (isInitializingShuffle) return;
  isInitializingShuffle = true;

  try {
    const mood = state.streamMood && state.streamMood !== 'default' && state.streamMood !== 'all' ? state.streamMood : null;
    const serverTracks = await fetchShuffleTracks(50, mood, [seedTrack.id]);
    if (serverTracks && serverTracks.length > 0 && state.isShuffle && state.currentTrack && state.currentTrack.id === seedTrack.id && !state.activePlaylist && !state.isStreamActive) {
      const filtered = serverTracks.filter(t => t.id !== seedTrack.id);
      updateState('queue', [seedTrack, ...filtered]);
      updateState('queueIndex', 0);
      savePlaybackSession(true);
      console.log(`[Shuffle] Очередь случайного порядка обновлена со всего сервера (${filtered.length} треков)`);
    }
  } catch (err) {
    console.warn('[Shuffle] Ошибка загрузки серверного микса всей фонотеки:', err);
  } finally {
    isInitializingShuffle = false;
  }
}

export function playTrack(track, queueList = null, isStream = false, autoPlay = true, startPosition = 0) {
  if (!track) return;

  // Если был текущий трек и он отличается от нового, сохраняем его в историю
  if (state.currentTrack && state.currentTrack.id !== track.id) {
    const currentHist = Array.isArray(state.history) ? state.history : [];
    if (currentHist.length === 0 || currentHist[0].id !== state.currentTrack.id) {
      updateState('history', [state.currentTrack, ...currentHist].slice(0, 50));
    }
  }

  if (queueList) {
    const hasTrack = queueList.some(t => t.id === track.id);
    const effectiveQueue = hasTrack ? queueList : [track, ...queueList];
    if (state.isShuffle) {
      if (effectiveQueue.length > 1) {
        const shuffledQueue = shuffleListWithFirst(track, effectiveQueue);
        updateState('queue', shuffledQueue);
        updateState('queueIndex', 0);
      } else {
        updateState('queue', effectiveQueue);
        updateState('queueIndex', 0);
      }

      // Если режим Shuffle включен и мы в общей фонотеке (не в плейлисте и не в стриме):
      // наполняем очередь случайными треками со всего сервера (всей медиатеки)!
      if (!state.activePlaylist && !isStream) {
        initServerShuffleQueue(track);
      }
    } else {
      updateState('queue', effectiveQueue);
      const idx = effectiveQueue.findIndex(t => t.id === track.id);
      updateState('queueIndex', idx >= 0 ? idx : 0);
    }
  } else if (isStream) {
    // В режиме Потока добавляем каждый трек в очередь для сохранения истории
    const q = Array.isArray(state.queue) ? state.queue : [];
    if (q.length === 0 || q[q.length - 1].id !== track.id) {
      const newQ = [...q, track];
      updateState('queue', newQ);
      updateState('queueIndex', newQ.length - 1);
    }
  } else if (state.queue.length > 0) {
    const idx = state.queue.findIndex(t => t.id === track.id);
    if (idx >= 0) {
      updateState('queueIndex', idx);
    } else {
      // Трек не в текущей очереди: вставляем после текущего
      const newQ = [...state.queue];
      const insertAt = Math.max(0, state.queueIndex + 1);
      newQ.splice(insertAt, 0, track);
      updateState('queue', newQ);
      updateState('queueIndex', insertAt);
    }
    if (state.isShuffle && !state.activePlaylist && !isStream) {
      initServerShuffleQueue(track);
    }
  } else {
    updateState('queue', [track]);
    updateState('queueIndex', 0);
    if (state.isShuffle && !state.activePlaylist && !isStream) {
      initServerShuffleQueue(track);
    }
  }

  updateState('currentTrack', track);
  updateState('isStreamActive', isStream);
  updateState('currentTime', startPosition || 0);
  if (track.duration) {
    updateState('duration', track.duration);
  }
  updateState('activeLyricIndex', -1);

  // Сохраняем историю сессии Потока для защиты от повторов
  if (isStream && track && track.id > 0) {
    const recents = Array.isArray(state.recentStreamIds) ? [...state.recentStreamIds] : [];
    if (!recents.includes(track.id)) {
      recents.push(track.id);
      updateState('recentStreamIds', recents.slice(-50));
    }
  }

  const token = getAuthToken();
  const isPreview = track.preview_url || (track.id < 0 && track.file_path && track.file_path.startsWith('http'));
  const streamUrl = isPreview
    ? (track.preview_url || track.file_path)
    : `${API_BASE}/api/stream/${track.id}${token ? `?token=${token}` : ''}`;

  audio.src = streamUrl;

  if (startPosition > 0) {
    const applySeek = () => {
      try {
        audio.currentTime = startPosition;
        updateState('currentTime', startPosition);
        updateTimelineUI();
      } catch (e) {
        console.warn('[Player] Ошибка установки позиции воспроизведения:', e);
      }
    };
    if (audio.readyState >= 1) {
      applySeek();
    } else {
      audio.addEventListener('loadedmetadata', applySeek, { once: true });
    }
  }

  if (autoPlay) {
    audio.play().catch(e => {
      console.warn('Автовоспроизведение заблокировано браузером', e);
      updateState('isPlaying', false);
      updatePlayButtonsUI(false);
    });
    updateState('isPlaying', true);
    updatePlayButtonsUI(true);
  } else {
    audio.pause();
    updateState('isPlaying', false);
    updatePlayButtonsUI(false);
  }

  applyTrackLoudnessGain(track);

  if (track.is_discovery) {
    const reason = track.discovery_reason ? ` • ${track.discovery_reason}` : '';
    window.dispatchEvent(new CustomEvent('app:toast', {
      detail: `Новое открытие: ${track.artist} - ${track.title}${reason}`
    }));
  }

  updateTrackInfoUI(track);
  updateTimelineUI();
  setupMediaSession(track);

  // Оповещения об изменении трека и обновлении очереди
  window.dispatchEvent(new CustomEvent('track:changed', { detail: track }));
  window.dispatchEvent(new CustomEvent('queue:updated'));
  savePlaybackSession(true);
}

export function togglePlay() {
  if (!audio.src && state.tracks.length > 0) {
    playTrack(state.tracks[0], state.tracks);
    return;
  }
  if (audio.paused) {
    audio.play().catch(() => {});
  } else {
    audio.pause();
  }
}

export async function nextTrack() {
  if (state.isStreamActive) {
    window.dispatchEvent(new CustomEvent('stream:request-next'));
    return;
  }

  if (state.queue.length === 0) return;

  // Динамическая серверная подгрузка для бесконечного воспроизведения Shuffle
  if (state.isShuffle && !state.activePlaylist && state.queueIndex >= state.queue.length - 3) {
    try {
      const existingIds = state.queue.map(t => t.id);
      const mood = state.streamMood && state.streamMood !== 'default' && state.streamMood !== 'all' ? state.streamMood : null;
      const more = await fetchShuffleTracks(30, mood, existingIds.slice(-100));
      if (more && more.length > 0) {
        const existingSet = new Set(existingIds);
        const filtered = more.filter(t => !existingSet.has(t.id));
        if (filtered.length > 0) {
          updateState('queue', [...state.queue, ...filtered]);
        }
      }
    } catch (e) {
      console.warn('Ошибка автоподгрузки shuffle очереди:', e);
    }
  }

  let nextIdx = state.queueIndex + 1;
  if (nextIdx >= state.queue.length) {
    if (state.repeatMode === 'all') {
      if (state.isShuffle && state.queue.length > 1) {
        const reShuffled = shuffleListWithFirst(state.queue[0], state.queue);
        updateState('queue', reShuffled);
      }
      nextIdx = 0;
    } else {
      return;
    }
  }

  updateState('queueIndex', nextIdx);
  playTrack(state.queue[nextIdx]);
}

export function prevTrack() {
  if (audio && audio.currentTime > 3) {
    audio.currentTime = 0;
    return;
  }

  if (state.queue.length === 0) return;

  let prevIdx = state.queueIndex - 1;
  if (prevIdx < 0) {
    if (state.history && state.history.length > 0) {
      const prevTrackFromHistory = state.history[0];
      updateState('history', state.history.slice(1));
      const newQueue = [prevTrackFromHistory, ...state.queue];
      updateState('queue', newQueue);
      updateState('queueIndex', 0);
      playTrack(prevTrackFromHistory);
      return;
    }
    prevIdx = state.repeatMode === 'all' ? state.queue.length - 1 : 0;
  }

  updateState('queueIndex', prevIdx);
  playTrack(state.queue[prevIdx]);
}

export function seekPercentage(pct) {
  if (!audio || !audio.duration) return;
  audio.currentTime = Math.max(0, Math.min(1, pct)) * audio.duration;
}

export function seekTime(seconds) {
  if (!audio) return;
  audio.currentTime = seconds;
}

export function setVolume(val) {
  const v = Math.max(0, Math.min(1, val));
  updateState('volume', v);
  try {
    localStorage.setItem('sentinel_volume', v.toString());
  } catch (_) {}
  ensureAudioGraph();
  if (masterGainNode && audioCtx) {
    if (audio) audio.volume = 1.0;
    try {
      masterGainNode.gain.setTargetAtTime(state.isMuted ? 0 : v, audioCtx.currentTime, 0.02);
    } catch (e) {
      masterGainNode.gain.value = state.isMuted ? 0 : v;
    }
  } else if (audio) {
    audio.volume = v;
  }
  const fill = document.getElementById('volumeFill');
  if (fill) fill.style.width = `${v * 100}%`;
  const expFill = document.getElementById('expandedVolumeFill');
  if (expFill) expFill.style.width = `${v * 100}%`;
}

export function toggleMute() {
  const nextMuted = !state.isMuted;
  updateState('isMuted', nextMuted);
  try {
    localStorage.setItem('sentinel_muted', nextMuted ? 'true' : 'false');
  } catch (_) {}
  ensureAudioGraph();
  if (masterGainNode && audioCtx) {
    if (audio) audio.volume = 1.0;
    try {
      masterGainNode.gain.setTargetAtTime(nextMuted ? 0 : state.volume, audioCtx.currentTime, 0.02);
    } catch (e) {
      masterGainNode.gain.value = nextMuted ? 0 : state.volume;
    }
  }
  if (audio) {
    audio.muted = nextMuted;
  }
  const fill = document.getElementById('volumeFill');
  if (fill) fill.style.width = nextMuted ? '0%' : `${state.volume * 100}%`;
  const expFill = document.getElementById('expandedVolumeFill');
  if (expFill) expFill.style.width = nextMuted ? '0%' : `${state.volume * 100}%`;
}

export async function toggleShuffle() {
  const next = !state.isShuffle;
  updateState('isShuffle', next);
  const btn = document.getElementById('btnShuffle');
  if (btn) btn.classList.toggle('active', next);
  savePlaybackSession(true);

  if (next) {
    window.dispatchEvent(new CustomEvent('app:toast', { detail: 'Случайный порядок включен' }));
    if (state.currentTrack && state.queue && state.queue.length > 1) {
      const shuffled = shuffleListWithFirst(state.currentTrack, state.queue);
      updateState('queue', shuffled);
      updateState('queueIndex', 0);
      savePlaybackSession(true);
      if (!state.activePlaylist && !state.isStreamActive) {
        initServerShuffleQueue(state.currentTrack);
      }
    } else if (!state.activePlaylist && !state.isStreamActive) {
      if (state.currentTrack) {
        initServerShuffleQueue(state.currentTrack);
      } else if (!state.isPlaying) {
        await playShuffleTracks();
      }
    }
  } else {
    window.dispatchEvent(new CustomEvent('app:toast', { detail: 'Случайный порядок выключен' }));
  }
}

export async function playShuffleTracks(mood = null) {
  try {
    const shuffled = await fetchShuffleTracks(50, mood);
    if (!shuffled || shuffled.length === 0) return;

    updateState('isShuffle', true);
    const btn = document.getElementById('btnShuffle');
    if (btn) btn.classList.add('active');

    playTrack(shuffled[0], shuffled, false);
    const moodNameMap = { energy: 'бодрых треков', chill: 'спокойных треков', happy: 'радостных треков', sad: 'грустных треков' };
    const label = mood && moodNameMap[mood] ? `Запущен случайный микс ${moodNameMap[mood]}` : 'Запущен случайный микс всей фонотеки';
    window.dispatchEvent(new CustomEvent('app:toast', { detail: label }));
  } catch (err) {
    console.error('Ошибка запуска серверного шаффла:', err);
  }
}

export function toggleRepeat() {
  const modes = ['off', 'all', 'one'];
  const cur = modes.indexOf(state.repeatMode);
  const next = modes[(cur + 1) % modes.length];
  updateState('repeatMode', next);
  try {
    localStorage.setItem('sentinel_repeat_mode', next);
  } catch (_) {}
  const btn = document.getElementById('btnRepeat');
  if (btn) {
    btn.classList.toggle('active', next !== 'off');
    btn.innerHTML = next === 'one' ? icon('repeatOne', { size: 17 }) : icon('repeat', { size: 17 });
  }
  savePlaybackSession(true);
}

function onTrackEnded() {
  if (state.repeatMode === 'one') {
    audio.currentTime = 0;
    audio.play();
  } else {
    nextTrack();
  }
}

export function formatTime(seconds) {
  if (!seconds || isNaN(seconds)) return '0:00';
  const m = Math.floor(seconds / 60);
  const s = Math.floor(seconds % 60);
  return `${m}:${s < 10 ? '0' : ''}${s}`;
}

export function updateTimelineUI() {
  const cur = document.getElementById('timeCurrent');
  const dur = document.getElementById('timeTotal');
  const fill = document.getElementById('timelineFill');

  const curSec = (audio && !isNaN(audio.currentTime) && audio.currentTime > 0) ? audio.currentTime : (state.currentTime || 0);
  const durSec = (audio && !isNaN(audio.duration) && audio.duration > 0) ? audio.duration : (state.duration || (state.currentTrack ? state.currentTrack.duration : 0));

  if (cur) cur.textContent = formatTime(curSec);
  if (dur && durSec > 0) dur.textContent = formatTime(durSec);
  if (fill && durSec > 0) {
    const pct = (curSec / durSec) * 100;
    fill.style.width = `${Math.min(100, Math.max(0, pct))}%`;
  }
}

export function updatePlayButtonsUI(isPlaying) {
  const mainBtn = document.getElementById('ctrlPlayBtn');
  const orbBtn = document.getElementById('streamOrbBtn') || document.getElementById('streamOrbLargeBtn');
  const orb = document.getElementById('streamOrb');

  if (mainBtn) mainBtn.innerHTML = isPlaying ? icon('pause', { size: 18 }) : icon('play', { size: 18 });
  if (orbBtn) orbBtn.innerHTML = isPlaying ? icon('pause', { size: 24 }) : icon('play', { size: 24 });
  if (orb) orb.classList.toggle('playing', isPlaying);
}

export function updateTrackInfoUI(track) {
  const title = document.getElementById('playerTrackTitle');
  const artist = document.getElementById('playerTrackArtist');
  const cover = document.getElementById('playerTrackCover');

  if (title) title.textContent = track.title;
  if (artist) artist.textContent = track.artist;
  if (cover) {
    if (track.cover_url) {
      cover.src = track.cover_url;
    } else {
      cover.src = `${API_BASE}/api/covers/${track.id}`;
    }
    cover.style.display = 'block';
  }

  // Сквозная синхронизация состояния лайка во всех компонентах интерфейса
  syncTrackReactionUI(track.id, !!track.is_liked, !!track.is_disliked);
}

function setupMediaSession(track) {
  if ('mediaSession' in navigator) {
    navigator.mediaSession.metadata = new MediaMetadata({
      title: track.title,
      artist: track.artist,
      album: track.album || 'Фонотека',
      artwork: [{ src: `${API_BASE}/api/covers/${track.id}`, sizes: '512x512', type: 'image/jpeg' }]
    });

    navigator.mediaSession.setActionHandler('play', togglePlay);
    navigator.mediaSession.setActionHandler('pause', togglePlay);
    navigator.mediaSession.setActionHandler('previoustrack', prevTrack);
    navigator.mediaSession.setActionHandler('nexttrack', nextTrack);
  }
}

/**
 * Добавление трека в конец очереди воспроизведения.
 */
export function addToQueue(track) {
  if (!track) return;

  if (!state.currentTrack || !audio || !audio.src) {
    playTrack(track, [track], false);
    window.dispatchEvent(new CustomEvent('app:toast', { detail: `Воспроизведение «${track.title}»` }));
    return;
  }

  const currentQueue = Array.isArray(state.queue) ? [...state.queue] : [];
  currentQueue.push(track);
  updateState('queue', currentQueue);
  window.dispatchEvent(new CustomEvent('queue:updated'));
  window.dispatchEvent(new CustomEvent('app:toast', { detail: `«${track.title}» добавлен в очередь` }));
}

/**
 * Вставка трека для воспроизведения следующим.
 */
export function playNextInQueue(track) {
  if (!track) return;

  if (!state.currentTrack || !audio || !audio.src) {
    playTrack(track, [track], false);
    window.dispatchEvent(new CustomEvent('app:toast', { detail: `Воспроизведение «${track.title}»` }));
    return;
  }

  const currentQueue = Array.isArray(state.queue) ? [...state.queue] : [];
  const insertIndex = Math.max(0, state.queueIndex + 1);
  currentQueue.splice(insertIndex, 0, track);
  updateState('queue', currentQueue);
  window.dispatchEvent(new CustomEvent('queue:updated'));
  window.dispatchEvent(new CustomEvent('app:toast', { detail: `«${track.title}» будет воспроизведен следующим` }));
}

/**
 * Удаление трека из списка предстоящих (Upcoming) очереди.
 */
export function removeFromQueue(relativeUpcomingIndex) {
  const currentQueue = Array.isArray(state.queue) ? [...state.queue] : [];
  const absoluteIndex = state.queueIndex + 1 + relativeUpcomingIndex;
  if (absoluteIndex >= 0 && absoluteIndex < currentQueue.length) {
    const removed = currentQueue.splice(absoluteIndex, 1)[0];
    updateState('queue', currentQueue);
    window.dispatchEvent(new CustomEvent('queue:updated'));
    if (removed) {
      window.dispatchEvent(new CustomEvent('app:toast', { detail: `Удалено из очереди: «${removed.title}»` }));
    }
  }
}

/**
 * Очистка всех предстоящих треков в очереди.
 */
export function clearUpcomingQueue() {
  if (!state.queue || state.queue.length === 0) return;
  const kept = state.queue.slice(0, state.queueIndex + 1);
  updateState('queue', kept);
  window.dispatchEvent(new CustomEvent('queue:updated'));
  window.dispatchEvent(new CustomEvent('app:toast', { detail: 'Очередь следующих треков очищена' }));
}

/**
 * Очистка истории воспроизведения.
 */
export function clearHistory() {
  updateState('history', []);
  if (state.queue && state.queue.length > 0 && state.queueIndex > 0) {
    const kept = state.queue.slice(state.queueIndex);
    updateState('queue', kept);
    updateState('queueIndex', 0);
  }
  window.dispatchEvent(new CustomEvent('queue:updated'));
  window.dispatchEvent(new CustomEvent('app:toast', { detail: 'История воспроизведения очищена' }));
}

/**
 * Прямой переход к треку в очереди по абсолютному индексу.
 */
export function playQueueTrackAt(absoluteIndex) {
  if (!state.queue || absoluteIndex < 0 || absoluteIndex >= state.queue.length) return;
  updateState('queueIndex', absoluteIndex);
  playTrack(state.queue[absoluteIndex]);
}

/**
 * Воспроизведение трека из истории.
 */
export function playHistoryTrack(track) {
  if (!track) return;
  playNextInQueue(track);
  nextTrack();
}

/**
 * Очистка удаленного трека из текущего воспроизведения, очереди и истории.
 */
export function handleTrackDeleted(trackId) {
  // 1. Если удаленный трек играет прямо сейчас
  if (state.currentTrack && state.currentTrack.id === trackId) {
    if (state.queue && state.queue.length > 1) {
      nextTrack();
    } else {
      if (audio) {
        audio.pause();
        audio.src = '';
      }
      updateState('currentTrack', null);
      updateState('isPlaying', false);
    }
  }

  // 2. Удаляем из очереди воспроизведения
  if (Array.isArray(state.queue)) {
    const newQueue = state.queue.filter(t => t.id !== trackId);
    if (newQueue.length !== state.queue.length) {
      updateState('queue', newQueue);
      if (state.queueIndex >= newQueue.length) {
        updateState('queueIndex', Math.max(0, newQueue.length - 1));
      }
      window.dispatchEvent(new CustomEvent('queue:updated'));
    }
  }

  // 3. Удаляем из истории
  if (Array.isArray(state.history)) {
    const newHist = state.history.filter(t => t.id !== trackId);
    if (newHist.length !== state.history.length) {
      updateState('history', newHist);
      window.dispatchEvent(new CustomEvent('queue:updated'));
    }
  }
}

let lastSavePlaybackTime = 0;

/**
 * Сохраняет текущую сессию воспроизведения (трек, очередь, позиция, настройки) в localStorage браузера.
 */
export function savePlaybackSession(force = false, customTimestamp = null) {
  if (!state.currentTrack) {
    try {
      localStorage.removeItem('sentinel_playback_session');
    } catch (_) {}
    return;
  }

  const now = customTimestamp || Date.now();
  if (!force && !customTimestamp && Date.now() - lastSavePlaybackTime < 1000) {
    return;
  }
  if (!customTimestamp) {
    lastSavePlaybackTime = Date.now();
  }

  try {
    const curTime = (audio && !isNaN(audio.currentTime) && audio.currentTime > 0) ? audio.currentTime : (state.currentTime || 0);
    const durTime = (audio && !isNaN(audio.duration) && audio.duration > 0) ? audio.duration : (state.duration || (state.currentTrack ? state.currentTrack.duration : 0));

    const session = {
      currentTrack: state.currentTrack,
      queue: Array.isArray(state.queue) ? state.queue.slice(0, 500) : [],
      queueIndex: typeof state.queueIndex === 'number' ? state.queueIndex : 0,
      currentTime: curTime,
      duration: durTime,
      isShuffle: Boolean(state.isShuffle),
      repeatMode: state.repeatMode || 'off',
      history: Array.isArray(state.history) ? state.history.slice(0, 50) : [],
      timestamp: now
    };
    localStorage.setItem('sentinel_playback_session', JSON.stringify(session));
  } catch (err) {
    console.warn('[Player] Не удалось сохранить сессию воспроизведения в localStorage:', err);
  }
}

/**
 * Восстанавливает сохраненную сессию воспроизведения из localStorage при загрузке или F5.
 */
export function restorePlaybackSession() {
  try {
    const raw = localStorage.getItem('sentinel_playback_session');
    if (!raw) return false;
    const session = JSON.parse(raw);
    if (!session || !session.currentTrack) return false;

    if (session.repeatMode) {
      updateState('repeatMode', session.repeatMode);
      const btnRepeat = document.getElementById('btnRepeat');
      if (btnRepeat) {
        btnRepeat.classList.toggle('active', session.repeatMode !== 'off');
        btnRepeat.innerHTML = session.repeatMode === 'one' ? icon('repeatOne', { size: 17 }) : icon('repeat', { size: 17 });
      }
    }
    if (typeof session.isShuffle === 'boolean') {
      updateState('isShuffle', session.isShuffle);
      const btnShuffle = document.getElementById('btnShuffle');
      if (btnShuffle) btnShuffle.classList.toggle('active', session.isShuffle);
    }
    if (Array.isArray(session.history)) {
      updateState('history', session.history);
    }

    const queue = Array.isArray(session.queue) && session.queue.length > 0 ? session.queue : [session.currentTrack];
    const qIndex = typeof session.queueIndex === 'number' && session.queueIndex >= 0 && session.queueIndex < queue.length
      ? session.queueIndex
      : Math.max(0, queue.findIndex(t => t.id === session.currentTrack.id));

    const pos = typeof session.currentTime === 'number' && session.currentTime > 0 ? session.currentTime : 0;
    const originalTimestamp = session.timestamp || 0;

    // Выставляем очередь и индекс до playTrack
    updateState('queue', queue);
    updateState('queueIndex', qIndex);

    // Восстанавливаем плеер в режиме паузы на точной секунде (autoPlay = false)
    playTrack(session.currentTrack, null, false, false, pos);

    // Гарантируем сохранение очереди и индекса
    updateState('queue', queue);
    updateState('queueIndex', qIndex);

    // Обновляем отображение очереди
    window.dispatchEvent(new CustomEvent('queue:updated'));

    // Восстанавливаем исходный timestamp сессии, чтобы не затирать реальное время последнего прослушивания
    savePlaybackSession(true, originalTimestamp);

    console.log('[Player] Сессия успешно восстановлена из localStorage:', session.currentTrack.title, `(${pos}с, треков в очереди: ${queue.length})`);
    return true;
  } catch (err) {
    console.warn('[Player] Ошибка при восстановлении сессии воспроизведения:', err);
    return false;
  }
}

/**
 * Восстанавливает воспроизведение из серверной сессии (Handoff с Android-устройства).
 */
export function restorePlaybackFromRemote(session) {
  if (!session || !session.current_track) return false;
  try {
    const track = session.current_track;
    const queue = Array.isArray(session.queue) && session.queue.length > 0 ? session.queue : [track];
    const qIndex = Math.max(0, queue.findIndex(t => t.id === track.id));
    const posSec = (session.position_ms || 0) / 1000.0;
    const remoteTimestamp = session.saved_at ? (session.saved_at * 1000) : Date.now();

    updateState('queue', queue);
    updateState('queueIndex', qIndex);
    playTrack(track, null, false, false, posSec);
    updateState('queue', queue);
    updateState('queueIndex', qIndex);
    window.dispatchEvent(new CustomEvent('queue:updated'));
    savePlaybackSession(true, remoteTimestamp);
    console.log('[Player] Серверная сессия (Handoff) успешно восстановлена:', track.title, `(${posSec}с, треков в очереди: ${queue.length})`);
    return true;
  } catch (err) {
    console.warn('[Player] Ошибка восстановления серверной сессии:', err);
    return false;
  }
}

