/**
 * Sentinel Music — Экран «Поток» (Adaptive Personal Stream).
 * Центральный интерактивный экран с органической светящейся сферой,
 * динамическими звуковыми импульсами, переключателями настроения и частоты открытий.
 */

import { icon } from '../../icons.js';

export function renderStreamView() {
  return `
    <section id="viewStream" class="view-stream-container" data-mood="default" style="display: none;">
      <!-- Динамическая плазменная аура фона -->
      <div class="stream-ambient-glow" aria-hidden="true">
        <div class="aurora-blob aurora-1"></div>
        <div class="aurora-blob aurora-2"></div>
        <div class="aurora-blob aurora-3"></div>
      </div>

      <div class="stream-stage-content">
        <!-- Индикатор статуса AI -->
        <div class="stream-header-badge">
          <span class="stream-badge-pulse"></span>
          <span class="stream-badge-text">УМНЫЙ AI ПОТОК</span>
        </div>

        <!-- Центральная интерактивная сфера Потока со звуковыми импульсами -->
        <div class="stream-orb-stage" id="streamOrbStage">
          <!-- Звуковые эхо-кольца при воспроизведении музыки -->
          <div class="stream-echo-ring ring-1"></div>
          <div class="stream-echo-ring ring-2"></div>
          <div class="stream-echo-ring ring-3"></div>

          <!-- Сфера Потока -->
          <div class="stream-orb-wrapper" id="streamOrbContainerLarge" title="Включить / Приостановить Поток (Пробел)">
            <div class="stream-orb-halo"></div>
            <div class="stream-orb-core" id="streamOrbLargeCore">
              <div class="stream-orb-specular"></div>
            </div>
            <button class="stream-orb-glass-btn" id="streamOrbLargeBtn" title="Воспроизвести / Пауза">
              <span class="stream-btn-icon" id="streamOrbLargeIcon">
                ${icon('play', { size: 38 })}
              </span>
            </button>
          </div>
        </div>

        <!-- Заголовок и статус -->
        <h1 class="stream-hero-title">
          <span class="stream-title-gradient">Поток</span>
        </h1>
        <p class="stream-hero-subtitle" id="streamHeroSubtitle">
          Музыка подстраивается под ваш ритм, вкусы и реакции в реальном времени
        </p>

        <!-- Карточка играющего трека внутри Потока -->
        <div class="stream-now-playing" id="streamNowPlaying">
          <div class="stream-np-cover-wrap">
            <img src="" alt="" class="stream-np-cover" id="streamNpCover" style="display: none;">
            <div class="stream-np-placeholder" id="streamNpPlaceholder">
              ${icon('music', { size: 20 })}
            </div>
            <div class="stream-np-eq" id="streamNpEq">
              <span class="eq-bar"></span>
              <span class="eq-bar"></span>
              <span class="eq-bar"></span>
            </div>
          </div>
          <div class="stream-np-info">
            <div class="stream-np-title" id="streamNpTitle">Поток готов к запуску</div>
            <div class="stream-np-artist" id="streamNpArtist">Нажмите на сферу для старта</div>
          </div>
          <div class="stream-np-actions">
            <button class="stream-np-btn btn-np-like" id="btnStreamLike" title="Нравится">
              ${icon('heart', { size: 18 })}
            </button>
            <button class="stream-np-btn btn-np-dislike" id="btnStreamDislike" title="Не нравится (пропустить)">
              ${icon('thumbsDown', { size: 18 })}
            </button>
            <button class="stream-np-btn btn-np-next" id="btnStreamNext" title="Следующий трек">
              ${icon('skipForward', { size: 18 })}
            </button>
          </div>
        </div>

        <!-- Стеклянная док-панель управления Потоком -->
        <div class="stream-controls-dock">
          <!-- Фильтры настроения (Mood Chips) -->
          <div class="stream-dock-section">
            <div class="stream-section-header">
              <span class="stream-section-caption">НАСТРОЕНИЕ</span>
            </div>
            <div class="stream-mood-chips">
              <button class="mood-chip stream-mood-chip active" data-mood="default" title="Все подряд без ограничений">
                <span class="mood-icon-wrap icon-sparkles">${icon('sparkles', { size: 16 })}</span>
                <span>Все подряд</span>
              </button>
              <button class="mood-chip stream-mood-chip" data-mood="energy" title="Высокий темп и драйв">
                <span class="mood-icon-wrap icon-energy">${icon('flame', { size: 16 })}</span>
                <span>Бодрое</span>
              </button>
              <button class="mood-chip stream-mood-chip" data-mood="chill" title="Спокойный и чилловый ритм">
                <span class="mood-icon-wrap icon-chill">${icon('moon', { size: 16 })}</span>
                <span>Спокойное</span>
              </button>
              <button class="mood-chip stream-mood-chip" data-mood="happy" title="Позитивная и яркая музыка">
                <span class="mood-icon-wrap icon-happy">${icon('sun', { size: 16 })}</span>
                <span>Радостное</span>
              </button>
              <button class="mood-chip stream-mood-chip" data-mood="sad" title="Меланхоличные и глубокие треки">
                <span class="mood-icon-wrap icon-sad">${icon('cloudRain', { size: 16 })}</span>
                <span>Грустное</span>
              </button>
            </div>
          </div>

          <div class="stream-dock-divider"></div>

          <!-- Частота новых открытий (Discovery Frequency) -->
          <div class="stream-dock-section">
            <div class="stream-section-header">
              <span class="stream-section-caption">НОВАЯ МУЗЫКА</span>
            </div>
            <div class="stream-discovery-chips">
              <button class="stream-discovery-chip" data-ratio="0.0" title="Только треки из моей коллекции">
                <span>Только знакомое</span>
                <span class="chip-tag">0%</span>
              </button>
              <button class="stream-discovery-chip" data-ratio="0.1" title="Редко подмешивать новые открытия">
                <span>Редко</span>
                <span class="chip-tag">10%</span>
              </button>
              <button class="stream-discovery-chip active" data-ratio="0.2" title="Сбалансированный поток открытий (по умолчанию)">
                <span>Иногда</span>
                <span class="chip-tag">20%</span>
              </button>
              <button class="stream-discovery-chip" data-ratio="0.4" title="Часто знакомить с новой музыкой">
                <span>Часто</span>
                <span class="chip-tag">40%</span>
              </button>
              <button class="stream-discovery-chip" data-ratio="1.0" title="Только новые треки и свежие открытия">
                <span>Только новое</span>
                <span class="chip-tag">100%</span>
              </button>
            </div>
          </div>
        </div>
      </div>
    </section>
  `;
}
