/**
 * Модуль поиска по фонотеке и внешним онлайн-источникам (кандидаты с сервера).
 * Предоставляет мгновенный поиск:
 * - Поиск по локальной фонотеке («В фонотеке»)
 * - Поиск по динамическим источникам сервера («В сети»)
 * - Предпрослушивание и сохранение треков в фонотеку в 1 клик
 */

import { state, updateState } from '../state.js';
import { fetchTracks, searchCandidates, downloadCandidate } from '../api.js';
import { icon } from '../icons.js';
import { showToast, escapeHtml } from './toast.js';
import { stopCandidatePreview, toggleCandidatePreview, isCandidatePreviewSupported } from '../candidatePreview.js';
import {
  disconnectTracksScrollObserver,
  setHasMoreLibraryTracks,
  renderTracksTable,
  loadLibraryTracks
} from './trackList.js';
import { switchView } from './navigation.js';

let searchTimer = null;
let currentSearchId = 0;
let candidateAbortController = null;

let activeSearchTab = 'library'; // 'library' | 'network'
let activeCandidateFilter = 'all'; // 'all' | 'flac' | source_name
let currentLibraryResults = [];
let currentCandidates = [];
let isSearchingCandidates = false;

export function setupSearch() {
  const input = document.getElementById('searchInput');
  const clearBtn = document.getElementById('searchClear');

  if (!input) return;

  async function executeSearch(query) {
    const searchId = ++currentSearchId;
    updateState('searchQuery', query);
    disconnectTracksScrollObserver();

    if (candidateAbortController) {
      candidateAbortController.abort();
      candidateAbortController = null;
    }
    stopCandidatePreview();

    if (query.length > 0) {
      setHasMoreLibraryTracks(false);
      if (state.currentView !== 'tracks') {
        switchView('tracks', false);
      }

      const titleEl = document.getElementById('tracksViewTitle');
      if (titleEl) {
        titleEl.textContent = `Результаты поиска: «${query}»`;
      }

      // Показываем контейнер переключения вкладок поиска
      currentLibraryResults = [];
      currentCandidates = [];
      activeSearchTab = 'library';
      activeCandidateFilter = 'all';
      isSearchingCandidates = query.trim().length >= 2;

      renderSearchTabsBar(query);
      showTabContent();

      // 1. Поиск по локальной фонотеке
      const localPromise = fetchTracks(query, 100, 0).then((results) => {
        if (searchId !== currentSearchId) return;
        currentLibraryResults = results || [];
        updateState('tracks', currentLibraryResults);
        renderTracksTable(currentLibraryResults, 'tracksTableContainer');
        renderSearchTabsBar(query);
      });

      // 2. Поиск по внешним источникам сервера (если запрос от 2 символов)
      let networkPromise = Promise.resolve();
      if (query.trim().length >= 2) {
        candidateAbortController = new AbortController();
        networkPromise = searchCandidates('', '', query.trim(), 20, {
          signal: candidateAbortController.signal
        }).then((data) => {
          if (searchId !== currentSearchId) return;
          isSearchingCandidates = false;
          currentCandidates = (data && data.candidates) ? data.candidates : [];

          // Если в фонотеке ничего не найдено, а в сети найдены треки — автоматически переключаем на «В сети»
          if (currentLibraryResults.length === 0 && currentCandidates.length > 0 && activeSearchTab === 'library') {
            activeSearchTab = 'network';
            showTabContent();
          }

          renderSearchTabsBar(query);
          if (activeSearchTab === 'network') {
            renderCandidatesList();
          }
        }).catch((err) => {
          if (err.name === 'AbortError') return;
          if (searchId !== currentSearchId) return;
          isSearchingCandidates = false;
          renderSearchTabsBar(query);
        });
      } else {
        isSearchingCandidates = false;
        renderSearchTabsBar(query);
      }

      await Promise.all([localPromise, networkPromise]);
    } else {
      handleClearSearch();
    }
  }

  function handleClearSearch() {
    if (candidateAbortController) {
      candidateAbortController.abort();
      candidateAbortController = null;
    }
    stopCandidatePreview();
    currentLibraryResults = [];
    currentCandidates = [];
    activeSearchTab = 'library';
    activeCandidateFilter = 'all';
    isSearchingCandidates = false;

    const titleEl = document.getElementById('tracksViewTitle');
    if (titleEl) {
      titleEl.textContent = 'Коллекция треков';
    }

    const tabsBar = document.getElementById('searchTabsBar');
    if (tabsBar) tabsBar.style.display = 'none';

    const candView = document.getElementById('searchCandidatesView');
    if (candView) candView.style.display = 'none';

    const moodBar = document.getElementById('tracksMoodBar');
    if (moodBar) moodBar.style.display = 'flex';

    const tableEl = document.getElementById('tracksTableContainer');
    if (tableEl) tableEl.style.display = 'block';

    const sentinel = document.getElementById('tracksScrollSentinel');
    if (sentinel) sentinel.style.display = 'none';

    loadLibraryTracks(true);
  }

  function renderSearchTabsBar(query) {
    const tabsBar = document.getElementById('searchTabsBar');
    if (!tabsBar) return;

    tabsBar.style.display = 'flex';

    const localCount = currentLibraryResults.length;
    const netCount = currentCandidates.length;

    let netBadge = '';
    if (isSearchingCandidates) {
      netBadge = `<span class="search-tab-spinner"></span>`;
    } else {
      netBadge = `<span class="search-tab-badge">${netCount}</span>`;
    }

    tabsBar.innerHTML = `
      <button type="button" class="search-tab-btn ${activeSearchTab === 'library' ? 'active' : ''}" id="tabSearchLibrary">
        ${icon('server', { size: 15 })} <span>В фонотеке</span>
        <span class="search-tab-badge">${localCount}</span>
      </button>
      <button type="button" class="search-tab-btn ${activeSearchTab === 'network' ? 'active' : ''}" id="tabSearchNetwork">
        ${icon('globe', { size: 15 })} <span>В сети</span>
        ${netBadge}
      </button>
    `;

    const btnLib = tabsBar.querySelector('#tabSearchLibrary');
    if (btnLib) {
      btnLib.addEventListener('click', () => {
        stopCandidatePreview();
        activeSearchTab = 'library';
        renderSearchTabsBar(query);
        showTabContent();
      });
    }

    const btnNet = tabsBar.querySelector('#tabSearchNetwork');
    if (btnNet) {
      btnNet.addEventListener('click', () => {
        stopCandidatePreview();
        activeSearchTab = 'network';
        renderSearchTabsBar(query);
        showTabContent();
        renderCandidatesList();
      });
    }
  }

  function showTabContent() {
    const moodBar = document.getElementById('tracksMoodBar');
    const tableEl = document.getElementById('tracksTableContainer');
    const candView = document.getElementById('searchCandidatesView');
    const sentinel = document.getElementById('tracksScrollSentinel');

    if (activeSearchTab === 'library') {
      if (moodBar) moodBar.style.display = 'flex';
      if (tableEl) tableEl.style.display = 'block';
      if (candView) candView.style.display = 'none';
    } else {
      if (moodBar) moodBar.style.display = 'none';
      if (tableEl) tableEl.style.display = 'none';
      if (sentinel) sentinel.style.display = 'none';
      if (candView) {
        candView.style.display = 'block';
        renderCandidatesList();
      }
    }
  }

  function renderCandidatesList() {
    const candView = document.getElementById('searchCandidatesView');
    if (!candView) return;

    if (isSearchingCandidates && currentCandidates.length === 0) {
      candView.innerHTML = `
        <div style="padding: 48px; text-align: center; color: var(--text-muted);">
          <div class="search-tab-spinner" style="width: 24px; height: 24px; margin: 0 auto 12px auto;"></div>
          <div>Поиск треков в сети по внешним источникам...</div>
        </div>
      `;
      return;
    }

    if (!isSearchingCandidates && currentCandidates.length === 0) {
      candView.innerHTML = `
        <div style="padding: 48px; text-align: center; color: var(--text-muted);">
          ${icon('alert', { size: 32, className: 'icon-muted' })}
          <div style="margin-top: 12px; font-size: 1rem; font-weight: 600; color: var(--text-primary);">В сети ничего не найдено</div>
          <div style="font-size: 0.85rem; margin-top: 4px;">Попробуйте уточнить поисковый запрос</div>
        </div>
      `;
      return;
    }

    // Собираем уникальные динамические источники из результатов
    const dynamicSources = [];
    currentCandidates.forEach((cand) => {
      const src = (cand.source_name || cand.source || '').trim();
      if (src && !dynamicSources.includes(src)) {
        dynamicSources.push(src);
      }
    });

    // Фильтрация
    const filtered = currentCandidates.filter((cand) => {
      if (activeCandidateFilter === 'all') return true;
      if (activeCandidateFilter === 'flac') {
        const fmt = (cand.format || '').toLowerCase();
        const vtype = (cand.version_type || '').toLowerCase();
        return fmt === 'flac' || vtype.includes('flac');
      }
      const s = (cand.source_name || cand.source || '').toLowerCase();
      return s === activeCandidateFilter.toLowerCase();
    });

    let chipsHtml = `
      <div class="candidates-filter-bar">
        <button type="button" class="candidate-chip ${activeCandidateFilter === 'all' ? 'active' : ''}" data-filter="all">
          <span>Все (${currentCandidates.length})</span>
        </button>
        <button type="button" class="candidate-chip ${activeCandidateFilter === 'flac' ? 'active' : ''}" data-filter="flac">
          ${icon('sparkles', { size: 13 })} <span>FLAC Lossless</span>
        </button>
    `;

    dynamicSources.forEach((src) => {
      const count = currentCandidates.filter(c => (c.source_name || c.source || '').toLowerCase() === src.toLowerCase()).length;
      chipsHtml += `
        <button type="button" class="candidate-chip ${activeCandidateFilter.toLowerCase() === src.toLowerCase() ? 'active' : ''}" data-filter="${escapeHtml(src)}">
          <span>${escapeHtml(src)} (${count})</span>
        </button>
      `;
    });

    chipsHtml += `</div>`;

    let cardsHtml = `<div class="candidates-list">`;
    filtered.forEach((cand, idx) => {
      const isFlac = cand.format === 'flac' || (cand.version_type && cand.version_type.includes('flac'));
      const badgeClass = isFlac ? 'badge-flac' : 'badge-mp3';
      const badgeText = isFlac ? 'FLAC Lossless' : `${cand.bitrate || 320} kbps`;
      const durationText = cand.duration ? ` • ${icon('clock', { size: 13 })} ${escapeHtml(cand.duration)}` : '';
      const sizeText = cand.size ? ` • ${icon('database', { size: 13 })} ${(cand.size / 1024 / 1024).toFixed(1)} MB` : '';
      const sourceLabel = cand.source_name || cand.source || 'В сети';
      const canPreview = isCandidatePreviewSupported(cand);

      cardsHtml += `
        <div class="candidate-card" id="candidateCard_${idx}">
          <div class="candidate-info">
            <div class="candidate-title">${escapeHtml(cand.title || 'Без названия')}</div>
            <div class="candidate-meta">
              <span class="candidate-artist">${escapeHtml(cand.artist || 'Неизвестный исполнитель')}</span>
              <span class="candidate-source-badge">${escapeHtml(sourceLabel)}</span>
              <span class="candidate-badge ${badgeClass}">${badgeText}</span>
              <span class="candidate-meta-details">${durationText}${sizeText}</span>
            </div>
          </div>
          <div class="candidate-actions">
            ${canPreview ? `
              <button class="btn-secondary candidate-preview-btn" data-idx="${idx}">
                ${icon('play', { size: 14 })} <span>Слушать</span>
              </button>
            ` : ''}
            <button class="btn-primary candidate-download-btn" data-idx="${idx}">
              ${icon('download', { size: 15 })} <span>Скачать в фонотеку</span>
            </button>
          </div>
        </div>
      `;
    });
    cardsHtml += `</div>`;

    candView.innerHTML = chipsHtml + cardsHtml;

    // Слушатели фильтров
    candView.querySelectorAll('.candidate-chip').forEach((btn) => {
      btn.addEventListener('click', () => {
        activeCandidateFilter = btn.dataset.filter;
        renderCandidatesList();
      });
    });

    // Слушатели предпрослушивания
    candView.querySelectorAll('.candidate-preview-btn').forEach((btn) => {
      btn.addEventListener('click', (e) => {
        e.stopPropagation();
        const index = parseInt(btn.dataset.idx, 10);
        const cand = filtered[index];
        const card = btn.closest('.candidate-card');
        if (cand) {
          toggleCandidatePreview(cand, btn, card);
        }
      });
    });

    // Слушатели скачивания
    candView.querySelectorAll('.candidate-download-btn').forEach((btn) => {
      btn.addEventListener('click', async () => {
        const index = parseInt(btn.dataset.idx, 10);
        const cand = filtered[index];
        if (!cand) return;

        btn.disabled = true;
        btn.innerHTML = `${icon('loader', { size: 14, className: 'icon-spin' })} <span>Загрузка...</span>`;

        try {
          await downloadCandidate(cand);
          btn.innerHTML = `${icon('check', { size: 14, className: 'icon-success' })} <span>Скачано</span>`;
          btn.classList.remove('btn-primary');
          btn.classList.add('btn-secondary');

          showToast(`«${cand.artist} - ${cand.title}» скачан в фонотеку!`);

          currentLibraryResults.push({
            id: -999,
            artist: cand.artist,
            title: cand.title
          });
          const query = (input.value || '').trim();
          renderSearchTabsBar(query);
        } catch (err) {
          btn.disabled = false;
          btn.innerHTML = `${icon('alert', { size: 14 })} <span>Повторить</span>`;
          showToast(`Ошибка загрузки: ${err.message || 'Сбой сети'}`);
        }
      });
    });
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
      handleClearSearch();
    });
  }
}
