/**
 * Модуль выбора альтернативных версий трека (Не та версия / Заменить).
 */

import { state, updateState } from '../state.js';
import { fetchTrackCandidates, replaceTrackWithCandidate } from '../api.js';
import { formatTime, playTrack, applyTrackLoudnessGain } from '../player.js';
import { showToast, escapeHtml } from './toast.js';
import { icon } from '../icons.js';
import { isCandidatePreviewSupported, toggleCandidatePreview, stopCandidatePreview } from '../candidatePreview.js';

let currentModalTrack = null;
let currentCandidates = [];
let currentCandidateFilter = 'all';

/**
 * Открывает модальное окно выбора версии трека (Не та версия / Заменить).
 */
export async function openTrackVersionModal(track) {
  stopCandidatePreview();
  currentModalTrack = track;
  currentCandidateFilter = 'all';

  const modal = document.getElementById('trackVersionsModal');
  const currentText = document.getElementById('versionCurrentText');
  const candidatesList = document.getElementById('candidatesList');
  if (!modal || !candidatesList) return;

  const currentBitrate = track.bitrate ? `${track.bitrate} kbps` : '';
  const currentFmt = (track.audio_format || 'MP3').toUpperCase();
  currentText.innerHTML = `Текущий трек: <strong>${escapeHtml(track.artist)} — ${escapeHtml(track.title)}</strong> <span class="cand-badge badge-source" style="margin-left: 6px;">${currentFmt} ${currentBitrate}</span>`;

  // Сброс активного фильтра в чипах
  document.querySelectorAll('.version-filter-chip').forEach(chip => {
    chip.classList.toggle('active', chip.dataset.filter === 'all');
  });

  candidatesList.innerHTML = `
    <div class="candidate-loading-state">
      <div class="spinner"></div>
      <div>Поиск альтернативных версий по источникам...</div>
    </div>
  `;

  modal.classList.add('active');

  try {
    const data = await fetchTrackCandidates(track.id, 10);
    currentCandidates = (data && data.candidates) ? data.candidates : [];
    renderCandidateList(currentCandidates, currentCandidateFilter);
  } catch (err) {
    candidatesList.innerHTML = `
      <div class="candidate-empty-state">
        <div>${icon('alert', { size: 16, className: 'icon-danger' })} Ошибка поиска версий: ${escapeHtml(err.message || 'Сбой соединения')}</div>
      </div>
    `;
  }
}

/**
 * Отрисовка списка найденных версий-кандидатов с фильтрацией.
 */
function renderCandidateList(candidates, filter = 'all') {
  const container = document.getElementById('candidatesList');
  if (!container) return;

  const filtered = (candidates || []).filter(c => {
    if (filter === 'all') return true;
    const vType = (c.version_type || '').toLowerCase();
    const fmt = (c.format || '').toLowerCase();
    const src = (c.source || '').toLowerCase();
    if (filter === 'flac') return fmt === 'flac' || vType.includes('flac');
    if (filter === 'p2p') return src === 'p2p';
    if (filter === 'source_a') return src === 'source_a';
    if (filter === 'source_as') return src === 'source_as';
    if (filter === 'source_c') return src === 'source_c';
    if (filter === 'source_d') return src === 'source_d';
    if (filter === 'explicit') return c.explicit || vType.includes('explicit');
    if (filter === 'remix') return vType.includes('remix') || vType.includes('slowed') || vType.includes('speed');
    return true;
  });

  if (filtered.length === 0) {
    container.innerHTML = `
      <div class="candidate-empty-state">
        <div>По выбранному фильтру версий не найдено.</div>
      </div>
    `;
    return;
  }

  container.innerHTML = '';
  filtered.forEach(cand => {
    const card = document.createElement('div');
    card.className = 'candidate-card';

    const vType = (cand.version_type || 'original').toLowerCase();
    let vBadgeClass = 'badge-version-original';
    let vLabel = cand.version_label || 'Оригинал';
    if (vType.includes('explicit') || cand.explicit) {
      vBadgeClass = 'badge-version-explicit';
      vLabel = 'Explicit (18+)';
    } else if (vType.includes('flac') || cand.format === 'flac') {
      vBadgeClass = 'badge-version-flac';
      vLabel = 'FLAC Lossless';
    } else if (vType.includes('slowed')) {
      vBadgeClass = 'badge-version-slowed';
      vLabel = 'Slowed';
    } else if (vType.includes('speed') || vType.includes('sped')) {
      vBadgeClass = 'badge-version-speedup';
      vLabel = 'Speed Up';
    } else if (vType.includes('remix')) {
      vBadgeClass = 'badge-version-remix';
      vLabel = 'Remix';
    }

    const sourceName = cand.source_name || cand.source || 'Источник';
    const bitrateStr = cand.bitrate ? `${cand.bitrate} kbps` : '';
    const formatStr = (cand.format || 'MP3').toUpperCase();
    const durationStr = cand.duration ? (typeof cand.duration === 'number' ? formatTime(cand.duration) : cand.duration) : '';

    const canPreview = isCandidatePreviewSupported(cand);

    card.innerHTML = `
      <div class="candidate-main">
        <div class="candidate-header-line">
          <span class="cand-badge badge-source">${escapeHtml(sourceName)}</span>
          <span class="cand-badge ${vBadgeClass}">${escapeHtml(vLabel)}</span>
          <span class="cand-badge badge-source">${formatStr} ${bitrateStr}</span>
        </div>
        <div class="candidate-title" title="${escapeHtml(cand.title)}">${escapeHtml(cand.title)}</div>
        <div class="candidate-artist">${escapeHtml(cand.artist)}</div>
        ${durationStr ? `<div class="candidate-meta-line">${icon('clock', { size: 12 })} Длительность: ${durationStr}</div>` : ''}
      </div>
      <div class="candidate-actions">
        ${canPreview ? `
          <button class="btn-secondary cand-btn-preview">
            ${icon('play', { size: 13 })} Слушать
          </button>
        ` : ''}
        <button class="btn-primary cand-btn-select">Заменить</button>
      </div>
    `;

    const btnPreview = card.querySelector('.cand-btn-preview');
    if (btnPreview) {
      btnPreview.addEventListener('click', (e) => {
        e.stopPropagation();
        toggleCandidatePreview(cand, btnPreview, card);
      });
    }

    const btnSelect = card.querySelector('.cand-btn-select');
    btnSelect.addEventListener('click', async (e) => {
      e.stopPropagation();
      stopCandidatePreview();
      btnSelect.disabled = true;
      btnSelect.innerHTML = `${icon('loader', { size: 13, className: 'icon-spin' })} Загрузка...`;
      try {
        const res = await replaceTrackWithCandidate(currentModalTrack.id, cand);
        showToast(`Версия трека заменена на "${cand.title}"!`, 'checkCircle');

        document.getElementById('trackVersionsModal').classList.remove('active');

        if (res.track) {
          Object.assign(currentModalTrack, res.track);

          // Обновление строки трека в DOM
          const row = document.querySelector(`.track-row[data-id="${currentModalTrack.id}"]`);
          if (row) {
            const titleSpan = row.querySelector('.track-cell-title');
            if (titleSpan) titleSpan.textContent = res.track.title;
            const artistSpan = row.querySelector('.track-cell-artist');
            if (artistSpan) artistSpan.textContent = res.track.artist;
            const albumDiv = row.querySelector('.track-cell-album');
            if (albumDiv && res.track.album) albumDiv.textContent = res.track.album;
            const durDiv = row.querySelector('.track-cell-duration');
            if (durDiv && res.track.duration) durDiv.textContent = formatTime(res.track.duration);
            const flacBadge = row.querySelector('.flac-badge');
            const isNowFlac = (res.track.audio_format || '').toLowerCase() === 'flac';
            if (isNowFlac && !flacBadge) {
              const line = row.querySelector('.track-title-line');
              if (line) line.insertAdjacentHTML('beforeend', '<span class="flac-badge">FLAC</span>');
            } else if (!isNowFlac && flacBadge) {
              flacBadge.remove();
            }
          }

          // Если заменяемый трек сейчас играет или выбран в плеере
          if (state.currentTrack && state.currentTrack.id === currentModalTrack.id) {
            const wasPlaying = state.isPlaying;
            const updated = { ...state.currentTrack, ...res.track };
            updateState('currentTrack', updated);

            // Обновляем трек в очереди воспроизведения
            if (Array.isArray(state.queue)) {
              const qIdx = state.queue.findIndex(t => t.id === currentModalTrack.id);
              if (qIdx >= 0) {
                state.queue[qIdx] = updated;
              }
            }

            // Перезапускаем воспроизведение нового файла с начала
            if (wasPlaying) {
              playTrack(updated, null, state.isStreamActive);
            } else {
              applyTrackLoudnessGain(updated);
            }
          }
        }
      } catch (err) {
        showToast(`Ошибка замены: ${err.message || 'Сбой'}`, 'xCircle');
        btnSelect.disabled = false;
        btnSelect.innerHTML = 'Заменить';
      }
    });

    container.appendChild(card);
  });
}

export function setupTrackVersionFilters() {
  document.getElementById('versionFilterChips')?.addEventListener('click', (e) => {
    const chip = e.target.closest('.version-filter-chip');
    if (!chip) return;
    stopCandidatePreview();
    document.querySelectorAll('.version-filter-chip').forEach(c => c.classList.remove('active'));
    chip.classList.add('active');
    currentCandidateFilter = chip.dataset.filter;
    renderCandidateList(currentCandidates, currentCandidateFilter);
  });

  const modal = document.getElementById('trackVersionsModal');
  if (modal) {
    modal.addEventListener('click', (e) => {
      if (e.target === modal || e.target.classList.contains('btn-secondary')) {
        stopCandidatePreview();
      }
    });
  }
}
