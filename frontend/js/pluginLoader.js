/**
 * Динамический загрузчик модульных UI-плагинов Sentinel Music.
 * Запрашивает активные плагины с сервера (/api/plugins)
 * и монтирует их скрипты и стили без хардкода в ядре.
 */
import { apiFetch } from './api.js';

const loadedPlugins = new Map();

export async function loadFrontendPlugins() {
  try {
    const res = await apiFetch('/api/plugins');
    if (!res.ok) return;

    const plugins = await res.json();
    for (const p of plugins) {
      if (!p.enabled || !p.has_ui || !p.ui_entry) continue;

      // Пропускаем уже загруженные модули
      if (loadedPlugins.has(p.name)) continue;

      // 1. Динамическое подключение стилей плагина (если есть)
      if (p.ui_styles && !document.querySelector(`link[href="${p.ui_styles}"]`)) {
        const link = document.createElement('link');
        link.rel = 'stylesheet';
        link.href = p.ui_styles;
        document.head.appendChild(link);
      }

      // 2. Динамический импорт JS модуля плагина
      try {
        const module = await import(p.ui_entry);
        if (typeof module.init === 'function') {
          module.init();
        } else if (typeof module.initHybridSearchPlugin === 'function') {
          module.initHybridSearchPlugin();
        }
        loadedPlugins.set(p.name, module);
        console.log(`[PluginLoader] UI плагин «${p.name}» v${p.version} успешно активирован`);
      } catch (err) {
        console.error(`[PluginLoader] Ошибка загрузки UI плагина «${p.name}»:`, err);
      }
    }
  } catch (err) {
    console.warn('[PluginLoader] Не удалось загрузить список плагинов:', err);
  }
}
