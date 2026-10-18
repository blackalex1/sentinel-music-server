/**
 * Модуль контекстного меню действий над треком.
 */

import { addToQueue, playNextInQueue } from '../player.js';
import { openTrackVersionModal } from './trackVersions.js';
import { openAddToPlaylistModal, openDeleteTrackModal } from './modals.js';
import { removeTrackFromPlaylist } from '../api.js';
import { state } from '../state.js';
import { showToast } from './toast.js';
import { icon } from '../icons.js';

let activeContextMenu = null;

export function closeActiveContextMenu() {
  if (activeContextMenu) {
    activeContextMenu.remove();
    activeContextMenu = null;
  }
}

export function initContextMenuEvents() {
  document.addEventListener('click', () => closeActiveContextMenu());
  window.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') closeActiveContextMenu();
  });
}

export function openTrackContextMenu(track, anchorBtn) {
  closeActiveContextMenu();

  const isPlaylist = !!state.activePlaylist;
  const menu = document.createElement('div');
  menu.className = 'track-context-menu';
  menu.innerHTML = `
    <button class="track-context-item" data-action="queue">
      <span class="track-context-icon">${icon('plus', { size: 15 })}</span> В конец очереди
    </button>
    <button class="track-context-item" data-action="next">
      <span class="track-context-icon">${icon('skipForward', { size: 15 })}</span> Играть следующим
    </button>
    <button class="track-context-item" data-action="playlist">
      <span class="track-context-icon">${icon('folderPlus', { size: 15 })}</span> Добавить в плейлист
    </button>
    <button class="track-context-item" data-action="replace-version" style="border-top: 1px solid rgba(255,255,255,0.08); margin-top: 2px; padding-top: 8px;">
      <span class="track-context-icon">${icon('refresh', { size: 15 })}</span> Не та версия / Заменить
    </button>
    ${isPlaylist ? `
    <button class="track-context-item" data-action="remove-playlist">
      <span class="track-context-icon">${icon('minus', { size: 15 })}</span> Убрать из плейлиста
    </button>
    ` : ''}
    <button class="track-context-item danger" data-action="delete" style="border-top: 1px solid rgba(255,255,255,0.08); margin-top: 2px; padding-top: 8px;">
      <span class="track-context-icon">${icon('trash', { size: 15, className: 'icon-danger' })}</span> ${isPlaylist ? 'Удалить из фонотеки' : 'Удалить трек'}
    </button>
  `;

  const rect = anchorBtn.getBoundingClientRect();
  const menuWidth = 220;
  const menuHeight = isPlaylist ? 250 : 210;
  let top = rect.bottom + 4;
  let left = rect.right - menuWidth;

  if (left < 10) left = 10;
  if (top + menuHeight > window.innerHeight - 84) {
    top = rect.top - menuHeight - 4;
  }

  menu.style.top = `${top}px`;
  menu.style.left = `${left}px`;

  menu.addEventListener('click', (e) => {
    e.stopPropagation();
    const btn = e.target.closest('.track-context-item');
    if (!btn) return;
    const action = btn.dataset.action;

    closeActiveContextMenu();

    if (action === 'queue') {
      addToQueue(track);
    } else if (action === 'next') {
      playNextInQueue(track);
    } else if (action === 'playlist') {
      openAddToPlaylistModal(track);
    } else if (action === 'replace-version') {
      openTrackVersionModal(track);
    } else if (action === 'remove-playlist') {
      if (state.activePlaylist) {
        removeTrackFromPlaylist(state.activePlaylist.id, track.id).then(() => {
          showToast(`Трек убран из плейлиста «${state.activePlaylist.title}»`);
          window.dispatchEvent(new CustomEvent('track:removed-from-playlist', {
            detail: { track, trackId: track.id, playlistId: state.activePlaylist.id }
          }));
        }).catch((err) => {
          showToast(err.message || 'Ошибка удаления из плейлиста');
        });
      }
    } else if (action === 'delete') {
      openDeleteTrackModal(track);
    }
  });

  document.body.appendChild(menu);
  activeContextMenu = menu;
}
