/**
 * Sentinel Music — Модуль управления дубликатами треков (Duplicates Controller).
 * Отвечает за загрузку групп дубликатов, оценку качества, воспроизведение и безопасное удаление копий.
 */

import { fetchDuplicates, deleteDuplicatesBatch, resolveDuplicateGroup } from '../api.js';
import { playTrack, togglePlay, handleTrackDeleted } from '../player.js';
import { state, onStateChange } from '../state.js';
import { icon } from '../icons.js';
import { escapeHtml, showToast } from './toast.js';
import { showConfirm } from './notifications.js';

let duplicatesData = {
  total_groups: 0,
  total_extra_tracks: 0,
  potential_saved_bytes: 0,
  groups: []
};
let searchFilterTimer = null;

// Стабильные карты данных по ID (защита от сдвигов индексов при удалении)
const groupsMap = new Map(); // key: groupId -> group
const tracksMap = new Map(); // key: trackId -> { track, group }

export function initDuplicatesUI() {
  const btnRefresh = document.getElementById('btnRefreshDuplicates');
  if (btnRefresh) {
    btnRefresh.addEventListener('click', () => {
      btnRefresh.disabled = true;
      loadDuplicates().finally(() => {
        btnRefresh.disabled = false;
      });
    });
  }

  const btnResolveAll = document.getElementById('btnResolveAllDuplicates');
  if (btnResolveAll) {
    btnResolveAll.addEventListener('click', handleResolveAllDuplicates);
  }

  const searchInput = document.getElementById('duplicatesSearchInput');
  const searchClear = document.getElementById('duplicatesSearchClear');

  if (searchInput) {
    searchInput.addEventListener('input', () => {
      const q = searchInput.value.trim();
      if (searchClear) searchClear.style.display = q ? 'block' : 'none';

      clearTimeout(searchFilterTimer);
      searchFilterTimer = setTimeout(() => {
        loadDuplicates(q);
      }, 300);
    });
  }

  if (searchClear && searchInput) {
    searchClear.addEventListener('click', () => {
      searchInput.value = '';
      searchClear.style.display = 'none';
      loadDuplicates('');
    });
  }

  // Навешиваем единое делегирование событий для контейнера дубликатов
  attachDuplicatesDelegation();

  // Реактивное обновление иконок воспроизведения при смене трека или статуса воспроизведения
  onStateChange('isPlaying', () => updateDuplicatePlayIcons());
  onStateChange('currentTrack', () => updateDuplicatePlayIcons());
}

export async function loadDuplicates(query = '') {
  const container = document.getElementById('duplicatesList');
  if (container) {
    container.innerHTML = `
      <div class="duplicates-loading">
        <div class="duplicates-spinner"></div>
        <span>Сканирование фонотеки на наличие дубликатов...</span>
      </div>
    `;
  }

  try {
    const data = await fetchDuplicates(query);
    duplicatesData = data || { total_groups: 0, total_extra_tracks: 0, potential_saved_bytes: 0, groups: [] };

    updateDuplicatesStatsUI(duplicatesData);
    renderDuplicatesGroups(duplicatesData.groups);
  } catch (err) {
    console.error('[Duplicates] Ошибка загрузки дубликатов:', err);
    if (container) {
      container.innerHTML = `
        <div class="duplicates-error">
          ${icon('alert', { size: 32 })}
          <p>Не удалось загрузить отчет о дубликатах</p>
          <button class="btn-secondary" onclick="window.loadDuplicates()">Повторить</button>
        </div>
      `;
    }
  }
}

// Экспортируем в глобальную область для обработчиков повтора
window.loadDuplicates = loadDuplicates;

function updateDuplicatesStatsUI(data) {
  const statGroups = document.getElementById('statDupGroups');
  const statExtra = document.getElementById('statDupExtra');
  const statSize = document.getElementById('statDupSize');
  const btnResolveAll = document.getElementById('btnResolveAllDuplicates');
  const badge = document.getElementById('duplicatesCountBadge');

  if (statGroups) statGroups.textContent = data.total_groups || 0;
  if (statExtra) statExtra.textContent = data.total_extra_tracks || 0;
  if (statSize) statSize.textContent = formatBytes(data.potential_saved_bytes || 0);

  // Обновляем бейдж и динамическую видимость вкладки в боковом меню
  const navItem = document.getElementById('navItemDuplicates');
  if (navItem) {
    if (data.total_extra_tracks > 0) {
      navItem.style.display = 'flex';
    } else {
      navItem.style.display = 'none';
    }
  }

  if (badge) {
    if (data.total_extra_tracks > 0) {
      badge.textContent = data.total_extra_tracks;
      badge.style.display = 'inline-block';
    } else {
      badge.style.display = 'none';
    }
  }

  // Кнопка пакетного удаления лучших доступна, если есть что чистить
  if (btnResolveAll) {
    btnResolveAll.style.display = data.total_extra_tracks > 0 ? 'inline-flex' : 'none';
  }
}

function renderDuplicatesGroups(groups) {
  const container = document.getElementById('duplicatesList');
  if (!container) return;

  groupsMap.clear();
  tracksMap.clear();

  if (!groups || groups.length === 0) {
    container.innerHTML = `
      <div class="duplicates-empty-state">
        <div class="empty-icon">${icon('checkCircle', { size: 52 })}</div>
        <h3>Дубликатов не найдено</h3>
        <p>Ваша фонотека в идеальном порядке. Нет повторяющихся аудиофайлов.</p>
        <button class="btn-primary" onclick="window.switchView && window.switchView('main')" style="margin-top: 16px; display: inline-flex; align-items: center; gap: 8px;">
          ${icon('home', { size: 16 })} <span>Вернуться на Главное</span>
        </button>
      </div>
    `;
    return;
  }

  let html = `<div class="duplicates-groups-list">`;

  groups.forEach((group, gIdx) => {
    // Стабильный идентификатор группы, не зависящий от динамических индексов массива
    const groupId = 'grp_' + (group.best_track_id ? `${group.best_track_id}_${gIdx}` : `idx_${gIdx}`);
    group._groupId = groupId;
    groupsMap.set(groupId, group);

    const extraMb = formatBytes(group.extra_bytes || 0);
    const bestTrack = group.tracks.find(t => t.is_best) || group.tracks[0];

    html += `
      <div class="duplicate-group-card" id="dupGroup_${groupId}" data-group-id="${groupId}">
        <div class="dup-group-header">
          <div class="dup-group-info">
            <span class="dup-group-title">${escapeHtml(group.artist)} — ${escapeHtml(group.title)}</span>
            <div class="dup-group-badges">
              <span class="dup-badge-count">${group.count} версий</span>
              ${group.extra_bytes > 0 ? `<span class="dup-badge-size">+${extraMb} лишних</span>` : ''}
            </div>
          </div>

          <div class="dup-group-actions">
            <button class="btn-primary btn-resolve-best" data-group-id="${groupId}" title="Удалить все копии, оставив версию с наилучшим качеством">
              ${icon('check', { size: 14 })} <span>Оставить лучший</span>
            </button>
          </div>
        </div>

        <div class="dup-tracks-table">
    `;

    group.tracks.forEach((track) => {
      tracksMap.set(track.id, { track, group });

      const isBest = track.is_best;
      const isFlac = track.audio_format === 'flac' || track.audio_format === 'wav';
      const badgeClass = isFlac ? 'badge-flac' : 'badge-mp3';
      const badgeText = isFlac ? 'FLAC' : `${track.bitrate || 320} kbps`;
      const sizeText = formatBytes(track.file_size || 0);
      const durationText = formatDuration(track.duration);
      const isCurrentPlaying = state.currentTrack && state.currentTrack.id === track.id && state.isPlaying;

      html += `
        <div class="dup-track-row ${isBest ? 'is-best-row' : ''}" id="dupRow_${track.id}" data-track-id="${track.id}" data-group-id="${groupId}">
          <div class="dup-row-play">
            <button class="dup-play-btn ${isCurrentPlaying ? 'playing' : ''}" data-track-id="${track.id}" data-group-id="${groupId}" title="${isCurrentPlaying ? 'Пауза' : 'Прослушать эту версию'}">
              ${icon(isCurrentPlaying ? 'pause' : 'play', { size: 15 })}
            </button>
          </div>

          <div class="dup-row-main">
            <div class="dup-row-primary">
              <span class="dup-row-title">${escapeHtml(track.title)}</span>
              ${isBest ? `<span class="badge-recommended">${icon('star', { size: 12 })} Рекомендуется</span>` : ''}
            </div>
            <div class="dup-row-meta">
              <span class="hybrid-badge ${badgeClass}">${badgeText}</span>
              <span class="dup-meta-item">${durationText}</span>
              <span class="dup-meta-item">${sizeText}</span>
              ${track.album ? `<span class="dup-meta-item dup-album-name">• ${escapeHtml(track.album)}</span>` : ''}
            </div>
            <div class="dup-row-path" title="${escapeHtml(track.file_path)}">
              ${escapeHtml(track.file_path)}
            </div>
          </div>

          <div class="dup-row-actions">
            ${!isBest ? `
              <button class="btn-secondary btn-keep-this" data-track-id="${track.id}" data-group-id="${groupId}" title="Оставить именно эту версию и удалить остальные копии в группе">
                Оставить этот
              </button>
            ` : ''}
            <button class="dup-delete-btn" data-track-id="${track.id}" data-group-id="${groupId}" title="Удалить только этот файл">
              ${icon('trash', { size: 15 })}
            </button>
          </div>
        </div>
      `;
    });

    html += `
        </div>
      </div>
    `;
  });

  html += `</div>`;
  container.innerHTML = html;
}

/**
 * Делегирование обработки кликов в контейнере дубликатов.
 * Работает непрерывно и не ломается при удалении элементов из DOM.
 */
function attachDuplicatesDelegation() {
  const container = document.getElementById('duplicatesList');
  if (!container || container.dataset.hasDelegation) return;
  container.dataset.hasDelegation = 'true';

  container.addEventListener('click', async (e) => {
    // 1. Воспроизведение трека в основном плеере
    const playBtn = e.target.closest('.dup-play-btn');
    if (playBtn) {
      e.stopPropagation();
      const trackId = parseInt(playBtn.dataset.trackId, 10);
      const entry = tracksMap.get(trackId);
      if (!entry || !entry.track) {
        console.warn('[Duplicates] Трек не найден в карте дубликатов:', trackId);
        return;
      }
      const track = entry.track;

      if (state.currentTrack && state.currentTrack.id === track.id) {
        togglePlay();
      } else {
        playTrack(track, [track]);
        showToast(`Воспроизведение: «${track.artist} - ${track.title}»`);
      }
      return;
    }

    // 2. Одиночное удаление одного дубликата
    const deleteBtn = e.target.closest('.dup-delete-btn');
    if (deleteBtn) {
      e.stopPropagation();
      const trackId = parseInt(deleteBtn.dataset.trackId, 10);
      const groupId = deleteBtn.dataset.groupId;
      const group = groupsMap.get(groupId);
      const entry = tracksMap.get(trackId);
      const track = entry?.track;
      if (!track || !group) return;

      const ok = await showConfirm({
        title: 'Удалить дубликат?',
        subtitle: `${track.artist} — ${track.title}`,
        message: `Вы действительно хотите удалить аудиофайл (${track.audio_format.toUpperCase()}, ${formatBytes(track.file_size)}) с сервера?`,
        details: 'Аудиофайл и связанные субтитры (.lrc) будут безвозвратно удалены с диска.',
        confirmText: 'Удалить файл',
        cancelText: 'Отмена',
        type: 'danger',
        icon: 'trash'
      });
      if (!ok) return;

      deleteBtn.disabled = true;
      try {
        await deleteDuplicatesBatch([trackId], true);
        handleTrackDeleted(trackId);
        showToast(`Файл удален: «${track.title}»`);

        // Удаляем строку из DOM
        const row = document.getElementById(`dupRow_${trackId}`);
        if (row) row.remove();

        tracksMap.delete(trackId);
        group.tracks = group.tracks.filter(t => t.id !== trackId);
        group.count = group.tracks.length;

        if (group.tracks.length <= 1) {
          // Если остался только 1 трек, группа дубликатов разрешена
          if (group.tracks.length === 1) {
            tracksMap.delete(group.tracks[0].id);
          }
          groupsMap.delete(groupId);
          const card = document.getElementById(`dupGroup_${groupId}`);
          if (card) card.remove();
        } else {
          // Пересчитываем лучший трек, если удален лучший
          const best = group.tracks.find(t => t.is_best) || group.tracks[0];
          group.best_track_id = best.id;
        }

        duplicatesData.groups = Array.from(groupsMap.values());
        refreshStatsAfterLocalDeletion();
      } catch (err) {
        deleteBtn.disabled = false;
        showToast(`Ошибка удаления: ${err.message || 'Сбой'}`);
      }
      return;
    }

    // 3. «Оставить этот» (удалить остальные копии в группе)
    const keepBtn = e.target.closest('.btn-keep-this');
    if (keepBtn) {
      e.stopPropagation();
      const keepTrackId = parseInt(keepBtn.dataset.trackId, 10);
      const groupId = keepBtn.dataset.groupId;
      const group = groupsMap.get(groupId);
      if (!group) return;

      const deleteIds = group.tracks.filter(t => t.id !== keepTrackId).map(t => t.id);
      if (deleteIds.length === 0) return;

      const keepTrack = group.tracks.find(t => t.id === keepTrackId);
      const keepDesc = keepTrack ? ` (${keepTrack.audio_format.toUpperCase()}, ${formatBytes(keepTrack.file_size)})` : '';

      const ok = await showConfirm({
        title: 'Оставить выбранную версию?',
        subtitle: `${group.artist} — ${group.title}`,
        message: `Оставить выбранную версию${keepDesc} и удалить остальные копии (${deleteIds.length} шт.) с диска?`,
        details: `Будет удалено ${deleteIds.length} лишних аудиофайлов. Освобожденное место вернется на диск.`,
        confirmText: `Оставить и удалить копии (${deleteIds.length})`,
        cancelText: 'Отмена',
        type: 'danger',
        icon: 'trash'
      });
      if (!ok) return;

      keepBtn.disabled = true;
      keepBtn.innerHTML = `${icon('loader', { size: 14, className: 'icon-spin' })} Очистка...`;

      try {
        await resolveDuplicateGroup(keepTrackId, deleteIds, true);
        deleteIds.forEach(id => handleTrackDeleted(id));
        showToast(`Группа разрешена: оставлена 1 версия, удалено ${deleteIds.length} копий`);

        // Очищаем из карт
        deleteIds.forEach(id => tracksMap.delete(id));
        tracksMap.delete(keepTrackId);
        groupsMap.delete(groupId);

        const card = document.getElementById(`dupGroup_${groupId}`);
        if (card) card.remove();

        duplicatesData.groups = Array.from(groupsMap.values());
        refreshStatsAfterLocalDeletion();
      } catch (err) {
        keepBtn.disabled = false;
        keepBtn.textContent = 'Оставить этот';
        showToast(`Ошибка: ${err.message || 'Сбой'}`);
      }
      return;
    }

    // 4. «Оставить лучший» в группе
    const resolveBestBtn = e.target.closest('.btn-resolve-best');
    if (resolveBestBtn) {
      e.stopPropagation();
      const groupId = resolveBestBtn.dataset.groupId;
      const group = groupsMap.get(groupId);
      if (!group || !group.best_track_id) return;

      const keepTrackId = group.best_track_id;
      const deleteIds = group.tracks.filter(t => t.id !== keepTrackId).map(t => t.id);
      if (deleteIds.length === 0) return;

      const bestTrack = group.tracks.find(t => t.id === keepTrackId) || group.tracks[0];
      const ok = await showConfirm({
        title: 'Оставить наилучшую версию?',
        subtitle: `${group.artist} — ${group.title}`,
        message: `Оставить версию наилучшего качества (${bestTrack.audio_format.toUpperCase()}, ${bestTrack.bitrate || 320} kbps) и удалить остальные копии (${deleteIds.length} шт.)?`,
        details: 'Остальные копии трека будут удалены с диска сервера.',
        confirmText: `Удалить копии (${deleteIds.length})`,
        cancelText: 'Отмена',
        type: 'danger',
        icon: 'trash'
      });
      if (!ok) return;

      resolveBestBtn.disabled = true;
      resolveBestBtn.innerHTML = `${icon('loader', { size: 14, className: 'icon-spin' })} Очистка...`;

      try {
        await resolveDuplicateGroup(keepTrackId, deleteIds, true);
        deleteIds.forEach(id => handleTrackDeleted(id));
        showToast(`Оставлена лучшая версия «${group.artist} - ${group.title}», удалено ${deleteIds.length} копий`);

        // Очищаем из карт
        deleteIds.forEach(id => tracksMap.delete(id));
        tracksMap.delete(keepTrackId);
        groupsMap.delete(groupId);

        const card = document.getElementById(`dupGroup_${groupId}`);
        if (card) card.remove();

        duplicatesData.groups = Array.from(groupsMap.values());
        refreshStatsAfterLocalDeletion();
      } catch (err) {
        resolveBestBtn.disabled = false;
        resolveBestBtn.innerHTML = `${icon('check', { size: 14 })} <span>Оставить лучший</span>`;
        showToast(`Ошибка: ${err.message || 'Сбой'}`);
      }
      return;
    }
  });
}

function updateDuplicatePlayIcons() {
  const container = document.getElementById('duplicatesList');
  if (!container) return;
  const isPlaying = state.isPlaying;
  const currentId = state.currentTrack?.id;

  container.querySelectorAll('.dup-play-btn').forEach(btn => {
    const tid = parseInt(btn.dataset.trackId, 10);
    const active = currentId && tid === currentId;
    if (active && isPlaying) {
      btn.innerHTML = icon('pause', { size: 15 });
      btn.classList.add('playing');
      btn.title = 'Пауза';
    } else {
      btn.innerHTML = icon('play', { size: 15 });
      btn.classList.remove('playing');
      btn.title = 'Прослушать эту версию';
    }
  });
}

function refreshStatsAfterLocalDeletion() {
  const remainingGroups = duplicatesData.groups.filter(g => g.tracks && g.tracks.length > 1);
  let extraCount = 0;
  let extraBytes = 0;

  remainingGroups.forEach(g => {
    extraCount += (g.tracks.length - 1);
    const best = g.tracks.find(t => t.is_best) || g.tracks[0];
    extraBytes += g.tracks.filter(t => t.id !== best.id).reduce((sum, t) => sum + (t.file_size || 0), 0);
  });

  duplicatesData.total_groups = remainingGroups.length;
  duplicatesData.total_extra_tracks = extraCount;
  duplicatesData.potential_saved_bytes = extraBytes;

  updateDuplicatesStatsUI(duplicatesData);

  if (remainingGroups.length === 0) {
    const container = document.getElementById('duplicatesList');
    if (container) {
      container.innerHTML = `
        <div class="duplicates-empty-state">
          <div class="empty-icon">${icon('checkCircle', { size: 52 })}</div>
          <h3>Дубликатов не найдено</h3>
          <p>Все дубликаты успешно разрешены! Фонотека чиста.</p>
        </div>
      `;
    }
  }
}

async function handleResolveAllDuplicates() {
  if (!duplicatesData.groups || duplicatesData.groups.length === 0) return;

  const totalExtra = duplicatesData.total_extra_tracks;
  const sizeMb = formatBytes(duplicatesData.potential_saved_bytes);

  const ok = await showConfirm({
    title: 'Очистить все дубликаты?',
    subtitle: 'Массовая оптимизация фонотеки',
    message: `Во всех ${duplicatesData.total_groups} группах оставить только наилучшие версии (FLAC/HQ), а остальные ${totalExtra} копий (${sizeMb}) безвозвратно удалить с сервера?`,
    details: `Будет освобождено ${sizeMb} дискового пространства на сервере.`,
    confirmText: `Удалить ${totalExtra} копий (${sizeMb})`,
    cancelText: 'Отмена',
    type: 'danger',
    icon: 'trash'
  });
  if (!ok) return;

  const btnResolveAll = document.getElementById('btnResolveAllDuplicates');
  if (btnResolveAll) {
    btnResolveAll.disabled = true;
    btnResolveAll.innerHTML = `${icon('loader', { size: 15, className: 'icon-spin' })} Очистка всей медиатеки...`;
  }

  try {
    const allDeleteIds = [];
    duplicatesData.groups.forEach(g => {
      if (g.best_track_id && Array.isArray(g.tracks)) {
        g.tracks.forEach(t => {
          if (t.id !== g.best_track_id) {
            allDeleteIds.push(t.id);
          }
        });
      }
    });

    if (allDeleteIds.length > 0) {
      const res = await deleteDuplicatesBatch(allDeleteIds, true);
      allDeleteIds.forEach(id => handleTrackDeleted(id));
      showToast(`Успешно очищено ${res.deleted_count || allDeleteIds.length} дубликатов! Освобождено ${formatBytes(res.freed_bytes)}.`);
    }

    await loadDuplicates();
  } catch (err) {
    showToast(`Ошибка пакетной очистки: ${err.message || 'Сбой'}`);
  } finally {
    if (btnResolveAll) {
      btnResolveAll.disabled = false;
      btnResolveAll.innerHTML = `${icon('sparkles', { size: 15 })} <span>Оставить все лучшие</span>`;
    }
  }
}

function formatBytes(bytes) {
  if (!bytes || bytes <= 0) return '0 MB';
  const k = 1024;
  const dm = 1;
  const sizes = ['Байт', 'КБ', 'МБ', 'ГБ', 'ТБ'];
  const i = Math.floor(Math.log(bytes) / Math.log(k));
  if (i < 2) return `${(bytes / (k * k)).toFixed(1)} МБ`;
  return `${parseFloat((bytes / Math.pow(k, i)).toFixed(dm))} ${sizes[i]}`;
}

function formatDuration(sec) {
  if (!sec || isNaN(sec)) return '0:00';
  const m = Math.floor(sec / 60);
  const s = Math.floor(sec % 60);
  return `${m}:${s < 10 ? '0' : ''}${s}`;
}
