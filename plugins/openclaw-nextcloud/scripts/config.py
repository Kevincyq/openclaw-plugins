#!/usr/bin/env python3
"""
Nextcloud 配置管理
支持从环境变量或 .env 文件加载配置
"""

import os
from pathlib import Path
from typing import Optional
from dataclasses import dataclass


@dataclass
class NextcloudConfig:
    """Nextcloud 配置"""
    base_url: str
    username: str
    app_password: str
    
    @classmethod
    def from_env(cls) -> "NextcloudConfig":
        """从环境变量加载配置"""
        base_url = os.getenv("NEXTCLOUD_BASE_URL", "https://nextcloud.kmchat.cloud")
        username = os.getenv("NEXTCLOUD_USERNAME", "")
        app_password = os.getenv("NEXTCLOUD_APP_PASSWORD", "")
        
        if not username or not app_password:
            # 尝试从 .env 文件加载
            cls._load_from_env_file()
            username = os.getenv("NEXTCLOUD_USERNAME", "")
            app_password = os.getenv("NEXTCLOUD_APP_PASSWORD", "")
        
        if not username or not app_password:
            raise ValueError("Nextcloud 配置未设置，请设置 NEXTCLOUD_USERNAME 和 NEXTCLOUD_APP_PASSWORD 环境变量")
        
        return cls(base_url=base_url, username=username, app_password=app_password)
    
    @classmethod
    def _load_from_env_file(cls, env_file: str = ".env"):
        """从 .env 文件加载环境变量"""
        # 查找 .env 文件
        possible_paths = [
            Path.cwd() / env_file,
            Path(__file__).parent.parent / env_file,
            Path.home() / env_file,
        ]
        
        for env_path in possible_paths:
            if env_path.exists():
                with open(env_path) as f:
                    for line in f:
                        line = line.strip()
                        if line and not line.startswith("#"):
                            if "=" in line:
                                key, value = line.split("=", 1)
                                os.environ[key.strip()] = value.strip()
                break


# 单例配置实例
_config: Optional[NextcloudConfig] = None


def get_config() -> NextcloudConfig:
    """获取配置实例（单例）"""
    global _config
    if _config is None:
        _config = NextcloudConfig.from_env()
    return _config

def reset_config():
    """重置配置（用于测试或切换配置）"""
    global _config
    _config = None
