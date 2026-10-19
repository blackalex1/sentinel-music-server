/**
 * Модуль полноэкранного представления настроек (Settings View).
 * Предоставляет разделы:
 * 1. Профиль пользователя (смена логина и пароля).
 * 2. Управление пользователями системы (для администратора).
 * 3. Настройки подключения и QR-код для мобильного приложения.
 * 4. Управление и автоматический выпуск SSL-сертификатов (Let's Encrypt / ACME).
 */

import { icon } from '../../icons.js';

export function renderSettingsView() {
  return `
    <div id="viewSettings" style="display: none;">
      <div class="settings-screen-container">
        <!-- Шапка страницы настроек -->
        <div class="settings-screen-header">
          <div>
            <h2 class="settings-screen-title">
              ${icon('settings', { size: 24 })}
              <span>Параметры и Безопасность</span>
            </h2>
            <div class="settings-screen-subtitle">Управление профилем, пользователями, сетевыми подключениями и SSL</div>
          </div>
        </div>

        <!-- Сетка карточек настроек -->
        <div class="settings-grid">
          
          <!-- 1. Карточка профиля -->
          <div class="settings-card">
            <div class="settings-card-header">
              <div class="settings-card-icon">${icon('music', { size: 20 })}</div>
              <div>
                <h3 class="settings-card-title">Мой профиль</h3>
                <div class="settings-card-desc">Изменение имени пользователя и пароля текущей учетной записи</div>
              </div>
            </div>

            <form id="screenProfileForm">
              <div class="form-group">
                <label class="form-label" for="screenCurrentPassword">Текущий пароль *</label>
                <input type="password" id="screenCurrentPassword" class="form-input" placeholder="Введите текущий пароль для подтверждения" required>
              </div>

              <div class="settings-form-row">
                <div class="form-group" style="flex: 1;">
                  <label class="form-label" for="screenNewUsername">Новый логин</label>
                  <input type="text" id="screenNewUsername" class="form-input" placeholder="Оставьте пустым, если не меняется">
                </div>
                <div class="form-group" style="flex: 1;">
                  <label class="form-label" for="screenNewPassword">Новый пароль</label>
                  <input type="password" id="screenNewPassword" class="form-input" placeholder="Оставьте пустым, если не меняется">
                </div>
              </div>

              <div style="display: flex; justify-content: flex-end; margin-top: 10px;">
                <button type="submit" class="btn-primary" style="padding: 8px 18px;">
                  Сохранить профиль
                </button>
              </div>
            </form>
          </div>

          <!-- 2. Карточка сетевого подключения и Android -->
          <div class="settings-card">
            <div class="settings-card-header">
              <div class="settings-card-icon">${icon('cast', { size: 20 })}</div>
              <div>
                <h3 class="settings-card-title">Подключение и Приложение</h3>
                <div class="settings-card-desc">Адрес сервера для веб-клиента и сопряжение с мобильным приложением</div>
              </div>
            </div>

            <form id="screenServerHostForm">
              <div class="form-group">
                <label class="form-label" for="screenServerHostInput">URL сервера</label>
                <input type="text" id="screenServerHostInput" class="form-input" placeholder="http://192.168.1.100:8000" required>
              </div>

              <div style="display: flex; justify-content: space-between; align-items: center; margin-top: 12px; gap: 12px; flex-wrap: wrap;">
                <button type="button" class="btn-secondary" id="btnScreenOpenQr" style="display: inline-flex; align-items: center; gap: 8px;">
                  ${icon('qr', { size: 16 })} <span>Показать QR-код сопряжения</span>
                </button>
                <button type="submit" class="btn-primary">
                  Сохранить URL
                </button>
              </div>
            </form>
          </div>

          <!-- 3. Карточка SSL / HTTPS (Доступна администратору) -->
          <div class="settings-card" id="screenSslCard" style="display: none;">
            <div class="settings-card-header">
              <div class="settings-card-icon" style="color: #10b981;">${icon('checkCircle', { size: 20 })}</div>
              <div>
                <h3 class="settings-card-title">Безопасность SSL / HTTPS</h3>
                <div class="settings-card-desc">Выпуск доверенного сертификата Let's Encrypt (ACME) или самоподписанного</div>
              </div>
            </div>

            <!-- Текущий статус SSL -->
            <div class="ssl-status-banner" id="screenSslBanner">
              <div class="status-dot" id="screenSslDot"></div>
              <div id="screenSslStatusText">Проверка статуса сертификата...</div>
            </div>

            <form id="screenSslForm" style="margin-top: 14px;">
              <div class="settings-form-row">
                <div class="form-group" style="flex: 2;">
                  <label class="form-label" for="screenSslDomain">Доменное имя (FQDN)</label>
                  <input type="text" id="screenSslDomain" class="form-input" placeholder="music.example.com" required>
                </div>
                <div class="form-group" style="flex: 2;">
                  <label class="form-label" for="screenSslEmail">Email для Let's Encrypt</label>
                  <input type="email" id="screenSslEmail" class="form-input" placeholder="admin@example.com">
                </div>
              </div>

              <div style="margin: 10px 0 16px 0;">
                <label style="font-size: 0.85rem; color: var(--text-muted); display: inline-flex; align-items: center; gap: 8px; cursor: pointer;">
                  <input type="checkbox" id="screenSslSelfSigned">
                  <span>Самоподписанный сертификат (для IP / локальной сети LAN без внешнего домена)</span>
                </label>
              </div>

              <div style="display: flex; justify-content: flex-end;">
                <button type="submit" class="btn-primary" id="btnSubmitSsl">
                  Выпустить SSL сертификат
                </button>
              </div>
            </form>
          </div>

          <!-- 4. Карточка пользователей системы (Доступна администратору) -->
          <div class="settings-card settings-card-wide" id="screenAdminUsersCard" style="display: none;">
            <div class="settings-card-header">
              <div class="settings-card-icon" style="color: var(--primary);">${icon('copy', { size: 20 })}</div>
              <div style="flex: 1;">
                <div style="display: flex; justify-content: space-between; align-items: center;">
                  <div>
                    <h3 class="settings-card-title">Пользователи системы</h3>
                    <div class="settings-card-desc">Создание учетных записей слушателей и разграничение прав доступа</div>
                  </div>
                  <button type="button" class="btn-secondary" id="btnScreenToggleAddUser" style="padding: 6px 14px; font-size: 0.82rem;">
                    + Добавить пользователя
                  </button>
                </div>
              </div>
            </div>

            <!-- Форма добавления пользователя -->
            <form id="screenAdminCreateUserForm" style="display: none; background: rgba(255, 255, 255, 0.03); border: 1px solid var(--border-color); border-radius: 8px; padding: 16px; margin-bottom: 16px;">
              <h4 style="margin: 0 0 10px 0; font-size: 0.88rem; font-weight: 600;">Создать аккаунт</h4>
              <div class="settings-form-row">
                <div class="form-group" style="flex: 1;">
                  <label class="form-label" for="screenNewUserLogin">Логин *</label>
                  <input type="text" id="screenNewUserLogin" class="form-input" placeholder="Логин от 3 символов" required>
                </div>
                <div class="form-group" style="flex: 1;">
                  <label class="form-label" for="screenNewUserPassword">Пароль *</label>
                  <input type="password" id="screenNewUserPassword" class="form-input" placeholder="Пароль от 4 символов" required>
                </div>
              </div>
              <div style="display: flex; justify-content: space-between; align-items: center; margin-top: 6px;">
                <label style="font-size: 0.82rem; color: var(--text-muted); display: inline-flex; align-items: center; gap: 6px; cursor: pointer;">
                  <input type="checkbox" id="screenNewUserIsAdmin">
                  <span>Права администратора</span>
                </label>
                <div style="display: flex; gap: 8px;">
                  <button type="button" class="btn-secondary" id="btnScreenCancelAddUser" style="padding: 6px 12px; font-size: 0.82rem;">Отмена</button>
                  <button type="submit" class="btn-primary" style="padding: 6px 16px; font-size: 0.82rem;">Создать</button>
                </div>
              </div>
            </form>

            <!-- Список пользователей -->
            <div id="screenAdminUsersList" class="settings-users-list">
              <div style="text-align: center; color: var(--text-muted); padding: 16px;">Загрузка пользователей...</div>
            </div>
          </div>

        </div>
      </div>
    </div>
  `;
}
