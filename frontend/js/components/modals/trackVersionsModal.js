/**
 * Модуль модального окна выбора версии трека (Не та версия / Замена).
 */

export function renderTrackVersionsModal() {
  return `
    <div class="modal-overlay" id="trackVersionsModal">
      <div class="modal-card modal-card-wide">
        <h3 class="modal-title">Версии трека</h3>
        <div class="modal-subtitle">Выберите подходящую версию (оригинал, без цензуры, slowed, remix и др.)</div>

        <div class="version-current-info" id="versionCurrentInfo">
          <div class="version-current-text" id="versionCurrentText">
            Текущий трек: <strong>—</strong>
          </div>
        </div>

        <div class="version-filter-chips" id="versionFilterChips">
          <button class="version-filter-chip active" data-filter="all">Все</button>
          <button class="version-filter-chip" data-filter="flac">FLAC Lossless</button>
          <button class="version-filter-chip" data-filter="explicit">18+ Explicit</button>
          <button class="version-filter-chip" data-filter="remix">Remix / Edit</button>
          <span id="dynamicSourceFilterChips" style="display: contents;"></span>
        </div>

        <div class="candidates-scroll-area" id="candidatesList">
          <!-- Заполняется динамически -->
        </div>

        <div class="modal-actions">
          <button type="button" class="btn-secondary" onclick="document.getElementById('trackVersionsModal').classList.remove('active')">Закрыть</button>
        </div>
      </div>
    </div>
  `;
}
