#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
邮箱服务提供者包

提供统一的邮箱服务接口,支持多种临时邮箱服务

作者: AI Assistant
版本: 1.0
"""

from .email_provider import EmailProvider
from .chatgpt_mail_provider import ChatGPTMailProvider
from .email_provider_factory import EmailProviderFactory, PROVIDERS

__all__ = [
    'EmailProvider',
    'ChatGPTMailProvider',
    'EmailProviderFactory',
    'PROVIDERS',
]

