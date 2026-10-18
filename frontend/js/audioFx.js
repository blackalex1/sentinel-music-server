/**
 * Sentinel Music — Аудио-движок DSP: Эквалайзер и Лимитеры (Web Audio API).
 * Полный аналог DSP-модуля из Android-приложения (EqualizerManager.kt).
 */

export const EQ_FREQUENCIES = [60, 230, 910, 3600, 14000];

export const EQ_PRESETS = {
  "Обычный (Flat)": [0, 0, 0, 0, 0],
  "Рок": [4.5, 2.0, -1.0, 2.5, 4.5],
  "Поп": [-1.0, 2.0, 4.0, 2.0, -1.0],
  "Джаз": [3.5, 2.0, 0.0, 2.0, 3.5],
  "Хип-Хоп": [5.5, 3.0, 0.0, 1.5, 3.5],
  "Электроника": [4.5, 2.0, 0.0, 3.0, 4.5],
  "Классика": [3.5, 2.5, 0.0, 2.0, 3.5],
  "Усиление вокала": [-2.0, 1.0, 4.0, 2.0, -1.0],
  "Глубокий бас": [6.0, 4.0, 1.5, 0.0, 0.0],
  "Пользовательский": null
};

export const LIMITER_MODES = {
  off: {
    id: "off",
    name: "Выключен (Bypass)",
    badge: "Bypass",
    desc: "Чистый оригинальный звук без вмешательства в динамику",
    threshold: 0.0,
    knee: 0.0,
    ratio: 1.0,
    attack: 0.010,
    release: 0.100
  },
  soft: {
    id: "soft",
    name: "Мягкий (Soft)",
    badge: "Рекомендуется",
    desc: "Прозрачный лимитер без пампинга и заиканий звука",
    threshold: -0.5,
    knee: 12.0,
    ratio: 3.0,
    attack: 0.020,
    release: 0.250
  },
  balanced: {
    id: "balanced",
    name: "Студийный (Studio)",
    badge: "Balanced",
    desc: "Сбалансированная динамика и плотный контроль пиков",
    threshold: -1.0,
    knee: 6.0,
    ratio: 6.0,
    attack: 0.010,
    release: 0.150
  },
  hard: {
    id: "hard",
    name: "Защитный (Brickwall)",
    badge: "Brickwall",
    desc: "Строгий лимитер для защиты динамиков от клиппинга",
    threshold: -0.1,
    knee: 0.0,
    ratio: 20.0,
    attack: 0.003,
    release: 0.050
  },
  night: {
    id: "night",
    name: "Ночной режим (Night)",
    badge: "Night",
    desc: "Выравнивание тихих и громких звуков для комфорта ночью",
    threshold: -18.0,
    knee: 12.0,
    ratio: 4.0,
    attack: 0.015,
    release: 0.300
  }
};

class AudioFxEngine {
  constructor() {
    this.audioCtx = null;
    this.inputNode = null;
    this.outputNode = null;

    // Узлы графа
    this.bassBoostNode = null;
    this.eqNodes = [];
    this.limiterNode = null;

    // Состояние
    this.isEnabled = localStorage.getItem('sentinel_eq_enabled') === 'true';
    this.currentPreset = localStorage.getItem('sentinel_eq_preset') || 'Обычный (Flat)';
    this.bassBoostPercent = parseInt(localStorage.getItem('sentinel_eq_bass') || '0', 10);
    this.currentLimiterMode = localStorage.getItem('sentinel_limiter_mode') || 'soft';

    // Загрузка уровней полос
    let savedBands = null;
    try {
      const raw = localStorage.getItem('sentinel_eq_bands');
      if (raw) savedBands = JSON.parse(raw);
    } catch (_) {}

    if (Array.isArray(savedBands) && savedBands.length === 5) {
      this.bandLevels = savedBands.map(v => Math.max(-12, Math.min(12, Number(v) || 0)));
    } else {
      this.bandLevels = (EQ_PRESETS[this.currentPreset] || [0, 0, 0, 0, 0]).slice();
    }

    this._listeners = [];
  }

  init(audioCtx, inputNode, outputNode) {
    this.audioCtx = audioCtx;
    this.inputNode = inputNode;
    this.outputNode = outputNode;

    try {
      // 1. Узел Bass Boost (Low-shelf 100 Hz)
      this.bassBoostNode = this.audioCtx.createBiquadFilter();
      this.bassBoostNode.type = 'lowshelf';
      this.bassBoostNode.frequency.setValueAtTime(100, this.audioCtx.currentTime);

      // 2. 5 полос эквалайзера
      this.eqNodes = EQ_FREQUENCIES.map((freq, idx) => {
        const filter = this.audioCtx.createBiquadFilter();
        filter.frequency.setValueAtTime(freq, this.audioCtx.currentTime);

        if (idx === 0) {
          filter.type = 'lowshelf';
        } else if (idx === EQ_FREQUENCIES.length - 1) {
          filter.type = 'highshelf';
        } else {
          filter.type = 'peaking';
          filter.Q.setValueAtTime(1.0, this.audioCtx.currentTime);
        }
        return filter;
      });

      // 3. Узел Лимитера (DynamicsCompressor)
      this.limiterNode = this.audioCtx.createDynamicsCompressor();

      // Соединение цепочки:
      // inputNode -> bassBoostNode -> eq[0] -> ... -> eq[4] -> limiterNode -> outputNode
      let prevNode = this.inputNode;

      prevNode.connect(this.bassBoostNode);
      prevNode = this.bassBoostNode;

      for (const eqNode of this.eqNodes) {
        prevNode.connect(eqNode);
        prevNode = eqNode;
      }

      prevNode.connect(this.limiterNode);
      this.limiterNode.connect(this.outputNode);

      // Применяем сохраненные настройки к созданным узлам
      this.applyAll();
    } catch (err) {
      console.warn('[AudioFX] Ошибка инициализации графа DSP:', err);
    }
  }

  applyAll() {
    this.applyEq();
    this.applyBassBoost();
    this.applyLimiter();
  }

  applyEq() {
    if (!this.audioCtx || this.eqNodes.length !== 5) return;
    const now = this.audioCtx.currentTime;

    for (let i = 0; i < 5; i++) {
      const targetGain = this.isEnabled ? this.bandLevels[i] : 0.0;
      try {
        this.eqNodes[i].gain.setTargetAtTime(targetGain, now, 0.03);
      } catch (_) {
        this.eqNodes[i].gain.value = targetGain;
      }
    }
  }

  applyBassBoost() {
    if (!this.audioCtx || !this.bassBoostNode) return;
    const now = this.audioCtx.currentTime;
    // 0..100% -> 0..+12 dB
    const targetGain = this.isEnabled ? (this.bassBoostPercent / 100.0) * 12.0 : 0.0;

    try {
      this.bassBoostNode.gain.setTargetAtTime(targetGain, now, 0.03);
    } catch (_) {
      this.bassBoostNode.gain.value = targetGain;
    }
  }

  applyLimiter() {
    if (!this.audioCtx || !this.limiterNode) return;
    const cfg = LIMITER_MODES[this.currentLimiterMode] || LIMITER_MODES.soft;
    const now = this.audioCtx.currentTime;

    try {
      this.limiterNode.threshold.setTargetAtTime(cfg.threshold, now, 0.03);
      this.limiterNode.knee.setTargetAtTime(cfg.knee, now, 0.03);
      this.limiterNode.ratio.setTargetAtTime(cfg.ratio, now, 0.03);
      this.limiterNode.attack.setTargetAtTime(cfg.attack, now, 0.03);
      this.limiterNode.release.setTargetAtTime(cfg.release, now, 0.03);
    } catch (_) {
      this.limiterNode.threshold.value = cfg.threshold;
      this.limiterNode.knee.value = cfg.knee;
      this.limiterNode.ratio.value = cfg.ratio;
      this.limiterNode.attack.value = cfg.attack;
      this.limiterNode.release.value = cfg.release;
    }
  }

  setEnabled(enabled) {
    this.isEnabled = !!enabled;
    localStorage.setItem('sentinel_eq_enabled', this.isEnabled ? 'true' : 'false');
    this.applyEq();
    this.applyBassBoost();
    this._notify();
  }

  setBandLevel(index, levelDb) {
    if (index < 0 || index >= 5) return;
    const clamped = Math.max(-12, Math.min(12, Math.round(Number(levelDb) * 10) / 10));
    this.bandLevels[index] = clamped;
    this.currentPreset = "Пользовательский";

    localStorage.setItem('sentinel_eq_bands', JSON.stringify(this.bandLevels));
    localStorage.setItem('sentinel_eq_preset', this.currentPreset);

    if (this.audioCtx && this.eqNodes[index]) {
      const now = this.audioCtx.currentTime;
      const target = this.isEnabled ? clamped : 0.0;
      try {
        this.eqNodes[index].gain.setTargetAtTime(target, now, 0.03);
      } catch (_) {
        this.eqNodes[index].gain.value = target;
      }
    }
    this._notify();
  }

  setPreset(name) {
    const preset = EQ_PRESETS[name];
    if (!preset) return;

    this.currentPreset = name;
    this.bandLevels = preset.slice();

    localStorage.setItem('sentinel_eq_preset', name);
    localStorage.setItem('sentinel_eq_bands', JSON.stringify(this.bandLevels));

    this.applyEq();
    this._notify();
  }

  setBassBoost(percent) {
    const clamped = Math.max(0, Math.min(100, Math.round(Number(percent) || 0)));
    this.bassBoostPercent = clamped;
    localStorage.setItem('sentinel_eq_bass', clamped.toString());

    this.applyBassBoost();
    this._notify();
  }

  setLimiterMode(mode) {
    if (!LIMITER_MODES[mode]) mode = 'soft';
    this.currentLimiterMode = mode;
    localStorage.setItem('sentinel_limiter_mode', mode);

    this.applyLimiter();
    this._notify();
  }

  resetToFlat() {
    this.setPreset("Обычный (Flat)");
    this.setBassBoost(0);
  }

  getState() {
    return {
      isEnabled: this.isEnabled,
      currentPreset: this.currentPreset,
      bandLevels: [...this.bandLevels],
      bassBoostPercent: this.bassBoostPercent,
      currentLimiterMode: this.currentLimiterMode,
      frequencies: [...EQ_FREQUENCIES]
    };
  }

  subscribe(listener) {
    this._listeners.push(listener);
    return () => {
      this._listeners = this._listeners.filter(l => l !== listener);
    };
  }

  _notify() {
    const s = this.getState();
    for (const cb of this._listeners) {
      try {
        cb(s);
      } catch (_) {}
    }
  }
}

export const audioFx = new AudioFxEngine();
