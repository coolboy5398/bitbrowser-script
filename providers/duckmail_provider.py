#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
DuckMail 临时邮箱服务提供者

实现 https://api.duckmail.sbs 临时邮箱服务
"""

import random
import secrets
import time
from typing import Any, Callable, Dict, List, Optional

from curl_cffi import requests

from .email_provider import EmailProvider


class DuckMailProvider(EmailProvider):
    """DuckMail 临时邮箱服务提供者"""

    DEFAULT_API_BASE = "https://api.duckmail.sbs"
    DEFAULT_PAGE_URL = "https://duckmail.sbs"

    def __init__(
        self,
        api_base: str = DEFAULT_API_BASE,
        bearer_token: str = "",
        proxies: Any = None,
        timeout: int = 15,
    ):
        self.api_base = (api_base or self.DEFAULT_API_BASE).rstrip("/")
        self.bearer_token = (bearer_token or "").strip()
        self.proxies = proxies
        self.timeout = max(1, int(timeout or 15))
        self.current_email = ""
        self.current_password = ""
        self.current_token = ""

    def needs_browser_page(self) -> bool:
        """DuckMail 不需要打开浏览器页面"""
        return False

    def get_page_url(self) -> str:
        """获取邮箱页面 URL"""
        return self.DEFAULT_PAGE_URL

    def get_domain_patterns(self) -> list:
        """获取域名匹配模式"""
        return ["duckmail.sbs", "api.duckmail.sbs"]

    def _headers(self, *, token: str = "", use_json: bool = False) -> Dict[str, str]:
        headers = {"Accept": "application/json"}
        if use_json:
            headers["Content-Type"] = "application/json"
        if token:
            headers["Authorization"] = f"Bearer {token}"
        return headers

    def _request(self, method: str, url: str, **kwargs):
        return requests.request(
            method,
            url,
            proxies=self.proxies,
            impersonate="chrome",
            timeout=self.timeout,
            **kwargs,
        )

    def _get_domains(self) -> List[str]:
        resp = self._request(
            "GET",
            f"{self.api_base}/domains",
            headers={"Accept": "application/json"},
        )
        if resp.status_code != 200:
            raise RuntimeError(f"获取 DuckMail 域名失败，状态码: {resp.status_code}")

        data = resp.json()
        if isinstance(data, list):
            items = data
        elif isinstance(data, dict):
            items = data.get("hydra:member") or data.get("items") or []
        else:
            items = []

        domains: List[str] = []
        for item in items:
            if not isinstance(item, dict):
                continue
            domain = str(item.get("domain") or "").strip()
            is_active = item.get("isActive", True)
            is_private = item.get("isPrivate", False)
            if domain and is_active and not is_private:
                domains.append(domain)
        return domains

    def get_email_from_page(self, cdp, session_id) -> str:
        """DuckMail 不支持从网页提取邮箱地址"""
        print("   ⚠️  DuckMail 不支持从网页提取邮箱")
        print("   💡 请使用 get_email_from_api() 方法")
        return None

    def get_email_from_api(self) -> str:
        """通过 API 创建邮箱并缓存授权信息"""
        print("   🔍 通过 DuckMail API 创建邮箱...")

        try:
            domains = self._get_domains()
            if not domains:
                print("   ✗ DuckMail 没有可用域名")
                return None

            domain = random.choice(domains)
            headers = self._headers(token=self.bearer_token, use_json=True)

            for _ in range(5):
                local = f"oc{secrets.token_hex(5)}"
                email = f"{local}@{domain}"
                password = secrets.token_urlsafe(18)

                create_resp = self._request(
                    "POST",
                    f"{self.api_base}/accounts",
                    json={"address": email, "password": password},
                    headers=headers,
                )
                if create_resp.status_code not in (200, 201):
                    continue

                time.sleep(0.5)
                token_resp = self._request(
                    "POST",
                    f"{self.api_base}/token",
                    json={"address": email, "password": password},
                    headers=headers,
                )
                if token_resp.status_code != 200:
                    continue

                token = str(token_resp.json().get("token") or "").strip()
                if not token:
                    continue

                self.current_email = email
                self.current_password = password
                self.current_token = token
                print(f"   ✓ DuckMail 邮箱创建成功: {email}")
                return email

            print("   ✗ DuckMail 邮箱创建成功但获取 Token 失败")
            return None
        except Exception as e:
            print(f"   ✗ 请求 DuckMail API 出错: {e}")
            return None

    def get_latest_email_from_page(self, cdp, session_id, email: str) -> dict:
        """DuckMail 不支持从网页获取邮件"""
        print("   ⚠️  DuckMail 不支持从网页获取邮件")
        print("   💡 请使用 get_latest_email_from_api() 方法")
        return None

    def _list_messages(self) -> List[Dict[str, Any]]:
        if not self.current_token:
            return []

        resp = self._request(
            "GET",
            f"{self.api_base}/messages",
            headers=self._headers(token=self.current_token),
        )
        if resp.status_code != 200:
            return []

        data = resp.json()
        if isinstance(data, list):
            messages = data
        elif isinstance(data, dict):
            messages = (
                data.get("hydra:member")
                or data.get("member")
                or data.get("data")
                or data.get("messages")
                or []
            )
        else:
            messages = []

        return [msg for msg in messages if isinstance(msg, dict)]

    def _extract_message_id(self, message: Dict[str, Any]) -> str:
        raw_id = str(message.get("id") or message.get("@id") or "").strip()
        if not raw_id:
            return ""
        if raw_id.startswith("/"):
            return raw_id.split("/")[-1]
        return raw_id

    def _read_message(self, message_id: str) -> Optional[Dict[str, str]]:
        resp = self._request(
            "GET",
            f"{self.api_base}/messages/{message_id}",
            headers=self._headers(token=self.current_token),
        )
        if resp.status_code != 200:
            return None

        detail = resp.json()
        sender_info = detail.get("from") or {}
        if isinstance(sender_info, dict):
            sender = str(sender_info.get("address") or sender_info.get("email") or "").strip()
        else:
            sender = str(sender_info or "").strip()

        subject = str(detail.get("subject") or "").strip()
        text = str(detail.get("text") or "")
        html = detail.get("html") or ""
        if isinstance(html, list):
            html = "\n".join(str(item) for item in html)

        content_parts = [part for part in [subject, text, str(html)] if part]
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
            print("   ✗ DuckMail Token 不存在，请先调用 get_email_from_api()")
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
                    message_id = self._extract_message_id(msg_data)
                    if not message_id or message_id in seen_ids:
                        continue
                    seen_ids.add(message_id)

                    email_content = self._read_message(message_id)
                    if not email_content:
                        continue

                    if filter_func and not filter_func(email_content):
                        continue

                    print(f"   ✓ 收到邮件: {email_content.get('subject') or '(无主题)'}")
                    return email_content
            except Exception as e:
                print(f"   ⚠️  DuckMail 拉取邮件失败: {e}")

            time.sleep(max(1, int(check_interval or 3)))

        print("   ✗ 等待邮件超时")
        return None
