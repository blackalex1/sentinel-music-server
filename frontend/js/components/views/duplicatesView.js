/**
 * Модуль экрана «Управление дубликатами треков» (Duplicates View).
 * Оснащен векторными SVG-иконками Sentinel Design System.
 */

import { icon } from '../../icons.js';

export function renderDuplicatesView() {
  return `
    <section id="viewDuplicates" style="display: none;">
      <div class="duplicates-view-header">
        <div class="duplicates-header-title">
          <h2 style="font-size: 1.5rem; font-weight: 800; margin: 0; display: flex; align-items: center; gap: 10px;">
            ${icon('copy', { size: 22 })} <span>Дубликаты треков</span>
          </h2>
          <p class="duplicates-header-desc">
            Обнаружение и очистка одинаковых треков из разных источников. Сравните битрейт и форматы, чтобы оставить наилучшую версию и освободить место на диске.
          </p>
        </div>

        <div class="duplicates-header-actions">
          <button class="btn-secondary" id="btnRefreshDuplicates" title="Повторно проверить фонотеку на наличие дубликатов">
            ${icon('refresh', { size: 15 })} <span>Обновить</span>
          </button>
          <button class="btn-primary" id="btnResolveAllDuplicates" title="Автоматически оставить лучшие FLAC/HQ версии во всех группах и удалить дубли" style="display: none;">
            ${icon('sparkles', { size: 15 })} <span>Оставить все лучшие</span>
          </button>
        </div>
      </div>

      <!-- Сводная панель статистики -->
      <div class="duplicates-stats-bar" id="duplicatesStatsBar">
        <div class="stat-card">
          <div class="stat-icon">${icon('copy', { size: 20 })}</div>
          <div class="stat-info">
            <span class="stat-value" id="statDupGroups">0</span>
            <span class="stat-label">Групп дубликатов</span>
          </div>
        </div>

        <div class="stat-card">
          <div class="stat-icon">${icon('trash', { size: 20 })}</div>
          <div class="stat-info">
            <span class="stat-value" id="statDupExtra">0</span>
            <span class="stat-label">Лишних копий</span>
          </div>
        </div>

        <div class="stat-card">
          <div class="stat-icon">${icon('database', { size: 20 })}</div>
          <div class="stat-info">
            <span class="stat-value" id="statDupSize">0 MB</span>
            <span class="stat-label">Можно освободить</span>
          </div>
        </div>
      </div>

      <!-- Поисковый фильтр среди дубликатов -->
      <div class="duplicates-filter-bar">
        <div class="duplicates-search-wrapper">
          <span class="duplicates-search-icon">${icon('search', { size: 15 })}</span>
          <input
            type="text"
            id="duplicatesSearchInput"
            class="duplicates-search-input"
            placeholder="Фильтр по исполнителю или названию трека..."
            autocomplete="off"
          />
          <button id="duplicatesSearchClear" class="duplicates-search-clear" style="display: none;" title="Очистить">
            ${icon('close', { size: 14 })}
          </button>
        </div>
      </div>

      <!-- Контейнер для отображения списка групп -->
      <div class="duplicates-list-container" id="duplicatesList">
        <div class="duplicates-loading">
          <div class="duplicates-spinner"></div>
          <span>Поиск дубликатов в фонотеке...</span>
        </div>
      </div>
    </section>
  `;
}
