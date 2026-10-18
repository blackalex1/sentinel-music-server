import { icon } from '../../icons.js';

export function renderServerSettingsModal() {
  return `
    <div class="modal-overlay" id="serverSettingsModal">
      <div class="modal-card">
        <h3 class="modal-title">Подключение к серверу</h3>
        <div class="modal-subtitle">Укажите адрес вашего музыкального сервера</div>
        
        <form id="serverSettingsForm">
          <div class="form-group">
            <label class="form-label" for="serverHostInput">URL сервера</label>
            <input type="text" id="serverHostInput" class="form-input" placeholder="http://192.168.1.100:8000 или http://localhost:8000" required>
          </div>
          <div class="modal-actions">
            <button type="button" class="btn-secondary" onclick="document.getElementById('serverSettingsModal').classList.remove('active')">Отмена</button>
            <button type="submit" class="btn-primary">Сохранить</button>
          </div>
        </form>

        <div style="margin-top: 20px; padding-top: 16px; border-top: 1px solid var(--border-color); display: flex; justify-content: space-between; align-items: center;">
          <span style="font-size: 0.82rem; color: var(--text-muted);">Android приложение:</span>
          <button type="button" class="btn-secondary" id="btnOpenQrFromSettings" style="padding: 6px 12px; font-size: 0.8rem; display: inline-flex; align-items: center; gap: 6px;">
            ${icon('qr', { size: 15 })} <span>Подключить по QR</span>
          </button>
        </div>
      </div>
    </div>
  `;
}
