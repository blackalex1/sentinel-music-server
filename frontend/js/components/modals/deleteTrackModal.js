/**
 * Модуль модального окна подтверждения удаления трека из фонотеки.
 * Оснащен векторными SVG-иконками Sentinel Design System.
 */

import { icon } from '../../icons.js';

export function renderDeleteTrackModal() {
  return `
    <div class="modal-overlay" id="deleteTrackModal">
      <div class="modal-card">
        <h3 class="modal-title" style="color: var(--accent-rose); display: flex; align-items: center; gap: 8px;">
          ${icon('trash', { size: 20, className: 'icon-danger' })}
          <span>Удалить трек</span>
        </h3>
        <div class="modal-subtitle">Вы уверены, что хотите удалить этот трек из фонотеки?</div>

        <div id="deleteTrackPreview" style="display: flex; align-items: center; gap: 14px; background: rgba(255, 255, 255, 0.04); border: 1px solid var(--border-subtle); border-radius: var(--radius-md); padding: 12px; margin-bottom: 20px;">
          <img id="deleteTrackCover" src="" alt="" style="width: 48px; height: 48px; border-radius: var(--radius-sm); object-fit: cover; background: #222;" />
          <div style="overflow: hidden; flex: 1;">
            <div id="deleteTrackTitle" style="font-weight: 700; font-size: 0.95rem; color: #fff; white-space: nowrap; overflow: hidden; text-overflow: ellipsis;">—</div>
            <div id="deleteTrackArtist" style="font-size: 0.82rem; color: var(--text-secondary); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; margin-top: 2px;">—</div>
          </div>
        </div>

        <div style="margin-bottom: 24px;">
          <label style="display: flex; align-items: center; gap: 10px; cursor: pointer; user-select: none; font-size: 0.88rem; color: var(--text-primary);">
            <input type="checkbox" id="deleteTrackFileCheckbox" checked style="width: 16px; height: 16px; accent-color: var(--accent-rose); cursor: pointer;" />
            <span>Удалить аудиофайл с диска сервера</span>
          </label>
          <div style="font-size: 0.75rem; color: var(--text-muted); margin-top: 4px; margin-left: 26px;">
            При снятой галочке трек удалится только из базы данных фонотеки.
          </div>
        </div>

        <div class="modal-actions">
          <button type="button" class="btn-secondary" id="btnCancelDeleteTrack">Отмена</button>
          <button type="button" class="btn-danger" id="btnConfirmDeleteTrack">Удалить</button>
        </div>
      </div>
    </div>
  `;
}
