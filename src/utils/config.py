import yaml
import os
from typing import Dict, Any

class Config:
    def __init__(self, config_path: str = "config/config.yaml"):
        self.config_path = config_path
        self.config_data = self._load_config()
        
    def _load_config(self) -> Dict[str, Any]:
        if not os.path.exists(self.config_path):
            raise FileNotFoundError(f"Config file not found: {self.config_path}")
            
        with open(self.config_path, 'r') as f:
            return yaml.safe_load(f)
            
    def get(self, key: str, default: Any = None) -> Any:
        keys = key.split('.')
        data = self.config_data
        
        for k in keys:
            if isinstance(data, dict):
                data = data.get(k)
            else:
                return default
                
            if data is None:
                return default
                
        return data
        
    def set(self, key: str, value: Any):
        keys = key.split('.')
        data = self.config_data
        
        for k in keys[:-1]:
            if k not in data:
                data[k] = {}
            data = data[k]
            
        data[keys[-1]] = value
        
        with open(self.config_path, 'w') as f:
            yaml.dump(self.config_data, f)
