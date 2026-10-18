/**
 * Модуль управления и отображения плейлистов (Сетка, сайдбар, просмотр треков плейлиста).
 */

import { state, updateState } from '../state.js';
import { fetchPlaylists, fetchPlaylistDetails } from '../api.js';
import { playTrack } from '../player.js';
import { showToast, escapeHtml } from './toast.js';
import { disconnectTracksScrollObserver, setHasMoreLibraryTracks, renderTracksTable } from './trackList.js';
import { switchView } from './navigation.js';
import { icon } from '../icons.js';

export async function loadPlaylistsData() {
  const playlists = await fetchPlaylists();
  updateState('playlists', playlists);
  renderPlaylistsGrid(playlists);
  renderSidebarPlaylists(playlists);
}

export function renderPlaylistsGrid(playlists) {
  const container = document.getElementById('playlistsGridContainer');
  if (!container) return;

  const validPlaylists = (playlists || []).filter(pl => pl && pl.title && !['поток', 'stream', 'discovery_buffer'].includes(pl.title.trim().toLowerCase()));

  if (validPlaylists.length === 0) {
    container.innerHTML = `
      <div style="grid-column: 1/-1; text-align: center; color: var(--text-muted); padding: 50px 20px; background: rgba(255,255,255,0.02); border-radius: var(--radius-md); border: 1px dashed rgba(255,255,255,0.08);">
        <div style="font-size: 1.1rem; font-weight: 600; color: var(--text-secondary); margin-bottom: 8px;">У вас пока нет сохраненных плейлистов</div>
        <div style="font-size: 0.88rem; color: var(--text-muted); margin-bottom: 16px;">Создавайте собственные подборки и добавляйте любимые треки из коллекции через контекстное меню</div>
        <button class="btn-primary" onclick="window.showPlaylistModal && window.showPlaylistModal()">+ Создать первый плейлист</button>
      </div>
    `;
    return;
  }

  container.innerHTML = '';
  validPlaylists.forEach(pl => {
    const card = document.createElement('div');
    card.style.cssText = `
      background: var(--bg-card);
      border: 1px solid var(--border-subtle);
      border-radius: var(--radius-md);
      padding: 18px;
      cursor: pointer;
      transition: all var(--transition-fast);
      display: flex;
      flex-direction: column;
      gap: 8px;
    `;
    card.innerHTML = `
      <div style="width: 100%; aspect-ratio: 1; background: #252525; border-radius: var(--radius-sm); display: flex; align-items: center; justify-content: center; color: var(--primary);">
        ${icon('music', { size: 36 })}
      </div>
      <div style="font-weight: 700; font-size: 1rem; color: #fff; margin-top: 6px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis;">
        ${escapeHtml(pl.title)}
      </div>
      <div style="font-size: 0.8rem; color: var(--text-secondary);">
        ${pl.track_count} треков
      </div>
    `;

    card.addEventListener('mouseenter', () => {
      card.style.background = '#282828';
      card.style.transform = 'translateY(-4px)';
    });
    card.addEventListener('mouseleave', () => {
      card.style.background = 'var(--bg-card)';
      card.style.transform = 'none';
    });

    card.addEventListener('click', () => {
      openPlaylistDetails(pl);
    });

    container.appendChild(card);
  });
}

export async function openPlaylistDetails(pl) {
  try {
    const details = await fetchPlaylistDetails(pl.id);
    if (!details) return;

    disconnectTracksScrollObserver();
    setHasMoreLibraryTracks(false);

    updateState('activePlaylist', details);
    const tracks = Array.isArray(details.tracks) ? details.tracks : [];
    updateState('tracks', tracks);

    const catalog = document.getElementById('playlistsCatalogSection');
    const detail = document.getElementById('playlistDetailSection');
    const titleEl = document.getElementById('playlistDetailTitle');

    if (catalog) catalog.style.display = 'none';
    if (detail) detail.style.display = 'block';

    if (titleEl) {
      titleEl.innerHTML = `<span style="display: inline-flex; align-items: center; gap: 8px;">${icon('folder', { size: 20 })} <span>${escapeHtml(details.title)}</span></span> <span style="font-size: 0.88rem; font-weight: 500; color: var(--text-secondary); margin-left: 10px;">${tracks.length} треков</span>`;
    }

    switchView('playlists', false);
    renderTracksTable(tracks, 'playlistTracksContainer');
    showToast(`Открыт плейлист «${details.title}»`);
  } catch (err) {
    console.error('Ошибка открытия плейлиста:', err);
  }
}

export function closePlaylistDetails() {
  updateState('activePlaylist', null);
  const catalog = document.getElementById('playlistsCatalogSection');
  const detail = document.getElementById('playlistDetailSection');
  if (catalog) catalog.style.display = 'block';
  if (detail) detail.style.display = 'none';
  const container = document.getElementById('playlistTracksContainer');
  if (container) container.innerHTML = '';
}

export function initPlaylistsUI() {
  const btnBack = document.getElementById('btnBackToPlaylists');
  if (btnBack) {
    btnBack.addEventListener('click', () => {
      closePlaylistDetails();
    });
  }

  const btnPlayAll = document.getElementById('btnPlayAllPlaylist');
  if (btnPlayAll) {
    btnPlayAll.addEventListener('click', () => {
      const pl = state.activePlaylist;
      const tracks = pl && Array.isArray(pl.tracks) ? pl.tracks : [];
      if (tracks.length > 0) {
        playTrack(tracks[0], tracks, false);
      }
    });
  }

  const btnShuffle = document.getElementById('btnShufflePlaylist');
  if (btnShuffle) {
    btnShuffle.addEventListener('click', () => {
      const pl = state.activePlaylist;
      const tracks = pl && Array.isArray(pl.tracks) ? [...pl.tracks] : [];
      if (tracks.length > 0) {
        for (let i = tracks.length - 1; i > 0; i--) {
          const j = Math.floor(Math.random() * (i + 1));
          [tracks[i], tracks[j]] = [tracks[j], tracks[i]];
        }
        playTrack(tracks[0], tracks, false);
        showToast(`Перемешан плейлист «${pl.title}»`);
      }
    });
  }

  window.addEventListener('track:removed-from-playlist', (e) => {
    if (state.activePlaylist && e.detail && e.detail.playlistId === state.activePlaylist.id) {
      openPlaylistDetails(state.activePlaylist);
      loadPlaylistsData();
    }
  });
}

export function renderSidebarPlaylists(playlists) {
  const list = document.getElementById('sidebarPlaylistsList');
  if (!list) return;

  const validPlaylists = (playlists || []).filter(pl => pl && pl.title && !['поток', 'stream', 'discovery_buffer'].includes(pl.title.trim().toLowerCase()));

  list.innerHTML = '';
  validPlaylists.forEach(pl => {
    const item = document.createElement('div');
    item.className = 'playlist-nav-item';
    item.innerHTML = `<span style="display: flex; align-items: center; gap: 8px;">${icon('folder', { size: 15 })} <span>${escapeHtml(pl.title)}</span></span>`;
    item.title = pl.title;

    item.addEventListener('click', () => {
      openPlaylistDetails(pl);
    });

    list.appendChild(item);
  });
}
