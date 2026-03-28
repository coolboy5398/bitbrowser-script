import json
import re
import time
import random
import secrets
import hashlib
import base64
import argparse
import os
import urllib.parse
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

from curl_cffi import requests

from account_db import (
    delete_account_by_email,
    init_account_db,
    is_email_suffix_disabled,
    upsert_account_record,
    upsert_disabled_email_suffix,
)
from providers import EmailProviderFactory

AUTH_URL = "https://auth.openai.com/oauth/authorize"
TOKEN_URL = "https://auth.openai.com/oauth/token"
CLIENT_ID = "app_EMoamEEZ73f0CkXaXp7hrann"
CHATGPT_BASE = "https://chatgpt.com"
AUTH_BASE = "https://auth.openai.com"

DEFAULT_REDIRECT_URI = "http://localhost:1455/auth/callback"
DEFAULT_SCOPE = "openid email profile offline_access"
DEFAULT_MGMT_URL = "http://127.0.0.1:8045"
DEFAULT_PRECHECK_TARGET_TYPE = "codex"
DEFAULT_PRECHECK_UA = "codex_cli_rs/0.76.0 (Debian 13.0.0; x86_64) WindowsTerminal"
DEFAULT_PRECHECK_TIMEOUT = 12
DEFAULT_PRECHECK_WORKERS = 120
DEFAULT_PRECHECK_RETRIES = 1
DEFAULT_PRECHECK_OUTPUT_401 = "invalid_codex_accounts.json"
DEFAULT_TARGET_ACCOUNT_COUNT = 120
DEFAULT_EMAIL_PROVIDERS = ["tempmail-lol","chatgpt","chat-tempmail","do22","duckmail","mailtm"] #chatgpt,tempmail-lol,chat-tempmail,do22,domain-imap,duckmail,mailtm
PROVIDER_SELECTION_STATE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "openai_register_v2_provider_state.json")
BEIJING_TZ = timezone(timedelta(hours=8))


def beijing_now() -> datetime:
    return datetime.now(BEIJING_TZ)


def format_beijing_rfc3339(dt: datetime) -> str:
    return dt.astimezone(BEIJING_TZ).strftime("%Y-%m-%d %H:%M:%S")


def format_beijing_from_epoch(epoch_seconds: int) -> str:
    return datetime.fromtimestamp(epoch_seconds, tz=BEIJING_TZ).strftime("%Y-%m-%d %H:%M:%S")


def extract_email_suffix(email: str) -> str:
    email_text = str(email or "").strip().lower()
    if "@" not in email_text:
        return ""
    return "@" + email_text.rsplit("@", 1)[1]


def is_unsupported_email_error(error: Any) -> bool:
    error_text = str(error or "").strip().lower()
    if not error_text:
        return False
    return (
        "unsupported_email" in error_text
        or "unsupported email" in error_text
        or "the email you provided is not supported" in error_text
    )


def disable_email_suffix_for_unsupported_email(
    *,
    subscription_type: str,
    email: str,
    error: Any,
) -> bool:
    if not is_unsupported_email_error(error):
        return False

    email_suffix = extract_email_suffix(email)
    if not email_suffix:
        return False

    try:
        upsert_disabled_email_suffix(
            subscription_type=subscription_type,
            email_suffix=email_suffix,
            enabled=True,
        )
        print(
            f"[*] 已自动禁用邮箱后缀: {email_suffix} "
            f"(subscription_type={subscription_type}, reason=unsupported_email)"
        )
        return True
    except Exception as save_error:
        print(f"[Warning] 保存禁用邮箱后缀失败: {email_suffix}, error={save_error}")
        return False


def normalize_email_providers(email_providers: Optional[List[str]] = None) -> List[str]:
    provider_names = [
        str(name).strip()
        for name in (email_providers or DEFAULT_EMAIL_PROVIDERS)
        if str(name).strip()
    ]
    return provider_names or DEFAULT_EMAIL_PROVIDERS.copy()


def load_last_selected_provider() -> str:
    try:
        with open(PROVIDER_SELECTION_STATE_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict):
            return str(data.get("selected_provider") or "").strip()
    except FileNotFoundError:
        return ""
    except Exception as e:
        print(f"[Warning] 读取上次 provider 选择失败，将使用默认值: {e}")
    return ""


def save_last_selected_provider(provider_name: str) -> None:
    try:
        with open(PROVIDER_SELECTION_STATE_FILE, "w", encoding="utf-8") as f:
            json.dump({"selected_provider": str(provider_name or "").strip()}, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"[Warning] 保存 provider 选择失败，不影响主流程: {e}")


def choose_email_provider_interactively(provider_names: List[str]) -> str:
    normalized = normalize_email_providers(provider_names)
    last_selected_provider = load_last_selected_provider()
    default_provider = last_selected_provider if last_selected_provider in normalized else normalized[0]

    print("[*] 请选择本次使用的邮箱服务 provider:")
    for index, provider_name in enumerate(normalized, start=1):
        default_mark = " (默认)" if provider_name == default_provider else ""
        print(f"    {index}. {provider_name}{default_mark}")

    while True:
        try:
            default_index = normalized.index(default_provider) + 1
            selected = input(f"请输入序号并回车（默认 {default_index} = {default_provider}）: ").strip()
        except EOFError:
            selected = ""

        if not selected:
            print(f"[*] 未输入，使用默认邮箱服务: {default_provider}")
            save_last_selected_provider(default_provider)
            return default_provider

        if selected.isdigit():
            selected_index = int(selected)
            if 1 <= selected_index <= len(normalized):
                chosen_provider = normalized[selected_index - 1]
                print(f"[*] 已选择邮箱服务: {chosen_provider}")
                save_last_selected_provider(chosen_provider)
                return chosen_provider

        print("[Warning] 输入无效，请输入列表中的序号。")


def _b64url_no_pad(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _random_state() -> str:
    return _b64url_no_pad(secrets.token_bytes(32))


def _sha256_b64url_no_pad(s: str) -> str:
    return _b64url_no_pad(hashlib.sha256(s.encode("ascii")).digest())


def _pkce_verifier() -> str:
    return secrets.token_urlsafe(64)


def _decode_jwt_segment(seg: str) -> Dict[str, Any]:
    raw = (seg or "").strip()
    if not raw:
        return {}
    pad = "=" * ((4 - (len(raw) % 4)) % 4)
    try:
        decoded = base64.urlsafe_b64decode((raw + pad).encode("ascii"))
        return json.loads(decoded.decode("utf-8"))
    except Exception:
        return {}


def _jwt_claims_no_verify(id_token: str) -> Dict[str, Any]:
    if not id_token or id_token.count(".") < 2:
        return {}
    return _decode_jwt_segment(id_token.split(".")[1])


def _to_int(v: Any) -> int:
    try:
        return int(v)
    except (TypeError, ValueError):
        return 0


def safe_json(resp: Any) -> Dict[str, Any]:
    try:
        data = resp.json()
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def safe_json_text(text: str) -> Dict[str, Any]:
    try:
        data = json.loads(text)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _clip_text(value: Any, limit: int = 240) -> str:
    text = str(value or "").replace("\r", "\\r").replace("\n", "\\n")
    if len(text) <= limit:
        return text
    return f"{text[:limit]}...(truncated)"


def _sanitize_url_for_log(url: str) -> str:
    raw = str(url or "").strip()
    if not raw:
        return ""
    try:
        parsed = urllib.parse.urlparse(raw)
    except Exception:
        return _clip_text(raw, 200)
    if not parsed.scheme or not parsed.netloc:
        return _clip_text(raw, 200)

    query = urllib.parse.parse_qs(parsed.query, keep_blank_values=True)
    safe_pairs: List[str] = []
    for key in sorted(query.keys()):
        value = query.get(key, [""])[-1]
        if key in {"client_id", "prompt", "screen_hint", "response_type"}:
            safe_pairs.append(f"{key}={_clip_text(value, 60)}")
        elif key in {"redirect_uri", "audience", "scope"}:
            safe_pairs.append(f"{key}={_clip_text(value, 120)}")
        else:
            safe_pairs.append(f"{key}=[redacted]")

    base = urllib.parse.urlunparse((parsed.scheme, parsed.netloc, parsed.path, "", "", ""))
    query_summary = "&".join(safe_pairs)
    return f"{base}?{query_summary}" if query_summary else base


def _response_history_for_log(resp: Any) -> List[Dict[str, Any]]:
    history: List[Dict[str, Any]] = []
    for item in getattr(resp, "history", []) or []:
        headers = getattr(item, "headers", {}) or {}
        location = headers.get("Location") or headers.get("location") or ""
        history.append(
            {
                "status_code": getattr(item, "status_code", None),
                "url": _sanitize_url_for_log(str(getattr(item, "url", "") or "")),
                "location": _sanitize_url_for_log(str(location or "")),
            }
        )
    return history


def _response_summary_for_log(resp: Any, body_limit: int = 280) -> Dict[str, Any]:
    headers = getattr(resp, "headers", {}) or {}
    header_map = {str(k).lower(): str(v) for k, v in headers.items()}
    return {
        "status_code": getattr(resp, "status_code", None),
        "url": _sanitize_url_for_log(str(getattr(resp, "url", "") or "")),
        "content_type": header_map.get("content-type", ""),
        "content_length": header_map.get("content-length", ""),
        "location": _sanitize_url_for_log(header_map.get("location", "")),
        "cf_ray": header_map.get("cf-ray", ""),
        "server": header_map.get("server", ""),
        "x_request_id": header_map.get("x-request-id", ""),
        "history": _response_history_for_log(resp),
        "body_excerpt": _clip_text(getattr(resp, "text", "") or "", body_limit),
    }


def _session_cookie_summary(session: Any) -> Dict[str, Any]:
    jar = getattr(getattr(session, "cookies", None), "jar", None)
    cookie_items = list(jar) if jar is not None else []
    names = sorted({str(getattr(c, "name", "") or "") for c in cookie_items if getattr(c, "name", "")})
    domains = sorted({str(getattr(c, "domain", "") or "") for c in cookie_items if getattr(c, "domain", "")})
    interesting = {
        name: name in names
        for name in [
            "oai-did",
            "oai-client-auth-session",
            "next-auth.csrf-token",
            "next-auth.callback-url",
            "cf_clearance",
            "__cf_bm",
        ]
    }
    return {
        "count": len(cookie_items),
        "names": names[:20],
        "domains": domains[:10],
        "interesting": interesting,
    }


def mgmt_headers(token: str) -> Dict[str, str]:
    return {"Authorization": f"Bearer {token}", "Accept": "application/json"}


def get_item_type(item: Dict[str, Any]) -> str:
    return str(item.get("type") or item.get("typo") or "").strip()


def fetch_auth_files(base_url: str, token: str, timeout: int) -> List[Dict[str, Any]]:
    resp = requests.get(
        f"{base_url.rstrip('/')}/v0/management/auth-files",
        headers=mgmt_headers(token),
        timeout=timeout,
    )
    if resp.status_code >= 400:
        raise RuntimeError(f"获取 auth-files 失败: HTTP {resp.status_code} {resp.text[:200]}")
    data = safe_json(resp)
    files = data.get("files")
    return files if isinstance(files, list) else []


def delete_auth_file(base_url: str, token: str, name: str, timeout: int) -> None:
    resp = requests.delete(
        f"{base_url.rstrip('/')}/v0/management/auth-files",
        params={"name": name},
        headers=mgmt_headers(token),
        timeout=timeout,
    )
    if resp.status_code >= 400:
        raise RuntimeError(f"DELETE {name} 失败: HTTP {resp.status_code} {resp.text[:200]}")


def count_matching_auth_files(
    base_url: str,
    token: str,
    timeout: int,
    target_type: str,
    provider: Optional[str],
) -> int:
    files = fetch_auth_files(base_url, token, timeout)
    target_type_lower = str(target_type or "").lower()
    provider_lower = str(provider or "").lower()
    count = 0
    for item in files:
        item_type = get_item_type(item).lower()
        item_provider = str(item.get("provider") or "").lower()
        if target_type_lower and item_type != target_type_lower:
            continue
        if provider_lower and item_provider != provider_lower:
            continue
        count += 1
    return count


def build_probe_payload(auth_index: str, user_agent: str, chatgpt_account_id: str = "") -> Dict[str, Any]:
    headers = {
        "Authorization": "Bearer $TOKEN$",
        "Content-Type": "application/json",
        "User-Agent": user_agent,
    }
    if chatgpt_account_id:
        headers["Chatgpt-Account-Id"] = chatgpt_account_id
    return {
        "authIndex": auth_index,
        "method": "GET",
        "url": "https://chatgpt.com/backend-api/wham/usage",
        "header": headers,
    }


def probe_auth_file_401(
    base_url: str,
    token: str,
    item: Dict[str, Any],
    user_agent: str,
    chatgpt_account_id: str,
    timeout: int,
    retries: int,
) -> Dict[str, Any]:
    auth_index = item.get("auth_index")
    result: Dict[str, Any] = {
        "name": item.get("name") or item.get("id"),
        "account": item.get("account") or item.get("email"),
        "auth_index": auth_index,
        "type": get_item_type(item),
        "provider": item.get("provider"),
        "status_code": None,
        "invalid_401": False,
        "error": None,
    }
    if not auth_index:
        result["error"] = "missing auth_index"
        return result

    payload = build_probe_payload(str(auth_index), user_agent, chatgpt_account_id)
    max_retries = max(0, int(retries or 0))
    for attempt in range(max_retries + 1):
        try:
            resp = requests.post(
                f"{base_url.rstrip('/')}/v0/management/api-call",
                headers={**mgmt_headers(token), "Content-Type": "application/json"},
                json=payload,
                timeout=timeout,
            )
            if resp.status_code >= 400:
                raise RuntimeError(f"http {resp.status_code}: {resp.text[:200]}")
            data = safe_json(resp) or safe_json_text(resp.text)
            status_code = data.get("status_code")
            result["status_code"] = status_code
            result["invalid_401"] = status_code == 401
            result["error"] = None
            return result
        except Exception as e:
            result["error"] = str(e)
            if attempt >= max_retries:
                return result
    return result


def run_preclean_probe_all(
    base_url: str,
    token: str,
    target_type: str,
    provider: Optional[str],
    workers: int,
    timeout: int,
    retries: int,
    user_agent: str,
    chatgpt_account_id: str,
) -> List[Dict[str, Any]]:
    files = fetch_auth_files(base_url, token, timeout)
    candidates: List[Dict[str, Any]] = []
    target_type_lower = str(target_type or "").lower()
    provider_lower = str(provider or "").lower()

    for item in files:
        item_type = get_item_type(item).lower()
        item_provider = str(item.get("provider") or "").lower()
        if target_type_lower and item_type != target_type_lower:
            continue
        if provider_lower and item_provider != provider_lower:
            continue
        candidates.append(item)

    print(f"[*] 管理端账号总数: {len(files)}")
    print(f"[*] 待检查401账号数: {len(candidates)}")
    if not candidates:
        return []

    max_workers = max(1, min(int(workers or 1), len(candidates)))
    results: List[Dict[str, Any]] = []
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = [
            executor.submit(
                probe_auth_file_401,
                base_url,
                token,
                item,
                user_agent,
                chatgpt_account_id,
                timeout,
                retries,
            )
            for item in candidates
        ]
        total = len(futures)
        for done, future in enumerate(as_completed(futures), start=1):
            results.append(future.result())
            if done == total:
                print(f"[*] 401检测进度: {done}/{total}")
    return results


def action_auto_check_401_and_delete(
    base_url: str,
    token: str,
    timeout: int,
    results: List[Dict[str, Any]],
    output_401: str,
) -> Dict[str, int]:
    invalid_401 = [r for r in results if r.get("invalid_401")]
    invalid_401.sort(key=lambda x: x.get("name") or "")

    if output_401:
        output_dir = os.path.dirname(output_401)
        if output_dir:
            os.makedirs(output_dir, exist_ok=True)
        with open(output_401, "w", encoding="utf-8") as f:
            json.dump(invalid_401, f, ensure_ascii=False, indent=2)
        print(f"[*] 已导出401账号列表: {output_401}")

    print(f"[*] 检测到401账号: {len(invalid_401)}")
    if not invalid_401:
        print("[*] 无需删除401账号。")
        return {"detected": 0, "deleted": 0, "failed": 0}

    ok = 0
    fail = 0
    local_deleted = 0
    for item in invalid_401:
        name = str(item.get("name") or "").strip()
        account_email = str(item.get("account") or "").strip()
        if not name:
            fail += 1
            continue
        try:
            delete_auth_file(base_url, token, name, timeout)
            ok += 1
            print(f"[*] 已删除401账号: {name}")
            if account_email:
                deleted_rows = delete_account_by_email(account_email)
                local_deleted += deleted_rows
                print(f"[*] 本地数据库同步删除: {account_email} ({deleted_rows})")
        except Exception as e:
            fail += 1
            print(f"[FAIL] 删除401账号 {name}: {e}")

    print(f"[*] 401账号删除完成: 成功 {ok}，失败 {fail}，本地删除 {local_deleted}")
    return {"detected": len(invalid_401), "deleted": ok, "failed": fail}


def preclean_401_and_delete(
    base_url: str,
    token: str,
    *,
    target_type: str = DEFAULT_PRECHECK_TARGET_TYPE,
    provider: Optional[str] = None,
    workers: int = DEFAULT_PRECHECK_WORKERS,
    timeout: int = DEFAULT_PRECHECK_TIMEOUT,
    retries: int = DEFAULT_PRECHECK_RETRIES,
    user_agent: str = DEFAULT_PRECHECK_UA,
    chatgpt_account_id: str = "",
    output_401: str = DEFAULT_PRECHECK_OUTPUT_401,
) -> Dict[str, int]:
    if not base_url or not token:
        print("[*] 跳过注册前401清理：未配置 CLIProxyAPI 管理接口或 Token")
        return {"detected": 0, "deleted": 0, "failed": 0}

    print("[*] 注册前开始检查并自动删除 401 账号...")
    try:
        results = run_preclean_probe_all(
            base_url=base_url,
            token=token,
            target_type=target_type,
            provider=provider,
            workers=workers,
            timeout=timeout,
            retries=retries,
            user_agent=user_agent,
            chatgpt_account_id=chatgpt_account_id,
        )
        return action_auto_check_401_and_delete(
            base_url=base_url,
            token=token,
            timeout=timeout,
            results=results,
            output_401=output_401,
        )
    except Exception as e:
        print(f"[Warning] 注册前401清理失败: {e}")
        return {"detected": 0, "deleted": 0, "failed": 0}


def _random_delay(low: float = 0.3, high: float = 1.0) -> None:
    time.sleep(random.uniform(low, high))


class SentinelTokenGenerator:
    MAX_ATTEMPTS = 500000
    ERROR_PREFIX = "wQ8Lk5FbGpA2NcR9dShT6gYjU7VxZ4D"

    def __init__(self, device_id: Optional[str] = None, user_agent: Optional[str] = None):
        self.device_id = device_id or str(uuid.uuid4())
        self.user_agent = user_agent or (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/145.0.0.0 Safari/537.36"
        )
        self.requirements_seed = str(random.random())
        self.sid = str(uuid.uuid4())

    @staticmethod
    def _fnv1a_32(text: str) -> str:
        h = 2166136261
        for ch in text:
            h ^= ord(ch)
            h = (h * 16777619) & 0xFFFFFFFF
        h ^= (h >> 16)
        h = (h * 2246822507) & 0xFFFFFFFF
        h ^= (h >> 13)
        h = (h * 3266489909) & 0xFFFFFFFF
        h ^= (h >> 16)
        h &= 0xFFFFFFFF
        return format(h, "08x")

    def _get_config(self) -> List[Any]:
        now_str = time.strftime(
            "%a %b %d %Y %H:%M:%S GMT+0000 (Coordinated Universal Time)",
            time.gmtime(),
        )
        perf_now = random.uniform(1000, 50000)
        time_origin = time.time() * 1000 - perf_now
        nav_prop = random.choice([
            "vendorSub", "productSub", "vendor", "maxTouchPoints",
            "scheduling", "userActivation", "doNotTrack", "geolocation",
            "connection", "plugins", "mimeTypes", "pdfViewerEnabled",
            "webkitTemporaryStorage", "webkitPersistentStorage",
            "hardwareConcurrency", "cookieEnabled", "credentials",
            "mediaDevices", "permissions", "locks", "ink",
        ])
        nav_val = f"{nav_prop}-undefined"
        return [
            "1920x1080",
            now_str,
            4294705152,
            random.random(),
            self.user_agent,
            "https://sentinel.openai.com/sentinel/20260124ceb8/sdk.js",
            None,
            None,
            "en-US",
            "en-US,en",
            random.random(),
            nav_val,
            random.choice(["location", "implementation", "URL", "documentURI", "compatMode"]),
            random.choice(["Object", "Function", "Array", "Number", "parseFloat", "undefined"]),
            perf_now,
            self.sid,
            "",
            random.choice([4, 8, 12, 16]),
            time_origin,
        ]

    @staticmethod
    def _base64_encode(data: Any) -> str:
        raw = json.dumps(data, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
        return base64.b64encode(raw).decode("ascii")

    def _run_check(self, start_time: float, seed: str, difficulty: str, config: List[Any], nonce: int) -> Optional[str]:
        config[3] = nonce
        config[9] = round((time.time() - start_time) * 1000)
        data = self._base64_encode(config)
        hash_hex = self._fnv1a_32(seed + data)
        diff_len = len(difficulty)
        if hash_hex[:diff_len] <= difficulty:
            return data + "~S"
        return None

    def generate_token(self, seed: Optional[str] = None, difficulty: Optional[str] = None) -> str:
        seed = seed if seed is not None else self.requirements_seed
        difficulty = str(difficulty or "0")
        start_time = time.time()
        config = self._get_config()
        for i in range(self.MAX_ATTEMPTS):
            result = self._run_check(start_time, seed, difficulty, config, i)
            if result:
                return "gAAAAAB" + result
        return "gAAAAAB" + self.ERROR_PREFIX + self._base64_encode(str(None))

    def generate_requirements_token(self) -> str:
        config = self._get_config()
        config[3] = 1
        config[9] = round(random.uniform(5, 50))
        data = self._base64_encode(config)
        return "gAAAAAC" + data


def fetch_sentinel_challenge(
    session: Any,
    device_id: str,
    *,
    flow: str = "authorize_continue",
    user_agent: Optional[str] = None,
    sec_ch_ua: Optional[str] = None,
    impersonate: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    generator = SentinelTokenGenerator(device_id=device_id, user_agent=user_agent)
    req_body = {
        "p": generator.generate_requirements_token(),
        "id": device_id,
        "flow": flow,
    }
    headers = {
        "Content-Type": "text/plain;charset=UTF-8",
        "Referer": "https://sentinel.openai.com/backend-api/sentinel/frame.html",
        "Origin": "https://sentinel.openai.com",
        "User-Agent": user_agent or "Mozilla/5.0",
        "sec-ch-ua": sec_ch_ua or '"Not:A-Brand";v="99", "Google Chrome";v="145", "Chromium";v="145"',
        "sec-ch-ua-mobile": "?0",
        "sec-ch-ua-platform": '"Windows"',
    }
    kwargs: Dict[str, Any] = {
        "data": json.dumps(req_body),
        "headers": headers,
        "timeout": 20,
    }
    if impersonate:
        kwargs["impersonate"] = impersonate
    try:
        resp = session.post("https://sentinel.openai.com/backend-api/sentinel/req", **kwargs)
    except Exception:
        return None
    if resp.status_code != 200:
        return None
    try:
        data = resp.json()
        return data if isinstance(data, dict) else None
    except Exception:
        return None


def build_sentinel_token(
    session: Any,
    device_id: str,
    *,
    flow: str = "authorize_continue",
    user_agent: Optional[str] = None,
    sec_ch_ua: Optional[str] = None,
    impersonate: Optional[str] = None,
) -> Optional[str]:
    challenge = fetch_sentinel_challenge(
        session,
        device_id,
        flow=flow,
        user_agent=user_agent,
        sec_ch_ua=sec_ch_ua,
        impersonate=impersonate,
    )
    if not challenge:
        return None
    c_value = str(challenge.get("token") or "").strip()
    if not c_value:
        return None
    pow_data = challenge.get("proofofwork") or {}
    generator = SentinelTokenGenerator(device_id=device_id, user_agent=user_agent)
    if isinstance(pow_data, dict) and pow_data.get("required") and pow_data.get("seed"):
        p_value = generator.generate_token(
            seed=str(pow_data.get("seed") or ""),
            difficulty=str(pow_data.get("difficulty") or "0"),
        )
    else:
        p_value = generator.generate_requirements_token()
    return json.dumps(
        {
            "p": p_value,
            "t": "",
            "c": c_value,
            "id": device_id,
            "flow": flow,
        },
        separators=(",", ":"),
    )


def _make_trace_headers() -> Dict[str, str]:
    trace_id = random.randint(10**17, 10**18 - 1)
    parent_id = random.randint(10**17, 10**18 - 1)
    tp = f"00-{uuid.uuid4().hex}-{format(parent_id, '016x')}-01"
    return {
        "traceparent": tp,
        "tracestate": "dd=s:1;o:rum",
        "x-datadog-origin": "rum",
        "x-datadog-sampling-priority": "1",
        "x-datadog-trace-id": str(trace_id),
        "x-datadog-parent-id": str(parent_id),
    }


def _extract_code_from_url(url: str) -> Optional[str]:
    if not url or "code=" not in url:
        return None
    try:
        return urllib.parse.parse_qs(urllib.parse.urlparse(url).query).get("code", [None])[0]
    except Exception:
        return None


def _extract_state_from_url(url: str) -> Optional[str]:
    if not url or "state=" not in url:
        return None
    try:
        return urllib.parse.parse_qs(urllib.parse.urlparse(url).query).get("state", [None])[0]
    except Exception:
        return None


def _extract_callback_url_from_exception(exc: Exception) -> Optional[str]:
    try:
        msg = str(exc)
    except Exception:
        return None
    match = re.search(r'(https?://localhost[^\s\'\"]+)', msg)
    if match:
        return match.group(1)
    return None


def _append_code_state_to_url(url: str, code: str, state: str) -> str:
    candidate = (url or "").strip() or AUTH_BASE
    if not candidate.startswith("http"):
        candidate = f"{AUTH_BASE}{candidate if candidate.startswith('/') else '/'}"
    parsed = urllib.parse.urlparse(candidate)
    query = urllib.parse.parse_qs(parsed.query, keep_blank_values=True)
    if code:
        query["code"] = [code]
    if state:
        query["state"] = [state]
    rebuilt = urllib.parse.urlencode({k: v[-1] if isinstance(v, list) and v else v for k, v in query.items()})
    return urllib.parse.urlunparse(parsed._replace(query=rebuilt))


def _url_has_oauth_code(url: str) -> bool:
    return bool(_extract_code_from_url(url))


@dataclass(frozen=True)
class OAuthStart:
    auth_url: str
    state: str
    code_verifier: str
    redirect_uri: str


def generate_oauth_url(*, redirect_uri: str = DEFAULT_REDIRECT_URI, scope: str = DEFAULT_SCOPE) -> OAuthStart:
    state = _random_state()
    code_verifier = _pkce_verifier()
    code_challenge = _sha256_b64url_no_pad(code_verifier)
    params = {
        "client_id": CLIENT_ID,
        "response_type": "code",
        "redirect_uri": redirect_uri,
        "scope": scope,
        "state": state,
        "code_challenge": code_challenge,
        "code_challenge_method": "S256",
        "prompt": "login",
        "id_token_add_organizations": "true",
        "codex_cli_simplified_flow": "true",
    }
    auth_url = f"{AUTH_URL}?{urllib.parse.urlencode(params)}"
    return OAuthStart(
        auth_url=auth_url,
        state=state,
        code_verifier=code_verifier,
        redirect_uri=redirect_uri,
    )


def exchange_code_for_token(
    *,
    code: str,
    expected_state: str,
    callback_url: str,
    code_verifier: str,
    redirect_uri: str,
    proxies: Any = None,
    timeout: int = 30,
) -> str:
    got_state = _extract_state_from_url(callback_url)
    if expected_state and got_state != expected_state:
        raise ValueError("state mismatch")

    resp = requests.post(
        TOKEN_URL,
        data={
            "grant_type": "authorization_code",
            "client_id": CLIENT_ID,
            "code": code,
            "redirect_uri": redirect_uri,
            "code_verifier": code_verifier,
        },
        headers={
            "Content-Type": "application/x-www-form-urlencoded",
            "Accept": "application/json",
        },
        proxies=proxies,
        impersonate="chrome",
        timeout=timeout,
    )
    if resp.status_code != 200:
        raise RuntimeError(f"token exchange failed: {resp.status_code}: {resp.text}")

    token_resp = resp.json()
    access_token = (token_resp.get("access_token") or "").strip()
    refresh_token = (token_resp.get("refresh_token") or "").strip()
    id_token = (token_resp.get("id_token") or "").strip()
    expires_in = _to_int(token_resp.get("expires_in"))

    claims = _jwt_claims_no_verify(id_token)
    email = str(claims.get("email") or "").strip()
    auth_claims = claims.get("https://api.openai.com/auth") or {}
    account_id = str(auth_claims.get("chatgpt_account_id") or "").strip()

    now = int(time.time())
    expired_rfc3339 = format_beijing_from_epoch(now + max(expires_in, 0))
    now_rfc3339 = format_beijing_from_epoch(now)

    config = {
        "id_token": id_token,
        "access_token": access_token,
        "refresh_token": refresh_token,
        "account_id": account_id,
        "last_refresh": now_rfc3339,
        "email": email,
        "type": "codex",
        "expired": expired_rfc3339,
    }
    return json.dumps(config, ensure_ascii=False, separators=(",", ":"))


class HybridOpenAIRegister:
    def __init__(self, proxy: Optional[str] = None):
        self.proxy = proxy
        self.proxies: Any = None
        if proxy:
            self.proxies = {"http": proxy, "https": proxy}

        self.session = requests.Session(proxies=self.proxies, impersonate="chrome")
        self.device_id = str(uuid.uuid4())
        self.auth_session_logging_id = str(uuid.uuid4())
        self.ua = (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/131.0.0.0 Safari/537.36"
        )
        self.session.headers.update({
            "User-Agent": self.ua,
            "Accept-Language": random.choice([
                "en-US,en;q=0.9",
                "en-US,en;q=0.9,zh-CN;q=0.8",
                "en,en-US;q=0.9",
            ]),
            "sec-ch-ua": '"Google Chrome";v="131", "Chromium";v="131", "Not_A Brand";v="24"',
            "sec-ch-ua-mobile": "?0",
            "sec-ch-ua-platform": '"Windows"',
        })
        self.session.cookies.set("oai-did", self.device_id, domain="chatgpt.com")
        self.session.cookies.set("oai-did", self.device_id, domain="auth.openai.com")
        self.session.cookies.set("oai-did", self.device_id, domain=".auth.openai.com")
        self.oauth = generate_oauth_url()
        self._callback_url: Optional[str] = None

    def _build_authorize_continue_sentinel(self) -> Optional[str]:
        token = build_sentinel_token(
            self.session,
            self.device_id,
            flow="authorize_continue",
            user_agent=self.ua,
            sec_ch_ua='"Google Chrome";v="131", "Chromium";v="131", "Not_A Brand";v="24"',
            impersonate="chrome",
        )
        if not token:
            print("[Warning] create_account sentinel 缺少 token")
            return None
        return token

    def check_location(self) -> bool:
        try:
            trace = self.session.get("https://cloudflare.com/cdn-cgi/trace", timeout=10)
            trace_text = trace.text
            loc_re = re.search(r"^loc=(.+)$", trace_text, re.MULTILINE)
            loc = loc_re.group(1) if loc_re else None
            print(f"[*] 当前 IP 所在地: {loc}")
            if loc in {"CN", "HK"}:
                raise RuntimeError("检查代理哦w - 所在地不支持")
            return True
        except Exception as e:
            print(f"[Error] 网络连接检查失败: {e}")
            return False

    def visit_homepage(self) -> None:
        url = f"{CHATGPT_BASE}/"
        r = self.session.get(
            url,
            headers={
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
                "Upgrade-Insecure-Requests": "1",
            },
            allow_redirects=True,
            timeout=20,
        )
        print(f"[*] 访问首页状态: {r.status_code}")
        if r.status_code != 200:
            raise RuntimeError(f"Visit homepage 被拦截 ({r.status_code})")

    def get_csrf(self) -> str:
        url = f"{CHATGPT_BASE}/api/auth/csrf"
        r = self.session.get(url, headers={"Accept": "application/json", "Referer": f"{CHATGPT_BASE}/"}, timeout=20)
        data = safe_json(r)
        token = data.get("csrfToken", "")
        print(f"[*] 获取 CSRF 状态: {r.status_code}")
        if not token:
            raise RuntimeError("Failed to get CSRF token")
        return token

    def signin(self, email: str, csrf: str) -> str:
        url = f"{CHATGPT_BASE}/api/auth/signin/openai"
        params = {
            "prompt": "login",
            "ext-oai-did": self.device_id,
            "auth_session_logging_id": self.auth_session_logging_id,
            "screen_hint": "login_or_signup",
            "login_hint": email,
        }
        form_data = {"callbackUrl": f"{CHATGPT_BASE}/", "csrfToken": csrf, "json": "true"}
        r = self.session.post(
            url,
            params=params,
            data=form_data,
            headers={
                "Content-Type": "application/x-www-form-urlencoded",
                "Accept": "application/json",
                "Referer": f"{CHATGPT_BASE}/",
                "Origin": CHATGPT_BASE,
            },
            timeout=20,
        )
        data = safe_json(r)
        authorize_url = data.get("url", "")
        print(f"[*] signin/openai 状态: {r.status_code}")
        if authorize_url:
            print(f"[*] signin/openai authorize_url: {_sanitize_url_for_log(authorize_url)}")
        else:
            print(f"[Debug] signin/openai 响应摘要: {json.dumps(_response_summary_for_log(r), ensure_ascii=False)}")
            raise RuntimeError("Failed to get authorize URL")
        return authorize_url

    def authorize(self, url: str) -> str:
        print(f"[*] authorize 请求: {_sanitize_url_for_log(url)}")
        r = self.session.get(
            url,
            headers={
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Referer": f"{CHATGPT_BASE}/",
                "Upgrade-Insecure-Requests": "1",
            },
            allow_redirects=True,
            timeout=30,
        )
        final_url = str(r.url)
        print(f"[*] authorize 状态: {r.status_code} -> {_sanitize_url_for_log(final_url)}")
        history = _response_history_for_log(r)
        if history:
            print(f"[*] authorize 跳转链: {json.dumps(history, ensure_ascii=False)}")
        if r.status_code >= 400:
            print(f"[Debug] authorize 响应摘要: {json.dumps(_response_summary_for_log(r), ensure_ascii=False)}")
            print(f"[Debug] authorize 会话 Cookie: {json.dumps(_session_cookie_summary(self.session), ensure_ascii=False)}")
            raise RuntimeError(f"Authorize 被拦截 ({r.status_code})")
        return final_url

    def register(self, email: str, password: str) -> Tuple[int, Dict[str, Any]]:
        url = f"{AUTH_BASE}/api/accounts/user/register"
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
            "Referer": f"{AUTH_BASE}/create-account/password",
            "Origin": AUTH_BASE,
        }
        headers.update(_make_trace_headers())
        r = self.session.post(url, json={"username": email, "password": password}, headers=headers, timeout=20)
        data = safe_json(r) or {"text": r.text[:500]}
        print(f"[*] 提交注册状态: {r.status_code}")
        return r.status_code, data

    def send_otp(self) -> Tuple[int, Dict[str, Any]]:
        url = f"{AUTH_BASE}/api/accounts/email-otp/send"
        r = self.session.get(
            url,
            headers={
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Referer": f"{AUTH_BASE}/create-account/password",
                "Upgrade-Insecure-Requests": "1",
            },
            allow_redirects=True,
            timeout=20,
        )
        data = safe_json(r) or {"final_url": str(r.url), "status": r.status_code}
        print(f"[*] 发送 OTP 状态: {r.status_code}")
        return r.status_code, data

    def validate_otp(self, code: str) -> Tuple[int, Dict[str, Any]]:
        url = f"{AUTH_BASE}/api/accounts/email-otp/validate"
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
            "Referer": f"{AUTH_BASE}/email-verification",
            "Origin": AUTH_BASE,
        }
        headers.update(_make_trace_headers())
        r = self.session.post(url, json={"code": code}, headers=headers, timeout=20)
        data = safe_json(r) or {"text": r.text[:500]}
        print(f"[*] 校验 OTP 状态: {r.status_code}")
        return r.status_code, data

    def create_account(self, name: str, birthdate: str) -> Tuple[int, Dict[str, Any]]:
        url = f"{AUTH_BASE}/api/accounts/create_account"
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
            "Referer": f"{AUTH_BASE}/about-you",
            "Origin": AUTH_BASE,
        }
        headers.update(_make_trace_headers())
        sentinel_token = self._build_authorize_continue_sentinel()
        if sentinel_token:
            headers["openai-sentinel-token"] = sentinel_token
            print("[*] create_account 已附带 authorize_continue sentinel")
        r = self.session.post(url, json={"name": name, "birthdate": birthdate}, headers=headers, timeout=20)
        data = safe_json(r) or {"text": r.text[:500]}
        print(f"[*] 创建账户状态: {r.status_code}")
        if isinstance(data, dict):
            cb = data.get("continue_url") or data.get("url") or data.get("redirect_url")
            if cb:
                self._callback_url = cb
        return r.status_code, data

    def callback(self, url: Optional[str] = None) -> Tuple[Optional[int], Optional[Dict[str, Any]]]:
        if not url:
            url = self._callback_url
        if not url:
            print("[!] No callback URL, skipping.")
            return None, None
        r = self.session.get(
            url,
            headers={
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Upgrade-Insecure-Requests": "1",
            },
            allow_redirects=True,
            timeout=30,
        )
        final_url = str(r.url)
        print(f"[*] callback 状态: {r.status_code} -> {final_url}")
        self._callback_url = final_url
        return r.status_code, {"final_url": final_url}

    def _decode_oauth_session_cookie(self) -> Optional[Dict[str, Any]]:
        jar = getattr(self.session.cookies, "jar", None)
        cookie_items = list(jar) if jar is not None else []
        for c in cookie_items:
            name = getattr(c, "name", "") or ""
            if "oai-client-auth-session" not in name:
                continue
            raw_val = (getattr(c, "value", "") or "").strip()
            if not raw_val:
                continue
            candidates = [raw_val]
            try:
                from urllib.parse import unquote
                decoded = unquote(raw_val)
                if decoded != raw_val:
                    candidates.append(decoded)
            except Exception:
                pass
            for val in candidates:
                try:
                    if (val.startswith('"') and val.endswith('"')) or (val.startswith("'") and val.endswith("'")):
                        val = val[1:-1]
                    part = val.split(".")[0] if "." in val else val
                    pad = 4 - len(part) % 4
                    if pad != 4:
                        part += "=" * pad
                    raw = base64.urlsafe_b64decode(part)
                    data = json.loads(raw.decode("utf-8"))
                    if isinstance(data, dict):
                        return data
                except Exception:
                    continue
        return None

    def _oauth_follow_for_code(self, start_url: str, referer: Optional[str] = None, max_hops: int = 16) -> Tuple[Optional[str], str]:
        headers = {
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Upgrade-Insecure-Requests": "1",
            "User-Agent": self.ua,
        }
        if referer:
            headers["Referer"] = referer

        current_url = start_url
        last_url = start_url
        for hop in range(max_hops):
            try:
                resp = self.session.get(current_url, headers=headers, allow_redirects=False, timeout=30)
            except Exception as e:
                callback_url = _extract_callback_url_from_exception(e)
                if callback_url:
                    code = _extract_code_from_url(callback_url)
                    if code:
                        print(f"[*] OAuth follow[{hop + 1}] 命中 localhost 回调")
                        return code, callback_url
                print(f"[Warning] OAuth follow[{hop + 1}] 请求异常: {e}")
                return None, last_url

            last_url = str(resp.url)
            print(f"[*] OAuth follow[{hop + 1}] {resp.status_code} {last_url[:180]}")
            code = _extract_code_from_url(last_url)
            if code:
                return code, last_url

            if resp.status_code in (301, 302, 303, 307, 308):
                loc = resp.headers.get("Location", "")
                if not loc:
                    return None, last_url
                if loc.startswith("/"):
                    loc = f"{AUTH_BASE}{loc}"
                code = _extract_code_from_url(loc)
                if code:
                    return code, loc
                current_url = loc
                headers["Referer"] = last_url
                continue

            return None, last_url

        return None, last_url

    def _oauth_allow_redirect_extract_code(self, url: str, referer: Optional[str] = None) -> Optional[str]:
        headers = {
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Upgrade-Insecure-Requests": "1",
            "User-Agent": self.ua,
        }
        if referer:
            headers["Referer"] = referer
        try:
            resp = self.session.get(url, headers=headers, allow_redirects=True, timeout=30)
            final_url = str(resp.url)
            code = _extract_code_from_url(final_url)
            if code:
                print("[*] OAuth allow_redirect 命中最终 URL code")
                return code
            for r in getattr(resp, "history", []) or []:
                loc = r.headers.get("Location", "")
                code = _extract_code_from_url(loc)
                if code:
                    print("[*] OAuth allow_redirect 命中 history Location code")
                    return code
                code = _extract_code_from_url(str(r.url))
                if code:
                    print("[*] OAuth allow_redirect 命中 history URL code")
                    return code
        except Exception as e:
            maybe_localhost = re.search(r'(https?://localhost[^\s\'\"]+)', str(e))
            if maybe_localhost:
                code = _extract_code_from_url(maybe_localhost.group(1))
                if code:
                    print("[*] OAuth allow_redirect 从 localhost 异常提取 code")
                    return code
            print(f"[Warning] OAuth allow_redirect 异常: {e}")
        return None

    def _oauth_submit_workspace_and_org(self, consent_url: str) -> Optional[str]:
        session_data = self._decode_oauth_session_cookie()
        if not session_data:
            print("[Warning] 无法解码 oai-client-auth-session")
            return None

        workspaces = session_data.get("workspaces", [])
        if not workspaces:
            print("[Warning] session 中没有 workspace 信息")
            return None

        workspace_id = (workspaces[0] or {}).get("id")
        if not workspace_id:
            print("[Warning] workspace_id 为空")
            return None

        headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
            "Origin": AUTH_BASE,
            "Referer": consent_url,
            "User-Agent": self.ua,
            "oai-device-id": self.device_id,
        }
        headers.update(_make_trace_headers())

        resp = self.session.post(
            f"{AUTH_BASE}/api/accounts/workspace/select",
            json={"workspace_id": workspace_id},
            headers=headers,
            allow_redirects=False,
            timeout=30,
        )
        print(f"[*] OAuth workspace/select -> {resp.status_code}")

        if resp.status_code in (301, 302, 303, 307, 308):
            loc = resp.headers.get("Location", "")
            if loc.startswith("/"):
                loc = f"{AUTH_BASE}{loc}"
            code = _extract_code_from_url(loc)
            if code:
                return code
            code, _ = self._oauth_follow_for_code(loc, referer=consent_url)
            if not code:
                code = self._oauth_allow_redirect_extract_code(loc, referer=consent_url)
            return code

        if resp.status_code != 200:
            print(f"[Warning] OAuth workspace/select 失败: {resp.status_code}")
            return None

        ws_data = safe_json(resp)
        ws_next = str(ws_data.get("continue_url") or "")
        orgs = ((ws_data.get("data") or {}).get("orgs") or []) if isinstance(ws_data.get("data"), dict) else []
        org_id = None
        project_id = None
        if orgs:
            org_id = (orgs[0] or {}).get("id")
            projects = (orgs[0] or {}).get("projects", [])
            if projects:
                project_id = (projects[0] or {}).get("id")

        if org_id:
            org_body = {"org_id": org_id}
            if project_id:
                org_body["project_id"] = project_id
            h_org = dict(headers)
            if ws_next:
                h_org["Referer"] = ws_next if ws_next.startswith("http") else f"{AUTH_BASE}{ws_next}"
            resp_org = self.session.post(
                f"{AUTH_BASE}/api/accounts/organization/select",
                json=org_body,
                headers=h_org,
                allow_redirects=False,
                timeout=30,
            )
            print(f"[*] OAuth organization/select -> {resp_org.status_code}")
            if resp_org.status_code in (301, 302, 303, 307, 308):
                loc = resp_org.headers.get("Location", "")
                if loc.startswith("/"):
                    loc = f"{AUTH_BASE}{loc}"
                code = _extract_code_from_url(loc)
                if code:
                    return code
                code, _ = self._oauth_follow_for_code(loc, referer=h_org.get("Referer"))
                if not code:
                    code = self._oauth_allow_redirect_extract_code(loc, referer=h_org.get("Referer"))
                return code
            if resp_org.status_code == 200:
                org_data = safe_json(resp_org)
                org_next = str(org_data.get("continue_url") or "")
                if org_next:
                    if org_next.startswith("/"):
                        org_next = f"{AUTH_BASE}{org_next}"
                    code, _ = self._oauth_follow_for_code(org_next, referer=h_org.get("Referer"))
                    if not code:
                        code = self._oauth_allow_redirect_extract_code(org_next, referer=h_org.get("Referer"))
                    return code

        if ws_next:
            if ws_next.startswith("/"):
                ws_next = f"{AUTH_BASE}{ws_next}"
            code, _ = self._oauth_follow_for_code(ws_next, referer=consent_url)
            if not code:
                code = self._oauth_allow_redirect_extract_code(ws_next, referer=consent_url)
            return code
        return None

    def perform_codex_oauth_login_http(self, email: str, password: str, email_provider: Any = None):
        print("[*] 开始执行 Codex OAuth 纯协议流程...")
        self.session.cookies.set("oai-did", self.device_id, domain=".auth.openai.com")
        self.session.cookies.set("oai-did", self.device_id, domain="auth.openai.com")

        oauth = self.oauth

        def oauth_json_headers(referer: str) -> Dict[str, str]:
            h = {
                "Accept": "application/json",
                "Content-Type": "application/json",
                "Origin": AUTH_BASE,
                "Referer": referer,
                "User-Agent": self.ua,
                "oai-device-id": self.device_id,
            }
            h.update(_make_trace_headers())
            return h

        def with_pow_sentinel(headers: Dict[str, str], flow: str) -> Dict[str, str]:
            merged = dict(headers)
            sentinel_token = build_sentinel_token(
                self.session,
                self.device_id,
                flow=flow,
                user_agent=self.ua,
                sec_ch_ua='"Google Chrome";v="131", "Chromium";v="131", "Not_A Brand";v="24"',
                impersonate="chrome",
            )
            if sentinel_token:
                merged["openai-sentinel-token"] = sentinel_token
            else:
                print(f"[Warning] {flow} 的 PoW sentinel token 获取失败")
            return merged

        print("[*] OAuth 1/6 GET /oauth/authorize")
        authorize_final_url = ""
        try:
            r = self.session.get(
                oauth.auth_url,
                headers={
                    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                    "Referer": f"{CHATGPT_BASE}/",
                    "Upgrade-Insecure-Requests": "1",
                    "User-Agent": self.ua,
                },
                allow_redirects=True,
                timeout=30,
            )
            authorize_final_url = str(r.url)
            print(f"[*] /oauth/authorize -> {r.status_code}, final={authorize_final_url[:180]}")
        except Exception as e:
            callback_url = _extract_callback_url_from_exception(e)
            if callback_url and _url_has_oauth_code(callback_url):
                print("[*] /oauth/authorize 已直接命中 localhost callback")
                code = _extract_code_from_url(callback_url)
                try:
                    token_json = exchange_code_for_token(
                        code=code or "",
                        expected_state=oauth.state,
                        callback_url=callback_url,
                        code_verifier=oauth.code_verifier,
                        redirect_uri=oauth.redirect_uri,
                        proxies=self.proxies,
                    )
                    print("[*] Codex Token 获取成功")
                    return token_json
                except Exception as ex:
                    print(f"[Warning] localhost callback token 交换失败: {ex}")
                    return None
            print(f"[Warning] /oauth/authorize 异常: {e}")
            return None

        continue_referer = authorize_final_url if authorize_final_url.startswith(AUTH_BASE) else f"{AUTH_BASE}/log-in"

        print("[*] OAuth 2/6 POST /api/accounts/authorize/continue")
        resp_continue = self.session.post(
            f"{AUTH_BASE}/api/accounts/authorize/continue",
            json={"username": {"kind": "email", "value": email}},
            headers=with_pow_sentinel(oauth_json_headers(continue_referer), "authorize_continue"),
            timeout=30,
            allow_redirects=False,
        )
        print(f"[*] /authorize/continue -> {resp_continue.status_code}")
        if resp_continue.status_code == 400 and "invalid_auth_step" in (resp_continue.text or ""):
            print("[*] invalid_auth_step，回退到 authorize 结果重试")
            resp_continue = self.session.post(
                f"{AUTH_BASE}/api/accounts/authorize/continue",
                json={"username": {"kind": "email", "value": email}},
                headers=with_pow_sentinel(oauth_json_headers(authorize_final_url or continue_referer), "authorize_continue"),
                timeout=30,
                allow_redirects=False,
            )
            print(f"[*] /authorize/continue(重试) -> {resp_continue.status_code}")
        if resp_continue.status_code != 200:
            print(f"[Warning] 邮箱提交失败: {resp_continue.text[:180]}")
            return None
        continue_data = safe_json(resp_continue)
        continue_url = str(continue_data.get("continue_url") or "")
        page_type = str((continue_data.get("page") or {}).get("type") or "")

        print("[*] OAuth 3/6 POST /api/accounts/password/verify")
        password_verify_referer = continue_url or f"{AUTH_BASE}/log-in/password"
        if password_verify_referer.startswith("/"):
            password_verify_referer = f"{AUTH_BASE}{password_verify_referer}"
        resp_verify = self.session.post(
            f"{AUTH_BASE}/api/accounts/password/verify",
            json={"password": password},
            headers=with_pow_sentinel(oauth_json_headers(password_verify_referer), "password_verify"),
            timeout=30,
            allow_redirects=False,
        )
        print(f"[*] /password/verify -> {resp_verify.status_code}")
        if resp_verify.status_code == 401:
            retry_referers = []
            for candidate in [
                continue_url,
                authorize_final_url,
                f"{AUTH_BASE}/log-in/password",
                f"{AUTH_BASE}/log-in",
            ]:
                ref = str(candidate or "").strip()
                if not ref:
                    continue
                if ref.startswith("/"):
                    ref = f"{AUTH_BASE}{ref}"
                if ref not in retry_referers:
                    retry_referers.append(ref)
            for retry_referer in retry_referers[1:]:
                print(f"[*] /password/verify 401，切换 Referer 重试: {retry_referer}")
                resp_verify = self.session.post(
                    f"{AUTH_BASE}/api/accounts/password/verify",
                    json={"password": password},
                    headers=with_pow_sentinel(oauth_json_headers(retry_referer), "password_verify"),
                    timeout=30,
                    allow_redirects=False,
                )
                print(f"[*] /password/verify(重试) -> {resp_verify.status_code}")
                if resp_verify.status_code == 200:
                    break
        if resp_verify.status_code != 200:
            print(f"[Warning] 密码校验失败: {resp_verify.text[:180]}")
            return None
        verify_data = safe_json(resp_verify)
        continue_url = str(verify_data.get("continue_url") or continue_url)
        page_type = str((verify_data.get("page") or {}).get("type") or page_type)

        need_oauth_otp = (
            page_type == "email_otp_verification"
            or "email-verification" in continue_url
            or "email-otp" in continue_url
        )
        if need_oauth_otp:
            if not email_provider:
                print("[Warning] OAuth 阶段需要邮箱 OTP，但没有 provider")
                return None
            print("[*] OAuth 4/6 检测到邮箱 OTP 验证")
            tried_codes = set()
            otp_success = False
            otp_deadline = time.time() + 120
            while time.time() < otp_deadline and not otp_success:
                email_content = email_provider.get_latest_email_from_api(email, timeout=12, check_interval=3)
                code = email_provider.parse_openai_code(email_content)
                if not code or code in tried_codes:
                    print("[*] OAuth OTP 等待中...")
                    time.sleep(2)
                    continue
                tried_codes.add(code)
                print(f"[*] OAuth 尝试 OTP: {code}")
                resp_otp = self.session.post(
                    f"{AUTH_BASE}/api/accounts/email-otp/validate",
                    json={"code": code},
                    headers=oauth_json_headers(f"{AUTH_BASE}/email-verification"),
                    timeout=30,
                    allow_redirects=False,
                )
                print(f"[*] /email-otp/validate -> {resp_otp.status_code}")
                if resp_otp.status_code != 200:
                    continue
                otp_data = safe_json(resp_otp)
                continue_url = str(otp_data.get("continue_url") or continue_url)
                page_type = str((otp_data.get("page") or {}).get("type") or page_type)
                otp_success = True
            if not otp_success:
                print("[Warning] OAuth 阶段 OTP 验证失败")
                return None

        code = None
        callback_url = self._callback_url or ""
        consent_url = continue_url
        if consent_url and consent_url.startswith("/"):
            consent_url = f"{AUTH_BASE}{consent_url}"
        if not consent_url and "consent" in page_type:
            consent_url = f"{AUTH_BASE}/sign-in-with-chatgpt/codex/consent"

        if consent_url:
            code = _extract_code_from_url(consent_url)
            if code:
                callback_url = consent_url

        if not code and consent_url:
            print("[*] OAuth 5/6 跟随 continue_url 提取 code")
            code, callback_url = self._oauth_follow_for_code(consent_url, referer=f"{AUTH_BASE}/log-in/password")
            if code:
                self._callback_url = callback_url

        consent_hint = (
            ("consent" in (consent_url or ""))
            or ("sign-in-with-chatgpt" in (consent_url or ""))
            or ("workspace" in (consent_url or ""))
            or ("organization" in (consent_url or ""))
            or ("consent" in page_type)
            or ("organization" in page_type)
        )
        if not code and consent_hint:
            if not consent_url:
                consent_url = f"{AUTH_BASE}/sign-in-with-chatgpt/codex/consent"
            print("[*] OAuth 5/6 执行 workspace/org 选择")
            code = self._oauth_submit_workspace_and_org(consent_url)
            if code:
                callback_url = _append_code_state_to_url(consent_url, code, oauth.state)

        if not code:
            fallback_consent = f"{AUTH_BASE}/sign-in-with-chatgpt/codex/consent"
            print("[*] OAuth fallback consent 重试")
            code = self._oauth_submit_workspace_and_org(fallback_consent)
            if code:
                callback_url = _append_code_state_to_url(fallback_consent, code, oauth.state)
            else:
                code, callback_url = self._oauth_follow_for_code(fallback_consent, referer=f"{AUTH_BASE}/log-in/password")
                if code:
                    self._callback_url = callback_url

        if not code and self._callback_url and _url_has_oauth_code(self._callback_url):
            code = _extract_code_from_url(self._callback_url)
            callback_url = self._callback_url

        if not code:
            print("[Warning] 未获取到 authorization code")
            return None

        callback_url = callback_url or self._callback_url or consent_url or oauth.auth_url
        callback_url = _append_code_state_to_url(callback_url, code, oauth.state)

        print("[*] OAuth 6/6 POST /oauth/token")
        try:
            token_json = exchange_code_for_token(
                code=code,
                expected_state=oauth.state,
                callback_url=callback_url,
                code_verifier=oauth.code_verifier,
                redirect_uri=oauth.redirect_uri,
                proxies=self.proxies,
            )
            print("[*] Codex Token 获取成功")
            return token_json
        except Exception as e:
            print(f"[Warning] token 交换失败: {e}")
            return None

    def run_register_flow(self, email: str, password: str, name: str, birthdate: str, email_provider: Any) -> bool:
        self.visit_homepage()
        _random_delay(0.3, 0.8)
        csrf = self.get_csrf()
        _random_delay(0.2, 0.5)
        auth_url = self.signin(email, csrf)
        _random_delay(0.3, 0.8)
        try:
            final_url = self.authorize(auth_url)
        except Exception:
            print(
                f"[Debug] run_register_flow 上下文: email={email}, device_id={self.device_id}, "
                f"auth_session_logging_id={self.auth_session_logging_id}, "
                f"oauth_redirect_uri={self.oauth.redirect_uri}"
            )
            print(f"[Debug] run_register_flow auth_url: {_sanitize_url_for_log(auth_url)}")
            raise
        final_path = urllib.parse.urlparse(final_url).path
        _random_delay(0.3, 0.8)
        print(f"[*] Authorize -> {final_path}")

        need_otp = False
        if "create-account/password" in final_path:
            print("[*] 全新注册流程")
            _random_delay(0.5, 1.0)
            status, data = self.register(email, password)
            if status != 200:
                raise RuntimeError(f"Register 失败 ({status}): {data}")
            _random_delay(0.3, 0.8)
            self.send_otp()
            need_otp = True
        elif "email-verification" in final_path or "email-otp" in final_path:
            print("[*] 跳到 OTP 验证阶段 (authorize 已触发 OTP，不再重复发送)")
            need_otp = True
        elif "about-you" in final_path:
            print("[*] 跳到填写信息阶段")
            _random_delay(0.5, 1.0)
            self.create_account(name, birthdate)
            _random_delay(0.3, 0.5)
            self.callback()
            return True
        elif "callback" in final_path or "chatgpt.com" in final_url:
            print("[*] 账号已完成注册")
            return True
        else:
            print(f"[*] 未知跳转: {final_url}")
            self.register(email, password)
            self.send_otp()
            need_otp = True

        if need_otp:
            email_content = email_provider.get_latest_email_from_api(email, timeout=120, check_interval=3)
            otp_code = email_provider.parse_openai_code(email_content)
            if not otp_code:
                raise RuntimeError("未能获取验证码")
            _random_delay(0.3, 0.8)
            status, data = self.validate_otp(otp_code)
            if status != 200:
                print("[*] 验证码失败，重试...")
                self.send_otp()
                _random_delay(1.0, 2.0)
                email_content = email_provider.get_latest_email_from_api(email, timeout=60, check_interval=3)
                otp_code = email_provider.parse_openai_code(email_content)
                if not otp_code:
                    raise RuntimeError("重试后仍未获取验证码")
                _random_delay(0.3, 0.8)
                status, data = self.validate_otp(otp_code)
                if status != 200:
                    raise RuntimeError(f"验证码失败 ({status}): {data}")

        _random_delay(0.5, 1.5)
        status, data = self.create_account(name, birthdate)
        if status != 200:
            raise RuntimeError(f"Create account 失败 ({status}): {data}")
        _random_delay(0.2, 0.5)
        self.callback()
        return True


def build_local_account_record(token_json: str, password: str, mail_address: str = "") -> Optional[Dict[str, str]]:
    try:
        token_data = json.loads(token_json)
    except Exception as e:
        print(f"[Warning] 解析 token_json 失败，跳过本地数据库保存: {e}")
        return None

    email = str(token_data.get("email") or "").strip()
    access_token = str(token_data.get("access_token") or "").strip()
    refresh_token = str(token_data.get("refresh_token") or "").strip()
    expired = str(token_data.get("expired") or "").strip()
    registered_at = format_beijing_rfc3339(beijing_now())

    if not email or not access_token:
        print("[Warning] token_json 缺少 email 或 access_token，跳过本地数据库保存")
        return None

    return {
        "email": email,
        "password": password,
        "registered_at": registered_at,
        "token": access_token,
        "refresh_token": refresh_token,
        "expired": expired,
        "mail_address": str(mail_address or "").strip(),
    }


def save_account_to_db(token_json: str, password: str, mail_address: str = "") -> bool:
    record = build_local_account_record(token_json, password, mail_address=mail_address)
    if not record:
        return False
    try:
        upsert_account_record(**record)
        print(f"[*] 本地数据库已保存账号: {record['email']}")
        return True
    except Exception as e:
        print(f"[Warning] 保存本地数据库失败: {e}")
        return False


def upload_token_to_cliproxyapi(base_url: str, token: str, file_name: str, token_json: str) -> bool:
    upload_url = f"{base_url.rstrip('/')}/v0/management/auth-files?name={os.path.basename(file_name)}"
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }
    resp_push = requests.post(upload_url, data=token_json.encode("utf-8"), headers=headers, timeout=15)
    if resp_push.status_code == 200:
        print("[*] ✅ 自动注入 CLIProxyAPI 成功，API已热加载生效！喵~")
        return True
    print(f"[-] 自动注入 CLIProxyAPI 失败: HTTP {resp_push.status_code} {resp_push.text}")
    return False


def register_once(proxy: Optional[str], email_provider_name: Optional[str] = None) -> Optional[Dict[str, str]]:
    provider_name = str(email_provider_name or DEFAULT_EMAIL_PROVIDERS[0]).strip()
    print(f"[*] 本次使用邮箱服务: {provider_name}")
    registrar = HybridOpenAIRegister(proxy=proxy)
    print(
        f"[*] 注册会话: device_id={registrar.device_id}, "
        f"auth_session_logging_id={registrar.auth_session_logging_id}"
    )
    if not registrar.check_location():
        return None

    try:
        email_provider = EmailProviderFactory.create(provider_name, proxies=registrar.proxies, timeout=15)
    except Exception as e:
        print(f"[Error] 邮箱服务 {provider_name} 初始化失败: {e}")
        return None

    register_email = ""
    mail_address = ""
    max_email_attempts = 5

    try:
        for attempt in range(1, max_email_attempts + 1):
            email = email_provider.get_email_from_api()
            if not email:
                continue

            candidate_email = str(email).strip()
            email_suffix = extract_email_suffix(candidate_email)
            if is_email_suffix_disabled("OpenAI", email_suffix):
                print(
                    f"[Warning] 邮箱后缀已禁用，跳过: {candidate_email} "
                    f"(subscription_type=OpenAI, attempt={attempt}/{max_email_attempts})"
                )
                continue

            register_email = candidate_email
            mail_address = str(email_provider.get_mail_access_identifier() or register_email).strip()
            print(f"[*] 成功获取邮箱: {register_email}")
            print(f"[*] 取邮件标识: {mail_address}")
            break
    except Exception as e:
        print(f"[Error] 邮箱服务 {provider_name} 调用失败: {e}")
        return None

    if not register_email:
        print(f"[Error] 邮箱服务 {provider_name} 未获取到可用邮箱")
        return None

    password = secrets.token_urlsafe(16)
    random_name = random.choice([
        "Alex", "Sam", "Jordan", "Taylor", "Morgan", "Casey", "Riley", "Quinn", "Avery", "Blake"
    ])
    random_year = random.randint(1985, 2003)
    random_month = random.randint(1, 12)
    random_day = random.randint(1, 28)
    birthdate = f"{random_year}-{random_month:02d}-{random_day:02d}"

    try:
        registrar.run_register_flow(register_email, password, random_name, birthdate, email_provider)
        token_json = registrar.perform_codex_oauth_login_http(register_email, password, email_provider=email_provider)
        if not token_json:
            print("[Error] OAuth 获取 token 失败")
            return None
        save_account_to_db(token_json, password, mail_address=mail_address)
        return {"token_json": token_json, "password": password}
    except Exception as e:
        print(
            f"[Debug] register_once 失败上下文: provider={provider_name}, email={register_email}, "
            f"mail_access={mail_address}, device_id={registrar.device_id}, "
            f"auth_session_logging_id={registrar.auth_session_logging_id}"
        )
        disable_email_suffix_for_unsupported_email(
            subscription_type="OpenAI",
            email=register_email,
            error=e,
        )
        print(f"[Error] 运行时发生错误: {e}")
        return None


def register_until_target_count(
    *,
    proxy: Optional[str],
    base_url: str,
    token: str,
    timeout: int,
    target_type: str,
    provider: Optional[str],
    target_count: int,
    email_providers: Optional[List[str]] = None,
    selected_provider: Optional[str] = None,
) -> int:
    if not base_url or not token:
        print("[*] 跳过补量：未配置 CLIProxyAPI 管理接口或 Token")
        return 0

    desired_count = max(0, int(target_count or 0))
    if desired_count <= 0:
        return 0

    try:
        current_count = count_matching_auth_files(
            base_url=base_url,
            token=token,
            timeout=timeout,
            target_type=target_type,
            provider=provider,
        )
    except Exception as e:
        print(f"[Warning] 统计现有账号数失败，跳过补量: {e}")
        return 0

    deficit = max(0, desired_count - current_count)
    print(f"[*] 当前符合条件账号数: {current_count}，目标数: {desired_count}")
    if deficit <= 0:
        print("[*] 现有账号数量已满足目标，无需补量。")
        return 0

    print(f"[*] 删除401后数量不足，开始补充差额: {deficit}")
    provider_names = normalize_email_providers(email_providers)
    active_provider = str(selected_provider or "").strip()
    if active_provider and active_provider not in provider_names:
        print(f"[Warning] 已选 provider 不在候选列表中，回退到默认列表: {active_provider}")
        active_provider = ""
    success = 0
    attempt_count = 0
    total_start_time = time.time()

    while success < deficit:
        attempt_count += 1
        attempt_no = success + 1
        provider_name = active_provider or provider_names[(attempt_count - 1) % len(provider_names)]
        attempt_start_time = time.time()
        mode_label = "已选" if active_provider else "轮换"
        print(f"[*] 补量进度: {attempt_no}/{deficit}，第 {attempt_count} 次尝试，本次{mode_label}邮箱服务: {provider_name}")
        token_result = register_once(proxy, email_provider_name=provider_name)
        if not token_result:
            print("[-] 本次补量注册失败。")
            continue
        token_json = token_result["token_json"]
        try:
            t_data = json.loads(token_json)
            fname_email = t_data.get("email", "unknown").replace("@", "_")
        except Exception:
            fname_email = "unknown"

        os.makedirs("tokens", exist_ok=True)
        file_name = os.path.join("tokens", f"token_{fname_email}_{int(time.time())}.json")
        with open(file_name, "w", encoding="utf-8") as f:
            f.write(token_json)
        print(f"[*] 补量成功! Token 已保存至: {file_name}")

        try:
            if upload_token_to_cliproxyapi(base_url, token, file_name, token_json):
                success += 1
                duration = time.time() - attempt_start_time
                print(f"[*] 第 {success} 个账号创建成功，耗时: {duration:.2f} 秒")
        except Exception as ex:
            print(f"[-] 补量账号自动注入过程发生错误: {ex}")

    total_duration = time.time() - total_start_time
    average_duration = (total_duration / success) if success else 0.0
    print(f"[*] 补量完成，本次共补充 {success} 个账号。")
    print(f"[*] 总耗时: {total_duration:.2f} 秒")
    print(f"[*] 平均每个账号耗时: {average_duration:.2f} 秒")
    print(f"[*] 成功创建账号数: {success}")
    return success


def main() -> int:
    init_account_db()
    parser = argparse.ArgumentParser(description="OpenAI 混合自动注册脚本")
    parser.add_argument("--proxy", default="http://127.0.0.1:7890", help="代理地址（默认 http://127.0.0.1:7890）")
    parser.add_argument("--once", action="store_true", help="只运行一次")
    parser.add_argument("--sleep-min", type=int, default=5, help="循环模式最短等待秒数")
    parser.add_argument("--sleep-max", type=int, default=30, help="循环模式最长等待秒数")
    parser.add_argument("--mgmt-url", default=DEFAULT_MGMT_URL, help="CLIProxyAPI 管理接口地址")
    parser.add_argument("--mgmt-token", default=os.getenv("MGMT_TOKEN", ""), help="CLIProxyAPI 管理 Token")
    parser.add_argument("--skip-preclean-401", action="store_true", help="跳过注册前自动检查并删除401账号")
    parser.add_argument("--preclean-target-type", default=DEFAULT_PRECHECK_TARGET_TYPE, help="注册前401检查时过滤的账号类型")
    parser.add_argument("--preclean-provider", default=None, help="注册前401检查时过滤的 provider")
    parser.add_argument("--preclean-workers", type=int, default=DEFAULT_PRECHECK_WORKERS, help="注册前401检查并发数")
    parser.add_argument("--preclean-timeout", type=int, default=DEFAULT_PRECHECK_TIMEOUT, help="注册前401检查超时秒数")
    parser.add_argument("--preclean-retries", type=int, default=DEFAULT_PRECHECK_RETRIES, help="注册前401检查重试次数")
    parser.add_argument("--preclean-user-agent", default=DEFAULT_PRECHECK_UA, help="注册前401检查使用的 User-Agent")
    parser.add_argument("--preclean-chatgpt-account-id", default=os.getenv("CHATGPT_ACCOUNT_ID", ""), help="注册前401检查使用的 Chatgpt-Account-Id")
    parser.add_argument("--preclean-output-401", default=DEFAULT_PRECHECK_OUTPUT_401, help="注册前401账号导出文件路径")
    parser.add_argument("--target-account-count", type=int, default=DEFAULT_TARGET_ACCOUNT_COUNT, help="删除401后希望维持的目标账号数")
    parser.add_argument("--email-providers", default=",".join(DEFAULT_EMAIL_PROVIDERS), help="邮箱服务顺序，逗号分隔")
    args = parser.parse_args()

    config_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "clean_codex", "config.json")
    if os.path.exists(config_path):
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                conf = json.load(f)
            if isinstance(conf, dict):
                if conf.get("base_url") and args.mgmt_url == DEFAULT_MGMT_URL:
                    args.mgmt_url = conf["base_url"]
                if conf.get("cpa_password") and not args.mgmt_token:
                    args.mgmt_token = conf["cpa_password"]
                if conf.get("user_agent") and args.preclean_user_agent == DEFAULT_PRECHECK_UA:
                    args.preclean_user_agent = conf["user_agent"]
                if conf.get("chatgpt_account_id") and not args.preclean_chatgpt_account_id:
                    args.preclean_chatgpt_account_id = conf["chatgpt_account_id"]
        except Exception as e:
            print(f"[Warning] 自动读取统一配置文件失败: {e}")

    sleep_min = max(1, args.sleep_min)
    sleep_max = max(sleep_min, args.sleep_max)
    email_providers = normalize_email_providers([name.strip() for name in str(args.email_providers or "").split(",") if name.strip()])
    selected_provider = choose_email_provider_interactively(email_providers)

    count = 0
    total_start_time = time.time()
    success_count = 0
    print("[Info] Hybrid OpenAI Auto-Registrar Started")
    print(f"[*] 当前邮箱服务顺序: {', '.join(email_providers)}")
    print(f"[*] 本次已选择邮箱服务: {selected_provider}")

    if not args.skip_preclean_401:
        preclean_401_and_delete(
            base_url=args.mgmt_url,
            token=args.mgmt_token,
            target_type=args.preclean_target_type,
            provider=args.preclean_provider,
            workers=args.preclean_workers,
            timeout=args.preclean_timeout,
            retries=args.preclean_retries,
            user_agent=args.preclean_user_agent,
            chatgpt_account_id=args.preclean_chatgpt_account_id,
            output_401=args.preclean_output_401,
        )
        register_until_target_count(
            proxy=args.proxy,
            base_url=args.mgmt_url,
            token=args.mgmt_token,
            timeout=args.preclean_timeout,
            target_type=args.preclean_target_type,
            provider=args.preclean_provider,
            target_count=args.target_account_count,
            email_providers=email_providers,
            selected_provider=selected_provider,
        )
        return 0

    while True:
        count += 1
        attempt_start_time = time.time()
        print(f"\n[{datetime.now().strftime('%H:%M:%S')}] >>> 开始第 {count} 次注册流程 <<<")
        print(f"[*] 当前已成功创建账号数: {success_count}")
        provider_name = selected_provider
        print(f"[*] 本次选择邮箱服务: {provider_name}")
        token_result = register_once(args.proxy, email_provider_name=provider_name)
        if token_result:
            token_json = token_result["token_json"]
            try:
                t_data = json.loads(token_json)
                fname_email = t_data.get("email", "unknown").replace("@", "_")
            except Exception:
                fname_email = "unknown"
            os.makedirs("tokens", exist_ok=True)
            file_name = os.path.join("tokens", f"token_{fname_email}_{int(time.time())}.json")
            with open(file_name, "w", encoding="utf-8") as f:
                f.write(token_json)
            print(f"[*] 成功! Token 已保存至: {file_name}")
            if args.mgmt_url and args.mgmt_token:
                try:
                    upload_token_to_cliproxyapi(args.mgmt_url, args.mgmt_token, file_name, token_json)
                except Exception as ex:
                    print(f"[-] 自动注入过程发生错误: {ex}")
            duration = time.time() - attempt_start_time
            success_count += 1
            total_duration = time.time() - total_start_time
            average_duration = total_duration / success_count
            print(f"[*] 第 {success_count} 个账号创建成功，耗时: {duration:.2f} 秒")
            print(f"[*] 当前累计总耗时: {total_duration:.2f} 秒")
            print(f"[*] 当前平均每个账号耗时: {average_duration:.2f} 秒")
        else:
            print("[-] 本次注册失败。")

        if args.once:
            break
        wait_time = random.randint(sleep_min, sleep_max)
        print(f"[*] 休息 {wait_time} 秒...")
        time.sleep(wait_time)

    total_duration = time.time() - total_start_time
    average_duration = (total_duration / success_count) if success_count else 0.0
    print(f"[*] 所有流程结束，总耗时: {total_duration:.2f} 秒")
    print(f"[*] 平均每个账号耗时: {average_duration:.2f} 秒")
    print(f"[*] 成功创建账号总数: {success_count}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
