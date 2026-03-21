#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ChatTempMail临时邮箱服务提供者

实现 https://chat-tempmail.com/ 临时邮箱服务

作者: AI Assistant
版本: 1.0
"""

import json
import os
import time
from typing import Any, Callable, Dict, Optional
from urllib.parse import urlencode
from urllib.request import urlopen, Request
from urllib.error import HTTPError

from .email_provider import EmailProvider

# 未传 api_key 且未设置环境变量 CHAT_TEMPMAIL_API_KEY 时使用
_DEFAULT_CHAT_TEMPMAIL_API_KEY = "mk_HvAkvMNu1qce02lzhwC3ZZbW-NOoRYMp"


class ChatTempMailProvider(EmailProvider):
    """ChatTempMail临时邮箱服务提供者
    
    实现 https://chat-tempmail.com/ 临时邮箱服务
    使用官方API接口进行邮箱管理和邮件获取
    """
    
    def __init__(self, api_key: str = None, **kwargs: Any):
        """初始化ChatTempMail服务

        Args:
            api_key: API密钥；省略时依次尝试环境变量 CHAT_TEMPMAIL_API_KEY、内置默认密钥
            **kwargs: 与工厂兼容（如 proxies、timeout），本实现使用 urllib 直连，忽略之
        """
        self.base_url = "https://chat-tempmail.com"
        self.api_base = "https://chat-tempmail.com/api"
        key = (api_key if api_key is not None else os.environ.get("CHAT_TEMPMAIL_API_KEY", "")).strip()
        if not key:
            key = _DEFAULT_CHAT_TEMPMAIL_API_KEY.strip()
        self.api_key = key or None
        self.domain_patterns = ["chat-tempmail.com"]

        # 缓存邮箱ID映射 {email_address: email_id}
        self.email_id_cache = {}
        self.current_email = ""
        self.current_email_id = ""

    def needs_browser_page(self) -> bool:
        """ChatTempMail不需要打开浏览器页面,直接通过API创建邮箱"""
        return False

    def get_page_url(self) -> str:
        """获取邮箱页面URL"""
        return f"{self.base_url}/"
    
    def get_domain_patterns(self) -> list:
        """获取域名匹配模式"""
        return self.domain_patterns

    def get_mail_access_identifier(self) -> str:
        """获取取邮件标识（返回可直接访问的 API inbox 地址）"""
        email_id = str(self.current_email_id or "").strip()
        if email_id:
            return f"{self.api_base}/emails/{email_id}"
        return ""
    
    # ==================== 邮箱地址获取 ====================

    def get_email_from_page(self, cdp, session_id) -> str:
        """从网页提取邮箱地址

        ChatTempMail不支持从网页提取,请使用get_email_from_api
        """
        print("   ⚠️  ChatTempMail不支持从网页提取邮箱")
        print("   💡 请使用get_email_from_api()方法")
        return None

    def get_email_from_api(self) -> str:
        """通过API获取邮箱地址

        Returns:
            str: 邮箱地址,失败返回None
        """
        print("   🔍 通过API创建邮箱...")
        self.current_email = ""
        self.current_email_id = ""

        if not self.api_key:
            print("   ✗ 错误: 未设置API密钥")
            return None

        try:
            email = self._create_email()
            if email:
                print(f"   ✓ 创建邮箱成功: {email}")
                if self.current_email_id:
                    print(f"   ℹ️  取邮件标识: {self.current_email_id}")
                return email

            print("   ⚠️  创建失败，尝试清理旧邮箱后重试...")
            cleaned = self._cleanup_old_emails()
            if cleaned > 0:
                email = self._create_email()
                if email:
                    print(f"   ✓ 清理后创建邮箱成功: {email}")
                    if self.current_email_id:
                        print(f"   ℹ️  取邮件标识: {self.current_email_id}")
                    return email

            print("   ✗ 创建邮箱失败")
            return None

        except Exception as e:
            print(f"   ✗ 创建邮箱出错: {e}")
            return None

    # ==================== 邮件内容获取 ====================

    def get_latest_email_from_page(self, cdp, session_id, email: str) -> dict:
        """从网页获取最新邮件内容

        ChatTempMail不支持从网页获取,请使用get_latest_email_from_api
        """
        print("   ⚠️  ChatTempMail不支持从网页获取邮件")
        print("   💡 请使用get_latest_email_from_api()方法")
        return None

    def get_latest_email_from_api(
        self,
        email_address: str,
        timeout: int = 120,
        check_interval: int = 3,
        filter_func: Optional[Callable[[Dict[str, str]], bool]] = None,
        **kwargs: Any,
    ) -> dict:
        """通过API获取最新邮件内容

        Args:
            email_address: 邮箱地址
            timeout: 最长等待时间（秒），与 openai_register / TempMail.lol 一致
            check_interval: 轮询间隔（秒）
            filter_func: 若提供，仅当对构造出的邮件 dict 返回 True 时才视为命中
            **kwargs: 忽略未知关键字，兼容其它 provider 的调用方式

        Returns:
            dict: 邮件内容字典 {'subject': str, 'content': str, 'html': str, 'from': str}
                  失败返回None
        """
        print(f"\n📧 正在从ChatTempMail API获取最新邮件...")
        print(f"   📮 邮箱地址: {email_address}")

        if not self.api_key:
            print("   ✗ 错误: 未设置API密钥")
            return None

        # 1. 获取邮箱ID
        email_id = self._get_email_id(email_address)
        if not email_id:
            print("   ✗ 无法获取邮箱ID")
            return None

        print(f"   ✓ 邮箱ID: {email_id}")

        start = time.time()
        deadline = start + max(1, int(timeout or 1))
        interval = max(1, int(check_interval or 3))
        attempt = 0

        while time.time() < deadline:
            attempt += 1
            try:
                print(f"   🔄 第 {attempt} 次尝试（约 {int(deadline - time.time())} 秒内结束）...")

                messages = self._get_messages(email_id)

                if not messages:
                    print(f"   ⏳ 暂无邮件,等待{interval}秒后重试...")
                    time.sleep(interval)
                    continue

                print(f"   ✓ 找到 {len(messages)} 封邮件")

                latest_msg = max(
                    messages,
                    key=lambda m: m.get('received_at') or 0,
                )
                from_addr = latest_msg.get('from_address', '')
                subject = latest_msg.get('subject', '')
                msg_id = latest_msg.get('id', '')

                print(f"   📧 最新邮件: {from_addr} - {subject}")

                message_detail = self._get_message_detail(email_id, msg_id)
                if message_detail:
                    email_content = {
                        'subject': subject,
                        'content': message_detail.get('content', ''),
                        'html': message_detail.get('html', ''),
                        'from': from_addr,
                    }
                    if filter_func and not filter_func(email_content):
                        print("   ⏳ 邮件未通过 filter，继续等待...")
                        time.sleep(interval)
                        continue
                    return email_content

                print(f"   ⚠️  无法获取邮件详情,{interval}秒后重试...")
                time.sleep(interval)

            except Exception as e:
                print(f"   ✗ 错误: {e}")
                time.sleep(interval)

        print(f"   ✗ 获取邮件超时（{timeout} 秒）")
        return None

    # ==================== 验证码解析 ====================
    # 使用基类的实现，无需重写
    
    def _create_email(self, name: str = None, expiry_time: int = 86400000, domain: str = None) -> str:
        """通过API创建新邮箱

        Args:
            name: 邮箱前缀,不指定则随机生成
            expiry_time: 有效期(毫秒) - 3600000(1小时)/86400000(1天,默认)/259200000(3天)/0(永久)
            domain: 邮箱域名,不指定则使用默认域名

        Returns:
            str: 创建的邮箱地址,失败返回None
        """
        if not self.api_key:
            print("   ✗ 错误: 未设置API密钥")
            return None

        try:
            import random
            import string

            # 如果没有指定名称,生成随机名称
            if not name:
                name = ''.join(random.choices(string.ascii_lowercase + string.digits, k=10))

            # 如果没有指定域名,获取可用域名列表并随机选择
            if not domain:
                domains = self._get_available_domains()
                if domains:
                    domain = random.choice(domains)  # 随机选择一个可用域名
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

            email_id = str(result.get('id') or '').strip()
            email_address = str(result.get('address') or result.get('email') or '').strip()
            if email_address:
                self.current_email = email_address
                self.current_email_id = email_id
                if email_id:
                    self.email_id_cache[email_address] = email_id
                return email_address

            print("   ⚠️  API响应中没有address/email字段")
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

        if not self.api_key:
            print("   ✗ 错误: 未设置API密钥")
            return None

        try:
            cursor = None
            max_pages = 200
            for _ in range(max_pages):
                path = "/emails"
                if cursor:
                    path = f"{path}?{urlencode({'cursor': cursor})}"
                url = f"{self.api_base}{path}"
                req = Request(url)
                req.add_header('X-API-Key', self.api_key)
                req.add_header('User-Agent', 'Mozilla/5.0')

                response = urlopen(req, timeout=10)
                data = json.loads(response.read().decode('utf-8'))

                for email_obj in data.get('emails', []):
                    if email_obj.get('address') == email_address:
                        email_id = email_obj.get('id')
                        self.email_id_cache[email_address] = email_id
                        return email_id

                cursor = data.get('nextCursor')
                if not cursor:
                    break

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
            all_messages = []
            cursor = None
            max_pages = 50
            for _ in range(max_pages):
                path = f"/emails/{email_id}"
                if cursor:
                    path = f"{path}?{urlencode({'cursor': cursor})}"
                url = f"{self.api_base}{path}"
                req = Request(url)
                req.add_header('X-API-Key', self.api_key)
                req.add_header('User-Agent', 'Mozilla/5.0')

                response = urlopen(req, timeout=10)
                data = json.loads(response.read().decode('utf-8'))

                batch = data.get('messages', [])
                all_messages.extend(batch)

                cursor = data.get('nextCursor')
                if not cursor:
                    break

            all_messages.sort(key=lambda m: m.get('received_at') or 0, reverse=True)
            return all_messages

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

    def _delete_email(self, email_id: str) -> bool:
        """删除指定邮箱"""
        try:
            url = f"{self.api_base}/emails/{email_id}"
            req = Request(url, method='DELETE')
            req.add_header('X-API-Key', self.api_key)
            req.add_header('User-Agent', 'Mozilla/5.0')

            response = urlopen(req, timeout=10)
            data = json.loads(response.read().decode('utf-8'))
            return data.get('success', False)
        except Exception as e:
            print(f"   ⚠️  删除邮箱 {email_id} 失败: {e}")
            return False

    def _cleanup_old_emails(self, keep: int = 0) -> int:
        """清理账户下已有邮箱，为新邮箱腾出配额

        Args:
            keep: 保留最新的 N 个邮箱，0 表示全部清理

        Returns:
            int: 成功删除的数量
        """
        try:
            all_emails = []
            cursor = None
            for _ in range(200):
                path = "/emails"
                if cursor:
                    path = f"{path}?{urlencode({'cursor': cursor})}"
                url = f"{self.api_base}{path}"
                req = Request(url)
                req.add_header('X-API-Key', self.api_key)
                req.add_header('User-Agent', 'Mozilla/5.0')

                response = urlopen(req, timeout=10)
                data = json.loads(response.read().decode('utf-8'))
                all_emails.extend(data.get('emails', []))
                cursor = data.get('nextCursor')
                if not cursor:
                    break

            if not all_emails:
                return 0

            all_emails.sort(key=lambda e: e.get('createdAt', ''), reverse=True)
            to_delete = all_emails[keep:]

            deleted = 0
            for email_obj in to_delete:
                eid = email_obj.get('id')
                addr = email_obj.get('address', '?')
                if eid and self._delete_email(eid):
                    self.email_id_cache.pop(addr, None)
                    deleted += 1
                    print(f"   🗑️  已删除旧邮箱: {addr}")

            print(f"   ✓ 清理完成，共删除 {deleted} 个邮箱")
            return deleted

        except Exception as e:
            print(f"   ✗ 清理旧邮箱失败: {e}")
            return 0
