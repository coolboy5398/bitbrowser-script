#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
邮箱服务提供者工厂

负责创建和管理邮箱服务实例

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


# 邮箱服务配置字典
PROVIDERS = {
    'chatgpt': {
        'name': 'ChatGPT临时邮箱',
        'class': ChatGPTMailProvider,
        'description': 'https://mail.chatgpt.org.uk/ 临时邮箱服务'
    },
    'chat-tempmail': {
        'name': 'ChatTempMail临时邮箱',
        'class': ChatTempMailProvider,
        'description': 'https://chat-tempmail.com/ 临时邮箱服务 (需要API密钥)'
    },
    'do22': {
        'name': '22.do临时邮箱',
        'class': Do22Provider,
        'description': 'https://22.do/api/v2 临时邮箱服务 (需要 bearer_token、token 或 address/password)'
    },
    'domain-imap': {
        'name': '域名IMAP邮箱',
        'class': DomainIMAPProvider,
        'description': '自定义域名邮箱 + QQ邮箱IMAP接收服务'
    },
    'duckmail': {
        'name': 'DuckMail临时邮箱',
        'class': DuckMailProvider,
        'description': 'https://api.duckmail.sbs/ 临时邮箱服务'
    },
    'mailtm': {
        'name': 'Mail.tm临时邮箱',
        'class': MailTmProvider,
        'description': 'https://api.mail.tm/ 临时邮箱服务'
    },
    'tempmail-lol': {
        'name': 'TempMail.lol临时邮箱',
        'class': TempMailLolProvider,
        'description': 'https://api.tempmail.lol/v2/ 临时邮箱服务'
    },
    # 未来可以添加更多邮箱服务
    # 'tempmail': {
    #     'name': 'TempMail',
    #     'class': TempMailProvider,
    #     'description': 'https://temp-mail.org/ 临时邮箱服务'
    # },
}


class EmailProviderFactory:
    """邮箱服务提供者工厂类
    
    负责创建和管理邮箱服务实例
    """
    
    @staticmethod
    def create(provider_name: str = 'chatgpt', **kwargs) -> EmailProvider:
        """创建邮箱服务实例

        Args:
            provider_name: 邮箱服务名称,默认为'chatgpt'
            **kwargs: 传递给提供者构造函数的额外参数
                     例如: api_key='your_api_key' (用于chat-tempmail)

        Returns:
            EmailProvider: 邮箱服务实例

        Raises:
            ValueError: 如果provider_name不存在
        """
        if provider_name not in PROVIDERS:
            available = ', '.join(PROVIDERS.keys())
            raise ValueError(f"未知的邮箱服务: {provider_name}。可用服务: {available}")

        provider_config = PROVIDERS[provider_name]
        provider_class = provider_config['class']

        # 传递额外参数给构造函数
        return provider_class(**kwargs)
    
    @staticmethod
    def get_available_providers() -> list:
        """获取所有可用的邮箱服务
        
        Returns:
            list: 可用邮箱服务列表
        """
        return [
            {
                'name': key,
                'display_name': config['name'],
                'description': config['description']
            }
            for key, config in PROVIDERS.items()
        ]

