/**
 * Модуль модального окна создания нового плейлиста.
 */

export function renderPlaylistModal() {
  return `
    <div class="modal-overlay" id="playlistModal">
      <div class="modal-card">
        <h3 class="modal-title">Новый плейлист</h3>
        <div class="modal-subtitle">Укажите название плейлиста</div>
        
        <form id="playlistForm">
          <div class="form-group">
            <input type="text" id="playlistTitleInput" class="form-input" placeholder="Название плейлиста" required>
          </div>
          <div class="modal-actions">
            <button type="button" class="btn-secondary" onclick="document.getElementById('playlistModal').classList.remove('active')">Отмена</button>
            <button type="submit" class="btn-primary">Создать</button>
          </div>
        </form>
      </div>
    </div>
  `;
}
