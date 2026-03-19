#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
TempMail.lol 临时邮箱服务提供者

实现 https://api.tempmail.lol/v2 临时邮箱服务
"""

import time
from typing import Any, Callable, Dict, Optional

from curl_cffi import requests

from .email_provider import EmailProvider


class TempMailLolProvider(EmailProvider):
    """TempMail.lol 临时邮箱服务提供者"""

    BASE_URL = "https://api.tempmail.lol/v2"
    DEFAULT_HEADERS = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/134.0.0.0 Safari/537.36",
        "Accept": "application/json",
        "Content-Type": "application/json",
    }

    def __init__(self, proxies: Any = None, timeout: int = 15):
        self.proxies = proxies
        self.timeout = timeout
        self.current_email = ""
        self.current_token = ""
        self.session = requests.Session(proxies=self.proxies, impersonate="chrome")
        self.session.headers.update(dict(self.DEFAULT_HEADERS))

    def needs_browser_page(self) -> bool:
        """TempMail.lol 不需要打开浏览器页面"""
        return False

    def get_page_url(self) -> str:
        """获取邮箱页面 URL"""
        return "https://tempmail.lol"

    def get_domain_patterns(self) -> list:
        """获取域名匹配模式"""
        return ["tempmail.lol", "api.tempmail.lol"]

    def get_email_from_page(self, cdp, session_id) -> str:
        """TempMail.lol 不支持从网页提取邮箱地址"""
        print("   ⚠️  TempMail.lol 不支持从网页提取邮箱")
        print("   💡 请使用 get_email_from_api() 方法")
        return None

    def get_email_from_api(self) -> str:
        """通过 API 创建邮箱并缓存 token"""
        print("   🔍 通过 TempMail.lol API 创建邮箱...")

        try:
            resp = self.session.post(
                f"{self.BASE_URL}/inbox/create",
                json={},
                timeout=self.timeout,
            )
            resp.raise_for_status()
            data = resp.json()

            address = str(data.get("address") or "").strip()
            token = str(data.get("token") or "").strip()
            if not address or not token:
                print("   ✗ TempMail.lol 响应缺少 address 或 token")
                return None

            self.current_email = address
            self.current_token = token
            print(f"   ✓ TempMail.lol 邮箱创建成功: {address}")
            return address
        except Exception as e:
            print(f"   ✗ 请求 TempMail.lol API 出错: {e}")
            return None

    def get_latest_email_from_page(self, cdp, session_id, email: str) -> dict:
        """TempMail.lol 不支持从网页获取邮件"""
        print("   ⚠️  TempMail.lol 不支持从网页获取邮件")
        print("   💡 请使用 get_latest_email_from_api() 方法")
        return None

    def _list_messages(self) -> list:
        if not self.current_token:
            return []

        resp = self.session.get(
            f"{self.BASE_URL}/inbox?token={self.current_token}",
            timeout=self.timeout,
        )
        resp.raise_for_status()
        data = resp.json()
        emails = data.get("emails") or []
        return emails if isinstance(emails, list) else []

    def _message_identity(self, msg_data: Dict[str, Any]) -> str:
        raw_id = str(msg_data.get("id") or msg_data.get("_id") or "").strip()
        if raw_id:
            return raw_id

        sender = str(msg_data.get("from") or "").strip()
        subject = str(msg_data.get("subject") or "").strip()
        body = str(msg_data.get("body") or "").strip()
        return f"{sender}|{subject}|{body[:80]}"

    def _normalize_message(self, msg_data: Dict[str, Any]) -> Optional[Dict[str, str]]:
        if not isinstance(msg_data, dict):
            return None

        sender = str(msg_data.get("from") or "").strip()
        subject = str(msg_data.get("subject") or "").strip()
        body = str(msg_data.get("body") or "")
        html = msg_data.get("html") or ""
        if isinstance(html, list):
            html = "\n".join(str(item) for item in html)

        content_parts = [part for part in [subject, body, str(html)] if part]
        return {
            "subject": subject,
            "content": "\n".join(content_parts),
            "html": str(html),
            "from": sender,
        }

    def get_latest_email_from_api(
        self,
        email_address: str,
        timeout: int = 120,
        check_interval: int = 3,
        filter_func: Optional[Callable[[Dict[str, str]], bool]] = None,
    ) -> dict:
        """轮询获取最新邮件内容"""
        if not self.current_token:
            print("   ✗ TempMail.lol Token 不存在，请先调用 get_email_from_api()")
            return None

        seen_ids: set[str] = set()
        start = time.time()
        deadline = start + max(1, int(timeout or 1))

        print(f"   📧 正在等待邮箱 {email_address} 的邮件...")

        while time.time() < deadline:
            try:
                messages = self._list_messages()
                elapsed = int(time.time() - start)
                print(f"   ↻ 已轮询 {elapsed} 秒，收到 {len(messages)} 封邮件...")

                for msg_data in messages:
                    if not isinstance(msg_data, dict):
                        continue

                    message_id = self._message_identity(msg_data)
                    if not message_id or message_id in seen_ids:
                        continue
                    seen_ids.add(message_id)

                    email_content = self._normalize_message(msg_data)
                    if not email_content:
                        continue

                    if filter_func and not filter_func(email_content):
                        continue

                    print(f"   ✓ 收到邮件: {email_content.get('subject') or '(无主题)'}")
                    return email_content
            except Exception as e:
                print(f"   ⚠️  TempMail.lol 拉取邮件失败: {e}")

            time.sleep(max(1, int(check_interval or 3)))

        print("   ✗ 等待邮件超时")
        return None
