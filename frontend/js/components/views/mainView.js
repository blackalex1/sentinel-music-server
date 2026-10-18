/**
 * Модуль экрана «Главное» (Hero «Поток», фильтры настроения, аналитика, недавние треки).
 * Оснащен векторными SVG-иконками Sentinel Design System.
 */

import { icon } from '../../icons.js';

export function renderMainView() {
  return `
    <section id="viewMain">
      <!-- Секция: Подборки по настроению в коллекции треков -->
      <div class="mood-collections-section">
        <div class="mood-section-header">
          <div>
            <h2 class="mood-section-title">Подборки по настроению</h2>
            <p class="mood-section-subtitle">Ваша фонотека по результатам психоакустического анализа</p>
          </div>
          <button class="mood-all-chip active" id="btnMoodAll" data-mood="default" title="Показать все недавно добавленные треки коллекции">
            ${icon('sparkles', { size: 14 })} <span>Все треки</span>
          </button>
        </div>

        <!-- Виджет статуса аналитики фонотеки -->
        <div class="stream-analytics-banner" id="streamAnalyticsBanner">
          <div class="analytics-info">
            <div class="analytics-title-row">
              <span id="analyticsStatusText">Анализ фонотеки: загрузка...</span>
              <button class="btn-analytics-action" id="btnStartAnalytics" style="display: none;">
                ${icon('zap', { size: 14 })} <span>Запустить анализ</span>
              </button>
            </div>
            <div class="analytics-moods" id="analyticsMoodsText"></div>
          </div>
          <div class="analytics-progress-bar">
            <div class="analytics-progress-fill" id="analyticsProgressFill" style="width: 0%;"></div>
          </div>
        </div>

        <div class="mood-cards-grid">
          <!-- Бодрое -->
          <div class="mood-collection-card mood-card-energy" data-mood="energy" role="button" tabindex="0">
            <div class="mood-card-glow"></div>
            <div class="mood-card-header">
              <div class="mood-badge-icon">
                ${icon('flame', { size: 24 })}
              </div>
              <button class="mood-quick-play-btn" data-mood="energy" title="Слушать микс бодрых треков">
                ${icon('play', { size: 18 })}
              </button>
            </div>
            <div class="mood-card-content">
              <div class="mood-card-title">Бодрое</div>
              <div class="mood-card-desc">Высокий темп и мощная динамика</div>
              <div class="mood-card-count" id="countMoodEnergy">Загрузка...</div>
            </div>
          </div>

          <!-- Спокойное -->
          <div class="mood-collection-card mood-card-chill" data-mood="chill" role="button" tabindex="0">
            <div class="mood-card-glow"></div>
            <div class="mood-card-header">
              <div class="mood-badge-icon">
                ${icon('moon', { size: 24 })}
              </div>
              <button class="mood-quick-play-btn" data-mood="chill" title="Слушать микс спокойных треков">
                ${icon('play', { size: 18 })}
              </button>
            </div>
            <div class="mood-card-content">
              <div class="mood-card-title">Спокойное</div>
              <div class="mood-card-desc">Плавный ритм для отдыха и фокуса</div>
              <div class="mood-card-count" id="countMoodChill">Загрузка...</div>
            </div>
          </div>

          <!-- Радостное -->
          <div class="mood-collection-card mood-card-happy" data-mood="happy" role="button" tabindex="0">
            <div class="mood-card-glow"></div>
            <div class="mood-card-header">
              <div class="mood-badge-icon">
                ${icon('sun', { size: 24 })}
              </div>
              <button class="mood-quick-play-btn" data-mood="happy" title="Слушать микс радостных треков">
                ${icon('play', { size: 18 })}
              </button>
            </div>
            <div class="mood-card-content">
              <div class="mood-card-title">Радостное</div>
              <div class="mood-card-desc">Мажорный вайб и светлая атмосфера</div>
              <div class="mood-card-count" id="countMoodHappy">Загрузка...</div>
            </div>
          </div>

          <!-- Грустное -->
          <div class="mood-collection-card mood-card-sad" data-mood="sad" role="button" tabindex="0">
            <div class="mood-card-glow"></div>
            <div class="mood-card-header">
              <div class="mood-badge-icon">
                ${icon('cloudRain', { size: 24 })}
              </div>
              <button class="mood-quick-play-btn" data-mood="sad" title="Слушать микс грустных треков">
                ${icon('play', { size: 18 })}
              </button>
            </div>
            <div class="mood-card-content">
              <div class="mood-card-title">Грустное</div>
              <div class="mood-card-desc">Глубокое и задумчивое звучание</div>
              <div class="mood-card-count" id="countMoodSad">Загрузка...</div>
            </div>
          </div>
        </div>
      </div>

      <div class="tracks-view-header" style="margin-bottom: 12px;">
        <h2 style="font-size: 1.3rem; font-weight: 800; margin: 0;" id="mainTracksTitle">Недавно добавленные треки</h2>
        <div class="tracks-header-actions" id="mainTracksActions" style="display: none;">
          <button class="btn-primary" id="btnPlayAllMainTracks" title="Воспроизвести подборку сначала">
            ${icon('play', { size: 16 })} <span>Слушать всё</span>
          </button>
          <button class="btn-secondary" id="btnShuffleMainTracks" title="Перемешать треки категории">
            ${icon('shuffle', { size: 16 })} <span>Перемешать</span>
          </button>
        </div>
      </div>
      <div class="track-table-container" id="mainTracksContainer">
        <!-- Таблица треков -->
      </div>
      <!-- Сентинел бесконечной подгрузки треков подборки -->
      <div id="mainTracksScrollSentinel" class="tracks-scroll-sentinel" style="display: none;"></div>
    </section>
  `;
}
