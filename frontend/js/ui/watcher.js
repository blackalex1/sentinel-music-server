/**
 * Модуль фонового опроса Watchdog и автообновления фонотеки при скачивании новых треков.
 */

import { state } from '../state.js';
import { fetchWatcherStatus } from '../api.js';
import { showToast } from './toast.js';
import { loadRecentTracks, loadLibraryTracks, setTotalTracksCount, loadMoodCollectionCounts } from './trackList.js';
import { loadDuplicates } from './duplicates.js';

let lastKnownTracksCount = null;

export function setupWatcherPolling() {
  async function check() {
    if (!state.isAuthenticated) return;
    try {
      const status = await fetchWatcherStatus();
      const dot = document.getElementById('watcherStatusDot');
      const label = document.getElementById('watcherStatusLabel');

      if (status && status.running) {
        if (dot) dot.style.background = '#00d26a';
        if (label) label.textContent = 'Автосканирование активно';
      } else if (status) {
        if (dot) dot.style.background = '#888';
        if (label) label.textContent = 'Фонотека синхронизирована';
      }

      if (status && typeof status.total_tracks === 'number') {
        if (lastKnownTracksCount !== null && status.total_tracks > lastKnownTracksCount) {
          const added = status.total_tracks - lastKnownTracksCount;
          setTotalTracksCount(status.total_tracks);

          // Обновляем заголовок счетчика треков
          const titleEl = document.getElementById('tracksViewTitle');
          if (titleEl) {
            titleEl.textContent = `Коллекция треков (${status.total_tracks.toLocaleString('ru-RU')} треков)`;
          }

          // Показываем уведомление (Toast)
          if (status.last_track && status.last_track.title) {
            showToast(`Скачан новый трек: ${status.last_track.artist} — ${status.last_track.title}`, 'sparkles');
          } else {
            showToast(`Фонотека обновлена (+${added} трек)`, 'sparkles');
          }

          await loadRecentTracks();
          loadMoodCollectionCounts();
          if (state.currentView === 'duplicates') {
            loadDuplicates();
          }

          // Если сейчас открыта страница всей коллекции и нет активного поиска/плейлиста —
          // мягко обновляем треки, чтобы новинки появились вверху
          const tracksSection = document.getElementById('viewTracks');
          if (tracksSection && tracksSection.style.display !== 'none' && !state.searchQuery && !state.activePlaylist) {
            await loadLibraryTracks(true, true);
          }
        }
        lastKnownTracksCount = status.total_tracks;
      }
    } catch (e) {}
  }

  check();
  setInterval(check, 4000);
}
