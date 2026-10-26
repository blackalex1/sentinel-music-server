/**
 * Модуль модального окна выбора активного устройства Sentinel Connect.
 * Позволяет переключать воспроизведение на колонку (Яндекс.Станция), смартфон или этот ПК.
 */

import { icon } from '../../icons.js';

export function renderDevicesModal() {
  return `
    <div class="modal-overlay" id="devicesModal">
      <div class="modal-card devices-modal-card">
        <div class="devices-modal-header">
          <div class="devices-modal-title-group">
            <div class="devices-modal-icon-badge">
              ${icon('cast', { size: 20 })}
            </div>
            <div>
              <h3 class="modal-title" style="margin: 0; font-size: 1.25rem;">Sentinel Connect</h3>
              <div class="modal-subtitle" style="margin: 0; font-size: 0.82rem;">Управление воспроизведением на устройствах</div>
            </div>
          </div>
          <button type="button" class="btn-icon" id="btnCloseDevicesModal" title="Закрыть">${icon('close', { size: 18 })}</button>
        </div>

        <!-- Текущее локальное устройство -->
        <div class="devices-section-title">Текущее устройство</div>
        <div class="device-card local-device-card active" id="localDeviceCard">
          <div class="device-card-left">
            <div class="device-type-icon monitor-icon">
              ${icon('monitor', { size: 20 })}
            </div>
            <div class="device-card-info">
              <div class="device-card-name" id="localDeviceName">Этот компьютер</div>
              <div class="device-card-desc" id="localDeviceStatus">Локальный вывод звука (в этом браузере / приложении)</div>
            </div>
          </div>
          <div class="device-card-action">
            <span class="device-active-badge" id="localDeviceActiveBadge">Активно</span>
            <button type="button" class="btn-secondary btn-sm" id="btnSelectLocalDevice" style="display: none;">Слушать здесь</button>
          </div>
        </div>

        <!-- Разделитель -->
        <div class="devices-section-title" style="display: flex; justify-content: space-between; align-items: center; margin-top: 18px;">
          <span>Устройства в сети</span>
          <button type="button" class="btn-text-action" id="btnRefreshDevicesList" title="Обновить список устройств">
            ${icon('refresh', { size: 13 })} <span>Обновить</span>
          </button>
        </div>

        <!-- Список найденных сетевых устройств -->
        <div class="devices-list" id="remoteDevicesList">
          <div class="devices-empty-state">
            <div class="spinner-small"></div>
            <span>Поиск устройств в сети...</span>
          </div>
        </div>

        <!-- Подсказка внизу окна -->
        <div class="devices-modal-footer-hint">
          ${icon('wifi', { size: 14 })}
          <span>Колонки и телефоны должны быть включены и подключены к вашему серверу Sentinel Music.</span>
        </div>
      </div>
    </div>
  `;
}
