/**
 * Модуль компонента нижней панели плеера (Player Bar).
 * Оснащен векторными SVG-иконками Sentinel Design System.
 */

import { icon } from '../icons.js';

export function renderPlayerBar() {
  return `
    <footer class="bottom-player-bar">
      <!-- Левая секция: обложка, название, лайк -->
      <div class="player-left">
        <img id="playerTrackCover" class="player-cover" src="" alt="" style="display: none; cursor: pointer;" title="Развернуть полноэкранный плеер" />
        <div class="player-track-info">
          <div id="playerTrackTitle" class="player-title">Трек не выбран</div>
          <div id="playerTrackArtist" class="player-artist">Sentinel Music</div>
          <div id="playerDevicePill" class="player-device-pill" style="display: none;" title="Нажмите, чтобы изменить устройство">
            ${icon('cast', { size: 12 })} <span id="playerDevicePillName">Колонка</span>
          </div>
        </div>
        <div class="player-reactions">
          <button id="btnPlayerLike" class="btn-like" title="Нравится">
            ${icon('heart', { size: 18 })}
          </button>
          <button id="btnPlayerDislike" class="btn-dislike" title="Не нравится (пропустить)">
            ${icon('thumbsDown', { size: 18 })}
          </button>
          <button id="btnPlayerReplace" class="btn-replace" title="Заменить трек (Не та версия / найти альтернативу)">
            ${icon('refresh', { size: 16 })}
          </button>
        </div>
      </div>

      <!-- Центральная секция: кнопки управления и таймлайн -->
      <div class="player-center">
        <div class="player-controls">
          <button id="btnShuffle" class="ctrl-btn-secondary" title="Перемешать (S)">
            ${icon('shuffle', { size: 17 })}
          </button>
          <button id="ctrlPrevBtn" class="ctrl-btn-secondary" title="Предыдущий (Shift+←)">
            ${icon('skipBack', { size: 18 })}
          </button>
          <button id="ctrlPlayBtn" class="ctrl-btn-play" title="Воспроизведение (Пробел)">
            ${icon('play', { size: 18 })}
          </button>
          <button id="ctrlNextBtn" class="ctrl-btn-secondary" title="Следующий (Shift+→)">
            ${icon('skipForward', { size: 18 })}
          </button>
          <button id="btnRepeat" class="ctrl-btn-secondary" title="Повтор (R)">
            ${icon('repeat', { size: 17 })}
          </button>
        </div>

        <div class="timeline-container">
          <span id="timeCurrent" class="time-label">0:00</span>
          <div class="timeline-bar" id="timelineBar">
            <div class="timeline-fill" id="timelineFill">
              <div class="timeline-thumb"></div>
            </div>
          </div>
          <span id="timeTotal" class="time-label">0:00</span>
        </div>
      </div>

      <!-- Правая секция: устройства, эквалайзер/настройки звука, караоке, очередь и громкость -->
      <div class="player-right">
        <button id="btnPlayerConnect" class="btn-feature" title="Устройства Sentinel Connect (D)">
          ${icon('cast', { size: 18 })}
        </button>
        <button id="btnPlayerEqualizer" class="btn-feature" title="Настройки звука и эквалайзер (E)">
          ${icon('equalizer', { size: 18 })}
        </button>
        <button id="btnPlayerLyrics" class="btn-feature" title="Текст песни (L)">
          ${icon('fileText', { size: 18 })}
        </button>
        <button id="btnPlayerQueue" class="btn-feature" title="Очередь воспроизведения (Q)">
          ${icon('queue', { size: 18 })}
        </button>
        <div class="volume-container">
          <button id="btnVolumeIcon" class="btn-feature" title="Звук (M)">
            ${icon('volume', { size: 18 })}
          </button>
          <div class="volume-slider" id="volumeSlider">
            <div class="volume-fill" id="volumeFill"></div>
          </div>
        </div>
      </div>
    </footer>
  `;
}
