#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
邮箱服务提供者抽象基类

定义所有邮箱服务必须实现的接口

作者: AI Assistant
版本: 1.0
"""

import re
from abc import ABC, abstractmethod
from typing import Any


class EmailProvider(ABC):
    """邮箱服务提供者抽象基类

    定义所有邮箱服务必须实现的接口
    """

    def needs_browser_page(self) -> bool:
        """是否需要打开浏览器页面获取邮箱

        Returns:
            bool: True表示需要打开页面, False表示可以直接通过API获取
        """
        return True  # 默认需要打开页面

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

    def get_mail_access_identifier(self) -> str:
        """获取取邮件用的地址/标识

        Returns:
            str: 供后续取邮件使用的地址、token、账号或其他标识；默认返回空字符串
        """
        return ""

    # ==================== 邮箱地址获取 ====================

    @abstractmethod
    def get_email_from_page(self, cdp, session_id) -> str:
        """从网页提取邮箱地址

        Args:
            cdp: CDPClient实例
            session_id: CDP会话ID

        Returns:
            str: 邮箱地址,失败返回None
        """
        pass

    @abstractmethod
    def get_email_from_api(self) -> str:
        """通过API获取邮箱地址

        Returns:
            str: 邮箱地址,失败返回None
        """
        pass

    # ==================== 邮件内容获取 ====================

    @abstractmethod
    def get_latest_email_from_page(self, cdp, session_id, email: str) -> dict:
        """从网页获取最新邮件内容

        Args:
            cdp: CDPClient实例
            session_id: CDP会话ID
            email: 邮箱地址

        Returns:
            dict: 邮件内容字典 {'subject': str, 'content': str, 'html': str, 'from': str}
                  失败返回None
        """
        pass

    @abstractmethod
    def get_latest_email_from_api(self, email_address: str) -> dict:
        """通过API获取最新邮件内容

        Args:
            email_address: 邮箱地址

        Returns:
            dict: 邮件内容字典 {'subject': str, 'content': str, 'html': str, 'from': str}
                  失败返回None
        """
        pass

    # ==================== 验证码解析 ====================

    def parse_augment_code(self, email_content: dict) -> str:
        """从邮件内容中解析Augment验证码

        Args:
            email_content: 邮件内容字典

        Returns:
            str: 验证码,失败返回None
        """
        if not email_content:
            return None

        from_addr = email_content.get('from', '')
        subject = email_content.get('subject', '')

        # 检查是否为 Augment 邮件（AWS SES 发送或主题包含 Augment）
        if 'amazonses.com' not in from_addr.lower() and 'augment' not in subject.lower():
            print("   ⚠️  不是Augment邮件")
            return None

        print(f"   ✓ 识别为Augment邮件")

        content = email_content.get('content', '')
        html = email_content.get('html', '')

        # 合并文本和HTML内容
        full_content = content + ' ' + html

        # Augment验证码匹配模式（按优先级排序）
        patterns = [
            r'verification code is:\s*<b>(\d{6})</b>',  # HTML格式优先
            r'verification code is:\s*(\d{6})',
            r'code is:\s*<b>(\d{6})</b>',
            r'code is:\s*(\d{6})',
            r'code:\s*(\d{6})',
            r'(\d{6})',  # 最后尝试匹配任意6位数字
        ]

        for pattern in patterns:
            match = re.search(pattern, full_content, re.IGNORECASE)
            if match:
                code = match.group(1)
                print(f"   ✓ 找到Augment验证码: {code}")
                return code

        print(f"   ⚠️  未能从邮件内容中提取Augment验证码")
        return None

    def parse_windsurf_code(self, email_content: dict) -> str:
        """从邮件内容中解析Windsurf验证码

        Args:
            email_content: 邮件内容字典

        Returns:
            str: 验证码,失败返回None
        """
        if not email_content:
            return None

        from_addr = email_content.get('from', '')
        subject = email_content.get('subject', '')

        # 检查是否为 Windsurf 邮件
        if 'windsurf' not in from_addr.lower() and 'windsurf' not in subject.lower():
            print("   ⚠️  不是Windsurf邮件")
            return None

        print(f"   ✓ 识别为Windsurf邮件")

        content = email_content.get('content', '')
        html = email_content.get('html', '')

        # 合并文本和HTML内容
        full_content = content + ' ' + html

        # Windsurf验证码匹配模式（按优先级排序）
        patterns = [
            r'verification code[:\s]*<b>(\d{6})</b>',  # HTML格式
            r'verification code[:\s]*(\d{6})',
            r'code[:\s]*<b>(\d{6})</b>',
            r'code[:\s]*(\d{6})',
            r'验证码[：:]\s*(\d{6})',
            r'(\d{6})',  # 最后尝试匹配任意6位数字
        ]

        for pattern in patterns:
            match = re.search(pattern, full_content, re.IGNORECASE)
            if match:
                code = match.group(1)
                print(f"   ✓ 找到Windsurf验证码: {code}")
                return code

        print(f"   ⚠️  未能从邮件内容中提取Windsurf验证码")
        return None

    def parse_ob1_code(self, email_content: dict) -> str:
        """从邮件内容中解析OB-1 / WorkOS验证码

        Args:
            email_content: 邮件内容字典

        Returns:
            str: 验证码,失败返回None
        """
        if not email_content:
            return None

        from_addr = email_content.get('from', '')
        subject = email_content.get('subject', '')
        content = email_content.get('content', '')
        html = email_content.get('html', '')

        from_lower = from_addr.lower()
        subject_lower = subject.lower()
        full_content = f"{subject}\n{content}\n{html}"
        full_lower = full_content.lower()

        # 检查是否为 OB-1 / WorkOS 邮件
        markers = [
            'workos',
            'openblocklabs',
            'openblock labs',
            'openblock',
            'ob-1',
            'obl',
        ]
        if not any(marker in from_lower or marker in subject_lower or marker in full_lower for marker in markers):
            print("   ⚠️  不是OB-1邮件")
            return None

        print("   ✓ 识别为OB-1邮件")

        patterns = [
            r'verification code(?: is|:)?\s*<b>(\d{6})</b>',
            r'verification code(?: is|:)?\s*(\d{6})',
            r'one[- ]time code(?: is|:)?\s*(\d{6})',
            r'验证码[：:]\s*(\d{6})',
            r'\b(\d{6})\b',
        ]

        for pattern in patterns:
            match = re.search(pattern, full_content, re.IGNORECASE)
            if match:
                code = match.group(1)
                print(f"   ✓ 找到OB-1验证码: {code}")
                return code

        print("   ⚠️  未能从邮件内容中提取OB-1验证码")
        return None

    def parse_openai_code(self, email_content: dict) -> str:
        """从邮件内容中解析 OpenAI 验证码

        Args:
            email_content: 邮件内容字典

        Returns:
            str: 验证码,失败返回None
        """
        if not email_content:
            return None

        from_addr = email_content.get('from', '')
        subject = email_content.get('subject', '')
        content = email_content.get('content', '')
        html = email_content.get('html', '')

        full_content = f"{subject}\n{content}\n{html}"
        from_lower = from_addr.lower()
        subject_lower = subject.lower()
        full_lower = full_content.lower()

        if 'openai' not in from_lower and 'openai' not in subject_lower and 'openai' not in full_lower:
            print("   ⚠️  不是OpenAI邮件")
            return None

        print("   ✓ 识别为OpenAI邮件")

        patterns = [
            r'验证码[：:]\s*(\d{6})',
            r'verification code(?: is|:)?\s*(\d{6})',
            r'code(?: is|:)?\s*(\d{6})',
            r'\b(\d{6})\b',
        ]

        for pattern in patterns:
            match = re.search(pattern, full_content, re.IGNORECASE)
            if match:
                code = match.group(1)
                print(f"   ✓ 找到OpenAI验证码: {code}")
                return code

        print("   ⚠️  未能从邮件内容中提取OpenAI验证码")
        return None

