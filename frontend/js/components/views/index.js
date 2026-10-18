/**
 * Агрегатор экранов и представлений контента рабочей области.
 */

import { renderMainView } from './mainView.js';
import { renderStreamView } from './streamView.js';
import { renderTracksView } from './tracksView.js';
import { renderPlaylistsView } from './playlistsView.js';
import { renderDuplicatesView } from './duplicatesView.js';

export function renderContentViews() {
  return `
    <div class="content-scrollable" id="contentArea">
      ${renderMainView()}
      ${renderStreamView()}
      ${renderTracksView()}
      ${renderPlaylistsView()}
      ${renderDuplicatesView()}
    </div>
  `;
}
