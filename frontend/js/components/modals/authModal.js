/**
 * Модуль модального окна авторизации и регистрации.
 */

export function renderAuthModal() {
  return `
    <div class="modal-overlay" id="authModal">
      <div class="modal-card">
        <h3 class="modal-title" id="authModalTitle">Вход в систему</h3>
        <div class="modal-subtitle">Авторизуйтесь для доступа к вашей фонотеке</div>
        <div class="modal-error" id="authError"></div>
        
        <form id="authForm" data-mode="login">
          <div class="form-group">
            <label class="form-label" for="authUsername">Имя пользователя</label>
            <input type="text" id="authUsername" class="form-input" autocomplete="username" required>
          </div>
          <div class="form-group">
            <label class="form-label" for="authPassword">Пароль</label>
            <input type="password" id="authPassword" class="form-input" autocomplete="current-password" required>
          </div>
          <div class="modal-actions">
            <button type="submit" class="btn-primary" id="authSubmitBtn">Войти</button>
          </div>
        </form>
      </div>
    </div>
  `;
}
