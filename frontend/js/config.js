/**
 * Модуль конфигурации и управления токенами сессий.
 */

export const isTauri = typeof window !== 'undefined' && (
  !!window.__TAURI_INTERNALS__ ||
  !!window.__TAURI__ ||
  (window.location && (window.location.origin.includes('tauri') || window.location.protocol === 'tauri:' || window.location.origin.includes('1420')))
);

// Динамическое определение базового адреса API (без хардкода IP)
export const API_BASE = (!isTauri && typeof window !== 'undefined' && window.location && window.location.origin && window.location.protocol.startsWith('http'))
  ? window.location.origin
  : (localStorage.getItem('music_server_host') || 'http://localhost:8000');

export function setServerHost(host) {
  let cleaned = host.trim().replace(/\/+$/, '');
  if (!cleaned.startsWith('http://') && !cleaned.startsWith('https://')) {
    cleaned = 'http://' + cleaned;
  }
  localStorage.setItem('music_server_host', cleaned);
}

export function getServerHost() {
  return (!isTauri && typeof window !== 'undefined' && window.location && window.location.origin && window.location.protocol.startsWith('http'))
    ? window.location.origin
    : (localStorage.getItem('music_server_host') || 'http://localhost:8000');
}

export function getAuthToken() {
  return localStorage.getItem('music_service_token') || '';
}

export function setAuthToken(token) {
  if (token) {
    localStorage.setItem('music_service_token', token);
  } else {
    localStorage.removeItem('music_service_token');
  }
}

export function clearAuthToken() {
  localStorage.removeItem('music_service_token');
}

export function getCurrentUser() {
  const data = localStorage.getItem('music_service_user');
  return data ? JSON.parse(data) : null;
}

export function setCurrentUser(user) {
  if (user) {
    localStorage.setItem('music_service_user', JSON.stringify(user));
  } else {
    localStorage.removeItem('music_service_user');
  }
}
