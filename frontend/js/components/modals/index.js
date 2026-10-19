/**
 * Агрегатор всех модальных окон приложения.
 */

import { renderAuthModal } from './authModal.js';
import { renderPlaylistModal } from './playlistModal.js';
import { renderAddToPlaylistModal } from './addToPlaylistModal.js';
import { renderTrackVersionsModal } from './trackVersionsModal.js';
import { renderDeleteTrackModal } from './deleteTrackModal.js';
import { renderUploadTracksModal } from './uploadTracksModal.js';
import { renderQrConnectModal } from './qrConnectModal.js';
import { renderEqualizerModal } from './equalizerModal.js';

export function renderModals() {
  return `
    <div id="modalsContainer">
      ${renderAuthModal()}
      ${renderPlaylistModal()}
      ${renderAddToPlaylistModal()}
      ${renderTrackVersionsModal()}
      ${renderDeleteTrackModal()}
      ${renderUploadTracksModal()}
      ${renderQrConnectModal()}
      ${renderEqualizerModal()}
    </div>
  `;
}
