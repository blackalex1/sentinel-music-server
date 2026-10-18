/**
 * Модуль мгновенного поиска по фонотеке с debounce.
 * Предоставляет события search:performed и search:cleared для подключаемых плагинов.
 */

import { state, updateState } from '../state.js';
import { fetchTracks } from '../api.js';
import {
  disconnectTracksScrollObserver,
  setHasMoreLibraryTracks,
  renderTracksTable,
  loadLibraryTracks
} from './trackList.js';
import { switchView } from './navigation.js';

let searchTimer = null;
let currentSearchId = 0;

export function setupSearch() {
  const input = document.getElementById('searchInput');
  const clearBtn = document.getElementById('searchClear');

  if (!input) return;

  async function executeSearch(query) {
    const searchId = ++currentSearchId;
    updateState('searchQuery', query);
    disconnectTracksScrollObserver();

    if (query.length > 0) {
      setHasMoreLibraryTracks(false);
      if (state.currentView !== 'tracks') {
        switchView('tracks', false);
      }
      const results = await fetchTracks(query, 100, 0);
      if (searchId !== currentSearchId) {
        // Запрос устарел, пользователь уже изменил поисковую строку
        return;
      }
      updateState('tracks', results);

      const titleEl = document.getElementById('tracksViewTitle');
      if (titleEl) {
        titleEl.textContent = `Результаты поиска: «${query}»`;
      }

      renderTracksTable(results, 'tracksTableContainer');

      // Оповещаем подключаемые плагины расширения о выполненном поиске
      window.dispatchEvent(new CustomEvent('search:performed', {
        detail: { query, localResults: results }
      }));
    } else {
      const titleEl = document.getElementById('tracksViewTitle');
      if (titleEl) {
        titleEl.textContent = 'Коллекция треков';
      }
      window.dispatchEvent(new CustomEvent('search:cleared'));
      loadLibraryTracks(true);
    }
  }

  input.addEventListener('input', () => {
    const query = input.value.trim();
    if (clearBtn) clearBtn.style.display = query ? 'block' : 'none';

    clearTimeout(searchTimer);
    searchTimer = setTimeout(() => {
      executeSearch(query);
    }, 450);
  });

  input.addEventListener('keydown', (e) => {
    if (e.key === 'Enter') {
      e.preventDefault();
      clearTimeout(searchTimer);
      executeSearch(input.value.trim());
    }
  });

  if (clearBtn) {
    clearBtn.addEventListener('click', () => {
      clearTimeout(searchTimer);
      currentSearchId++;
      input.value = '';
      clearBtn.style.display = 'none';
      updateState('searchQuery', '');
      const titleEl = document.getElementById('tracksViewTitle');
      if (titleEl) {
        titleEl.textContent = 'Коллекция треков';
      }
      window.dispatchEvent(new CustomEvent('search:cleared'));
      loadLibraryTracks(true);
    });
  }
}
