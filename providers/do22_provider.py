#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
22.do 临时邮箱服务提供者

实现 https://22.do/api/v2 临时邮箱服务
"""

import time
from typing import Any, Callable, Dict, List, Optional

from curl_cffi import requests

from .email_provider import EmailProvider


class Do22Provider(EmailProvider):
    """22.do 临时邮箱服务提供者"""

    BASE_URL = "https://22.do"
    API_BASE = f"{BASE_URL}/api/v2"
    DEFAULT_TIMEOUT = 15
    DEFAULT_POLL_TIMEOUT = 120
    DEFAULT_CHECK_INTERVAL = 3
    USER_AGENT = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/134.0.0.0 Safari/537.36"
    )

    def __init__(
        self,
        token: str = "57eac94a7f442784a311783b41116ea6",
        bearer_token: str = "",
        address: str = "",
        password: str = "",
        account_type: str = "standard",
        proxies: Any = None,
        timeout: int = 15,
    ):
        """初始化 22.do 服务

        Args:
            token: 22.do 平台 token，用于调用 `/token` 换取 Bearer
            bearer_token: 已有 Bearer token，提供后将跳过鉴权换取步骤
            address: 22.do 账户邮箱，用于调用 `/auth`
            password: 22.do 账户密码，用于调用 `/auth`
            account_type: 邮箱类型，支持 `standard` / `premium` / `private`
            proxies: 代理配置，兼容工厂传参
            timeout: HTTP 请求超时时间（秒）
        """
        self.token = (token or "").strip()
        self.bearer_token = (bearer_token or "").strip()
        self.address = (address or "").strip()
        self.password = password or ""
        self.account_type = self._normalize_account_type(account_type)
        self.proxies = proxies
        self.timeout = max(1, int(timeout or self.DEFAULT_TIMEOUT))
        self.current_email = ""
        self.current_inbox_time = 0
        self.session = requests.Session(proxies=self.proxies, impersonate="chrome")
        self.session.headers.update(
            {
                "Accept": "application/json",
                "Content-Type": "application/json",
                "User-Agent": self.USER_AGENT,
            }
        )

    def needs_browser_page(self) -> bool:
        """22.do 不需要打开浏览器页面"""
        return False

    def get_page_url(self) -> str:
        """获取邮箱页面 URL"""
        return self.BASE_URL

    def get_domain_patterns(self) -> list:
        """获取域名匹配模式"""
        return ["22.do"]

    def _normalize_account_type(self, value: str) -> str:
        text = str(value or "standard").strip().lower()
        if text in {"premium", "private"}:
            return text
        return "standard"

    def _headers(self, *, bearer_token: str = "", use_json: bool = True) -> Dict[str, str]:
        headers = {
            "Accept": "application/json",
            "User-Agent": self.USER_AGENT,
        }
        if use_json:
            headers["Content-Type"] = "application/json"

        token = (bearer_token or self.bearer_token).strip()
        if token:
            headers["Authorization"] = f"Bearer {token}"
        return headers

    def _as_text(self, value: Any) -> str:
        if value is None:
            return ""
        if isinstance(value, str):
            return value.strip()
        if isinstance(value, (int, float, bool)):
            return str(value)
        if isinstance(value, list):
            parts = [self._as_text(item) for item in value]
            return "\n".join(part for part in parts if part)
        return ""

    def _pick_text(self, source: Any, *keys: str) -> str:
        if not isinstance(source, dict):
            return ""

        for key in keys:
            if key not in source:
                continue
            text = self._as_text(source.get(key))
            if text:
                return text
        return ""

    def _extract_error_message(self, data: Any, fallback: str = "请求失败") -> str:
        if isinstance(data, dict):
            for key in ("msg", "message", "error", "detail"):
                value = data.get(key)
                if isinstance(value, str) and value.strip():
                    return value.strip()

            error = data.get("error")
            if isinstance(error, dict):
                for key in ("message", "error", "detail"):
                    value = error.get(key)
                    if isinstance(value, str) and value.strip():
                        return value.strip()

        if isinstance(data, str) and data.strip():
            return data.strip()
        return fallback

    def _request(
        self,
        method: str,
        path: str,
        *,
        bearer_token: str = "",
        payload: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        url = f"{self.API_BASE}{path}"
        request_kwargs = {
            "headers": self._headers(bearer_token=bearer_token, use_json=payload is not None),
            "timeout": self.timeout,
        }
        if payload is not None:
            request_kwargs["json"] = payload

        response = self.session.request(method, url, **request_kwargs)
        if response.status_code < 200 or response.status_code > 204:
            error_payload: Any
            try:
                error_payload = response.json()
            except Exception:
                error_payload = response.text.strip()
            error_msg = self._extract_error_message(error_payload, f"HTTP {response.status_code}")
            raise RuntimeError(f"{method} {path} 失败: {error_msg}")

        if response.status_code == 204 or not response.text.strip():
            return {}

        try:
            data = response.json()
        except Exception as exc:
            preview = response.text[:200].replace("\n", " ")
            raise ValueError(f"22.do API 返回无效 JSON: {url} -> {preview}") from exc

        if not isinstance(data, dict):
            raise ValueError(f"22.do API 响应格式错误: {url}")
        return data

    def _extract_response_data(self, data: Dict[str, Any], fallback: str) -> Any:
        if not isinstance(data, dict):
            raise RuntimeError(f"{fallback}: 响应格式错误")

        if data.get("status") is False:
            raise RuntimeError(f"{fallback}: {self._extract_error_message(data, fallback)}")

        return data.get("data")

    def _get_bearer_from_token(self) -> str:
        response = self._request("POST", "/token", payload={"token": self.token})
        data = self._extract_response_data(response, "通过 token 获取 Bearer 失败")
        bearer = self._pick_text(data, "Bearer", "bearer", "token")
        if not bearer:
            raise RuntimeError("通过 token 获取 Bearer 失败: 响应缺少 Bearer")
        return bearer

    def _get_bearer_from_credentials(self) -> str:
        response = self._request(
            "POST",
            "/auth",
            payload={"address": self.address, "password": self.password},
        )
        data = self._extract_response_data(response, "通过账号密码获取 Bearer 失败")
        bearer = self._pick_text(data, "Bearer", "bearer", "token")
        if not bearer:
            raise RuntimeError("通过账号密码获取 Bearer 失败: 响应缺少 Bearer")
        return bearer

    def _ensure_bearer_token(self) -> str:
        if self.bearer_token:
            return self.bearer_token

        if self.token:
            self.bearer_token = self._get_bearer_from_token()
            return self.bearer_token

        if self.address and self.password:
            self.bearer_token = self._get_bearer_from_credentials()
            return self.bearer_token

        raise RuntimeError("22.do 需要 bearer_token、token 或 address/password 其中一种认证方式")

    def _get_account_request(self):
        if self.account_type == "premium":
            return "GET", "/account/premium"
        if self.account_type == "private":
            return "GET", "/account/private"
        return "POST", "/account"

    def _coerce_message_list(self, data: Dict[str, Any]) -> List[Dict[str, Any]]:
        payload = self._extract_response_data(data, "获取邮件列表失败")
        if isinstance(payload, list):
            return [item for item in payload if isinstance(item, dict)]

        if isinstance(payload, dict):
            for key in ("items", "messages", "results", "data"):
                value = payload.get(key)
                if isinstance(value, list):
                    return [item for item in value if isinstance(item, dict)]

            if any(key in payload for key in ("messageId", "subject", "from", "to")):
                return [payload]

        return []

    def _coerce_message_detail(self, data: Dict[str, Any]) -> Dict[str, Any]:
        payload = self._extract_response_data(data, "获取邮件详情失败")
        if isinstance(payload, dict):
            return payload
        if isinstance(payload, list) and payload and isinstance(payload[0], dict):
            return payload[0]
        return {}

    def _message_identity(self, message: Dict[str, Any]) -> str:
        message_id = self._pick_text(message, "messageId", "id", "_id")
        if message_id:
            return message_id

        return "|".join(
            part
            for part in (
                self._pick_text(message, "subject"),
                self._pick_text(message, "from"),
                self._pick_text(message, "to"),
                self._pick_text(message, "time", "expireTime"),
            )
            if part
        )

    def _list_messages(self, email_address: str, since: int) -> List[Dict[str, Any]]:
        payload: Dict[str, Any] = {"email": email_address}
        if since > 0:
            payload["time"] = int(since)

        response = self._request(
            "POST",
            "/inbox",
            bearer_token=self._ensure_bearer_token(),
            payload=payload,
        )
        return self._coerce_message_list(response)

    def _read_message(self, message_id: str) -> Dict[str, Any]:
        response = self._request(
            "POST",
            "/inbox/message",
            bearer_token=self._ensure_bearer_token(),
            payload={"messageId": message_id},
        )
        return self._coerce_message_detail(response)

    def _normalize_message(
        self,
        primary_message: Optional[Dict[str, Any]],
        fallback_message: Optional[Dict[str, Any]] = None,
    ) -> Optional[Dict[str, str]]:
        sources = [source for source in (primary_message, fallback_message) if isinstance(source, dict)]
        if not sources:
            return None

        subject = ""
        body = ""
        html = ""
        from_addr = ""

        for source in sources:
            if not subject:
                subject = self._pick_text(source, "subject")
            if not body:
                body = self._pick_text(source, "body", "content", "text")
            if not html:
                html = self._pick_text(source, "html")
            if not from_addr:
                from_addr = self._pick_text(source, "from", "from_address", "fromAddress")

        content_parts = [part for part in (subject, body, html) if part]
        normalized = {
            "subject": subject,
            "content": "\n".join(content_parts),
            "html": html,
            "from": from_addr,
        }
        if any(normalized.values()):
            return normalized
        return None

    def get_email_from_page(self, cdp, session_id) -> str:
        """22.do 不支持从网页提取邮箱地址"""
        print("   ⚠️  22.do 不支持从网页提取邮箱")
        print("   💡 请使用 get_email_from_api() 方法")
        return None

    def get_email_from_api(self) -> str:
        """通过 API 创建邮箱地址"""
        print("   🔍 通过 22.do API 创建邮箱...")

        try:
            self._ensure_bearer_token()
            method, path = self._get_account_request()
            response = self._request(method, path, bearer_token=self.bearer_token)
            data = self._extract_response_data(response, "创建邮箱失败")

            email = self._pick_text(data, "email", "address")
            if not email:
                print("   ✗ API 响应中没有 email 字段")
                return None

            self.current_email = email
            self.current_inbox_time = max(0, int(time.time()) - 5)
            print(f"   ✓ 22.do 邮箱创建成功: {email}")
            return email
        except Exception as e:
            print(f"   ✗ 请求 22.do API 出错: {e}")
            return None

    def get_latest_email_from_page(self, cdp, session_id, email: str) -> dict:
        """22.do 不支持从网页获取邮件"""
        print("   ⚠️  22.do 不支持从网页获取邮件")
        print("   💡 请使用 get_latest_email_from_api() 方法")
        return None

    def get_latest_email_from_api(
        self,
        email_address: str,
        timeout: int = 120,
        check_interval: int = 3,
        filter_func: Optional[Callable[[Dict[str, str]], bool]] = None,
    ) -> dict:
        """轮询获取最新邮件内容"""
        email_address = (email_address or self.current_email).strip()
        if not email_address:
            print("   ✗ 邮箱地址为空，请先调用 get_email_from_api() 或传入有效邮箱")
            return None

        try:
            self._ensure_bearer_token()
        except Exception as e:
            print(f"   ✗ 认证失败: {e}")
            return None

        timeout = max(1, int(timeout or self.DEFAULT_POLL_TIMEOUT))
        check_interval = max(1, int(check_interval or self.DEFAULT_CHECK_INTERVAL))
        deadline = time.time() + timeout
        since = self.current_inbox_time or max(0, int(time.time()) - 60)
        seen_ids: set[str] = set()
        attempt = 0

        print(f"\n📧 正在从 22.do API 获取最新邮件...")
        print(f"   📮 邮箱地址: {email_address}")
        print(f"   ⏳ 超时时间: {timeout}秒, 检查间隔: {check_interval}秒")

        while time.time() < deadline:
            attempt += 1
            try:
                print(f"   🔄 第 {attempt} 次尝试...")
                messages = self._list_messages(email_address, since)
                print(f"   ✓ 当前命中 {len(messages)} 封邮件")

                if not messages:
                    print(f"   ⏳ 暂无邮件，{check_interval}秒后重试...")
                    time.sleep(check_interval)
                    continue

                for message in messages:
                    identity = self._message_identity(message)
                    if identity and identity in seen_ids:
                        continue
                    if identity:
                        seen_ids.add(identity)

                    message_id = self._pick_text(message, "messageId", "id", "_id")
                    detail_message: Optional[Dict[str, Any]] = None
                    if message_id:
                        try:
                            detail_message = self._read_message(message_id)
                        except Exception as detail_error:
                            print(f"   ⚠️  获取邮件详情失败: {detail_error}，将使用列表数据兜底")

                    normalized = self._normalize_message(detail_message, fallback_message=message)
                    if not normalized:
                        continue

                    if filter_func and not filter_func(normalized):
                        continue

                    print(
                        "   ✓ 收到邮件: "
                        f"{normalized.get('from') or '(未知发件人)'} - "
                        f"{normalized.get('subject') or '(无主题)'}"
                    )
                    return normalized
            except Exception as e:
                print(f"   ⚠️  22.do 拉取邮件失败: {e}")

            if time.time() < deadline:
                time.sleep(check_interval)

        print(f"   ✗ 获取邮件失败（已超时 {timeout} 秒）")
        return None
