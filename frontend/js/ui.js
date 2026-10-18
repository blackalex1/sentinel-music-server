/**
 * Главный фасад пользовательского интерфейса (UI) Sentinel Music.
 * Координирует работу модулей навигации, поиска, треков, плейлистов, модальных окон и плеера.
 */

import { onStateChange } from './state.js';
import { showToast, escapeHtml } from './ui/toast.js';
import { setupNavigation, switchView } from './ui/navigation.js';
import { setupSearch } from './ui/search.js';
import {
  loadMainViewTracks,
  loadRecentTracks,
  loadLibraryTracks,
  renderTracksTable,
  updateActiveRowEqualizers,
  initMoodCollectionsUI,
  syncMoodCardsActiveState,
  loadMoodCollectionCounts,
  initLibraryMoodChips,
  getCurrentLibraryMood
} from './ui/trackList.js';
import {
  loadPlaylistsData,
  openPlaylistDetails,
  renderPlaylistsGrid,
  renderSidebarPlaylists,
  initPlaylistsUI
} from './ui/playlists.js';
import {
  setupPlayerControls,
  updatePlayerReactionsUI,
  setupUserPill,
  updateUserInfoUI
} from './ui/playerControls.js';
import {
  syncTrackReactionUI,
  toggleLikeAction,
  toggleDislikeAction
} from './ui/reactions.js';
import {
  setupModals,
  setModalsCallbacks,
  showAuthModal,
  hideAuthModal,
  showPlaylistModal,
  hidePlaylistModal,
  openAddToPlaylistModal,
  openDeleteTrackModal,
  hideDeleteTrackModal,
  openUploadTracksModal,
  hideUploadTracksModal
} from './ui/modals.js';
import {
  openTrackContextMenu,
  closeActiveContextMenu,
  initContextMenuEvents
} from './ui/contextMenu.js';
import {
  openTrackVersionModal,
  setupTrackVersionFilters
} from './ui/trackVersions.js';
import { setupWatcherPolling } from './ui/watcher.js';
import { initDuplicatesUI, loadDuplicates } from './ui/duplicates.js';
import { showConfirm, showAlert, showPrompt } from './ui/notifications.js';
import { initExpandedPlayer, toggleExpandedPlayer } from './ui/expandedPlayer.js';
import { setupEqualizerUI, openEqualizerModal, closeEqualizerModal, toggleEqualizerModal } from './ui/equalizer.js';

// Публичный ре-экспорт всех компонентов для 100% обратной совместимости
export {
  showToast,
  escapeHtml,
  showConfirm,
  showAlert,
  showPrompt,
  switchView,
  setupNavigation,
  setupSearch,
  loadMainViewTracks,
  loadRecentTracks,
  loadLibraryTracks,
  renderTracksTable,
  updateActiveRowEqualizers,
  loadPlaylistsData,
  openPlaylistDetails,
  renderPlaylistsGrid,
  renderSidebarPlaylists,
  setupPlayerControls,
  updatePlayerReactionsUI,
  setupUserPill,
  updateUserInfoUI,
  setupModals,
  showAuthModal,
  hideAuthModal,
  showPlaylistModal,
  hidePlaylistModal,
  openAddToPlaylistModal,
  openDeleteTrackModal,
  hideDeleteTrackModal,
  openUploadTracksModal,
  hideUploadTracksModal,
  openTrackContextMenu,
  closeActiveContextMenu,
  openTrackVersionModal,
  setupWatcherPolling,
  loadDuplicates,
  toggleExpandedPlayer,
  syncTrackReactionUI,
  toggleLikeAction,
  toggleDislikeAction,
  initPlaylistsUI,
  initLibraryMoodChips,
  getCurrentLibraryMood,
  setupEqualizerUI,
  openEqualizerModal,
  closeEqualizerModal,
  toggleEqualizerModal
};

/**
 * Инициализация всех подсистем интерфейса.
 */
export function initUI() {
  setupNavigation();
  setupSearch();
  setupPlayerControls();
  setupModals();
  setupUserPill();
  setupWatcherPolling();
  initContextMenuEvents();
  setupTrackVersionFilters();
  initDuplicatesUI();
  initExpandedPlayer();
  setupEqualizerUI();
  initMoodCollectionsUI();
  initPlaylistsUI();
  initLibraryMoodChips();

  // Настройка обратных вызовов для модальных окон
  setModalsCallbacks({
    onAuthSuccess: (user) => {
      updateUserInfoUI(user);
      loadLibraryTracks();
      loadPlaylistsData();
      loadDuplicates();
    },
    onPlaylistCreated: () => {
      loadPlaylistsData();
    }
  });

  // Реакция на изменение состояния воспроизведения и активного трека
  onStateChange('isPlaying', () => {
    updateActiveRowEqualizers();
  });

  onStateChange('currentTrack', (track) => {
    updateActiveRowEqualizers();
    updatePlayerReactionsUI(track);
  });

  // Перенаправление на страницу авторизации при событии истечения сессии
  window.addEventListener('auth:required', () => {
    window.location.replace('login.html');
  });

  // Глобальный слушатель всплывающих уведомлений
  window.addEventListener('app:toast', (e) => {
    if (e.detail) showToast(e.detail);
  });

  // Переключение настроения в Потоке: обновление треков на Главной под выбранную категорию
  window.addEventListener('stream:mood-changed', (e) => {
    const mood = e.detail?.mood || 'default';
    syncMoodCardsActiveState(mood);
    loadMainViewTracks(mood);
  });
}
