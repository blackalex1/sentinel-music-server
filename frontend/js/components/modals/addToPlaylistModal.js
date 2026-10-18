/**
 * Модуль модального окна добавления трека в плейлист.
 */

export function renderAddToPlaylistModal() {
  return `
    <div class="modal-overlay" id="addToPlaylistModal">
      <div class="modal-card">
        <h3 class="modal-title">Добавить в плейлист</h3>
        <div class="modal-subtitle">Выберите целевой плейлист</div>
        
        <div id="addToPlaylistList" style="max-height: 240px; overflow-y: auto; display: flex; flex-direction: column; gap: 4px; margin-bottom: 20px;">
          <!-- Заполняется динамически -->
        </div>
        
        <div class="modal-actions">
          <button type="button" class="btn-secondary" onclick="document.getElementById('addToPlaylistModal').classList.remove('active')">Закрыть</button>
        </div>
      </div>
    </div>
  `;
}
