"""
Device Configuration

Centralized configuration for device specifications (screen size, etc.)
that can be easily accessed by any module in the application.
"""

from dataclasses import dataclass
from typing import Optional


@dataclass
class DeviceSpec:
    """Device screen specifications."""
    width: int = 1080      # Screen width in pixels
    height: int = 2400     # Screen height in pixels
    dpi: Optional[int] = None  # Optional DPI for scaling calculations
    
    def to_dict(self):
        """Convert to dictionary for logging/serialization."""
        return {
            "width": self.width,
            "height": self.height,
            "dpi": self.dpi,
        }


class DeviceConfig:
    """
    Global device configuration manager.
    
    Provides centralized access to device specifications across all modules.
    """
    
    _instance: Optional['DeviceConfig'] = None
    _device_spec: DeviceSpec = DeviceSpec()
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    @classmethod
    def set_device_spec(cls, width: int, height: int, dpi: Optional[int] = None):
        """
        Set the device screen specifications.
        
        Args:
            width: Screen width in pixels
            height: Screen height in pixels
            dpi: Optional DPI for scaling calculations
        """
        instance = cls()
        instance._device_spec = DeviceSpec(width=width, height=height, dpi=dpi)
    
    @classmethod
    def get_device_spec(cls) -> DeviceSpec:
        """
        Get the current device specifications.
        
        Returns:
            DeviceSpec with width, height, and optional dpi
        """
        return cls()._device_spec
    
    @classmethod
    def get_width(cls) -> int:
        """Get device screen width."""
        return cls.get_device_spec().width
    
    @classmethod
    def get_height(cls) -> int:
        """Get device screen height."""
        return cls.get_device_spec().height
    
    @classmethod
    def get_dpi(cls) -> Optional[int]:
        """Get device DPI if available."""
        return cls.get_device_spec().dpi
    
    @classmethod
    def reset(cls):
        """Reset to default device specifications."""
        instance = cls()
        instance._device_spec = DeviceSpec()


# Usage examples:
# 
# 1. Initialize at application startup:
#    DeviceConfig.set_device_spec(width=1080, height=2400, dpi=420)
#
# 2. Access from any module:
#    spec = DeviceConfig.get_device_spec()
#    width = DeviceConfig.get_width()
#    height = DeviceConfig.get_height()
