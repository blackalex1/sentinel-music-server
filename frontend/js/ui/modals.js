/**
 * Модуль управления модальными окнами (Авторизация, Плейлисты, Настройки сервера).
 */

import { state, updateState } from '../state.js';
import { apiFetch, apiLogin, apiRegister, createPlaylist, addTrackToPlaylist, deleteTrack, uploadTrackFiles, fetchQrCode, fetchQrHosts } from '../api.js';
import { setAuthToken, getServerHost, setServerHost, getApiBase, API_BASE } from '../config.js';
import { showToast, escapeHtml } from './toast.js';
import { handleTrackDeleted } from '../player.js';
import { loadLibraryTracks } from './trackList.js';
import { icon } from '../icons.js';
import { initRemoteConnect, selectPlaybackDevice, refreshDevicesHttp, requestDevices, getOrCreateDeviceId } from '../remote.js';
import { switchView } from './navigation.js';

let pendingTrackForPlaylist = null;
let pendingTrackToDelete = null;
let onDeleteTrackCallback = null;
let onAuthSuccessCallback = null;
let onPlaylistCreatedCallback = null;

let selectedUploadFiles = [];
const ALLOWED_UPLOAD_EXTS = ['.flac', '.mp3', '.m4a', '.wav', '.ogg'];

function formatFileSize(bytes) {
  if (!bytes || bytes <= 0) return '0 B';
  const units = ['B', 'KB', 'MB', 'GB'];
  let i = 0;
  let val = bytes;
  while (val >= 1024 && i < units.length - 1) {
    val /= 1024;
    i++;
  }
  return `${val.toFixed(i === 0 ? 0 : 1)} ${units[i]}`;
}

function isAudioFile(file) {
  if (!file || !file.name) return false;
  const ext = '.' + file.name.split('.').pop().toLowerCase();
  return ALLOWED_UPLOAD_EXTS.includes(ext) || (file.type && file.type.startsWith('audio/'));
}

function updateUploadModalUI() {
  const selectedSec = document.getElementById('uploadSelectedSection');
  const countSpan = document.getElementById('uploadSelectedCount');
  const filesList = document.getElementById('uploadFilesList');
  const submitBtn = document.getElementById('btnSubmitUpload');
  const errorEl = document.getElementById('uploadError');

  if (countSpan) countSpan.textContent = selectedUploadFiles.length;
  if (submitBtn) submitBtn.disabled = selectedUploadFiles.length === 0;

  if (selectedSec && filesList) {
    if (selectedUploadFiles.length === 0) {
      selectedSec.style.display = 'none';
      filesList.innerHTML = '';
    } else {
      selectedSec.style.display = 'block';
      filesList.innerHTML = selectedUploadFiles.map((f, idx) => `
        <div class="upload-file-item" data-index="${idx}">
          <div class="upload-file-info">
            <span style="display: flex; align-items: center; color: var(--primary);">${icon('music', { size: 16 })}</span>
            <span class="upload-file-name" title="${escapeHtml(f.name)}">${escapeHtml(f.name)}</span>
            <span class="upload-file-size">(${formatFileSize(f.size)})</span>
          </div>
          <button type="button" class="upload-file-remove" data-index="${idx}" title="Удалить из очереди">${icon('close', { size: 14 })}</button>
        </div>
      `).join('');
    }
  }

  if (errorEl) {
    errorEl.style.display = 'none';
    errorEl.textContent = '';
  }
}

function addFilesToUploadQueue(files) {
  if (!files || files.length === 0) return;
  let addedCount = 0;
  let rejectedCount = 0;

  for (let i = 0; i < files.length; i++) {
    const file = files[i];
    if (!isAudioFile(file)) {
      rejectedCount++;
      continue;
    }
    const alreadyInQueue = selectedUploadFiles.some(f => f.name === file.name && f.size === file.size);
    if (!alreadyInQueue) {
      selectedUploadFiles.push(file);
      addedCount++;
    }
  }

  if (rejectedCount > 0) {
    showToast(`Пропущено файлов неподдерживаемого формата: ${rejectedCount} (разрешены: FLAC, MP3, M4A, WAV, OGG)`, 'alert');
  }

  updateUploadModalUI();
}

export function setModalsCallbacks(callbacks = {}) {
  if (callbacks.onAuthSuccess) onAuthSuccessCallback = callbacks.onAuthSuccess;
  if (callbacks.onPlaylistCreated) onPlaylistCreatedCallback = callbacks.onPlaylistCreated;
}

export function setupModals() {
  // Закрытие по клику на фон
  document.querySelectorAll('.modal-overlay').forEach(modal => {
    modal.addEventListener('click', (e) => {
      if (e.target === modal) {
        if (modal.id === 'uploadTracksModal') {
          const submitBtn = document.getElementById('btnSubmitUpload');
          const progressSec = document.getElementById('uploadProgressSection');
          if (submitBtn && submitBtn.disabled && progressSec && progressSec.style.display !== 'none') {
            // Загрузка в процессе, не закрываем по клику на фон
            return;
          }
          hideUploadTracksModal();
          return;
        }
        modal.classList.remove('active');
      }
    });
  });

  // Авторизация / Регистрация
  const authForm = document.getElementById('authForm');
  if (authForm) {
    authForm.addEventListener('submit', async (e) => {
      e.preventDefault();
      const u = document.getElementById('authUsername').value.trim();
      const p = document.getElementById('authPassword').value.trim();
      const errEl = document.getElementById('authError');
      errEl.style.display = 'none';

      if (!u || !p) {
        errEl.textContent = 'Заполните логин и пароль';
        errEl.style.display = 'block';
        return;
      }

      try {
        const isRegister = authForm.dataset.mode === 'register';
        const res = isRegister ? await apiRegister(u, p) : await apiLogin(u, p);
        const data = await res.json();

        if (res.ok && data.token) {
          setAuthToken(data.token);
          updateState('isAuthenticated', true);
          updateState('currentUser', { username: data.username });
          initRemoteConnect();
          hideAuthModal();
          showToast(`Добро пожаловать, ${data.username}!`);
          if (onAuthSuccessCallback) onAuthSuccessCallback(data);
        } else {
          errEl.textContent = data.detail || 'Неверный логин или пароль';
          errEl.style.display = 'block';
        }
      } catch (err) {
        errEl.textContent = 'Ошибка сети или соединения с сервером';
        errEl.style.display = 'block';
      }
    });
  }

  // Создание плейлиста
  const playlistForm = document.getElementById('playlistForm');
  if (playlistForm) {
    playlistForm.addEventListener('submit', async (e) => {
      e.preventDefault();
      const input = document.getElementById('playlistTitleInput');
      const title = input.value.trim();
      if (!title) return;

      const res = await createPlaylist(title);
      if (res && res.status === 'created') {
        input.value = '';
        hidePlaylistModal();
        showToast(`Плейлист «${title}» создан`);
        if (onPlaylistCreatedCallback) onPlaylistCreatedCallback();
      }
    });
  }

  // Переход на экран настроек при наличии кнопки шестеренки (обратная совместимость)
  const btnSettings = document.getElementById('btnServerSettings');
  if (btnSettings) {
    btnSettings.addEventListener('click', () => {
      switchView('settings');
    });
  }

  // QR Сопряжение мобильного приложения
  const btnQrConnect = document.getElementById('btnQrConnect');
  const btnOpenQrFromSettings = document.getElementById('btnOpenQrFromSettings');
  const btnCloseQrModal = document.getElementById('btnCloseQrModal');
  const btnCloseQrModalAction = document.getElementById('btnCloseQrModalAction');
  const btnCopyQrPayload = document.getElementById('btnCopyQrPayload');
  const qrPayloadInput = document.getElementById('qrPayloadInput');
  const btnRefreshQr = document.getElementById('btnRefreshQr');
  const btnQrApplyHost = document.getElementById('btnQrApplyHost');
  const qrServerUrlInput = document.getElementById('qrServerUrlInput');

  if (btnQrConnect) {
    btnQrConnect.addEventListener('click', () => openQrModal());
  }

  if (btnOpenQrFromSettings) {
    btnOpenQrFromSettings.addEventListener('click', () => {
      const serverSettingsModal = document.getElementById('serverSettingsModal');
      if (serverSettingsModal) serverSettingsModal.classList.remove('active');
      openQrModal();
    });
  }

  if (btnCloseQrModal) {
    btnCloseQrModal.addEventListener('click', () => hideQrModal());
  }
  if (btnCloseQrModalAction) {
    btnCloseQrModalAction.addEventListener('click', () => hideQrModal());
  }

  async function performCopyQrPayload() {
    if (!qrPayloadInput || !qrPayloadInput.value) return;
    const text = qrPayloadInput.value;
    let copied = false;

    // 1. Попытка через Clipboard API (работает в безопасном HTTPS-контексте)
    if (navigator.clipboard && typeof navigator.clipboard.writeText === 'function') {
      try {
        await navigator.clipboard.writeText(text);
        copied = true;
      } catch (_) {
        copied = false;
      }
    }

    // 2. Надежный fallback для HTTP (локальная сеть LAN, http://192.168.1.X)
    if (!copied) {
      try {
        qrPayloadInput.focus();
        qrPayloadInput.select();
        if (typeof qrPayloadInput.setSelectionRange === 'function') {
          qrPayloadInput.setSelectionRange(0, 99999);
        }
        copied = document.execCommand('copy');
      } catch (err) {
        console.warn('[QR Copy] Fallback execCommand failed:', err);
      }
    }

    // 3. Fallback через временный textarea, если input не сработал
    if (!copied) {
      try {
        const temp = document.createElement('textarea');
        temp.value = text;
        temp.style.position = 'fixed';
        temp.style.top = '-9999px';
        temp.style.left = '-9999px';
        temp.style.opacity = '0';
        document.body.appendChild(temp);
        temp.focus();
        temp.select();
        temp.setSelectionRange(0, 99999);
        copied = document.execCommand('copy');
        document.body.removeChild(temp);
      } catch (_) {}
    }

    if (copied) {
      showToast('Строка сопряжения скопирована', 'checkCircle');
      const btnText = document.getElementById('btnCopyQrPayloadText');
      if (btnCopyQrPayload) {
        btnCopyQrPayload.classList.add('copied');
        if (btnText) btnText.textContent = 'Скопировано!';
        setTimeout(() => {
          btnCopyQrPayload.classList.remove('copied');
          if (btnText) btnText.textContent = 'Копировать';
        }, 2000);
      }
    } else {
      showToast('Выделите текст и нажмите Ctrl+C', 'alert');
    }
  }

  if (btnCopyQrPayload) {
    btnCopyQrPayload.addEventListener('click', () => performCopyQrPayload());
  }

  if (qrPayloadInput) {
    qrPayloadInput.addEventListener('click', () => performCopyQrPayload());
  }

  if (btnRefreshQr) {
    btnRefreshQr.addEventListener('click', async () => {
      const host = qrServerUrlInput ? qrServerUrlInput.value.trim() : null;
      await openQrModal(host, true);
      showToast('Сгенерирован новый токен сопряжения', 'refresh');
    });
  }

  if (btnQrApplyHost && qrServerUrlInput) {
    btnQrApplyHost.addEventListener('click', () => {
      openQrModal(qrServerUrlInput.value.trim(), false);
    });
  }



  // Модальное окно подтверждения удаления трека
  const deleteModal = document.getElementById('deleteTrackModal');
  const btnCancelDelete = document.getElementById('btnCancelDeleteTrack');
  const btnConfirmDelete = document.getElementById('btnConfirmDeleteTrack');

  if (btnCancelDelete && deleteModal) {
    btnCancelDelete.addEventListener('click', () => {
      deleteModal.classList.remove('active');
      pendingTrackToDelete = null;
      onDeleteTrackCallback = null;
    });
  }

  if (btnConfirmDelete && deleteModal) {
    btnConfirmDelete.addEventListener('click', async () => {
      if (!pendingTrackToDelete) return;
      const track = pendingTrackToDelete;
      const fileCheckbox = document.getElementById('deleteTrackFileCheckbox');
      const deleteFile = fileCheckbox ? fileCheckbox.checked : true;

      btnConfirmDelete.disabled = true;
      btnConfirmDelete.innerHTML = '<span class="spinner" style="width: 14px; height: 14px; display: inline-block; border-width: 2px;"></span> Удаление...';

      try {
        await deleteTrack(track.id, deleteFile);
        deleteModal.classList.remove('active');
        showToast(`Трек «${track.artist} — ${track.title}» удален`, 'trash');

        // Очистка воспроизведения и очередей
        handleTrackDeleted(track.id);

        // Уведомление через глобальное событие
        window.dispatchEvent(new CustomEvent('track:deleted', { detail: { track, trackId: track.id } }));

        if (onDeleteTrackCallback) {
          onDeleteTrackCallback(track);
        }
      } catch (err) {
        console.error('Ошибка удаления трека:', err);
        showToast(err.message || 'Не удалось удалить трек');
      } finally {
        btnConfirmDelete.disabled = false;
        btnConfirmDelete.textContent = 'Удалить';
        pendingTrackToDelete = null;
        onDeleteTrackCallback = null;
      }
    });
  }

  // Модальное окно ручной загрузки треков с компьютера
  const btnUploadTracks = document.getElementById('btnUploadTracks');
  const btnCloseUpload = document.getElementById('btnCloseUploadModal');
  const btnCancelUpload = document.getElementById('btnCancelUpload');
  const btnClearFiles = document.getElementById('btnClearSelectedFiles');
  const uploadFilesList = document.getElementById('uploadFilesList');
  const dropZone = document.getElementById('uploadDropZone');
  const fileInput = document.getElementById('uploadFileInput');
  const submitUploadBtn = document.getElementById('btnSubmitUpload');

  if (btnUploadTracks) {
    btnUploadTracks.addEventListener('click', () => openUploadTracksModal());
  }

  if (btnCloseUpload) {
    btnCloseUpload.addEventListener('click', () => hideUploadTracksModal());
  }

  if (btnCancelUpload) {
    btnCancelUpload.addEventListener('click', () => hideUploadTracksModal());
  }

  if (btnClearFiles) {
    btnClearFiles.addEventListener('click', () => {
      selectedUploadFiles = [];
      if (fileInput) fileInput.value = '';
      updateUploadModalUI();
    });
  }

  if (uploadFilesList) {
    uploadFilesList.addEventListener('click', (e) => {
      const btn = e.target.closest('.upload-file-remove');
      if (btn) {
        const idx = parseInt(btn.dataset.index, 10);
        if (!isNaN(idx) && idx >= 0 && idx < selectedUploadFiles.length) {
          selectedUploadFiles.splice(idx, 1);
          updateUploadModalUI();
        }
      }
    });
  }

  if (dropZone && fileInput) {
    dropZone.addEventListener('click', (e) => {
      if (e.target !== fileInput) {
        fileInput.click();
      }
    });

    fileInput.addEventListener('change', (e) => {
      if (e.target.files && e.target.files.length > 0) {
        addFilesToUploadQueue(e.target.files);
        fileInput.value = '';
      }
    });

    ['dragenter', 'dragover'].forEach(eventName => {
      dropZone.addEventListener(eventName, (e) => {
        e.preventDefault();
        e.stopPropagation();
        dropZone.classList.add('dragover');
      });
    });

    ['dragleave', 'dragend'].forEach(eventName => {
      dropZone.addEventListener(eventName, (e) => {
        e.preventDefault();
        e.stopPropagation();
        dropZone.classList.remove('dragover');
      });
    });

    dropZone.addEventListener('drop', (e) => {
      e.preventDefault();
      e.stopPropagation();
      dropZone.classList.remove('dragover');
      if (e.dataTransfer && e.dataTransfer.files) {
        addFilesToUploadQueue(e.dataTransfer.files);
      }
    });
  }

  // Безопасная обработка перетаскивания файлов в окно браузера
  window.addEventListener('dragover', (e) => {
    e.preventDefault();
  });
  window.addEventListener('drop', (e) => {
    e.preventDefault();
  });

  const tracksView = document.getElementById('viewTracks');
  if (tracksView) {
    tracksView.addEventListener('drop', (e) => {
      if (e.dataTransfer && e.dataTransfer.files && e.dataTransfer.files.length > 0) {
        const hasAudio = Array.from(e.dataTransfer.files).some(isAudioFile);
        if (hasAudio) {
          openUploadTracksModal(e.dataTransfer.files);
        }
      }
    });
  }

  if (submitUploadBtn) {
    submitUploadBtn.addEventListener('click', async () => {
      if (selectedUploadFiles.length === 0) return;

      const filesToUpload = [...selectedUploadFiles];
      const progressSec = document.getElementById('uploadProgressSection');
      const progressBar = document.getElementById('uploadProgressBar');
      const progressPercent = document.getElementById('uploadProgressPercent');
      const progressStatus = document.getElementById('uploadProgressStatus');
      const errorEl = document.getElementById('uploadError');
      const cancelBtn = document.getElementById('btnCancelUpload');

      submitUploadBtn.disabled = true;
      if (cancelBtn) cancelBtn.disabled = true;
      if (dropZone) dropZone.style.pointerEvents = 'none';
      if (errorEl) {
        errorEl.style.display = 'none';
        errorEl.textContent = '';
      }

      if (progressSec) progressSec.style.display = 'block';
      if (progressBar) progressBar.style.width = '0%';
      if (progressPercent) progressPercent.textContent = '0%';
      if (progressStatus) {
        progressStatus.textContent = `Загрузка ${filesToUpload.length} аудиофайлов...`;
      }

      try {
        const res = await uploadTrackFiles(filesToUpload, (percent, loaded, total) => {
          if (progressBar) progressBar.style.width = `${percent}%`;
          if (progressPercent) progressPercent.textContent = `${percent}%`;
          if (progressStatus) {
            if (percent >= 100) {
              progressStatus.textContent = 'Обработка и сохранение метаданных на сервере...';
            } else {
              progressStatus.textContent = `Загрузка: ${formatFileSize(loaded)} из ${formatFileSize(total)}`;
            }
          }
        });

        const uploaded = res.uploaded || [];
        const failed = res.failed || [];

        if (uploaded.length > 0) {
          let msg = `Загружено треков в фонотеку: ${uploaded.length}`;
          if (failed.length > 0) {
            msg += ` (${failed.length} с ошибками)`;
          }
          showToast(msg, 'checkCircle');
        } else if (failed.length > 0) {
          showToast(`Не удалось загрузить файлы: ${failed[0].error}`, 'xCircle');
        }

        hideUploadTracksModal();
        loadLibraryTracks();
      } catch (err) {
        console.error('Ошибка загрузки файлов:', err);
        if (errorEl) {
          errorEl.textContent = err.message || 'Ошибка при загрузке аудиофайлов на сервер';
          errorEl.style.display = 'block';
        }
        submitUploadBtn.disabled = false;
        if (cancelBtn) cancelBtn.disabled = false;
        if (dropZone) dropZone.style.pointerEvents = 'auto';
      }
    });
  }

  // --- Настройка модального окна Sentinel Connect (Выбор устройств) ---
  const btnConnect = document.getElementById('btnPlayerConnect');
  const pillDevice = document.getElementById('playerDevicePill');
  const btnCloseDevices = document.getElementById('btnCloseDevicesModal');
  const modalDevices = document.getElementById('devicesModal');
  const btnRefreshDevices = document.getElementById('btnRefreshDevicesList');
  const localCard = document.getElementById('localDeviceCard');

  if (btnConnect) {
    btnConnect.addEventListener('click', () => openDevicesModal());
  }
  if (pillDevice) {
    pillDevice.addEventListener('click', () => openDevicesModal());
  }
  if (btnCloseDevices && modalDevices) {
    btnCloseDevices.addEventListener('click', () => hideDevicesModal());
    modalDevices.addEventListener('click', (e) => {
      if (e.target === modalDevices) hideDevicesModal();
    });
  }
  if (btnRefreshDevices) {
    btnRefreshDevices.addEventListener('click', () => {
      refreshDevicesHttp();
      requestDevices();
    });
  }
  if (localCard) {
    localCard.addEventListener('click', () => {
      selectPlaybackDevice(null);
      hideDevicesModal();
    });
  }

  const remoteDevicesList = document.getElementById('remoteDevicesList');
  if (remoteDevicesList) {
    remoteDevicesList.addEventListener('click', (e) => {
      const card = e.target.closest('.device-card');
      if (!card) return;
      const devId = card.getAttribute('data-device-id');
      if (!devId) return;
      const targetDev = (state.availableDevices || []).find(d => d.id === devId);
      if (targetDev) {
        selectPlaybackDevice(targetDev);
        hideDevicesModal();
      }
    });
  }

  window.addEventListener('sentinel:devices-changed', (e) => {
    if (modalDevices && modalDevices.classList.contains('active')) {
      renderDevicesListUI(e.detail || state.availableDevices);
    }
  });

  window.addEventListener('sentinel:device-selected', () => {
    if (modalDevices && modalDevices.classList.contains('active')) {
      renderDevicesListUI(state.availableDevices);
    }
  });
}


export function showAuthModal(isRegister = false) {
  window.location.replace('login.html');
}

export function hideAuthModal() {
  const modal = document.getElementById('authModal');
  if (modal) modal.classList.remove('active');
}

export function showPlaylistModal() {
  const modal = document.getElementById('playlistModal');
  if (modal) {
    modal.classList.add('active');
    const input = document.getElementById('playlistTitleInput');
    if (input) input.focus();
  }
}
window.showPlaylistModal = showPlaylistModal;

export function hidePlaylistModal() {
  const modal = document.getElementById('playlistModal');
  if (modal) modal.classList.remove('active');
}

export function openAddToPlaylistModal(track) {
  pendingTrackForPlaylist = track;
  const modal = document.getElementById('addToPlaylistModal');
  const listContainer = document.getElementById('addToPlaylistList');

  if (!modal || !listContainer) return;

  listContainer.innerHTML = '';
  if (state.playlists.length === 0) {
    listContainer.innerHTML = '<div style="color: var(--text-muted); padding: 12px;">Сначала создайте плейлист</div>';
  } else {
    state.playlists.forEach(pl => {
      const item = document.createElement('div');
      item.className = 'playlist-nav-item';
      item.style.padding = '10px 14px';
      item.innerHTML = `<span style="display: flex; align-items: center; gap: 8px;">${icon('folder', { size: 16 })} <span>${escapeHtml(pl.title)}</span></span>`;

      item.addEventListener('click', async () => {
        await addTrackToPlaylist(pl.id, track.id);
        modal.classList.remove('active');
        showToast(`Добавлено в плейлист «${pl.title}»`);
        if (onPlaylistCreatedCallback) onPlaylistCreatedCallback();
      });

      listContainer.appendChild(item);
    });
  }

  modal.classList.add('active');
}

export function openDeleteTrackModal(track, onDeleted = null) {
  pendingTrackToDelete = track;
  onDeleteTrackCallback = onDeleted;

  const modal = document.getElementById('deleteTrackModal');
  const coverEl = document.getElementById('deleteTrackCover');
  const titleEl = document.getElementById('deleteTrackTitle');
  const artistEl = document.getElementById('deleteTrackArtist');
  const checkbox = document.getElementById('deleteTrackFileCheckbox');

  if (!modal) return;

  if (coverEl) coverEl.src = `${getApiBase()}/api/covers/${track.id}`;
  if (titleEl) titleEl.textContent = track.title || 'Без названия';
  if (artistEl) artistEl.textContent = track.artist || 'Неизвестный исполнитель';
  if (checkbox) checkbox.checked = true;

  modal.classList.add('active');
}

export function hideDeleteTrackModal() {
  const modal = document.getElementById('deleteTrackModal');
  if (modal) modal.classList.remove('active');
  pendingTrackToDelete = null;
  onDeleteTrackCallback = null;
}

export function openUploadTracksModal(initialFiles = null) {
  const modal = document.getElementById('uploadTracksModal');
  if (!modal) return;

  const progressSec = document.getElementById('uploadProgressSection');
  const progressBar = document.getElementById('uploadProgressBar');
  const progressPercent = document.getElementById('uploadProgressPercent');
  const progressStatus = document.getElementById('uploadProgressStatus');
  const submitBtn = document.getElementById('btnSubmitUpload');
  const cancelBtn = document.getElementById('btnCancelUpload');
  const dropZone = document.getElementById('uploadDropZone');
  const fileInput = document.getElementById('uploadFileInput');

  if (progressSec) progressSec.style.display = 'none';
  if (progressBar) progressBar.style.width = '0%';
  if (progressPercent) progressPercent.textContent = '0%';
  if (progressStatus) progressStatus.textContent = 'Загрузка файлов...';
  if (submitBtn) {
    submitBtn.disabled = true;
    submitBtn.textContent = 'Начать загрузку';
  }
  if (cancelBtn) cancelBtn.disabled = false;
  if (dropZone) dropZone.style.pointerEvents = 'auto';
  if (fileInput) fileInput.value = '';

  if (initialFiles) {
    addFilesToUploadQueue(initialFiles);
  } else {
    updateUploadModalUI();
  }

  // Динамический рендеринг расширений плагинов
  const uploadExtContainer = document.getElementById('uploadModalPluginExtensions');
  if (uploadExtContainer && window.Sentinel && window.Sentinel.ui) {
    uploadExtContainer.innerHTML = '';
    window.Sentinel.ui.renderExtensionPoints('upload:modal', uploadExtContainer);
  }

  modal.classList.add('active');
}

export function hideUploadTracksModal() {
  const modal = document.getElementById('uploadTracksModal');
  if (modal) modal.classList.remove('active');
  selectedUploadFiles = [];
  updateUploadModalUI();
}

let cachedQrHosts = null;

function isDockerOrLoopbackHost(hostname) {
  if (!hostname) return true;
  if (hostname === 'localhost' || hostname === '127.0.0.1' || hostname === '0.0.0.0') return true;
  const parts = hostname.split('.');
  if (parts.length === 4) {
    const p0 = parseInt(parts[0], 10);
    const p1 = parseInt(parts[1], 10);
    if (p0 === 172 && p1 >= 16 && p1 <= 31) return true;
  }
  return false;
}

export async function openQrModal(requestedHost = null, createNewSession = false) {
  if (!state.isAuthenticated) {
    showToast('Сначала выполните вход на сервере', 'alert');
    showAuthModal();
    return;
  }

  const modal = document.getElementById('qrConnectModal');
  const imgEl = document.getElementById('qrCodeImg');
  const spinnerEl = document.getElementById('qrLoadingSpinner');
  const errEl = document.getElementById('qrError');
  const hostInput = document.getElementById('qrServerUrlInput');
  const payloadInput = document.getElementById('qrPayloadInput');
  const downloadBtn = document.getElementById('btnDownloadQr');

  if (!modal) return;
  modal.classList.add('active');

  if (errEl) {
    errEl.style.display = 'none';
    errEl.textContent = '';
  }
  if (imgEl) imgEl.style.display = 'none';
  if (spinnerEl) spinnerEl.style.display = 'flex';

  try {
    if (!cachedQrHosts) {
      cachedQrHosts = await fetchQrHosts();
    }

    let lanCandidate = cachedQrHosts ? cachedQrHosts.lan_url : null;
    if (window.location && window.location.hostname && !isDockerOrLoopbackHost(window.location.hostname)) {
      const port = window.location.port ? `:${window.location.port}` : '';
      const browserUrl = `${window.location.protocol}//${window.location.hostname}${port}`;
      if (!lanCandidate) {
        lanCandidate = browserUrl;
      } else {
        try {
          const parsed = new URL(lanCandidate);
          if (isDockerOrLoopbackHost(parsed.hostname)) {
            lanCandidate = browserUrl;
          }
        } catch (_) {
          lanCandidate = browserUrl;
        }
      }
    }

    let hostToUse = requestedHost;
    if (!hostToUse && hostInput && hostInput.value.trim()) {
      const val = hostInput.value.trim();
      try {
        const parsed = new URL(val);
        if (!isDockerOrLoopbackHost(parsed.hostname)) {
          hostToUse = val;
        }
      } catch (_) {}
    }
    if (!hostToUse) {
      hostToUse = lanCandidate;
    }

    const data = await fetchQrCode(hostToUse, createNewSession);

    if (hostInput && data.server_url) {
      hostInput.value = data.server_url;
    }
    if (payloadInput && data.payload_json) {
      payloadInput.value = data.payload_json;
    }
    if (imgEl && data.qr_image) {
      imgEl.src = data.qr_image;
      imgEl.style.display = 'block';
    }
    if (downloadBtn && data.qr_image) {
      downloadBtn.href = data.qr_image;
    }
    if (spinnerEl) spinnerEl.style.display = 'none';
  } catch (err) {
    console.error('Ошибка загрузки QR-кода:', err);
    if (spinnerEl) spinnerEl.style.display = 'none';
    if (errEl) {
      errEl.textContent = 'Не удалось загрузить QR-код: ' + (err.message || 'Ошибка сети');
      errEl.style.display = 'block';
    }
  }
}

export function hideQrModal() {
  const modal = document.getElementById('qrConnectModal');
  if (modal) modal.classList.remove('active');
}




export function openDevicesModal() {
  const modal = document.getElementById('devicesModal');
  if (!modal) return;
  modal.classList.add('active');
  renderDevicesListUI(state.availableDevices);
  refreshDevicesHttp();
  requestDevices();
}
window.openDevicesModal = openDevicesModal;

export function hideDevicesModal() {
  const modal = document.getElementById('devicesModal');
  if (modal) modal.classList.remove('active');
}
window.hideDevicesModal = hideDevicesModal;

export function renderDevicesListUI(devices) {
  const container = document.getElementById('remoteDevicesList');
  if (!container) return;

  const currentSelectedId = state.selectedRemoteDevice ? state.selectedRemoteDevice.id : null;
  const localCard = document.getElementById('localDeviceCard');
  const localActiveBadge = document.getElementById('localDeviceActiveBadge');
  const btnSelectLocal = document.getElementById('btnSelectLocalDevice');

  if (localCard && localActiveBadge && btnSelectLocal) {
    const isLocalActive = !currentSelectedId;
    localCard.classList.toggle('active', isLocalActive);
    localActiveBadge.style.display = isLocalActive ? 'inline-block' : 'none';
    btnSelectLocal.style.display = isLocalActive ? 'none' : 'inline-block';
  }

  const rawList = Array.isArray(devices) ? devices : (state.availableDevices || []);
  const myId = getOrCreateDeviceId();
  const remoteList = rawList.filter(d => d.id !== myId);

  if (remoteList.length === 0) {
    container.innerHTML = `
      <div class="devices-empty-state">
        <span>Нет доступных устройств в домашней сети</span>
        <span style="font-size: 0.72rem; color: var(--text-muted, #94a3b8);">Включите Яндекс.Станцию или откройте Sentinel Music на телефоне</span>
      </div>
    `;
    return;
  }

  container.innerHTML = remoteList.map(dev => {
    const isSelected = currentSelectedId === dev.id;
    const isPlaying = Boolean(dev.is_playing);
    const trackName = dev.current_track ? `${escapeHtml(dev.current_track.artist || '')} — ${escapeHtml(dev.current_track.title || 'Трек')}` : null;

    const nameLower = (dev.name || '').toLowerCase();
    let iconName = 'speaker';
    let iconClass = 'speaker-icon';
    if (nameLower.includes('смартфон') || nameLower.includes('телефон') || nameLower.includes('android') || nameLower.includes('pixel') || nameLower.includes('samsung') || nameLower.includes('iphone')) {
      iconName = 'smartphone';
      iconClass = 'phone-icon';
    } else if (nameLower.includes('компьютер') || nameLower.includes('пк') || nameLower.includes('desktop') || nameLower.includes('ноутбук') || nameLower.includes('браузер') || (dev.type === 'player' && !nameLower.includes('станция'))) {
      iconName = 'monitor';
      iconClass = 'monitor-icon';
    }

    const descHtml = isPlaying
      ? `<span class="device-card-desc playing">${icon('play', { size: 10 })} Играет: ${trackName}</span>`
      : `<span class="device-card-desc"><span style="color: #4ade80;">●</span> В сети</span>`;

    const actionHtml = isSelected
      ? `<span class="device-active-badge">Активно</span>`
      : `<button type="button" class="btn-secondary btn-sm btn-select-remote" data-device-id="${escapeHtml(dev.id)}">Выбрать</button>`;

    return `
      <div class="device-card ${isSelected ? 'active' : ''}" data-device-id="${escapeHtml(dev.id)}">
        <div class="device-card-left">
          <div class="device-type-icon ${iconClass}">
            ${icon(iconName, { size: 20 })}
          </div>
          <div class="device-card-info">
            <div class="device-card-name">${escapeHtml(dev.name || 'Устройство')}</div>
            ${descHtml}
          </div>
        </div>
        <div class="device-card-action">
          ${actionHtml}
        </div>
      </div>
    `;
  }).join('');
}
