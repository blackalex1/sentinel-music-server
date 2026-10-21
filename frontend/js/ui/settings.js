/**
 * Контроллер экрана настроек (Settings View Controller).
 * Отвечает за:
 * - Загрузку и сохранение профиля текущего пользователя
 * - Управление списком пользователей для администратора
 * - Настройку адреса подключения сервера и QR-код
 * - Запрос статуса и автоматический выпуск SSL-сертификатов Let's Encrypt / Self-Signed
 */

import { state, updateState } from '../state.js';
import { apiFetch } from '../api.js';
import { getServerHost, setServerHost } from '../config.js';
import { showToast } from './toast.js';
import { showConfirm } from './notifications.js';
import { icon } from '../icons.js';
import { updateUserInfoUI } from './playerControls.js';
import { openQrModal } from './modals.js';
import { switchView } from './navigation.js';

export function initSettingsView() {
  setupProfileForm();
  setupServerHostForm();
  setupAdminUsersSection();
  setupSslSection();
  setupAppUpdateSection();

  // При открытии экрана настроек обновляем видимость и данные
  window.addEventListener('settings:opened', () => {
    refreshSettingsScreen();
    checkAppUpdate(true);
  });
}

export function refreshSettingsScreen() {
  const hostInput = document.getElementById('screenServerHostInput');
  if (hostInput) {
    hostInput.value = getServerHost();
  }

  const isAdmin = state.currentUser && state.currentUser.is_admin;
  const adminUsersCard = document.getElementById('screenAdminUsersCard');
  const sslCard = document.getElementById('screenSslCard');

  if (adminUsersCard) {
    adminUsersCard.style.display = isAdmin ? 'block' : 'none';
    if (isAdmin) loadAdminUsersList();
  }

  if (sslCard) {
    sslCard.style.display = isAdmin ? 'block' : 'none';
    if (isAdmin) loadSslStatus();
  }
}

/**
 * 1. Форма обновления профиля
 */
function setupProfileForm() {
  const form = document.getElementById('screenProfileForm');
  if (!form) return;

  form.addEventListener('submit', async (e) => {
    e.preventDefault();
    const curPwdInput = document.getElementById('screenCurrentPassword');
    const newUnameInput = document.getElementById('screenNewUsername');
    const newPwdInput = document.getElementById('screenNewPassword');

    const current_password = curPwdInput ? curPwdInput.value.trim() : '';
    const new_username = newUnameInput ? newUnameInput.value.trim() : '';
    const new_password = newPwdInput ? newPwdInput.value.trim() : '';

    if (!current_password) {
      showToast('Введите текущий пароль для подтверждения', 'alert');
      return;
    }
    if (!new_username && !new_password) {
      showToast('Укажите новый логин или новый пароль', 'alert');
      return;
    }

    const payload = { current_password };
    if (new_username) payload.new_username = new_username;
    if (new_password) payload.new_password = new_password;

    try {
      const res = await apiFetch('/api/auth/profile', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
      });

      if (res.ok) {
        const data = await res.json();
        showToast('Профиль успешно обновлен!', 'checkCircle');
        if (curPwdInput) curPwdInput.value = '';
        if (newUnameInput) newUnameInput.value = '';
        if (newPwdInput) newPwdInput.value = '';

        if (data.user) {
          updateState('currentUser', data.user);
          updateUserInfoUI(data.user);
        }
      } else {
        const err = await res.json();
        showToast(err.detail || 'Не удалось обновить профиль', 'alert');
      }
    } catch (err) {
      showToast('Ошибка при связи с сервером', 'alert');
    }
  });
}

/**
 * 2. Настройки хоста и QR-код
 */
function setupServerHostForm() {
  const form = document.getElementById('screenServerHostForm');
  const btnQr = document.getElementById('btnScreenOpenQr');

  if (form) {
    form.addEventListener('submit', (e) => {
      e.preventDefault();
      const hostInput = document.getElementById('screenServerHostInput');
      const host = hostInput ? hostInput.value.trim() : '';
      if (!host) return;

      setServerHost(host);
      showToast('Адрес сервера сохранен, переподключение...');
      setTimeout(() => location.reload(), 500);
    });
  }

  if (btnQr) {
    btnQr.addEventListener('click', () => {
      openQrModal();
    });
  }

  // Динамический рендеринг расширений плагинов в карточке настроек
  const extContainer = document.getElementById('settingsPluginExtensions');
  if (extContainer && window.Sentinel && window.Sentinel.ui) {
    window.Sentinel.ui.renderExtensionPoints('settings:view', extContainer);
  }
}

/**
 * 3. Управление пользователями
 */
function setupAdminUsersSection() {
  const btnToggle = document.getElementById('btnScreenToggleAddUser');
  const btnCancel = document.getElementById('btnScreenCancelAddUser');
  const form = document.getElementById('screenAdminCreateUserForm');

  if (btnToggle && form) {
    btnToggle.addEventListener('click', () => {
      const isVisible = form.style.display !== 'none';
      form.style.display = isVisible ? 'none' : 'block';
      if (!isVisible) {
        const input = document.getElementById('screenNewUserLogin');
        if (input) input.focus();
      }
    });
  }

  if (btnCancel && form) {
    btnCancel.addEventListener('click', () => {
      form.style.display = 'none';
    });
  }

  if (form) {
    form.addEventListener('submit', async (e) => {
      e.preventDefault();
      const uInput = document.getElementById('screenNewUserLogin');
      const pInput = document.getElementById('screenNewUserPassword');
      const adminCheck = document.getElementById('screenNewUserIsAdmin');

      const username = uInput ? uInput.value.trim() : '';
      const password = pInput ? pInput.value.trim() : '';
      const is_admin = adminCheck ? adminCheck.checked : false;

      if (!username || !password) return;

      try {
        const res = await apiFetch('/api/auth/users', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ username, password, is_admin })
        });

        if (res.ok) {
          showToast(`Пользователь «${username}» успешно создан!`, 'checkCircle');
          if (uInput) uInput.value = '';
          if (pInput) pInput.value = '';
          if (adminCheck) adminCheck.checked = false;
          form.style.display = 'none';
          loadAdminUsersList();
        } else {
          const err = await res.json();
          showToast(err.detail || 'Не удалось создать пользователя', 'alert');
        }
      } catch (err) {
        showToast('Ошибка при связи с сервером', 'alert');
      }
    });
  }
}

async function loadAdminUsersList() {
  const listEl = document.getElementById('screenAdminUsersList');
  if (!listEl) return;

  try {
    const res = await apiFetch('/api/auth/users');
    if (!res.ok) {
      listEl.innerHTML = '<div style="color: var(--text-muted); padding: 12px; text-align: center;">Не удалось загрузить список</div>';
      return;
    }
    const users = await res.json();
    if (!users || users.length === 0) {
      listEl.innerHTML = '<div style="color: var(--text-muted); padding: 12px; text-align: center;">Пользователи отсутствуют</div>';
      return;
    }

    listEl.innerHTML = users.map(u => {
      const isCurrent = state.currentUser && state.currentUser.id === u.id;
      const deleteBtn = isCurrent ? '' : `
        <button type="button" class="btn-icon btn-screen-del-user" data-user-id="${u.id}" data-username="${escapeHtml(u.username)}" title="Удалить аккаунт" style="color: var(--text-muted); padding: 4px 8px;">
          ${icon('close', { size: 15 })}
        </button>
      `;
      const adminBadge = u.is_admin ? '<span class="settings-user-badge-admin">ADMIN</span>' : '';

      return `
        <div class="settings-user-row">
          <div style="display: flex; align-items: center; gap: 10px;">
            <span style="font-size: 14px; font-weight: 500; color: var(--text-primary);">${escapeHtml(u.username)}</span>
            ${adminBadge}
            ${isCurrent ? '<span style="font-size: 11px; color: var(--text-muted);">(вы)</span>' : ''}
          </div>
          ${deleteBtn}
        </div>
      `;
    }).join('');

    listEl.querySelectorAll('.btn-screen-del-user').forEach(btn => {
      btn.addEventListener('click', async (e) => {
        e.stopPropagation();
        const userId = btn.dataset.userId;
        const uname = btn.dataset.username;
        const ok = await showConfirm({
          title: 'Удаление пользователя',
          subtitle: `Пользователь: ${uname}`,
          message: `Вы действительно хотите удалить учетную запись «${uname}»? Все персональные данные, история и настройки будут безвозвратно удалены.`,
          confirmText: 'Удалить',
          cancelText: 'Отмена',
          type: 'danger',
          icon: 'trash'
        });
        if (!ok) return;

        try {
          const delRes = await apiFetch(`/api/auth/users/${userId}`, { method: 'DELETE' });
          if (delRes.ok) {
            showToast(`Пользователь «${uname}» удален`, 'checkCircle');
            loadAdminUsersList();
          } else {
            const err = await delRes.json();
            showToast(err.detail || 'Не удалось удалить пользователя', 'alert');
          }
        } catch (e) {
          showToast('Ошибка при удалении', 'alert');
        }
      });
    });
  } catch (err) {
    listEl.innerHTML = '<div style="color: var(--text-muted); padding: 12px; text-align: center;">Ошибка загрузки</div>';
  }
}

/**
 * 4. Управление и выпуск SSL-сертификатов
 */
function setupSslSection() {
  const form = document.getElementById('screenSslForm');
  if (!form) return;

  form.addEventListener('submit', async (e) => {
    e.preventDefault();
    const domainInput = document.getElementById('screenSslDomain');
    const emailInput = document.getElementById('screenSslEmail');
    const selfSignedCheck = document.getElementById('screenSslSelfSigned');
    const submitBtn = document.getElementById('btnSubmitSsl');

    const domain = domainInput ? domainInput.value.trim() : '';
    const email = emailInput ? emailInput.value.trim() : '';
    const is_self_signed = selfSignedCheck ? selfSignedCheck.checked : false;

    if (!domain) {
      showToast('Укажите доменное имя', 'alert');
      return;
    }

    if (submitBtn) {
      submitBtn.disabled = true;
      submitBtn.textContent = is_self_signed ? 'Генерация сертификата...' : 'Выпуск Let\'s Encrypt (ACME)...';
    }

    try {
      const res = await apiFetch('/api/system/ssl/generate', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ domain, email, is_self_signed })
      });

      if (res.ok) {
        const data = await res.json();
        showToast(data.message || 'SSL сертификат успешно установлен!', 'checkCircle');
        loadSslStatus();
      } else {
        const err = await res.json();
        showToast(err.detail || 'Ошибка при выпуске сертификата', 'alert');
      }
    } catch (err) {
      showToast('Ошибка при связи с сервером', 'alert');
    } finally {
      if (submitBtn) {
        submitBtn.disabled = false;
        submitBtn.textContent = 'Выпустить SSL сертификат';
      }
    }
  });
}

async function loadSslStatus() {
  const bannerText = document.getElementById('screenSslStatusText');
  const dot = document.getElementById('screenSslDot');
  if (!bannerText) return;

  try {
    const res = await apiFetch('/api/system/ssl/status');
    if (!res.ok) {
      bannerText.textContent = 'Не удалось получить статус SSL';
      return;
    }
    const data = await res.json();
    if (data.installed) {
      if (dot) dot.style.background = '#10b981';
      const typeStr = data.is_self_signed ? 'Самоподписанный' : 'Let\'s Encrypt (Доверенный)';
      bannerText.innerHTML = `
        <span><b>Активен:</b> ${escapeHtml(data.common_name)} (${typeStr}) — действует до ${escapeHtml(data.expires_at || '—')}</span>
      `;
    } else {
      if (dot) dot.style.background = 'var(--text-muted)';
      bannerText.textContent = 'Сертификат не установлен. Сервер работает по HTTP.';
    }
  } catch (err) {
    bannerText.textContent = 'Ошибка проверки SSL';
  }
}

function escapeHtml(str) {
  if (!str) return '';
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#039;');
}


/**
 * 5. Проверка и загрузка обновлений с GitHub
 */
let CURRENT_APP_VERSION = '0.0.2';
const isTauriDesktop = !!(window.__TAURI_INTERNALS__ || window.__TAURI__);
const GITHUB_DESKTOP_REPO = isTauriDesktop ? 'blackalex1/sentinel-music-desktop' : 'blackalex1/sentinel-music-server';

function setupAppUpdateSection() {
  const btnCheck = document.getElementById('btnCheckAppUpdate');
  if (btnCheck) {
    btnCheck.addEventListener('click', () => checkAppUpdate(false));
  }
  // Первоначальное определение актуальной версии сервера при работе в Web
  if (!isTauriDesktop) {
    apiFetch('/api/system/version')
      .then(r => r.ok ? r.json() : null)
      .then(info => {
        if (info && info.version) {
          CURRENT_APP_VERSION = info.version;
          const verEl = document.getElementById('appCurrentVersionText');
          if (verEl) verEl.textContent = `v${info.version}`;
        }
      })
      .catch(() => {});
  }
}

async function checkAppUpdate(silent = false) {
  const statusEl = document.getElementById('appUpdateStatusText');
  const btnCheck = document.getElementById('btnCheckAppUpdate');
  const btnDownload = document.getElementById('btnDownloadAppUpdate');
  const notesEl = document.getElementById('appUpdateNotes');

  if (!statusEl) return;

  if (!silent) {
    statusEl.textContent = 'Проверка обновлений на GitHub...';
    statusEl.style.color = 'var(--text-muted)';
    if (btnCheck) btnCheck.disabled = true;
  }

  // Обновляем версию сервера из API перед проверкой
  if (!isTauriDesktop) {
    try {
      const vRes = await apiFetch('/api/system/version');
      if (vRes.ok) {
        const vInfo = await vRes.json();
        if (vInfo.version) CURRENT_APP_VERSION = vInfo.version;
      }
    } catch (_) {}
  }

  try {
    const res = await fetch(`https://api.github.com/repos/${GITHUB_DESKTOP_REPO}/releases/latest`, {
      headers: { 'Accept': 'application/vnd.github.v3+json' }
    });

    if (!res.ok) {
      if (res.status === 404) {
        statusEl.textContent = 'Релизов пока нет. У вас актуальная версия.';
        return;
      }
      throw new Error(`Статус GitHub: ${res.status}`);
    }

    const data = await res.json();
    const latestTag = (data.tag_name || '').replace(/^v/, '').trim();
    const isAdmin = !!(state.currentUser && state.currentUser.is_admin);

    if (isNewerVersion(latestTag, CURRENT_APP_VERSION)) {
      statusEl.innerHTML = `<span style="color: #10b981; font-weight: 600;">✓ Доступна новая версия: v${latestTag}!</span>`;
      if (btnDownload) {
        btnDownload.style.display = 'inline-flex';
        btnDownload.disabled = false;
        btnDownload.style.opacity = '1';
        btnDownload.style.pointerEvents = 'auto';

        if (!isTauriDesktop) {
          // В Web-интерфейсе сервера предлагаем обновление в 1 клик для администратора
          if (isAdmin) {
            btnDownload.textContent = `Обновить сервер до v${latestTag}`;
            btnDownload.onclick = (e) => {
              e.preventDefault();
              triggerServerUpdate(latestTag);
            };
          } else {
            btnDownload.textContent = `Открыть v${latestTag} на GitHub`;
            btnDownload.onclick = (e) => {
              e.preventDefault();
              openExternalUrl(data.html_url);
            };
            statusEl.innerHTML += `<div style="margin-top: 4px; color: var(--text-muted); font-size: 0.8rem;">Автообновление доступно администратору сервера.</div>`;
          }
        } else {
          // В приложении Desktop скачиваем и обновляем в 1 клик
          const portableAsset = (data.assets || []).find(a => a.name.toLowerCase().includes('portable') && a.name.endsWith('.exe'));
          const setupAsset = (data.assets || []).find(a => a.name.toLowerCase().includes('setup') && a.name.endsWith('.exe'));
          const targetAsset = portableAsset || setupAsset;
          const downloadUrl = targetAsset ? targetAsset.browser_download_url : data.html_url;

          btnDownload.textContent = `Обновить приложение до v${latestTag}`;
          btnDownload.onclick = async (e) => {
            e.preventDefault();
            if (!targetAsset) {
              openExternalUrl(downloadUrl);
              return;
            }
            const confirmed = await showConfirm(
              `Обновить Sentinel Music Desktop до версии v${latestTag}?\n\n` +
              `Приложение автоматически скачает обновление и перезапустится за несколько секунд.`
            );
            if (!confirmed) return;

            btnDownload.disabled = true;
            btnDownload.style.opacity = '0.6';
            btnDownload.style.pointerEvents = 'none';
            btnDownload.textContent = '⏳ Скачивание и обновление...';
            if (btnCheck) btnCheck.disabled = true;
            if (statusEl) {
              statusEl.innerHTML = `<span style="color: #38bdf8;">⏳ Загрузка версии v${latestTag} с GitHub и замена файлов... Пожалуйста, подождите.</span>`;
            }

            try {
              const invoke = window.__TAURI__?.core?.invoke || window.__TAURI_INTERNALS__?.invoke;
              if (typeof invoke === 'function') {
                await invoke('install_desktop_update', {
                  downloadUrl: targetAsset.browser_download_url,
                  isInstaller: !portableAsset
                });
              } else {
                openExternalUrl(downloadUrl);
              }
            } catch (err) {
              showToast(err || 'Ошибка при обновлении приложения', 'alert');
              if (statusEl) {
                statusEl.innerHTML = `<span style="color: #f87171;">Ошибка: ${escapeHtml(err)}</span>`;
              }
              btnDownload.disabled = false;
              btnDownload.style.opacity = '1';
              btnDownload.style.pointerEvents = 'auto';
              btnDownload.textContent = `Повторить обновление до v${latestTag}`;
              if (btnCheck) btnCheck.disabled = false;
            }
          };
        }
      }
      if (notesEl && data.body) {
        notesEl.style.display = 'block';
        const escaped = (data.body || '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
        const linked = escaped.replace(/(https?:\/\/[^\s]+)/g, '<a href="$1" target="_blank" style="color: #a78bfa; text-decoration: underline;">$1</a>');
        notesEl.innerHTML = linked;
      }
      if (!silent) {
        showToast(`Доступно обновление Sentinel Music v${latestTag}`, 'success');
      }
    } else {
      statusEl.textContent = `У вас установлена самая свежая версия (v${CURRENT_APP_VERSION}).`;
      statusEl.style.color = '#94a3b8';
      if (btnDownload) btnDownload.style.display = 'none';
      if (notesEl) notesEl.style.display = 'none';
      if (!silent) {
        showToast('Установлена актуальная версия', 'info');
      }
    }
  } catch (err) {
    if (!silent) {
      statusEl.textContent = 'Не удалось связаться с GitHub. Проверьте интернет-соединение.';
      statusEl.style.color = '#f87171';
      showToast('Ошибка при проверке обновлений', 'alert');
    }
  } finally {
    if (btnCheck) btnCheck.disabled = false;
  }
}

async function triggerServerUpdate(latestTag) {
  const confirmed = await showConfirm(
    `Обновить Sentinel Music Server до версии v${latestTag}?\n\n` +
    `Сервер автоматически загрузит актуальные изменения с GitHub и перезапустится.\n` +
    `Связь временно прервется на 3-5 секунд.`
  );
  if (!confirmed) return;

  const statusEl = document.getElementById('appUpdateStatusText');
  const btnDownload = document.getElementById('btnDownloadAppUpdate');
  const btnCheck = document.getElementById('btnCheckAppUpdate');

  if (btnDownload) {
    btnDownload.disabled = true;
    btnDownload.style.opacity = '0.6';
    btnDownload.style.pointerEvents = 'none';
    btnDownload.textContent = '⏳ Применение обновления...';
  }
  if (btnCheck) btnCheck.disabled = true;
  if (statusEl) {
    statusEl.innerHTML = `<span style="color: #38bdf8;">⏳ Загрузка обновления с GitHub и перезапуск сервера... Пожалуйста, не закрывайте страницу.</span>`;
  }

  try {
    const res = await apiFetch('/api/system/update', { method: 'POST' });
    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: 'Ошибка сервера' }));
      throw new Error(err.detail || 'Не удалось запустить обновление');
    }

    showToast('Обновление применено! Сервер перезапускается...', 'info');

    // Ожидание перезапуска сервера: пингуем /api/auth/status каждые 2 секунды
    let attempts = 0;
    const maxAttempts = 30; // до 60 секунд ожидания
    const pollInterval = setInterval(async () => {
      attempts++;
      try {
        const ping = await fetch('/api/auth/status', { cache: 'no-store' });
        if (ping.ok) {
          clearInterval(pollInterval);
          if (statusEl) {
            statusEl.innerHTML = `<span style="color: #10b981; font-weight: 600;">✓ Сервер успешно обновлен до v${latestTag}! Перезагрузка страницы...</span>`;
          }
          showToast(`Сервер успешно обновлен до v${latestTag}!`, 'checkCircle');
          setTimeout(() => {
            window.location.reload();
          }, 1500);
        }
      } catch (_) {
        if (attempts >= maxAttempts) {
          clearInterval(pollInterval);
          if (statusEl) {
            statusEl.innerHTML = `<span style="color: #f87171;">Сервер перезапускается дольше обычного. Обновите страницу вручную.</span>`;
          }
          if (btnDownload) {
            btnDownload.disabled = false;
            btnDownload.style.opacity = '1';
            btnDownload.style.pointerEvents = 'auto';
          }
          if (btnCheck) btnCheck.disabled = false;
        }
      }
    }, 2000);
  } catch (err) {
    showToast(err.message || 'Ошибка обновления сервера', 'alert');
    if (statusEl) {
      statusEl.innerHTML = `<span style="color: #f87171;">Ошибка: ${escapeHtml(err.message)}</span>`;
    }
    if (btnDownload) {
      btnDownload.disabled = false;
      btnDownload.style.opacity = '1';
      btnDownload.style.pointerEvents = 'auto';
      btnDownload.textContent = `Повторить обновление до v${latestTag}`;
    }
    if (btnCheck) btnCheck.disabled = false;
  }
}

function isNewerVersion(latest, current) {
  if (!latest || !current) return false;
  const pLatest = latest.split('.').map(n => parseInt(n, 10) || 0);
  const pCurrent = current.split('.').map(n => parseInt(n, 10) || 0);
  for (let i = 0; i < Math.max(pLatest.length, pCurrent.length); i++) {
    const l = pLatest[i] || 0;
    const c = pCurrent[i] || 0;
    if (l > c) return true;
    if (l < c) return false;
  }
  return false;
}


export function openExternalUrl(url) {
  if (!url) return;
  try {
    if (window.__TAURI__ && window.__TAURI__.core && typeof window.__TAURI__.core.invoke === 'function') {
      window.__TAURI__.core.invoke('open_in_browser', { url }).catch(err => {
        console.warn('[Desktop] Tauri open_in_browser error:', err);
        fallbackOpen(url);
      });
      return;
    }
    if (window.__TAURI_INTERNALS__ && typeof window.__TAURI_INTERNALS__.invoke === 'function') {
      window.__TAURI_INTERNALS__.invoke('open_in_browser', { url }).catch(err => {
        console.warn('[Desktop] Tauri internals open_in_browser error:', err);
        fallbackOpen(url);
      });
      return;
    }
  } catch (e) {
    console.warn('[Desktop] Error invoking Tauri open_in_browser:', e);
  }
  fallbackOpen(url);
}

function fallbackOpen(url) {
  try {
    const win = window.open(url, '_blank');
    if (!win) {
      window.location.href = url;
    }
  } catch (_) {
    window.location.href = url;
  }
}
