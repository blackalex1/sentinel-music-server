/**
 * Модуль модального окна ручной загрузки аудиофайлов с компьютера в фонотеку.
 * Оснащен векторными SVG-иконками Sentinel Design System и модульными стилями.
 */

import { icon } from '../../icons.js';

export function renderUploadTracksModal() {
  return `
    <div class="modal-overlay" id="uploadTracksModal">
      <div class="modal-card upload-modal-card">
        <div class="upload-modal-header">
          <h3 class="modal-title" style="display: flex; align-items: center; gap: 8px;">
            ${icon('upload', { size: 20 })}
            <span>Загрузка треков</span>
          </h3>
          <button type="button" class="btn-icon" id="btnCloseUploadModal" title="Закрыть">
            ${icon('close', { size: 18 })}
          </button>
        </div>
        <div class="modal-subtitle" style="margin-bottom: 18px;">
          Загрузите аудиофайлы с вашего компьютера прямо в фонотеку. Метаданные (артист, название, обложка) определятся автоматически.
        </div>

        <!-- Зона Drag & Drop -->
        <div class="upload-drop-zone" id="uploadDropZone">
          <div class="upload-drop-icon">
            ${icon('uploadCloud', { size: 44 })}
          </div>
          <div class="upload-drop-text">Перетащите аудиофайлы сюда</div>
          <div class="upload-drop-subtext">или <span class="upload-browse-btn">выберите на компьютере</span></div>
          <div class="upload-formats-badge">FLAC, MP3, M4A, WAV, OGG</div>
          <input type="file" id="uploadFileInput" multiple accept=".mp3,.flac,.m4a,.wav,.ogg,audio/*" style="display: none;" />
        </div>

        <div style="margin-top: 10px; text-align: center;">
          <button type="button" id="btnOpenBatchFromUploadModal" style="background: none; border: none; font-size: 0.8rem; color: var(--primary); cursor: pointer; display: inline-flex; align-items: center; gap: 6px; padding: 4px 8px; border-radius: 4px;">
            ${icon('download', { size: 14 })} <span>Открыть отчет пакетного скачивания</span>
          </button>
        </div>

        <!-- Список выбранных файлов -->
        <div id="uploadSelectedSection" class="upload-selected-section" style="display: none;">
          <div class="upload-selected-header">
            <span class="upload-selected-title">
              Выбрано файлов: <span id="uploadSelectedCount">0</span>
            </span>
            <button type="button" id="btnClearSelectedFiles" class="upload-btn-clear">Очистить всё</button>
          </div>
          <div class="upload-files-list" id="uploadFilesList"></div>
        </div>

        <!-- Контейнер прогресса загрузки -->
        <div id="uploadProgressSection" class="upload-progress-section" style="display: none;">
          <div class="upload-progress-header">
            <span id="uploadProgressStatus" style="font-weight: 600; color: var(--text-primary);">Загрузка файлов...</span>
            <span id="uploadProgressPercent" style="font-weight: 700; color: var(--primary);">0%</span>
          </div>
          <div class="upload-progress-track">
            <div class="upload-progress-bar" id="uploadProgressBar" style="width: 0%;"></div>
          </div>
        </div>

        <!-- Ошибки -->
        <div class="modal-error" id="uploadError" style="margin-top: 14px; margin-bottom: 0;"></div>

        <!-- Кнопки действий -->
        <div class="modal-actions" style="margin-top: 22px;">
          <button type="button" class="btn-secondary" id="btnCancelUpload">Отмена</button>
          <button type="button" class="btn-primary" id="btnSubmitUpload" disabled>Начать загрузку</button>
        </div>
      </div>
    </div>
  `;
}
