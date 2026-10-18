/**
 * Sentinel Music — Контроллер пользовательского интерфейса графического эквалайзера и лимитеров.
 * Обеспечивает двустороннее связывание между DOM-элементами модального окна и DSP-движком audioFx.js.
 */

import { audioFx, EQ_PRESETS, LIMITER_MODES } from '../audioFx.js';
import { ensureAudioGraph, toggleLoudnessNormalization } from '../player.js';
import { state as playerState } from '../state.js';
import { showToast } from './toast.js';

let isInitialized = false;

export function openEqualizerModal() {
  const modal = document.getElementById('equalizerModal');
  if (!modal) return;

  // Инициализируем аудио граф при первом открытии окна DSP
  try {
    ensureAudioGraph();
  } catch (_) {}

  syncEqualizerUI(audioFx.getState());
  modal.classList.add('active');
}

export function closeEqualizerModal() {
  const modal = document.getElementById('equalizerModal');
  if (modal) {
    modal.classList.remove('active');
  }
}

export function toggleEqualizerModal() {
  const modal = document.getElementById('equalizerModal');
  if (!modal) return;
  if (modal.classList.contains('active')) {
    closeEqualizerModal();
  } else {
    openEqualizerModal();
  }
}

/**
 * Синхронизирует все элементы интерфейса с текущим состоянием DSP-движка.
 */
export function syncEqualizerUI(s) {
  const state = s || audioFx.getState();
  const modal = document.getElementById('equalizerModal');
  if (!modal) return;

  const card = modal.querySelector('.modal-equalizer');
  const powerToggle = document.getElementById('eqPowerToggle');
  const powerStatus = document.getElementById('eqPowerStatus');
  const presetLabel = document.getElementById('eqCurrentPresetLabel');

  // 0. Нормализация громкости (EBU R128)
  const loudnessToggle = document.getElementById('loudnessPowerToggle');
  const loudnessStatus = document.getElementById('loudnessPowerStatus');
  const loudnessBadge = document.getElementById('loudnessTrackBadge');
  const isNorm = Boolean(playerState.isLoudnessNormalization);

  if (loudnessToggle) loudnessToggle.checked = isNorm;
  if (loudnessStatus) {
    loudnessStatus.textContent = isNorm ? 'Включена' : 'Выключена';
    loudnessStatus.style.color = isNorm ? 'var(--accent-cyan)' : 'var(--text-muted)';
  }
  if (loudnessBadge) {
    if (!isNorm) {
      loudnessBadge.textContent = 'Режим: Оригинальный уровень громкости (без коррекции)';
      loudnessBadge.style.color = 'var(--text-muted)';
    } else if (playerState.currentTrackLoudness !== null && playerState.currentTrackLoudness !== undefined) {
      const sign = (playerState.currentTrackGain || 0) >= 0 ? '+' : '';
      loudnessBadge.textContent = `Текущий трек: ${playerState.currentTrackLoudness} LUFS (коррекция: ${sign}${playerState.currentTrackGain} дБ до -14 LUFS)`;
      loudnessBadge.style.color = 'var(--accent-cyan)';
    } else {
      loudnessBadge.textContent = 'Текущий трек: без EBU-разметки (активен защитный пик-лимитер)';
      loudnessBadge.style.color = 'var(--text-secondary)';
    }
  }

  // 1. Статус питания DSP
  if (powerToggle) powerToggle.checked = state.isEnabled;
  if (powerStatus) {
    powerStatus.textContent = state.isEnabled ? 'Включен' : 'Выключен';
    powerStatus.style.color = state.isEnabled ? 'var(--primary-hover)' : 'var(--text-muted)';
  }
  if (card) {
    card.classList.toggle('eq-disabled', !state.isEnabled);
  }

  // 2. Пресет
  if (presetLabel) {
    presetLabel.textContent = state.currentPreset;
  }
  const presetChips = modal.querySelectorAll('.eq-preset-chip');
  presetChips.forEach(chip => {
    chip.classList.toggle('active', chip.dataset.preset === state.currentPreset);
  });

  // 3. 5 полос эквалайзера
  for (let i = 0; i < 5; i++) {
    const slider = document.getElementById(`eqBandSlider_${i}`);
    const valLabel = document.getElementById(`eqBandVal_${i}`);
    const val = state.bandLevels[i] !== undefined ? state.bandLevels[i] : 0;

    if (slider && Number(slider.value) !== Number(val)) {
      slider.value = val;
    }
    if (valLabel) {
      const sign = val > 0 ? '+' : '';
      valLabel.textContent = `${sign}${val.toFixed(1)} dB`;
      valLabel.className = 'eq-band-db ' + (val > 0 ? 'positive' : val < 0 ? 'negative' : 'zero');
    }
  }

  // 4. Bass Boost
  const bassSlider = document.getElementById('eqBassBoostSlider');
  const bassVal = document.getElementById('eqBassBoostVal');
  if (bassSlider && Number(bassSlider.value) !== state.bassBoostPercent) {
    bassSlider.value = state.bassBoostPercent;
  }
  if (bassVal) {
    const db = ((state.bassBoostPercent / 100.0) * 12.0).toFixed(1);
    bassVal.textContent = `${state.bassBoostPercent}% (+${db} dB)`;
  }

  // 5. Лимитеры
  const limiterCards = modal.querySelectorAll('.eq-limiter-card');
  limiterCards.forEach(cardEl => {
    cardEl.classList.toggle('active', cardEl.dataset.limiter === state.currentLimiterMode);
  });

  // 6. Подсветка кнопок вызова в панели управления плеером
  updateEqualizerStatusButtons(state);
}

/**
 * Обновляет состояние подсветки и подсказок кнопок в PlayerBar и Full Player.
 */
export function updateEqualizerStatusButtons(s) {
  const state = s || audioFx.getState();
  const btnMain = document.getElementById('btnPlayerEqualizer');
  const btnExp = document.getElementById('btnExpandedEqualizer');

  const isLoudness = Boolean(playerState.isLoudnessNormalization);
  const isActive = state.isEnabled || state.currentLimiterMode !== 'off' || isLoudness;
  const limiterCfg = LIMITER_MODES[state.currentLimiterMode] || LIMITER_MODES.soft;

  const eqDesc = state.isEnabled ? state.currentPreset : 'Выкл';
  const normDesc = isLoudness ? '-14 LUFS' : 'Выкл';
  const title = `Настройки звука: Эквалайзер [${eqDesc}], Нормализация [${normDesc}], Лимитер [${limiterCfg.name}] (E)`;

  [btnMain, btnExp].forEach(btn => {
    if (btn) {
      btn.classList.toggle('active', isActive);
      btn.title = title;
    }
  });
}

/**
 * Инициализирует обработчики событий для эквалайзера и модального окна.
 */
export function setupEqualizerUI() {
  if (isInitialized) return;
  isInitialized = true;

  const modal = document.getElementById('equalizerModal');
  if (!modal) return;

  const btnClose = document.getElementById('btnCloseEqualizerModal');
  const btnApplyClose = document.getElementById('btnApplyEqClose');
  const powerToggle = document.getElementById('eqPowerToggle');
  const loudnessToggle = document.getElementById('loudnessPowerToggle');
  const btnResetFlat = document.getElementById('btnResetEqFlat');
  const bassSlider = document.getElementById('eqBassBoostSlider');

  // Закрытие модального окна
  if (btnClose) btnClose.addEventListener('click', closeEqualizerModal);
  if (btnApplyClose) btnApplyClose.addEventListener('click', closeEqualizerModal);

  modal.addEventListener('click', (e) => {
    if (e.target === modal) {
      closeEqualizerModal();
    }
  });

  // Тумблер Нормализация громкости (EBU R128)
  if (loudnessToggle) {
    loudnessToggle.addEventListener('change', () => {
      toggleLoudnessNormalization();
      syncEqualizerUI();
    });
  }

  // Тумблер Вкл / Выкл
  if (powerToggle) {
    powerToggle.addEventListener('change', (e) => {
      audioFx.setEnabled(e.target.checked);
      const text = e.target.checked ? 'Эквалайзер включен' : 'Эквалайзер отключен (Bypass)';
      showToast(text, 'sliders');
    });
  }

  // Кнопка сброса в Flat
  if (btnResetFlat) {
    btnResetFlat.addEventListener('click', () => {
      audioFx.resetToFlat();
      showToast('Эквалайзер сброшен в Flat (0 dB)', 'refresh');
    });
  }

  // Пресеты
  const presetChips = modal.querySelectorAll('.eq-preset-chip');
  presetChips.forEach(chip => {
    chip.addEventListener('click', () => {
      const presetName = chip.dataset.preset;
      if (presetName && EQ_PRESETS[presetName] !== undefined) {
        audioFx.setPreset(presetName);
        showToast(`Пресет «${presetName}» применен`, 'sliders');
      }
    });
  });

  // 5 полос фейдеров
  for (let i = 0; i < 5; i++) {
    const slider = document.getElementById(`eqBandSlider_${i}`);
    if (slider) {
      slider.addEventListener('input', (e) => {
        const val = parseFloat(e.target.value);
        audioFx.setBandLevel(i, val);
      });
    }
  }

  // Bass Boost
  if (bassSlider) {
    bassSlider.addEventListener('input', (e) => {
      const val = parseInt(e.target.value, 10);
      audioFx.setBassBoost(val);
    });
  }

  // Режимы Лимитера
  const limiterCards = modal.querySelectorAll('.eq-limiter-card');
  limiterCards.forEach(cardEl => {
    cardEl.addEventListener('click', () => {
      const mode = cardEl.dataset.limiter;
      if (mode && LIMITER_MODES[mode]) {
        audioFx.setLimiterMode(mode);
        const name = LIMITER_MODES[mode].name;
        showToast(`Режим лимитера: ${name}`, 'sliders');
      }
    });
  });

  // Реактивная подписка на изменения состояния audioFx
  audioFx.subscribe((newState) => {
    syncEqualizerUI(newState);
  });

  // Первичная синхронизация UI
  syncEqualizerUI(audioFx.getState());
}
