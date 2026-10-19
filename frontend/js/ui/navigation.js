/**
 * Модуль навигации по разделам интерфейса и переключения экранов.
 */

import { state, updateState } from '../state.js';
import { showPlaylistModal } from './modals.js';
import { loadLibraryTracks, loadRecentTracks, disconnectTracksScrollObserver, disconnectMainTracksScrollObserver } from './trackList.js';
import { loadPlaylistsData, closePlaylistDetails } from './playlists.js';
import { loadDuplicates } from './duplicates.js';
import { toggleLyricsOverlay } from '../lyrics.js';

export function switchView(viewName, shouldReload = true) {
  updateState('currentView', viewName);
  disconnectTracksScrollObserver();
  disconnectMainTracksScrollObserver();

  // Обновляем активный пункт в боковом меню
  document.querySelectorAll('.nav-item').forEach(item => {
    item.classList.toggle('active', item.dataset.view === viewName);
  });

  // Скрываем все страницы контента и показываем целевую
  const views = ['viewMain', 'viewStream', 'viewTracks', 'viewPlaylists', 'viewDuplicates', 'viewBatchImport', 'viewSettings'];
  views.forEach(v => {
    const el = document.getElementById(v);
    if (el) el.style.setProperty('display', 'none', 'important');
  });

  const activeTarget = {
    main: 'viewMain',
    stream: 'viewStream',
    tracks: 'viewTracks',
    playlists: 'viewPlaylists',
    duplicates: 'viewDuplicates',
    batchImport: 'viewBatchImport',
    settings: 'viewSettings'
  }[viewName];

  if (activeTarget) {
    const el = document.getElementById(activeTarget);
    if (el) {
      const displayVal = (el.id === 'viewStream' || el.classList.contains('view-stream-container')) ? 'flex' : 'block';
      el.style.setProperty('display', displayVal, 'important');
    }
  }

  // Обновляем контент в зависимости от вкладки
  if (viewName === 'tracks') {
    if (shouldReload) {
      // Сбрасываем поисковую строку при явном открытии фонотеки
      const searchInput = document.getElementById('searchInput');
      const searchClear = document.getElementById('searchClear');
      if (searchInput && searchInput.value) {
        searchInput.value = '';
      }
      if (searchClear) {
        searchClear.style.display = 'none';
      }
      if (state.searchQuery) {
        updateState('searchQuery', '');
        window.dispatchEvent(new CustomEvent('search:cleared'));
      }

      const titleEl = document.getElementById('tracksViewTitle');
      if (titleEl) titleEl.textContent = 'Коллекция треков';
      updateState('activePlaylist', null);
      loadLibraryTracks();
    }
  } else if (viewName === 'playlists') {
    if (shouldReload) {
      closePlaylistDetails();
      loadPlaylistsData();
    }
  } else if (viewName === 'main') {
    if (shouldReload) {
      loadRecentTracks();
    }
  } else if (viewName === 'duplicates') {
    if (shouldReload) {
      loadDuplicates();
    }
  } else if (viewName === 'settings') {
    window.dispatchEvent(new CustomEvent('settings:opened'));
  }
}

export function setupNavigation() {
  document.querySelectorAll('.nav-item').forEach(item => {
    item.addEventListener('click', (e) => {
      e.preventDefault();
      const view = item.dataset.view;
      if (view) switchView(view);
    });
  });

  // Кнопка логотипа ведет на Главное
  const brand = document.querySelector('.brand-logo');
  if (brand) {
    brand.addEventListener('click', () => switchView('main'));
  }

  // Кнопка открытия/сворачивания караоке-текста из нижнего плеера
  const btnLyrics = document.getElementById('btnPlayerLyrics');
  if (btnLyrics) {
    btnLyrics.addEventListener('click', () => {
      toggleLyricsOverlay();
    });
  }

  // Кнопка добавления плейлиста в сайдбаре
  const btnAddPl = document.getElementById('btnAddPlaylist');
  if (btnAddPl) {
    btnAddPl.addEventListener('click', () => showPlaylistModal());
  }
}
