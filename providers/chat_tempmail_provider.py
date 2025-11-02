#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ChatTempMail临时邮箱服务提供者

实现 https://chat-tempmail.com/ 临时邮箱服务

作者: AI Assistant
版本: 1.0
"""

import re
import json
import time
from urllib.request import urlopen, Request
from urllib.error import URLError, HTTPError

from .email_provider import EmailProvider


class ChatTempMailProvider(EmailProvider):
    """ChatTempMail临时邮箱服务提供者
    
    实现 https://chat-tempmail.com/ 临时邮箱服务
    使用官方API接口进行邮箱管理和邮件获取
    """
    
    def __init__(self, api_key: str = None):
        """初始化ChatTempMail服务
        
        Args:
            api_key: API密钥,如果不提供则需要从环境变量或配置文件读取
        """
        self.base_url = "https://chat-tempmail.com"
        self.api_base = "https://chat-tempmail.com/api"
        self.api_key = api_key
        self.domain_patterns = ["chat-tempmail.com"]

        # 缓存邮箱ID映射 {email_address: email_id}
        self.email_id_cache = {}

    def needs_browser_page(self) -> bool:
        """ChatTempMail不需要打开浏览器页面,直接通过API创建邮箱"""
        return False

    def get_page_url(self) -> str:
        """获取邮箱页面URL"""
        return f"{self.base_url}/"
    
    def get_domain_patterns(self) -> list:
        """获取域名匹配模式"""
        return self.domain_patterns
    
    def get_email_from_page(self, cdp, session_id) -> str:
        """通过API创建并获取邮箱地址

        不需要从页面获取,直接调用API创建新邮箱
        """
        print("   🔍 步骤5: 通过API创建邮箱...")

        try:
            # 调用API创建邮箱
            email = self._create_email()

            if email:
                print(f"   ✓ 创建邮箱成功: {email}")
                return email
            else:
                print("   ✗ 创建邮箱失败")
                return None

        except Exception as e:
            print(f"   ✗ 创建邮箱出错: {e}")
            return None
    
    def get_verification_code(self, email: str) -> str:
        """从ChatTempMail API获取验证码
        
        Args:
            email: 邮箱地址
            
        Returns:
            str: 验证码,失败返回None
        """
        print(f"\n📧 正在从ChatTempMail获取验证码...")
        print(f"   📮 邮箱地址: {email}")
        
        if not self.api_key:
            print("   ✗ 错误: 未设置API密钥")
            return None
        
        # 1. 获取邮箱ID
        email_id = self._get_email_id(email)
        if not email_id:
            print("   ✗ 无法获取邮箱ID")
            return None
        
        print(f"   ✓ 邮箱ID: {email_id}")
        
        # 2. 轮询获取邮件
        max_retries = 10
        for attempt in range(max_retries):
            try:
                print(f"   🔄 第 {attempt + 1}/{max_retries} 次尝试...")
                
                # 获取邮件列表
                messages = self._get_messages(email_id)
                
                if not messages:
                    print(f"   ⏳ 暂无邮件,等待3秒后重试...")
                    time.sleep(3)
                    continue
                
                print(f"   ✓ 找到 {len(messages)} 封邮件")
                
                # 查找来自 augmentcode.com 的邮件
                for msg in messages:
                    from_addr = msg.get('from_address', '')
                    subject = msg.get('subject', '')
                    msg_id = msg.get('id', '')
                    
                    print(f"   📧 邮件: {from_addr} - {subject}")
                    
                    if 'augmentcode.com' in from_addr.lower():
                        print(f"   ✓ 找到Augment邮件")
                        
                        # 获取邮件详情
                        message_detail = self._get_message_detail(email_id, msg_id)
                        if not message_detail:
                            continue
                        
                        content = message_detail.get('content', '')
                        html = message_detail.get('html', '')
                        
                        # 从内容中提取验证码
                        code = self._extract_verification_code(content, html)
                        if code:
                            print(f"   ✓ 找到验证码: {code}")
                            return code
                        
                        print(f"   ⚠️  未能从邮件内容中提取验证码")
                
                print(f"   ⚠️  未找到Augment邮件,等待3秒后重试...")
                time.sleep(3)
                
            except Exception as e:
                print(f"   ✗ 错误: {e}")
                if attempt < max_retries - 1:
                    time.sleep(3)
        
        print(f"   ✗ 获取验证码失败（已尝试{max_retries}次）")
        return None
    
    def _create_email(self, name: str = None, expiry_time: int = 0, domain: str = None) -> str:
        """通过API创建新邮箱

        Args:
            name: 邮箱前缀,不指定则随机生成
            expiry_time: 有效期(毫秒) - 3600000(1小时)/86400000(1天)/259200000(3天)/0(永久)
            domain: 邮箱域名,不指定则使用默认域名

        Returns:
            str: 创建的邮箱地址,失败返回None
        """
        try:
            import random
            import string

            # 如果没有指定名称,生成随机名称
            if not name:
                name = ''.join(random.choices(string.ascii_lowercase + string.digits, k=10))

            # 如果没有指定域名,获取可用域名列表
            if not domain:
                domains = self._get_available_domains()
                if domains:
                    domain = domains[0]  # 使用第一个可用域名
                else:
                    domain = "chat-tempmail.com"  # 默认域名

            # 构建请求数据
            data = {
                "name": name,
                "expiryTime": expiry_time,
                "domain": domain
            }

            # 调用API创建邮箱
            url = f"{self.api_base}/emails/generate"
            req = Request(url, data=json.dumps(data).encode('utf-8'), method='POST')
            req.add_header('X-API-Key', self.api_key)
            req.add_header('Content-Type', 'application/json')
            req.add_header('User-Agent', 'Mozilla/5.0')

            response = urlopen(req, timeout=10)
            response_data = response.read().decode('utf-8')
            result = json.loads(response_data)

            print(f"   📝 API响应: {response_data}")

            # 提取邮箱地址 (API返回的字段是 'email' 而不是 'address')
            email_address = result.get('email')
            if email_address:
                # 缓存邮箱ID
                email_id = result.get('id')
                if email_id:
                    self.email_id_cache[email_address] = email_id

                return email_address

            print(f"   ⚠️  API响应中没有email字段")
            return None

        except HTTPError as e:
            error_body = e.read().decode('utf-8') if e.fp else 'No error body'
            print(f"   ✗ HTTP错误 {e.code}: {error_body}")
            return None
        except Exception as e:
            print(f"   ✗ 创建邮箱失败: {type(e).__name__}: {e}")
            import traceback
            traceback.print_exc()
            return None

    def _get_available_domains(self) -> list:
        """获取可用的邮箱域名列表

        Returns:
            list: 域名列表,失败返回空列表
        """
        try:
            url = f"{self.api_base}/email/domains"
            req = Request(url)
            req.add_header('X-API-Key', self.api_key)
            req.add_header('User-Agent', 'Mozilla/5.0')

            response = urlopen(req, timeout=10)
            response_data = response.read().decode('utf-8')
            data = json.loads(response_data)

            print(f"   📝 可用域名: {data.get('domains', [])}")
            return data.get('domains', [])

        except HTTPError as e:
            error_body = e.read().decode('utf-8') if e.fp else 'No error body'
            print(f"   ⚠️  获取域名列表HTTP错误 {e.code}: {error_body}")
            return []
        except Exception as e:
            print(f"   ⚠️  获取域名列表失败: {type(e).__name__}: {e}")
            return []

    def _get_email_id(self, email_address: str) -> str:
        """获取邮箱ID
        
        Args:
            email_address: 邮箱地址
            
        Returns:
            str: 邮箱ID,失败返回None
        """
        # 检查缓存
        if email_address in self.email_id_cache:
            return self.email_id_cache[email_address]
        
        try:
            # 调用API获取邮箱列表
            url = f"{self.api_base}/emails"
            req = Request(url)
            req.add_header('X-API-Key', self.api_key)
            req.add_header('User-Agent', 'Mozilla/5.0')
            
            response = urlopen(req, timeout=10)
            data = json.loads(response.read().decode('utf-8'))
            
            emails = data.get('emails', [])
            for email_obj in emails:
                if email_obj.get('address') == email_address:
                    email_id = email_obj.get('id')
                    # 缓存结果
                    self.email_id_cache[email_address] = email_id
                    return email_id
            
            print(f"   ⚠️  在账户中未找到邮箱: {email_address}")
            return None
            
        except Exception as e:
            print(f"   ✗ 获取邮箱ID失败: {e}")
            return None

    def _get_messages(self, email_id: str) -> list:
        """获取邮件列表

        Args:
            email_id: 邮箱ID

        Returns:
            list: 邮件列表,失败返回空列表
        """
        try:
            url = f"{self.api_base}/emails/{email_id}"
            req = Request(url)
            req.add_header('X-API-Key', self.api_key)
            req.add_header('User-Agent', 'Mozilla/5.0')

            response = urlopen(req, timeout=10)
            data = json.loads(response.read().decode('utf-8'))

            return data.get('messages', [])

        except Exception as e:
            print(f"   ✗ 获取邮件列表失败: {e}")
            return []

    def _get_message_detail(self, email_id: str, message_id: str) -> dict:
        """获取邮件详情

        Args:
            email_id: 邮箱ID
            message_id: 邮件ID

        Returns:
            dict: 邮件详情,失败返回None
        """
        try:
            url = f"{self.api_base}/emails/{email_id}/{message_id}"
            req = Request(url)
            req.add_header('X-API-Key', self.api_key)
            req.add_header('User-Agent', 'Mozilla/5.0')

            response = urlopen(req, timeout=10)
            data = json.loads(response.read().decode('utf-8'))

            return data.get('message', {})

        except Exception as e:
            print(f"   ✗ 获取邮件详情失败: {e}")
            return None

    def _extract_verification_code(self, content: str, html: str = '') -> str:
        """从邮件内容中提取验证码

        Args:
            content: 纯文本内容
            html: HTML内容

        Returns:
            str: 验证码,失败返回None
        """
        # 合并文本和HTML内容
        full_content = content + ' ' + html

        # 验证码匹配模式
        patterns = [
            r'verification code is:\s*(\d{6})',
            r'verification code is:\s*<b>(\d{6})</b>',
            r'code is:\s*(\d{6})',
            r'code:\s*(\d{6})',
            r'验证码[：:]\s*(\d{6})',
            r'(\d{6})',  # 最后尝试匹配任意6位数字
        ]

        for pattern in patterns:
            match = re.search(pattern, full_content, re.IGNORECASE)
            if match:
                return match.group(1)

        return None

