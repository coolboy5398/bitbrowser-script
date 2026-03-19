#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ChatGPT临时邮箱服务提供者

基于 https://mail.chatgpt.org.uk/api 的公开 API 实现
"""

import json
import time
from typing import Any, Dict, List, Optional
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode
from urllib.request import ProxyHandler, Request, build_opener, urlopen

from .email_provider import EmailProvider


class ChatGPTMailProvider(EmailProvider):
    """ChatGPT临时邮箱服务提供者

    基于 https://mail.chatgpt.org.uk/api 的公开 API 实现。
    支持通过 API 生成邮箱、轮询邮箱列表并读取单封邮件详情。
    """

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
        api_key: str = "sk-57pxXsUy7hhJ",
        proxies: Any = None,
        timeout: int = 15,
        prefix: str = None,
        domain: str = None,
    ):
        """初始化 ChatGPTMail 服务

        Args:
            api_key: API 密钥，不提供时默认使用官方公开测试密钥 `gpt-test`
            proxies: 代理配置，兼容 [`EmailProviderFactory.create()`](providers/email_provider_factory.py:63)
            timeout: HTTP 请求超时时间（秒）
            prefix: 可选的邮箱前缀，提供后将改用 POST 方式生成邮箱
            domain: 可选的邮箱域名，提供后将改用 POST 方式生成邮箱
        """
        self.base_url = "https://mail.chatgpt.org.uk"
        self.api_base_url = f"{self.base_url}/api"
        self.api_url = f"{self.api_base_url}/emails"
        self.api_key = (api_key or "gpt-test").strip()
        self.proxies = proxies
        self.timeout = max(1, int(timeout or self.DEFAULT_TIMEOUT))
        self.prefix = (prefix or "").strip()
        self.domain = (domain or "").strip()
        self.current_email = ""

    def needs_browser_page(self) -> bool:
        """ChatGPT邮箱不需要打开浏览器页面"""
        return False

    def get_page_url(self) -> str:
        """获取邮箱页面URL"""
        return f"{self.base_url}/"

    def get_domain_patterns(self) -> list:
        """获取域名匹配模式"""
        return ["chatgpt.org.uk"]

    def _build_headers(self, *, use_json: bool = False) -> Dict[str, str]:
        """构建 API 请求头"""
        headers = {
            "Accept": "application/json",
            "User-Agent": self.USER_AGENT,
        }
        if self.api_key:
            headers["X-API-Key"] = self.api_key
        if use_json:
            headers["Content-Type"] = "application/json; charset=utf-8"
        return headers

    def _read_response_json(self, response, url: str) -> Dict[str, Any]:
        """读取并解析 JSON 响应"""
        raw_text = response.read().decode("utf-8", errors="replace")
        if not raw_text:
            return {}

        try:
            data = json.loads(raw_text)
            return data if isinstance(data, dict) else {"data": data}
        except json.JSONDecodeError as exc:
            preview = raw_text[:200].replace("\n", " ")
            raise ValueError(f"API返回了无效JSON: {url} -> {preview}") from exc

    def _request(
        self,
        path: str,
        *,
        method: str = "GET",
        query: Optional[Dict[str, Any]] = None,
        payload: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """发送 API 请求并返回 JSON 数据"""
        url = f"{self.api_base_url}{path}"

        clean_query = {}
        for key, value in (query or {}).items():
            if value is None:
                continue
            text = str(value).strip()
            if text:
                clean_query[key] = text
        if clean_query:
            url = f"{url}?{urlencode(clean_query)}"

        body = None
        if payload is not None:
            body = json.dumps(payload).encode("utf-8")

        req = Request(url, data=body, method=method)
        for header_name, header_value in self._build_headers(use_json=payload is not None).items():
            req.add_header(header_name, header_value)

        if self.proxies:
            opener = build_opener(ProxyHandler(self.proxies))
            response = opener.open(req, timeout=self.timeout)
        else:
            response = urlopen(req, timeout=self.timeout)

        with response as response_obj:
            return self._read_response_json(response_obj, url)

    def _extract_error_message(self, data: Any, fallback: str = "请求失败") -> str:
        """从 API 响应中提取错误信息"""
        if isinstance(data, dict):
            error = data.get("error")
            if isinstance(error, str) and error.strip():
                return error.strip()
            if isinstance(error, dict):
                for key in ("message", "error", "detail"):
                    value = error.get(key)
                    if isinstance(value, str) and value.strip():
                        return value.strip()
        return fallback

    def _extract_response_data(self, data: Dict[str, Any]) -> Any:
        """提取响应中的 data 字段"""
        if isinstance(data, dict):
            return data.get("data")
        return None

    def _as_text(self, value: Any) -> str:
        """将任意值安全转换为字符串"""
        if value is None:
            return ""
        if isinstance(value, str):
            return value.strip()
        if isinstance(value, (int, float, bool)):
            return str(value)
        return ""

    def _pick_text(self, source: Any, *keys: str) -> str:
        """从字典中按顺序获取非空文本字段"""
        if not isinstance(source, dict):
            return ""

        for key in keys:
            if key not in source:
                continue
            text = self._as_text(source.get(key))
            if text:
                return text
        return ""

    def _normalize_sender(self, raw_sender: Any) -> str:
        """将不同格式的发件人字段标准化为字符串"""
        if isinstance(raw_sender, str):
            return raw_sender.strip()

        if isinstance(raw_sender, list):
            for item in raw_sender:
                sender = self._normalize_sender(item)
                if sender:
                    return sender
            return ""

        if isinstance(raw_sender, dict):
            value = raw_sender.get("value")
            sender = self._normalize_sender(value)
            if sender:
                return sender

            address = self._pick_text(raw_sender, "address", "email")
            name = self._pick_text(raw_sender, "name", "display_name", "displayName")
            if name and address:
                return f"{name} <{address}>"
            return address or name

        return ""

    def _coerce_message_list(self, data: Dict[str, Any]) -> List[Dict[str, Any]]:
        """从列表接口响应中提取邮件列表"""
        payload = self._extract_response_data(data)

        if isinstance(payload, list):
            return [item for item in payload if isinstance(item, dict)]

        if isinstance(payload, dict):
            for key in ("emails", "messages", "items", "results"):
                value = payload.get(key)
                if isinstance(value, list):
                    return [item for item in value if isinstance(item, dict)]

            if any(
                key in payload
                for key in (
                    "id",
                    "_id",
                    "email_id",
                    "message_id",
                    "subject",
                    "from",
                    "from_address",
                )
            ):
                return [payload]

        return []

    def _coerce_message_detail(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """从详情接口响应中提取邮件详情字典"""
        payload = self._extract_response_data(data)

        if isinstance(payload, dict):
            for key in ("email", "message", "item"):
                nested = payload.get(key)
                if isinstance(nested, dict):
                    return nested
            return payload

        if isinstance(payload, list) and payload and isinstance(payload[0], dict):
            return payload[0]

        return {}

    def _extract_message_id(self, message: Dict[str, Any]) -> str:
        """提取邮件 ID"""
        return self._pick_text(message, "id", "_id", "email_id", "message_id")

    def _normalize_message(
        self,
        primary_message: Optional[Dict[str, Any]],
        fallback_message: Optional[Dict[str, Any]] = None,
    ) -> Optional[Dict[str, str]]:
        """将邮件数据标准化为统一结构"""
        sources = [source for source in (primary_message, fallback_message) if isinstance(source, dict)]
        if not sources:
            return None

        subject = ""
        content = ""
        html = ""
        from_addr = ""

        for source in sources:
            if not subject:
                subject = self._pick_text(source, "subject", "title")

            if not content:
                content = self._pick_text(
                    source,
                    "content",
                    "text",
                    "text_content",
                    "plain_text",
                    "plainText",
                    "body_text",
                    "bodyText",
                )

            if not html:
                html = self._pick_text(
                    source,
                    "html_content",
                    "html",
                    "html_body",
                    "htmlBody",
                    "body_html",
                    "bodyHtml",
                )

            if not from_addr:
                from_addr = self._pick_text(
                    source,
                    "from_address",
                    "fromAddress",
                    "sender_address",
                    "senderAddress",
                )
                if not from_addr:
                    from_addr = self._normalize_sender(source.get("from"))
                if not from_addr:
                    from_addr = self._normalize_sender(source.get("sender"))

        normalized = {
            "subject": subject,
            "content": content,
            "html": html,
            "from": from_addr,
        }
        if any(normalized.values()):
            return normalized
        return None

    def _sleep_for_retry(self, seconds: int) -> None:
        """轮询等待"""
        time.sleep(max(1, int(seconds or self.DEFAULT_CHECK_INTERVAL)))

    def get_email_from_page(self, cdp, session_id) -> str:
        """ChatGPT Mail 不再使用网页提取流程"""
        print("   ⚠️  ChatGPT Mail 已改为纯 API 模式，不支持从网页提取邮箱")
        print("   💡 请使用 get_email_from_api() 方法")
        return None

    def get_email_from_api(self) -> str:
        """通过 API 生成邮箱地址"""
        print("   🔍 通过 ChatGPT Mail API 生成邮箱...")

        try:
            payload = {}
            if self.prefix:
                payload["prefix"] = self.prefix
            if self.domain:
                payload["domain"] = self.domain

            response = self._request(
                "/generate-email",
                method="POST" if payload else "GET",
                payload=payload or None,
            )

            if not response.get("success"):
                error_msg = self._extract_error_message(response, "生成邮箱失败")
                print(f"   ✗ {error_msg}")
                return None

            data = self._extract_response_data(response)
            email = self._pick_text(data, "email", "address")
            if not email:
                email = self._pick_text(response, "email", "address")

            if not email:
                print("   ✗ API响应中没有 email 字段")
                return None

            self.current_email = email
            print(f"   ✓ 生成邮箱成功: {email}")
            return email

        except HTTPError as e:
            error_body = e.read().decode("utf-8", errors="replace") if e.fp else ""
            print(f"   ✗ HTTP错误 {e.code}: {error_body or e.reason}")
            return None
        except URLError as e:
            print(f"   ✗ 网络错误: {e.reason}")
            return None
        except Exception as e:
            print(f"   ✗ 生成邮箱失败: {type(e).__name__}: {e}")
            return None

    def get_latest_email_from_page(self, cdp, session_id, email: str) -> dict:
        """ChatGPT Mail 不再使用网页提取流程"""
        print("   ⚠️  ChatGPT Mail 已改为纯 API 模式，不支持从网页获取邮件")
        print("   💡 请使用 get_latest_email_from_api() 方法")
        return None

    def get_latest_email_from_api(
        self,
        email_address: str,
        timeout: int = 120,
        check_interval: int = 3,
    ) -> dict:
        """通过 API 轮询获取最新邮件内容"""
        email_address = (email_address or self.current_email).strip()
        if not email_address:
            print("   ✗ 邮箱地址为空，请先调用 get_email_from_api() 或传入有效邮箱")
            return None

        timeout = max(1, int(timeout or self.DEFAULT_POLL_TIMEOUT))
        check_interval = max(1, int(check_interval or self.DEFAULT_CHECK_INTERVAL))
        deadline = time.time() + timeout
        attempt = 0

        print("\n📧 正在从 ChatGPT Mail API 获取最新邮件...")
        print(f"   📮 邮箱地址: {email_address}")
        print(f"   ⏳ 超时时间: {timeout}秒, 检查间隔: {check_interval}秒")

        while time.time() < deadline:
            attempt += 1
            try:
                print(f"   🔄 第 {attempt} 次尝试...")
                list_response = self._request("/emails", query={"email": email_address})

                if not list_response.get("success"):
                    error_msg = self._extract_error_message(list_response, "获取邮件列表失败")
                    print(f"   ⚠️  API错误: {error_msg}")
                    self._sleep_for_retry(check_interval)
                    continue

                messages = self._coerce_message_list(list_response)
                print(f"   ✓ 当前邮箱共有 {len(messages)} 封邮件")

                if not messages:
                    print(f"   ⏳ 暂无邮件，{check_interval}秒后重试...")
                    self._sleep_for_retry(check_interval)
                    continue

                latest_message = messages[0]
                message_id = self._extract_message_id(latest_message)
                detail_message = None

                if message_id:
                    try:
                        detail_response = self._request(f"/email/{quote(message_id, safe='')}")
                        if detail_response.get("success"):
                            detail_message = self._coerce_message_detail(detail_response)
                        else:
                            error_msg = self._extract_error_message(detail_response, "获取邮件详情失败")
                            print(f"   ⚠️  {error_msg}，将使用列表数据兜底")
                    except Exception as detail_error:
                        print(f"   ⚠️  获取邮件详情失败: {detail_error}，将使用列表数据兜底")
                else:
                    print("   ⚠️  邮件列表中缺少邮件ID，将直接使用列表数据")

                normalized = self._normalize_message(detail_message, fallback_message=latest_message)
                if not normalized:
                    print(f"   ⚠️  邮件存在但无法解析，{check_interval}秒后重试...")
                    self._sleep_for_retry(check_interval)
                    continue

                print(
                    "   ✓ 收到邮件: "
                    f"{normalized.get('from') or '(未知发件人)'} - "
                    f"{normalized.get('subject') or '(无主题)'}"
                )
                return normalized

            except HTTPError as e:
                error_body = e.read().decode("utf-8", errors="replace") if e.fp else ""
                print(f"   ✗ HTTP错误 {e.code}: {error_body or e.reason}")
            except URLError as e:
                print(f"   ✗ 网络错误: {e.reason}")
            except Exception as e:
                print(f"   ✗ 获取邮件出错: {type(e).__name__}: {e}")

            if time.time() < deadline:
                self._sleep_for_retry(check_interval)

        print(f"   ✗ 获取邮件失败（已超时 {timeout} 秒）")
        return None

    # ==================== 验证码解析 ====================
    # 使用基类的实现，无需重写
