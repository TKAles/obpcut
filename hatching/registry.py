"""
Plugin registry for managing hatching strategies.
"""

from typing import Dict, Type, Optional, List
from .base import HatchingPlugin, HatchingStrategy


class HatchingRegistry:
    """
    Registry for managing hatching plugins.

    This singleton class maintains a registry of available hatching plugins
    and provides methods to register, retrieve, and list plugins.
    """

    _instance = None
    _plugins: Dict[HatchingStrategy, Type[HatchingPlugin]] = {}

    def __new__(cls):
        """Ensure singleton pattern."""
        if cls._instance is None:
            cls._instance = super(HatchingRegistry, cls).__new__(cls)
            cls._instance._plugins = {}
        return cls._instance

    def register(self, strategy: HatchingStrategy, plugin_class: Type[HatchingPlugin]) -> None:
        """
        Register a hatching plugin.

        Args:
            strategy: The hatching strategy enum value
            plugin_class: The plugin class (not instance) to register

        Raises:
            TypeError: If plugin_class is not a subclass of HatchingPlugin
        """
        if not issubclass(plugin_class, HatchingPlugin):
            raise TypeError(f"{plugin_class.__name__} must be a subclass of HatchingPlugin")

        self._plugins[strategy] = plugin_class

    def unregister(self, strategy: HatchingStrategy) -> None:
        """
        Unregister a hatching plugin.

        Args:
            strategy: The hatching strategy to unregister
        """
        if strategy in self._plugins:
            del self._plugins[strategy]

    def get_plugin(self, strategy: HatchingStrategy) -> Optional[HatchingPlugin]:
        """
        Get an instance of a registered plugin.

        Args:
            strategy: The hatching strategy to retrieve

        Returns:
            Instance of the plugin, or None if not found
        """
        plugin_class = self._plugins.get(strategy)
        if plugin_class:
            return plugin_class()
        return None

    def get_plugin_class(self, strategy: HatchingStrategy) -> Optional[Type[HatchingPlugin]]:
        """
        Get the class of a registered plugin.

        Args:
            strategy: The hatching strategy to retrieve

        Returns:
            The plugin class, or None if not found
        """
        return self._plugins.get(strategy)

    def list_strategies(self) -> List[HatchingStrategy]:
        """
        List all registered hatching strategies.

        Returns:
            List of registered HatchingStrategy enum values
        """
        return list(self._plugins.keys())

    def is_registered(self, strategy: HatchingStrategy) -> bool:
        """
        Check if a strategy is registered.

        Args:
            strategy: The hatching strategy to check

        Returns:
            True if registered, False otherwise
        """
        return strategy in self._plugins

    def clear(self) -> None:
        """Clear all registered plugins."""
        self._plugins.clear()

    def __len__(self) -> int:
        """Get the number of registered plugins."""
        return len(self._plugins)

    def __contains__(self, strategy: HatchingStrategy) -> bool:
        """Check if a strategy is registered using 'in' operator."""
        return strategy in self._plugins


# Global registry instance
registry = HatchingRegistry()
