#!/usr/bin/env python3
"""
PKB 知识库配置管理
支持从环境变量或 .env 文件加载配置
"""

import os
from pathlib import Path
from typing import Optional
from dataclasses import dataclass


@dataclass
class PKBConfig:
    """PKB 知识库配置"""
    base_url: str
    api_key: str
    user_id: str
    # Nextcloud 配置（用于同步文件）
    nextcloud_base_url: str
    nextcloud_username: str
    nextcloud_app_password: str
    
    @classmethod
    def from_env(cls) -> "PKBConfig":
        """从环境变量加载配置"""
        # 先尝试加载 .env 文件
        cls._load_from_env_file()
        
        # PKB 配置
        base_url = os.getenv("PKB_BASE_URL", "https://api.miaoda.io")
        api_key = os.getenv("PKB_API_KEY", "")
        user_id = os.getenv("PKB_USER_ID", "")
        
        if not api_key or not user_id:
            raise ValueError("PKB 配置未设置，请设置 PKB_API_KEY 和 PKB_USER_ID 环境变量")
        
        # Nextcloud 配置（复用）
        nextcloud_base_url = os.getenv("NEXTCLOUD_BASE_URL", "https://nextcloud.kmchat.cloud")
        nextcloud_username = os.getenv("NEXTCLOUD_USERNAME", "")
        nextcloud_app_password = os.getenv("NEXTCLOUD_APP_PASSWORD", "")
        
        return cls(
            base_url=base_url,
            api_key=api_key,
            user_id=user_id,
            nextcloud_base_url=nextcloud_base_url,
            nextcloud_username=nextcloud_username,
            nextcloud_app_password=nextcloud_app_password
        )
    
    @classmethod
    def _load_from_env_file(cls, env_file: str = ".env"):
        """从 .env 文件加载环境变量"""
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
_config: Optional[PKBConfig] = None


def get_config() -> PKBConfig:
    """获取配置实例（单例）"""
    global _config
    if _config is None:
        _config = PKBConfig.from_env()
    return _config


def reset_config():
    """重置配置"""
    global _config
    _config = None
