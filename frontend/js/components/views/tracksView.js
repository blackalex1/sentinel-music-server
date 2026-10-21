/**
 * Модуль экрана «Коллекция треков» (Шапка, воспроизведение/микс, таблица треков).
 * Оснащен векторными SVG-иконками Sentinel Design System.
 */

import { icon } from '../../icons.js';

export function renderTracksView() {
  return `
    <section id="viewTracks" style="display: none;">
      <div class="tracks-view-header">
        <h2 id="tracksViewTitle" style="font-size: 1.5rem; font-weight: 800; margin: 0;">Коллекция треков</h2>
        <div class="tracks-header-actions">
          <button class="btn-primary" id="btnPlayAllTracks" title="Воспроизвести коллекцию сначала">
            ${icon('play', { size: 16 })} <span>Слушать всё</span>
          </button>
          <button class="btn-secondary" id="btnShuffleAllTracks" title="Серверный случайный микс всей коллекции">
            ${icon('shuffle', { size: 16 })} <span>Перемешать</span>
          </button>
          <button class="btn-secondary" id="btnUploadTracks" title="Загрузить аудиофайлы с компьютера">
            ${icon('upload', { size: 16 })} <span>Загрузить треки</span>
          </button>
        </div>
      </div>

      <!-- Вкладки поиска: В фонотеке / В сети -->
      <div id="searchTabsBar" class="search-tabs-bar" style="display: none;"></div>

      <!-- Фильтры настроения коллекции: только Бодрое, Спокойное, Радостное, Грустное -->
      <div class="tracks-mood-bar" id="tracksMoodBar">
        <button class="tracks-mood-chip active" data-mood="all" id="chipTrackMoodAll">
          <span>Все треки</span>
        </button>
        <button class="tracks-mood-chip" data-mood="energy" id="chipTrackMoodEnergy">
          ${icon('flame', { size: 15 })} <span>Бодрое</span>
        </button>
        <button class="tracks-mood-chip" data-mood="chill" id="chipTrackMoodChill">
          ${icon('moon', { size: 15 })} <span>Спокойное</span>
        </button>
        <button class="tracks-mood-chip" data-mood="happy" id="chipTrackMoodHappy">
          ${icon('sun', { size: 15 })} <span>Радостное</span>
        </button>
        <button class="tracks-mood-chip" data-mood="sad" id="chipTrackMoodSad">
          ${icon('cloudRain', { size: 15 })} <span>Грустное</span>
        </button>
      </div>
      
      <!-- Результаты онлайн-поиска по внешним источникам -->
      <div id="searchCandidatesView" class="search-candidates-view" style="display: none;"></div>
      
      <div class="track-table-container" id="tracksTableContainer">
        <!-- Таблица треков -->
      </div>
      
      <!-- Сентинел бесконечной подгрузки коллекции треков -->
      <div id="tracksScrollSentinel" class="tracks-scroll-sentinel" style="display: none;"></div>
    </section>
  `;
}
