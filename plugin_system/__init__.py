"""
Подсистема расширений и плагинов музыкального сервиса Sentinel Music.
"""

from plugin_system.base import BasePlugin
from plugin_system.manager import plugin_manager, PluginManager

__all__ = ["BasePlugin", "plugin_manager", "PluginManager"]
