/**
 * Модуль клиентских REST API запросов.
 */

import { API_BASE, getAuthToken, clearAuthToken } from './config.js';

export async function apiFetch(path, options = {}) {
  const token = getAuthToken();
  const headers = { ...(options.headers || {}) };

  if (token) {
    headers['Authorization'] = `Bearer ${token}`;
  }

  const url = path.startsWith('http') ? path : `${API_BASE}${path}`;
  const response = await fetch(url, { ...options, headers });

  if (response.status === 401) {
    // Токен истек или недействителен
    clearAuthToken();
    window.dispatchEvent(new CustomEvent('auth:required'));
  }

  return response;
}

export async function checkAuthStatus() {
  const res = await fetch(`${API_BASE}/api/auth/status`);
  return res.json();
}

export async function apiLogin(username, password) {
  const res = await fetch(`${API_BASE}/api/auth/login`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ username, password, device_name: 'Web / Sentinel Music' })
  });
  return res;
}

export async function apiRegister(username, password) {
  const res = await fetch(`${API_BASE}/api/auth/register`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ username, password })
  });
  return res;
}

export async function apiLogout() {
  return apiFetch('/api/auth/logout', { method: 'POST' });
}

export async function fetchQrCode(host = null, createNewSession = true) {
  const params = new URLSearchParams();
  if (host) params.append('host', host);
  if (createNewSession !== undefined) params.append('create_new_session', createNewSession);
  const query = params.toString() ? `?${params.toString()}` : '';
  const res = await apiFetch(`/api/auth/qr/code${query}`);
  return res.json();
}

export async function fetchQrHosts() {
  const res = await apiFetch('/api/auth/qr/hosts');
  return res.json();
}

export async function fetchTracks(query = '', limit = 50, offset = 0, sort = 'recent', mood = null) {
  const effectiveLimit = query ? Math.min(limit, 100) : limit;
  let path = query
    ? `/api/tracks/search?q=${encodeURIComponent(query)}&limit=${effectiveLimit}&offset=${offset}`
    : `/api/tracks?limit=${limit}&offset=${offset}&sort=${sort}`;
  if (mood && mood !== 'default') {
    path += `&mood=${encodeURIComponent(mood)}`;
  }
  const res = await apiFetch(path);
  if (!res.ok) return [];
  return res.json();
}

export async function fetchRecentTracks(limit = 50, mood = null, offset = 0) {
  let url = `/api/tracks/recent?limit=${limit}&offset=${offset}`;
  if (mood && mood !== 'default' && mood !== 'all') {
    url += `&mood=${encodeURIComponent(mood)}`;
  }
  const res = await apiFetch(url);
  if (!res.ok) return [];
  return res.json();
}

export async function fetchTracksCount(mood = null) {
  let url = '/api/tracks/count';
  if (mood && mood !== 'default' && mood !== 'all') {
    url += `?mood=${encodeURIComponent(mood)}`;
  }
  const res = await apiFetch(url);
  if (!res.ok) return { count: 0 };
  return res.json();
}

export async function fetchShuffleTracks(limit = 50, mood = null) {
  let url = `/api/tracks/shuffle?limit=${limit}`;
  if (mood && mood !== 'default' && mood !== 'all') {
    url += `&mood=${encodeURIComponent(mood)}`;
  }
  const res = await apiFetch(url);
  if (!res.ok) return [];
  return res.json();
}

export async function fetchPlaylists() {
  const res = await apiFetch('/api/playlists');
  if (!res.ok) return [];
  return res.json();
}

export async function createPlaylist(title) {
  const res = await apiFetch('/api/playlists', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ title })
  });
  return res.json();
}

export async function addTrackToPlaylist(playlistId, trackId) {
  const res = await apiFetch(`/api/playlists/${playlistId}/tracks`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ track_id: trackId })
  });
  return res.json();
}

export async function fetchPlaylistDetails(playlistId) {
  const res = await apiFetch(`/api/playlists/${playlistId}`);
  if (!res.ok) return null;
  return res.json();
}

export async function fetchStreamNext(optionsOrCurrentTrackId = null, moodEnergyFallback = null) {
  let url = '/api/stream/next';
  const params = [];

  if (typeof optionsOrCurrentTrackId === 'object' && optionsOrCurrentTrackId !== null) {
    const {
      currentTrackId,
      mood = 'default',
      moodEnergy,
      recentIds,
      discoveryRatio = 0.2,
      consecutiveArtist,
      consecutiveCount
    } = optionsOrCurrentTrackId;

    if (currentTrackId) params.push(`current_track_id=${currentTrackId}`);
    if (mood) params.push(`mood=${encodeURIComponent(mood)}`);
    if (moodEnergy !== null && moodEnergy !== undefined) params.push(`mood_energy=${moodEnergy}`);
    if (recentIds && recentIds.length > 0) params.push(`recent_ids=${recentIds.join(',')}`);
    if (discoveryRatio !== undefined && discoveryRatio !== null) params.push(`discovery_ratio=${discoveryRatio}`);
    if (consecutiveArtist) params.push(`consecutive_artist=${encodeURIComponent(consecutiveArtist)}`);
    if (consecutiveCount) params.push(`consecutive_count=${consecutiveCount}`);
  } else {
    // Обратная совместимость для сигнатуры (currentTrackId, moodEnergy)
    if (optionsOrCurrentTrackId) params.push(`current_track_id=${optionsOrCurrentTrackId}`);
    if (moodEnergyFallback !== null && moodEnergyFallback !== undefined) params.push(`mood_energy=${moodEnergyFallback}`);
  }

  if (params.length > 0) url += `?${params.join('&')}`;
  const res = await apiFetch(url);
  if (!res.ok) return null;
  return res.json();
}

export async function fetchAnalyticsStatus() {
  const res = await apiFetch('/api/stream/analytics/status');
  if (!res.ok) return null;
  return res.json();
}

export async function startAnalytics() {
  const res = await apiFetch('/api/stream/analytics/start', { method: 'POST' });
  if (!res.ok) return null;
  return res.json();
}

export async function stopAnalytics() {
  const res = await apiFetch('/api/stream/analytics/stop', { method: 'POST' });
  if (!res.ok) return null;
  return res.json();
}

export async function fetchDiscoveryCandidates() {
  const res = await apiFetch('/api/stream/discovery/candidates');
  if (!res.ok) return null;
  return res.json();
}

export async function importDiscoveryTrack(artist, title) {
  const res = await apiFetch('/api/stream/discovery/import', {
    method: 'POST',
    body: JSON.stringify({ artist, title })
  });
  if (!res.ok) return null;
  return res.json();
}

export async function sendReaction(trackId, isLike) {
  const res = await apiFetch(`/api/reaction/${trackId}?is_like=${isLike}`, {
    method: 'POST'
  });
  if (!res.ok) return null;
  return res.json();
}

export async function fetchLyrics(trackId) {
  const res = await apiFetch(`/api/lyrics/${trackId}`);
  if (!res.ok) return null;
  return res.json();
}

export async function fetchWatcherStatus() {
  const res = await apiFetch('/api/watcher');
  if (!res.ok) return null;
  return res.json();
}

export async function fetchTrackCandidates(trackId, limit = 5) {
  const res = await apiFetch(`/api/tracks/${trackId}/candidates?limit=${limit}`);
  if (!res.ok) return null;
  return res.json();
}

export async function replaceTrackWithCandidate(trackId, candidate) {
  const res = await apiFetch(`/api/tracks/${trackId}/replace`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ candidate })
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: 'Ошибка сервера' }));
    throw new Error(err.detail || 'Не удалось заменить трек');
  }
  return res.json();
}

export async function searchCandidates(artist = '', title = '', q = '', limit = 5, options = {}) {
  let url = `/api/tracks/candidates/search?limit=${limit}`;
  if (artist) url += `&artist=${encodeURIComponent(artist)}`;
  if (title) url += `&title=${encodeURIComponent(title)}`;
  if (q) url += `&q=${encodeURIComponent(q)}`;
  const res = await apiFetch(url, options);
  if (!res.ok) return null;
  return res.json();
}

export async function downloadCandidate(candidate) {
  const res = await apiFetch('/api/tracks/candidates/download', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ candidate })
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: 'Ошибка сервера' }));
    throw new Error(err.detail || 'Не удалось скачать трек');
  }
  return res.json();
}

export async function deleteTrack(trackId, deleteFile = true) {
  const res = await apiFetch(`/api/tracks/${trackId}?delete_file=${deleteFile}`, {
    method: 'DELETE'
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: 'Ошибка сервера' }));
    throw new Error(err.detail || 'Не удалось удалить трек');
  }
  return res.json();
}

export async function removeTrackFromPlaylist(playlistId, trackId) {
  const res = await apiFetch(`/api/playlists/${playlistId}/tracks/${trackId}`, {
    method: 'DELETE'
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: 'Ошибка сервера' }));
    throw new Error(err.detail || 'Не удалось удалить трек из плейлиста');
  }
  return res.json();
}

export function uploadTrackFiles(fileList, onProgress = null) {
  return new Promise((resolve, reject) => {
    const formData = new FormData();
    for (let i = 0; i < fileList.length; i++) {
      formData.append('files', fileList[i]);
    }

    const xhr = new XMLHttpRequest();
    const token = getAuthToken();
    const url = `${API_BASE}/api/tracks/upload`;

    xhr.open('POST', url, true);
    if (token) {
      xhr.setRequestHeader('Authorization', `Bearer ${token}`);
    }

    if (xhr.upload && onProgress) {
      xhr.upload.onprogress = (e) => {
        if (e.lengthComputable) {
          const percent = Math.round((e.loaded / e.total) * 100);
          onProgress(percent, e.loaded, e.total);
        }
      };
    }

    xhr.onload = () => {
      if (xhr.status >= 200 && xhr.status < 300) {
        try {
          const data = JSON.parse(xhr.responseText);
          resolve(data);
        } catch (e) {
          resolve({ status: 'ok' });
        }
      } else if (xhr.status === 401) {
        clearAuthToken();
        window.dispatchEvent(new CustomEvent('auth:required'));
        reject(new Error('Необходима авторизация'));
      } else {
        try {
          const err = JSON.parse(xhr.responseText);
          reject(new Error(err.detail || `Ошибка сервера: HTTP ${xhr.status}`));
        } catch (e) {
          reject(new Error(`Ошибка сервера: HTTP ${xhr.status}`));
        }
      }
    };

    xhr.onerror = () => {
      reject(new Error('Сетевая ошибка при загрузке аудиофайлов'));
    };

    xhr.send(formData);
  });
}

export async function fetchDuplicates(query = '') {
  let url = '/api/tracks/duplicates';
  if (query) url += `?q=${encodeURIComponent(query)}`;
  const res = await apiFetch(url);
  if (!res.ok) return { total_groups: 0, total_extra_tracks: 0, potential_saved_bytes: 0, groups: [] };
  return res.json();
}

export async function deleteDuplicatesBatch(trackIds, deleteFiles = true) {
  const res = await apiFetch('/api/tracks/duplicates/delete', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ track_ids: trackIds, delete_files: deleteFiles })
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: 'Ошибка сервера' }));
    throw new Error(err.detail || 'Не удалось удалить дубликаты');
  }
  return res.json();
}

export async function resolveDuplicateGroup(keepTrackId, deleteTrackIds, deleteFiles = true) {
  const res = await apiFetch('/api/tracks/duplicates/resolve-group', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ keep_track_id: keepTrackId, delete_track_ids: deleteTrackIds, delete_files: deleteFiles })
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: 'Ошибка сервера' }));
    throw new Error(err.detail || 'Не удалось разрешить группу дубликатов');
  }
  return res.json();
}



