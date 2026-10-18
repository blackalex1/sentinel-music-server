/**
 * Модуль всплывающих уведомлений (Toast) и вспомогательных утилит форматирования.
 * Интегрирован с векторной системой иконок Sentinel SVG Icons.
 */

import { icon, stripEmojis } from '../icons.js';

export function showToast(payload, forcedIconName = null) {
  let container = document.getElementById('toastContainer');
  if (!container) {
    container = document.createElement('div');
    container.id = 'toastContainer';
    container.className = 'toast-container';
    document.body.appendChild(container);
  }

  let text = '';
  let iconName = forcedIconName;

  if (typeof payload === 'object' && payload !== null) {
    text = payload.detail || payload.message || payload.text || '';
    iconName = iconName || payload.icon;
  } else {
    text = String(payload || '');
  }

  // Автоматическое определение подходящей SVG-иконки по ключевым маркерам или эмодзи
  if (!iconName) {
    if (text.includes('\u2705') || text.includes('скачан') || text.includes('Загружено') || text.includes('успешн')) {
      iconName = 'checkCircle';
    } else if (text.includes('\u274C') || text.includes('Ошибка') || text.includes('Сбой') || text.includes('не удалось')) {
      iconName = 'xCircle';
    } else if (text.includes('\u26A0') || text.includes('Пропущено') || text.includes('Внимание')) {
      iconName = 'alert';
    } else if (text.includes('\u2764') || text.includes('сохранен') || text.includes('коллекци')) {
      iconName = 'heartFilled';
    } else if (text.includes('\uD83D\uDD00') || text.includes('Случайный') || text.includes('микс')) {
      iconName = 'shuffle';
    } else if (text.includes('\uD83D\uDDD1') || text.includes('удален')) {
      iconName = 'trash';
    } else if (text.includes('\u26A1') || text.includes('анализ') || text.includes('Поток')) {
      iconName = 'zap';
    } else if (text.includes('\uD83C\uDF1F') || text.includes('открытие') || text.includes('\u2728') || text.includes('Рекомендация')) {
      iconName = 'sparkles';
    } else if (text.includes('\uD83D\uDCC1') || text.includes('плейлист')) {
      iconName = 'folder';
    } else if (text.includes('\u23ED') || text.includes('\u2795') || text.includes('очередь')) {
      iconName = 'queue';
    } else {
      iconName = 'disc';
    }
  }

  // Очищаем текст от растровых эмодзи
  const cleanText = stripEmojis(text);

  const toast = document.createElement('div');
  toast.className = 'toast';

  const iconClass = (iconName === 'xCircle') ? 'icon-danger' : (iconName === 'checkCircle' ? 'icon-success' : '');
  toast.innerHTML = `
    <span class="toast-icon">${icon(iconName, { size: 18, className: iconClass })}</span>
    <span class="toast-text">${escapeHtml(cleanText)}</span>
  `;

  container.appendChild(toast);

  setTimeout(() => {
    toast.style.opacity = '0';
    toast.style.transform = 'translateY(10px)';
    toast.style.transition = 'all 0.3s ease';
    setTimeout(() => toast.remove(), 300);
  }, 2800);
}

export function escapeHtml(text) {
  if (!text) return '';
  const map = { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#039;' };
  return String(text).replace(/[&<>"']/g, m => map[m]);
}
