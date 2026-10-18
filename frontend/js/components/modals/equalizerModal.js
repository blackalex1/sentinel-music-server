/**
 * Sentinel Music — Модальное окно графического эквалайзера и лимитеров (Equalizer & Limiter Modal).
 * Предоставляет 5-полосный эквалайзер, выбор пресетов, регулировку Bass Boost и 5 режимов лимитера (как в Android).
 */

import { icon } from '../../icons.js';
import { EQ_FREQUENCIES, EQ_PRESETS, LIMITER_MODES } from '../../audioFx.js';

export function renderEqualizerModal() {
  const presetKeys = Object.keys(EQ_PRESETS);
  const limiterKeys = Object.keys(LIMITER_MODES);

  return `
    <div class="modal-overlay" id="equalizerModal">
      <div class="modal-card modal-equalizer">
        <!-- Шапка окна: Заголовок, статус, тумблер питания и кнопка закрытия -->
        <div class="eq-modal-header">
          <div class="eq-header-left">
            <div class="eq-header-icon">${icon('equalizer', { size: 24 })}</div>
            <div>
              <h3 class="modal-title" style="margin-bottom: 2px;">Настройки звука и Эквалайзер</h3>
              <div class="modal-subtitle" style="margin-bottom: 0;">Аппаратная DSP-обработка звука и нормализация EBU R128</div>
            </div>
          </div>
          <div class="eq-header-right">
            <label class="eq-switch-label" title="Включить или отключить эквалайзер">
              <span class="eq-switch-text" id="eqPowerStatus">Включен</span>
              <input type="checkbox" id="eqPowerToggle" class="eq-toggle-input" checked />
              <span class="eq-toggle-slider"></span>
            </label>
            <button type="button" class="btn-icon-close" id="btnCloseEqualizerModal" title="Закрыть (Esc)">
              ${icon('close', { size: 20 })}
            </button>
          </div>
        </div>

        <div class="eq-modal-body">
          <!-- Секция: Нормализация громкости (EBU R128) -->
          <div class="eq-section eq-loudness-card">
            <div class="eq-loudness-header">
              <div class="eq-loudness-title-wrap">
                <span class="eq-loudness-icon">${icon('sliders', { size: 18 })}</span>
                <div>
                  <div class="eq-loudness-title">Нормализация громкости (EBU R128)</div>
                  <div class="eq-loudness-subtitle">Автоматическое выравнивание всех треков к единому уровню (-14 LUFS)</div>
                </div>
              </div>
              <label class="eq-switch-label" title="Включить или отключить нормализацию громкости">
                <span class="eq-switch-text" id="loudnessPowerStatus">Включена</span>
                <input type="checkbox" id="loudnessPowerToggle" class="eq-toggle-input" checked />
                <span class="eq-toggle-slider"></span>
              </label>
            </div>
            <div class="eq-loudness-track-info">
              <span class="eq-loudness-badge" id="loudnessTrackBadge">Текущий трек: без поправки</span>
            </div>
          </div>

          <!-- Секция выбора пресетов -->
          <div class="eq-section">
            <div class="eq-section-title">
              <span>Пресеты эквалайзера</span>
              <span class="eq-active-preset-badge" id="eqCurrentPresetLabel">Обычный (Flat)</span>
            </div>
            <div class="eq-presets-chips" id="eqPresetsContainer">
              ${presetKeys.map(name => `
                <button type="button" class="eq-preset-chip" data-preset="${name}">
                  ${name}
                </button>
              `).join('')}
            </div>
          </div>

          <!-- 5-полосный графический эквалайзер -->
          <div class="eq-section eq-console-wrapper">
            <div class="eq-console-grid">
              ${EQ_FREQUENCIES.map((freq, idx) => {
                const freqLabel = freq >= 1000 ? `${freq / 1000} кГц` : `${freq} Гц`;
                const bandNames = ['Низкие (60)', 'Мидбас (230)', 'Средние (910)', 'Высокие (3.6k)', 'Воздух (14k)'];
                return `
                  <div class="eq-band-col" data-band-index="${idx}">
                    <span class="eq-band-db" id="eqBandVal_${idx}">0.0 dB</span>
                    <div class="eq-fader-track">
                      <div class="eq-fader-ticks">
                        <span class="eq-tick tick-plus">+12</span>
                        <span class="eq-tick tick-zero">0</span>
                        <span class="eq-tick tick-minus">-12</span>
                      </div>
                      <input type="range" class="eq-fader-slider" id="eqBandSlider_${idx}" 
                             min="-12" max="12" step="0.5" value="0" orient="vertical" />
                    </div>
                    <span class="eq-band-freq">${freqLabel}</span>
                    <span class="eq-band-name">${bandNames[idx]}</span>
                  </div>
                `;
              }).join('')}
            </div>
          </div>

          <!-- Регулятор Bass Boost -->
          <div class="eq-section eq-bass-boost-section">
            <div class="eq-bass-header">
              <div class="eq-bass-title">
                <span class="eq-bass-icon">${icon('zap', { size: 16 })}</span>
                <span>Глубокий бас (Bass Boost @ 100 Hz)</span>
              </div>
              <span class="eq-bass-value" id="eqBassBoostVal">0% (0.0 dB)</span>
            </div>
            <div class="eq-bass-slider-wrapper">
              <input type="range" id="eqBassBoostSlider" class="eq-horizontal-slider" min="0" max="100" step="1" value="0" />
            </div>
          </div>

          <!-- Режимы Лимитера -->
          <div class="eq-section eq-limiter-section">
            <div class="eq-section-title">
              <div style="display: flex; align-items: center; gap: 6px;">
                <span>${icon('sliders', { size: 16 })}</span>
                <span>Режим Лимитера (Dynamic Limiter & Peak Protection)</span>
              </div>
              <span style="font-size: 0.75rem; color: var(--text-muted);">Защита от перегрузок и выравнивание динамики</span>
            </div>
            <div class="eq-limiter-grid">
              ${limiterKeys.map(key => {
                const item = LIMITER_MODES[key];
                return `
                  <div class="eq-limiter-card" data-limiter="${item.id}">
                    <div class="eq-limiter-card-header">
                      <span class="eq-limiter-card-name">${item.name}</span>
                      <span class="eq-limiter-badge ${item.id === 'soft' ? 'badge-recommend' : ''}">${item.badge}</span>
                    </div>
                    <div class="eq-limiter-card-desc">${item.desc}</div>
                  </div>
                `;
              }).join('')}
            </div>
          </div>
        </div>

        <!-- Нижняя панель действий -->
        <div class="eq-modal-footer">
          <button type="button" class="btn-secondary" id="btnResetEqFlat">
            ${icon('refresh', { size: 15 })} <span>Сбросить в Flat</span>
          </button>
          <button type="button" class="btn-primary" id="btnApplyEqClose">
            Готово
          </button>
        </div>
      </div>
    </div>
  `;
}
