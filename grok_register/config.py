#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Grok 注册配置加载与保存。"""

import json
import os

CONFIG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.json")

DEFAULT_CONFIG = {
    "email_provider": "duckmail",
    "duckmail_api_key": "",
    "chat_tempmail_api_key": "",
    "imap_host": "imap.qq.com",
    "imap_port": 993,
    "imap_user": "",
    "imap_password": "",
    "email_suffixes_file": os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "..", "email_suffixes.json"
    ),
    "proxy": "http://127.0.0.1:7890",
    "enable_nsfw": True,
    "register_count": 1,
    "user_agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/138.0.0.0 Safari/537.36"
    ),
    "cpa_auto_add": False,
    "cpa_auth_dir": "",
    "cpa_remote_url": "",
    "cpa_management_key": "",
}

config = DEFAULT_CONFIG.copy()

PROVIDER_OPTIONS = [
    "domain-imap",
    "duckmail",
    "mailtm",
    "chatgpt",
    "chat-tempmail",
    "do22",
    "tempmail-lol",
]


def load_config():
    global config
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                loaded = json.load(f)
            config = {**DEFAULT_CONFIG, **loaded}
        except Exception:
            config = DEFAULT_CONFIG.copy()
    return config


def save_config():
    try:
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(config, f, indent=4, ensure_ascii=False)
    except Exception as e:
        print(f"保存配置失败: {e}")


load_config()
