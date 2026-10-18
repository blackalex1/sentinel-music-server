/**
 * Модуль модального окна сопряжения мобильного приложения через QR-код.
 */

import { icon } from '../../icons.js';

export function renderQrConnectModal() {
  return `
    <div class="modal-overlay" id="qrConnectModal">
      <div class="modal-card" style="max-width: 480px; text-align: center;">
        <div style="display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 4px;">
          <div style="display: flex; align-items: center; gap: 10px; text-align: left;">
            <div style="width: 36px; height: 36px; border-radius: 10px; background: rgba(138, 43, 226, 0.2); display: flex; align-items: center; justify-content: center; color: #8a2be2;">
              ${icon('qr', { size: 20 })}
            </div>
            <div>
              <h3 class="modal-title" style="margin: 0; font-size: 1.25rem;">Подключение смартфона</h3>
              <div class="modal-subtitle" style="margin: 0; font-size: 0.82rem;">Быстрый вход через QR-код</div>
            </div>
          </div>
          <button type="button" class="btn-icon" id="btnCloseQrModal" title="Закрыть">${icon('close', { size: 18 })}</button>
        </div>

        <div class="modal-error" id="qrError"></div>

        <!-- Контейнер QR-кода -->
        <div style="position: relative; margin: 18px auto 14px; width: 230px; height: 230px; background: #ffffff; border-radius: 16px; padding: 12px; box-shadow: 0 8px 32px rgba(0, 0, 0, 0.35); display: flex; align-items: center; justify-content: center;">
          <img id="qrCodeImg" src="" alt="QR-код подключения" style="width: 100%; height: 100%; object-fit: contain; display: none;">
          <div id="qrLoadingSpinner" style="display: flex; flex-direction: column; align-items: center; gap: 8px; color: #333333;">
            <div class="spinner" style="width: 28px; height: 28px; border-width: 3px; border-color: #8a2be2; border-top-color: transparent;"></div>
            <span style="font-size: 0.78rem; font-weight: 600; color: #666666;">Генерация кода...</span>
          </div>
        </div>

        <!-- Сетевой адрес сервера в локальной сети (LAN) -->
        <div style="margin-bottom: 12px; text-align: left;">
          <label class="form-label" style="font-size: 0.72rem; margin-bottom: 6px;">Адрес сервера в локальной сети (LAN):</label>
          <div style="display: flex; gap: 6px;">
            <input type="text" id="qrServerUrlInput" class="form-input" style="padding: 8px 12px; font-size: 0.85rem;" placeholder="http://192.168.1.100:8000">
            <button type="button" class="btn-primary" id="btnQrApplyHost" style="padding: 8px 14px; font-size: 0.82rem; white-space: nowrap;">Обновить</button>
          </div>
        </div>

        <!-- Данные для ручного ввода / копирования -->
        <div style="margin-bottom: 14px; text-align: left;">
          <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 4px;">
            <label class="form-label" style="font-size: 0.72rem; margin: 0;">Строка сопряжения (JSON / Токен):</label>
            <button type="button" class="btn-icon" id="btnCopyQrPayload" title="Скопировать строку" style="padding: 2px 6px; font-size: 0.75rem; color: #8a2be2; display: flex; align-items: center; gap: 4px;">
              ${icon('copy', { size: 13 })} <span>Копировать</span>
            </button>
          </div>
          <input type="text" id="qrPayloadInput" readonly class="form-input" style="padding: 6px 10px; font-size: 0.76rem; background: rgba(0, 0, 0, 0.4); color: #aaaaaa; cursor: pointer; text-overflow: ellipsis;" title="Нажмите, чтобы скопировать">
        </div>

        <!-- Инструкция -->
        <div style="background: rgba(255, 255, 255, 0.03); border: 1px solid rgba(255, 255, 255, 0.07); border-radius: 10px; padding: 10px 14px; text-align: left; font-size: 0.76rem; color: var(--text-muted); margin-bottom: 16px; line-height: 1.4;">
          <div>1. Откройте приложение <strong>Sentinel Music</strong> на Android.</div>
          <div>2. Нажмите <strong>«Вход по QR-коду / Токену»</strong> на экране авторизации.</div>
          <div>3. Вставьте строку сопряжения или отсканируйте камерой.</div>
        </div>

        <!-- Кнопки действий -->
        <div class="modal-actions" style="margin-top: 0; justify-content: space-between;">
          <div style="display: flex; gap: 8px;">
            <button type="button" class="btn-secondary" id="btnRefreshQr" style="padding: 8px 14px; font-size: 0.82rem;">
              ${icon('refresh', { size: 14 })} <span>Новый токен</span>
            </button>
            <a id="btnDownloadQr" class="btn-secondary" download="sentinel_qr_connect.png" style="padding: 8px 14px; font-size: 0.82rem; text-decoration: none;">
              ${icon('download', { size: 14 })} <span>Скачать PNG</span>
            </a>
          </div>
          <button type="button" class="btn-primary" id="btnCloseQrModalAction" style="padding: 8px 18px; font-size: 0.82rem;">Готово</button>
        </div>
      </div>
    </div>
  `;
}
