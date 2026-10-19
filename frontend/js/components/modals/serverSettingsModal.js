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

        <!-- Секция администратора: Управление и создание пользователей -->
        <div id="adminUsersSection" style="display: none; margin-top: 24px; padding-top: 18px; border-top: 1px solid var(--border-color);">
          <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px;">
            <h4 style="font-size: 0.95rem; font-weight: 600; margin: 0; color: var(--text-primary); display: flex; align-items: center; gap: 6px;">
              ${icon('copy', { size: 16 })} <span>Пользователи системы</span>
            </h4>
            <button type="button" class="btn-secondary" id="btnToggleAddUserForm" style="padding: 4px 10px; font-size: 0.78rem;">
              + Создать аккаунт
            </button>
          </div>

          <!-- Форма создания нового пользователя -->
          <form id="adminCreateUserForm" style="display: none; background: rgba(255, 255, 255, 0.03); border: 1px solid var(--border-color); border-radius: 8px; padding: 12px; margin-bottom: 14px;">
            <div style="font-size: 0.82rem; font-weight: 600; margin-bottom: 8px; color: var(--text-primary);">Новый пользователь</div>
            <div style="display: flex; gap: 8px; margin-bottom: 8px; flex-wrap: wrap;">
              <input type="text" id="adminNewUsername" class="form-input" placeholder="Логин (от 3 симв.)" style="flex: 1; min-width: 120px;" required>
              <input type="password" id="adminNewPassword" class="form-input" placeholder="Пароль (от 4 симв.)" style="flex: 1; min-width: 120px;" required>
            </div>
            <div style="display: flex; justify-content: space-between; align-items: center;">
              <label style="font-size: 0.8rem; color: var(--text-muted); display: flex; align-items: center; gap: 6px; cursor: pointer;">
                <input type="checkbox" id="adminNewIsAdmin"> Права администратора
              </label>
              <div style="display: flex; gap: 6px;">
                <button type="button" class="btn-secondary" id="btnCancelAddUser" style="padding: 4px 10px; font-size: 0.78rem;">Отмена</button>
                <button type="submit" class="btn-primary" style="padding: 4px 12px; font-size: 0.78rem;">Создать</button>
              </div>
            </div>
          </form>

          <!-- Список пользователей -->
          <div id="adminUsersList" style="max-height: 140px; overflow-y: auto; display: flex; flex-direction: column; gap: 6px;">
            <div style="font-size: 0.8rem; color: var(--text-muted); text-align: center; padding: 8px;">Загрузка пользователей...</div>
          </div>
        </div>

        <!-- Секция профиля текущего пользователя (Смена логина и пароля) -->
        <div id="userProfileSection" style="margin-top: 24px; padding-top: 18px; border-top: 1px solid var(--border-color);">
          <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px;">
            <h4 style="font-size: 0.95rem; font-weight: 600; margin: 0; color: var(--text-primary); display: flex; align-items: center; gap: 6px;">
              ${icon('music', { size: 16 })} <span>Мой профиль</span>
            </h4>
            <button type="button" class="btn-secondary" id="btnToggleProfileForm" style="padding: 4px 10px; font-size: 0.78rem;">
              Изменить логин/пароль
            </button>
          </div>

          <form id="userProfileForm" style="display: none; background: rgba(255, 255, 255, 0.03); border: 1px solid var(--border-color); border-radius: 8px; padding: 12px; margin-bottom: 8px;">
            <div style="font-size: 0.8rem; color: var(--text-muted); margin-bottom: 10px;">
              Для изменения имени пользователя или пароля подтвердите действие текущим паролем.
            </div>
            <div class="form-group" style="margin-bottom: 8px;">
              <label class="form-label" style="font-size: 0.78rem;" for="profileCurrentPassword">Текущий пароль *</label>
              <input type="password" id="profileCurrentPassword" class="form-input" placeholder="Введите текущий пароль" required>
            </div>
            <div style="display: flex; gap: 8px; margin-bottom: 10px; flex-wrap: wrap;">
              <div style="flex: 1; min-width: 130px;">
                <label class="form-label" style="font-size: 0.78rem;" for="profileNewUsername">Новый логин (необязательно)</label>
                <input type="text" id="profileNewUsername" class="form-input" placeholder="Новый логин">
              </div>
              <div style="flex: 1; min-width: 130px;">
                <label class="form-label" style="font-size: 0.78rem;" for="profileNewPassword">Новый пароль (необязательно)</label>
                <input type="password" id="profileNewPassword" class="form-input" placeholder="Новый пароль">
              </div>
            </div>
            <div style="display: flex; justify-content: flex-end; gap: 6px;">
              <button type="button" class="btn-secondary" id="btnCancelProfileEdit" style="padding: 4px 10px; font-size: 0.78rem;">Отмена</button>
              <button type="submit" class="btn-primary" style="padding: 4px 14px; font-size: 0.78rem;">Сохранить изменения</button>
            </div>
          </form>
        </div>
      </div>
    </div>
  `;
}
