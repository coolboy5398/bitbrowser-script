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
from .chat_tempmail_provider import ChatTempMailProvider
from .do22_provider import Do22Provider
from .domain_imap_provider import DomainIMAPProvider
from .duckmail_provider import DuckMailProvider
from .mailtm_provider import MailTmProvider
from .tempmail_lol_provider import TempMailLolProvider
from .email_provider_factory import EmailProviderFactory, PROVIDERS

__all__ = [
    'EmailProvider',
    'ChatGPTMailProvider',
    'ChatTempMailProvider',
    'Do22Provider',
    'DomainIMAPProvider',
    'DuckMailProvider',
    'MailTmProvider',
    'TempMailLolProvider',
    'EmailProviderFactory',
    'PROVIDERS',
]

