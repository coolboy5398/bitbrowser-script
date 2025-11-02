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


# 邮箱服务配置字典
PROVIDERS = {
    'chatgpt': {
        'name': 'ChatGPT临时邮箱',
        'class': ChatGPTMailProvider,
        'description': 'https://mail.chatgpt.org.uk/ 临时邮箱服务'
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
    def create(provider_name: str = 'chatgpt') -> EmailProvider:
        """创建邮箱服务实例
        
        Args:
            provider_name: 邮箱服务名称,默认为'chatgpt'
            
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
        
        return provider_class()
    
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

