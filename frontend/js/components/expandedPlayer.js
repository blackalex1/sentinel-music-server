/**
 * Sentinel Music — Модуль полноэкранного развернутого плеера (Expanded Full Player).
 * Раскрывается при клике на миниатюру обложки в левом нижнем углу интерфейса.
 */

import { icon } from '../icons.js';

export function renderExpandedPlayer() {
  return `
    <div class="expanded-player-overlay" id="expandedPlayerOverlay">
      <!-- Динамический размытый фон обложки -->
      <div class="expanded-player-backdrop">
        <img id="expandedBackdropCover" class="expanded-backdrop-img" src="" alt="" style="display: none;" />
        <div class="expanded-backdrop-gradient"></div>
      </div>

      <div class="expanded-player-container">
        <!-- Верхняя панель: свернуть, статус, шорткаты -->
        <header class="expanded-player-header">
          <button class="expanded-btn-icon" id="btnCollapsePlayer" title="Свернуть плеер (Esc)">
            ${icon('close', { size: 20 })}
          </button>

          <div class="expanded-header-title">
            <span class="expanded-badge-pulse"></span>
            <span>Сейчас играет • Sentinel Player</span>
          </div>

          <div class="expanded-header-actions">
            <button class="expanded-btn-icon" id="btnExpandedReplaceHeader" title="Заменить трек (Не та версия / поиск)">
              ${icon('refresh', { size: 19 })}
            </button>
            <button class="expanded-btn-icon" id="btnExpandedLyrics" title="Текст песни (L)">
              ${icon('fileText', { size: 19 })}
            </button>
            <button class="expanded-btn-icon" id="btnExpandedQueue" title="Очередь воспроизведения (Q)">
              ${icon('queue', { size: 19 })}
            </button>
          </div>
        </header>

        <!-- Центральная секция: обложка и информация -->
        <div class="expanded-player-body">
          <div class="expanded-cover-wrapper">
            <img id="expandedCoverImg" class="expanded-cover-img" src="" alt="" style="display: none;" />
            <div id="expandedCoverPlaceholder" class="expanded-cover-placeholder">
              ${icon('disc', { size: 72 })}
            </div>
            <div class="expanded-cover-glow" id="expandedCoverGlow"></div>
          </div>

          <div class="expanded-track-meta">
            <div class="expanded-meta-text">
              <h1 id="expandedTitle" class="expanded-title">Трек не выбран</h1>
              <div id="expandedArtist" class="expanded-artist">Sentinel Music</div>
              <div id="expandedAlbum" class="expanded-album"></div>
            </div>

            <div class="expanded-reactions">
              <button id="btnExpandedLike" class="btn-expanded-like" title="Нравится">
                ${icon('heart', { size: 22 })}
              </button>
              <button id="btnExpandedDislike" class="btn-expanded-dislike" title="Не нравится (пропустить)">
                ${icon('thumbsDown', { size: 22 })}
              </button>
              <button id="btnExpandedReplace" class="btn-expanded-replace" title="Заменить трек (Не та версия / найти в лучшем качестве)">
                ${icon('refresh', { size: 20 })}
              </button>
            </div>
          </div>

          <!-- Бейджи качества аудио (FLAC/MP3, битрейт, длительность) -->
          <div class="expanded-badges-row" id="expandedBadgesRow">
            <span class="hybrid-badge badge-mp3" id="expandedBadgeFormat">MP3 320</span>
          </div>

          <!-- Таймлайн воспроизведения -->
          <div class="expanded-timeline-section">
            <div class="expanded-timeline-bar" id="expandedTimelineBar">
              <div class="expanded-timeline-fill" id="expandedTimelineFill">
                <div class="expanded-timeline-thumb"></div>
              </div>
            </div>
            <div class="expanded-time-labels">
              <span id="expandedTimeCurrent">0:00</span>
              <span id="expandedTimeTotal">0:00</span>
            </div>
          </div>

          <!-- Основные кнопки управления воспроизведением -->
          <div class="expanded-controls-row">
            <button id="btnExpandedShuffle" class="expanded-ctrl-btn" title="Перемешать (S)">
              ${icon('shuffle', { size: 20 })}
            </button>
            <button id="btnExpandedPrev" class="expanded-ctrl-btn" title="Предыдущий (Shift+←)">
              ${icon('skipBack', { size: 22 })}
            </button>
            <button id="btnExpandedPlay" class="expanded-ctrl-play" title="Воспроизведение / Пауза (Пробел)">
              ${icon('play', { size: 26 })}
            </button>
            <button id="btnExpandedNext" class="expanded-ctrl-btn" title="Следующий (Shift+→)">
              ${icon('skipForward', { size: 22 })}
            </button>
            <button id="btnExpandedRepeat" class="expanded-ctrl-btn" title="Повтор (R)">
              ${icon('repeat', { size: 20 })}
            </button>
          </div>

          <!-- Громкость и настройки звука -->
          <div class="expanded-volume-row">
            <button id="btnExpandedEqualizer" class="expanded-btn-icon" title="Настройки звука и эквалайзер (E)">
              ${icon('equalizer', { size: 18 })}
            </button>
            <button id="btnExpandedVolumeIcon" class="expanded-btn-icon" title="Звук (M)">
              ${icon('volume', { size: 18 })}
            </button>
            <div class="expanded-volume-bar" id="expandedVolumeBar">
              <div class="expanded-volume-fill" id="expandedVolumeFill"></div>
            </div>
          </div>
        </div>
      </div>
    </div>
  `;
}
