#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Mail.tm 临时邮箱服务提供者

实现 https://api.mail.tm 临时邮箱服务
"""

import random
import secrets
import time
from typing import Any, Dict, List, Optional

from curl_cffi import requests

from .email_provider import EmailProvider


class MailTmProvider(EmailProvider):
    """Mail.tm 临时邮箱服务提供者"""

    BASE_URL = "https://api.mail.tm"

    def __init__(self, proxies: Any = None, timeout: int = 15):
        self.proxies = proxies
        self.timeout = timeout
        self.current_email = ""
        self.current_password = ""
        self.current_token = ""

    def needs_browser_page(self) -> bool:
        """Mail.tm 不需要打开浏览器页面"""
        return False

    def get_page_url(self) -> str:
        """获取邮箱页面 URL"""
        return "https://mail.tm"

    def get_domain_patterns(self) -> list:
        """获取域名匹配模式"""
        return ["mail.tm"]

    def _headers(self, *, token: str = "", use_json: bool = False) -> Dict[str, str]:
        headers = {"Accept": "application/json"}
        if use_json:
            headers["Content-Type"] = "application/json"
        if token:
            headers["Authorization"] = f"Bearer {token}"
        return headers

    def _get_domains(self) -> List[str]:
        resp = requests.get(
            f"{self.BASE_URL}/domains",
            headers=self._headers(),
            proxies=self.proxies,
            impersonate="chrome",
            timeout=self.timeout,
        )
        if resp.status_code != 200:
            raise RuntimeError(f"获取 Mail.tm 域名失败，状态码: {resp.status_code}")

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
        """Mail.tm 不支持从网页提取邮箱地址"""
        print("   ⚠️  Mail.tm 不支持从网页提取邮箱")
        print("   💡 请使用 get_email_from_api() 方法")
        return None

    def get_email_from_api(self) -> str:
        """通过 API 创建邮箱并缓存授权信息"""
        print("   🔍 通过 Mail.tm API 创建邮箱...")

        try:
            domains = self._get_domains()
            if not domains:
                print("   ✗ Mail.tm 没有可用域名")
                return None

            domain = random.choice(domains)
            for _ in range(5):
                local = f"oc{secrets.token_hex(5)}"
                email = f"{local}@{domain}"
                password = secrets.token_urlsafe(18)

                create_resp = requests.post(
                    f"{self.BASE_URL}/accounts",
                    headers=self._headers(use_json=True),
                    json={"address": email, "password": password},
                    proxies=self.proxies,
                    impersonate="chrome",
                    timeout=self.timeout,
                )
                if create_resp.status_code not in (200, 201):
                    continue

                token_resp = requests.post(
                    f"{self.BASE_URL}/token",
                    headers=self._headers(use_json=True),
                    json={"address": email, "password": password},
                    proxies=self.proxies,
                    impersonate="chrome",
                    timeout=self.timeout,
                )
                if token_resp.status_code != 200:
                    continue

                token = str(token_resp.json().get("token") or "").strip()
                if not token:
                    continue

                self.current_email = email
                self.current_password = password
                self.current_token = token
                print(f"   ✓ Mail.tm 邮箱创建成功: {email}")
                return email

            print("   ✗ Mail.tm 邮箱创建成功但获取 Token 失败")
            return None
        except Exception as e:
            print(f"   ✗ 请求 Mail.tm API 出错: {e}")
            return None

    def get_latest_email_from_page(self, cdp, session_id, email: str) -> dict:
        """Mail.tm 不支持从网页获取邮件"""
        print("   ⚠️  Mail.tm 不支持从网页获取邮件")
        print("   💡 请使用 get_latest_email_from_api() 方法")
        return None

    def _read_message(self, message_id: str) -> Optional[Dict[str, str]]:
        read_resp = requests.get(
            f"{self.BASE_URL}/messages/{message_id}",
            headers=self._headers(token=self.current_token),
            proxies=self.proxies,
            impersonate="chrome",
            timeout=self.timeout,
        )
        if read_resp.status_code != 200:
            return None

        mail_data = read_resp.json()
        sender = str(((mail_data.get("from") or {}).get("address") or "")).strip()
        subject = str(mail_data.get("subject") or "")
        intro = str(mail_data.get("intro") or "")
        text = str(mail_data.get("text") or "")
        html = mail_data.get("html") or ""
        if isinstance(html, list):
            html = "\n".join(str(x) for x in html)

        return {
            "subject": subject,
            "content": "\n".join([subject, intro, text, str(html)]),
            "html": str(html),
            "from": sender,
        }

    def get_latest_email_from_api(
        self,
        email_address: str,
        timeout: int = 120,
        check_interval: int = 3,
    ) -> dict:
        """轮询获取最新的 OpenAI 邮件内容"""
        if not self.current_token:
            print("   ✗ Mail.tm Token 不存在，请先调用 get_email_from_api()")
            return None

        url_list = f"{self.BASE_URL}/messages"
        seen_ids: set[str] = set()
        deadline = time.time() + max(1, int(timeout or 1))

        print(f"   📧 正在等待邮箱 {email_address} 的 OpenAI 邮件...")

        while time.time() < deadline:
            try:
                resp = requests.get(
                    url_list,
                    headers=self._headers(token=self.current_token),
                    proxies=self.proxies,
                    impersonate="chrome",
                    timeout=self.timeout,
                )
                if resp.status_code != 200:
                    time.sleep(max(1, int(check_interval or 3)))
                    continue

                data = resp.json()
                if isinstance(data, list):
                    messages = data
                elif isinstance(data, dict):
                    messages = data.get("hydra:member") or data.get("messages") or []
                else:
                    messages = []

                for msg in messages:
                    if not isinstance(msg, dict):
                        continue

                    msg_id = str(msg.get("id") or "").strip()
                    if not msg_id or msg_id in seen_ids:
                        continue
                    seen_ids.add(msg_id)

                    email_content = self._read_message(msg_id)
                    if not email_content:
                        continue

                    sender = str(email_content.get("from") or "").lower()
                    merged_content = "\n".join(
                        [
                            str(email_content.get("subject") or ""),
                            str(email_content.get("content") or ""),
                            str(email_content.get("html") or ""),
                        ]
                    ).lower()

                    if "openai" not in sender and "openai" not in merged_content:
                        continue

                    print(f"   ✓ 收到目标邮件: {email_content.get('subject') or '(无主题)'}")
                    return email_content
            except Exception as e:
                print(f"   ⚠️  Mail.tm 拉取邮件失败: {e}")

            time.sleep(max(1, int(check_interval or 3)))

        print("   ✗ 等待 OpenAI 邮件超时")
        return None
