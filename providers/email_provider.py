#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
邮箱服务提供者抽象基类

定义所有邮箱服务必须实现的接口

作者: AI Assistant
版本: 1.0
"""

from abc import ABC, abstractmethod


class EmailProvider(ABC):
    """邮箱服务提供者抽象基类
    
    定义所有邮箱服务必须实现的接口
    """
    
    @abstractmethod
    def get_page_url(self) -> str:
        """获取邮箱页面URL
        
        Returns:
            str: 邮箱页面URL
        """
        pass
    
    @abstractmethod
    def get_domain_patterns(self) -> list:
        """获取邮箱域名匹配模式
        
        Returns:
            list: 域名匹配模式列表,用于识别邮箱页面
        """
        pass
    
    @abstractmethod
    def get_email_from_page(self, cdp, session_id) -> str:
        """从页面获取邮箱地址
        
        Args:
            cdp: CDPClient实例
            session_id: CDP会话ID
            
        Returns:
            str: 邮箱地址,失败返回None
        """
        pass
    
    @abstractmethod
    def get_verification_code(self, email: str) -> str:
        """获取验证码

        Args:
            email: 邮箱地址

        Returns:
            str: 验证码,失败返回None
        """
        pass

