import json
import re
import time
import random
import secrets
import hashlib
import base64
import argparse
import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from dataclasses import dataclass
from typing import Any, Dict, List, Optional
import urllib.parse

from curl_cffi import requests

# ==========================================
# Mail.tm 临时邮箱 API
# ==========================================

MAILTM_BASE = "https://api.mail.tm"


def _mailtm_headers(*, token: str = "", use_json: bool = False) -> Dict[str, str]:
    headers = {"Accept": "application/json"}
    if use_json:
        headers["Content-Type"] = "application/json"
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


def _mailtm_domains(proxies: Any = None) -> list[str]:
    resp = requests.get(
        f"{MAILTM_BASE}/domains",
        headers=_mailtm_headers(),
        proxies=proxies,
        impersonate="chrome",
        timeout=15,
    )
    if resp.status_code != 200:
        raise RuntimeError(f"获取 Mail.tm 域名失败，状态码: {resp.status_code}")

    data = resp.json()
    domains = []
    if isinstance(data, list):
        items = data
    elif isinstance(data, dict):
        items = data.get("hydra:member") or data.get("items") or []
    else:
        items = []

    for item in items:
        if not isinstance(item, dict):
            continue
        domain = str(item.get("domain") or "").strip()
        is_active = item.get("isActive", True)
        is_private = item.get("isPrivate", False)
        if domain and is_active and not is_private:
            domains.append(domain)

    return domains


def get_email_and_token(proxies: Any = None) -> tuple[str, str]:
    """创建 Mail.tm 邮箱并获取 Bearer Token"""
    try:
        domains = _mailtm_domains(proxies)
        if not domains:
            print("[Error] Mail.tm 没有可用域名")
            return "", ""
        domain = random.choice(domains)

        for _ in range(5):
            local = f"oc{secrets.token_hex(5)}"
            email = f"{local}@{domain}"
            password = secrets.token_urlsafe(18)

            create_resp = requests.post(
                f"{MAILTM_BASE}/accounts",
                headers=_mailtm_headers(use_json=True),
                json={"address": email, "password": password},
                proxies=proxies,
                impersonate="chrome",
                timeout=15,
            )

            if create_resp.status_code not in (200, 201):
                continue

            token_resp = requests.post(
                f"{MAILTM_BASE}/token",
                headers=_mailtm_headers(use_json=True),
                json={"address": email, "password": password},
                proxies=proxies,
                impersonate="chrome",
                timeout=15,
            )

            if token_resp.status_code == 200:
                token = str(token_resp.json().get("token") or "").strip()
                if token:
                    return email, token

        print("[Error] Mail.tm 邮箱创建成功但获取 Token 失败")
        return "", ""
    except Exception as e:
        print(f"[Error] 请求 Mail.tm API 出错: {e}")
        return "", ""


def get_oai_code(token: str, email: str, proxies: Any = None) -> str:
    """使用 Mail.tm Token 轮询获取 OpenAI 验证码"""
    url_list = f"{MAILTM_BASE}/messages"
    regex = r"(?<!\d)(\d{6})(?!\d)"
    seen_ids: set[str] = set()

    print(f"[*] 正在等待邮箱 {email} 的验证码...", end="", flush=True)

    for _ in range(40):
        print(".", end="", flush=True)
        try:
            resp = requests.get(
                url_list,
                headers=_mailtm_headers(token=token),
                proxies=proxies,
                impersonate="chrome",
                timeout=15,
            )
            if resp.status_code != 200:
                time.sleep(3)
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

                read_resp = requests.get(
                    f"{MAILTM_BASE}/messages/{msg_id}",
                    headers=_mailtm_headers(token=token),
                    proxies=proxies,
                    impersonate="chrome",
                    timeout=15,
                )
                if read_resp.status_code != 200:
                    continue

                mail_data = read_resp.json()
                sender = str(
                    ((mail_data.get("from") or {}).get("address") or "")
                ).lower()
                subject = str(mail_data.get("subject") or "")
                intro = str(mail_data.get("intro") or "")
                text = str(mail_data.get("text") or "")
                html = mail_data.get("html") or ""
                if isinstance(html, list):
                    html = "\n".join(str(x) for x in html)
                content = "\n".join([subject, intro, text, str(html)])

                if "openai" not in sender and "openai" not in content.lower():
                    continue

                m = re.search(regex, content)
                if m:
                    print(" 抓到啦! 验证码:", m.group(1))
                    return m.group(1)
        except Exception:
            pass

        time.sleep(3)

    print(" 超时，未收到验证码")
    return ""


# ==========================================
# OAuth 授权与辅助函数
# ==========================================

AUTH_URL = "https://auth.openai.com/oauth/authorize"
TOKEN_URL = "https://auth.openai.com/oauth/token"
CLIENT_ID = "app_EMoamEEZ73f0CkXaXp7hrann"

DEFAULT_REDIRECT_URI = f"http://localhost:1455/auth/callback"
DEFAULT_SCOPE = "openid email profile offline_access"
DEFAULT_MGMT_URL = "http://127.0.0.1:8045"
DEFAULT_PRECHECK_TARGET_TYPE = "codex"
DEFAULT_PRECHECK_UA = "codex_cli_rs/0.76.0 (Debian 13.0.0; x86_64) WindowsTerminal"
DEFAULT_PRECHECK_TIMEOUT = 12
DEFAULT_PRECHECK_WORKERS = 120
DEFAULT_PRECHECK_RETRIES = 1
DEFAULT_PRECHECK_OUTPUT_401 = "invalid_codex_accounts.json"
DEFAULT_TARGET_ACCOUNT_COUNT = 100


def _b64url_no_pad(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


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


def _random_state() -> str:
    return _b64url_no_pad(secrets.token_bytes(32))


def _sha256_b64url_no_pad(s: str) -> str:
    return _b64url_no_pad(hashlib.sha256(s.encode("ascii")).digest())


def _pkce_verifier() -> str:
    return secrets.token_urlsafe(64)


def _parse_callback_url(callback_url: str) -> Dict[str, str]:
    candidate = callback_url.strip()
    if not candidate:
        return {"code": "", "state": "", "error": "", "error_description": ""}

    if "://" not in candidate:
        if candidate.startswith("?"):
            candidate = f"http://localhost{candidate}"
        elif any(ch in candidate for ch in "/?#") or ":" in candidate:
            candidate = f"http://{candidate}"
        elif "=" in candidate:
            candidate = f"http://localhost/?{candidate}"

    parsed = urllib.parse.urlparse(candidate)
    query = urllib.parse.parse_qs(parsed.query, keep_blank_values=True)
    fragment = urllib.parse.parse_qs(parsed.fragment, keep_blank_values=True)

    for key, values in fragment.items():
        if key not in query or not query[key] or not (query[key][0] or "").strip():
            query[key] = values

    def get1(k: str) -> str:
        v = query.get(k, [""])
        return (v[0] or "").strip()

    code = get1("code")
    state = get1("state")
    error = get1("error")
    error_description = get1("error_description")

    if code and not state and "#" in code:
        code, state = code.split("#", 1)

    if not error and error_description:
        error, error_description = error_description, ""

    return {
        "code": code,
        "state": state,
        "error": error,
        "error_description": error_description,
    }


def _jwt_claims_no_verify(id_token: str) -> Dict[str, Any]:
    if not id_token or id_token.count(".") < 2:
        return {}
    payload_b64 = id_token.split(".")[1]
    pad = "=" * ((4 - (len(payload_b64) % 4)) % 4)
    try:
        payload = base64.urlsafe_b64decode((payload_b64 + pad).encode("ascii"))
        return json.loads(payload.decode("utf-8"))
    except Exception:
        return {}


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


def build_probe_payload(
    auth_index: str, user_agent: str, chatgpt_account_id: str = ""
) -> Dict[str, Any]:
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

            data = safe_json(resp)
            if not data:
                data = safe_json_text(resp.text)

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
            if done % 100 == 0 or done == total:
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
    for item in invalid_401:
        name = str(item.get("name") or "").strip()
        if not name:
            fail += 1
            continue
        try:
            delete_auth_file(base_url, token, name, timeout)
            ok += 1
            print(f"[*] 已删除401账号: {name}")
        except Exception as e:
            fail += 1
            print(f"[FAIL] 删除401账号 {name}: {e}")

    print(f"[*] 401账号删除完成: 成功 {ok}，失败 {fail}")
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


def register_until_target_count(
    *,
    proxy: Optional[str],
    base_url: str,
    token: str,
    timeout: int,
    target_type: str,
    provider: Optional[str],
    target_count: int,
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
    success = 0

    while success < deficit:
        attempt_no = success + 1
        print(f"[*] 补量进度: {attempt_no}/{deficit}")
        try:
            token_json = run(proxy)
            if not token_json:
                print("[-] 本次补量注册失败。")
                continue

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

            base_name = os.path.basename(file_name)
            upload_url = f"{base_url.rstrip('/')}/v0/management/auth-files?name={base_name}"
            try:
                headers = {
                    "Authorization": f"Bearer {token}",
                    "Content-Type": "application/json",
                }
                resp_push = requests.post(
                    upload_url,
                    data=token_json.encode("utf-8"),
                    headers=headers,
                    timeout=15,
                )
                if resp_push.status_code == 200:
                    success += 1
                    print("[*] 补量账号已自动注入 CLIProxyAPI，API已热加载生效！喵~")
                else:
                    print(
                        f"[-] 补量账号自动注入 CLIProxyAPI 失败: HTTP {resp_push.status_code} {resp_push.text}"
                    )
            except Exception as ex:
                print(f"[-] 补量账号自动注入过程发生错误: {ex}")
        except Exception as e:
            print(f"[Error] 补量过程中发生未捕获异常: {e}")

    print(f"[*] 补量完成，本次共补充 {success} 个账号。")
    return success


def _post_form(
    url: str, data: Dict[str, str], proxies: Any = None, timeout: int = 30
) -> Dict[str, Any]:
    resp = requests.post(
        url,
        data=data,
        headers={
            "Content-Type": "application/x-www-form-urlencoded",
            "Accept": "application/json",
        },
        proxies=proxies,
        impersonate="chrome",
        timeout=timeout,
    )
    if resp.status_code != 200:
        raise RuntimeError(
            f"token exchange failed: {resp.status_code}: {resp.text}"
        )
    return resp.json()


@dataclass(frozen=True)
class OAuthStart:
    auth_url: str
    state: str
    code_verifier: str
    redirect_uri: str


def generate_oauth_url(
    *, redirect_uri: str = DEFAULT_REDIRECT_URI, scope: str = DEFAULT_SCOPE
) -> OAuthStart:
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


def submit_callback_url(
    *,
    callback_url: str,
    expected_state: str,
    code_verifier: str,
    redirect_uri: str = DEFAULT_REDIRECT_URI,
    proxies: Any = None,
) -> str:
    cb = _parse_callback_url(callback_url)
    if cb["error"]:
        desc = cb["error_description"]
        raise RuntimeError(f"oauth error: {cb['error']}: {desc}".strip())

    if not cb["code"]:
        raise ValueError("callback url missing ?code=")
    if not cb["state"]:
        raise ValueError("callback url missing ?state=")
    if cb["state"] != expected_state:
        raise ValueError("state mismatch")

    token_resp = _post_form(
        TOKEN_URL,
        {
            "grant_type": "authorization_code",
            "client_id": CLIENT_ID,
            "code": cb["code"],
            "redirect_uri": redirect_uri,
            "code_verifier": code_verifier,
        },
        proxies=proxies,
    )

    access_token = (token_resp.get("access_token") or "").strip()
    refresh_token = (token_resp.get("refresh_token") or "").strip()
    id_token = (token_resp.get("id_token") or "").strip()
    expires_in = _to_int(token_resp.get("expires_in"))

    claims = _jwt_claims_no_verify(id_token)
    email = str(claims.get("email") or "").strip()
    auth_claims = claims.get("https://api.openai.com/auth") or {}
    account_id = str(auth_claims.get("chatgpt_account_id") or "").strip()

    now = int(time.time())
    expired_rfc3339 = time.strftime(
        "%Y-%m-%dT%H:%M:%SZ", time.gmtime(now + max(expires_in, 0))
    )
    now_rfc3339 = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(now))

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


# ==========================================
# 核心注册逻辑
# ==========================================


def run(proxy: Optional[str]) -> Optional[str]:
    proxies: Any = None
    if proxy:
        proxies = {"http": proxy, "https": proxy}

    s = requests.Session(proxies=proxies, impersonate="chrome")

    try:
        trace = s.get("https://cloudflare.com/cdn-cgi/trace", timeout=10)
        trace = trace.text
        loc_re = re.search(r"^loc=(.+)$", trace, re.MULTILINE)
        loc = loc_re.group(1) if loc_re else None
        print(f"[*] 当前 IP 所在地: {loc}")
        if loc == "CN" or loc == "HK":
            raise RuntimeError("检查代理哦w - 所在地不支持")
    except Exception as e:
        print(f"[Error] 网络连接检查失败: {e}")
        return None

    email, dev_token = get_email_and_token(proxies)
    if not email or not dev_token:
        return None
    print(f"[*] 成功获取 Mail.tm 邮箱与授权: {email}")

    oauth = generate_oauth_url()
    url = oauth.auth_url

    try:
        resp = s.get(url, timeout=15)
        did = s.cookies.get("oai-did")
        print(f"[*] Device ID: {did}")

        signup_body = json.dumps({"username": {"value": email, "kind": "email"}, "screen_hint": "signup"})
        sen_req_body = json.dumps({"p": "", "id": did, "flow": "authorize_continue"})

        sen_resp = requests.post(
            "https://sentinel.openai.com/backend-api/sentinel/req",
            headers={
                "origin": "https://sentinel.openai.com",
                "referer": "https://sentinel.openai.com/backend-api/sentinel/frame.html?sv=20260219f9f6",
                "content-type": "text/plain;charset=UTF-8",
            },
            data=sen_req_body,
            proxies=proxies,
            impersonate="chrome",
            timeout=15,
        )

        if sen_resp.status_code != 200:
            print(f"[Error] Sentinel 异常拦截，状态码: {sen_resp.status_code}")
            return None

        sen_token = sen_resp.json()["token"]
        sentinel = json.dumps({"p": "", "t": "", "c": sen_token, "id": did, "flow": "authorize_continue"})

        signup_resp = s.post(
            "https://auth.openai.com/api/accounts/authorize/continue",
            headers={
                "referer": "https://auth.openai.com/create-account",
                "accept": "application/json",
                "content-type": "application/json",
                "openai-sentinel-token": sentinel,
            },
            data=signup_body,
        )
        print(f"[*] 提交注册表单状态: {signup_resp.status_code}")
        if signup_resp.status_code not in (200, 201):
            print(f"[Error] 注册表单提交失败: {signup_resp.text}")
            return None

        # 1. 生成随机密码并记录当前执行步骤
        password = secrets.token_urlsafe(16)
        print(f"[*] 生成密码: {password}")

        # 2. 封装注册请求的 JSON Payload
        register_body = json.dumps({
            "password": password, 
            "username": email
        })

        # 3. 发起「提交注册信息」请求 (POST)
        pwd_resp = s.post(
            "https://auth.openai.com/api/accounts/user/register",
            headers={
                "referer": "https://auth.openai.com/create-account/password",
                "accept": "application/json",
                "content-type": "application/json",
            },
            data=register_body,
            timeout=15,
        )
        print(f"[*] 提交注册信息(附加密码)状态: {pwd_resp.status_code}")
        if pwd_resp.status_code not in (200, 201):
            print(f"[Error] 带有密码的注册请求提交失败: {pwd_resp.text}")
            return None

        # 4. 发起「发送邮箱验证码」请求 (GET)
        otp_send_resp = s.get(
            "https://auth.openai.com/api/accounts/email-otp/send",
            headers={
                "referer": "https://auth.openai.com/create-account/password",
                "accept": "application/json",
            },
            timeout=15,
        )
        print(f"[*] 验证码发送状态: {otp_send_resp.status_code}")
        if otp_send_resp.status_code != 200:
            print(f"[Error] 验证码发送失败: {otp_send_resp.text}")
            return None

        code = get_oai_code(dev_token, email, proxies)
        if not code:
            return None

        code_body = json.dumps({"code": code})
        code_resp = s.post(
            "https://auth.openai.com/api/accounts/email-otp/validate",
            headers={
                "referer": "https://auth.openai.com/email-verification",
                "accept": "application/json",
                "content-type": "application/json",
            },
            data=code_body,
        )
        print(f"[*] 验证码校验状态: {code_resp.status_code}")
        if code_resp.status_code != 200:
            print(f"[Error] 验证码校验失败: {code_resp.text}")
            return None

        random_name = random.choice(["Alex", "Sam", "Jordan", "Taylor", "Morgan", "Casey", "Riley", "Quinn", "Avery", "Blake"])
        random_year = random.randint(1985, 2003)
        random_month = random.randint(1, 12)
        random_day = random.randint(1, 28)
        create_account_body = json.dumps({
            "name": random_name,
            "birthdate": f"{random_year}-{random_month:02d}-{random_day:02d}",
        })
        create_account_resp = s.post(
            "https://auth.openai.com/api/accounts/create_account",
            headers={
                "referer": "https://auth.openai.com/about-you",
                "accept": "application/json",
                "content-type": "application/json",
            },
            data=create_account_body,
        )
        create_account_status = create_account_resp.status_code
        print(f"[*] 账户创建状态: {create_account_status}")

        if create_account_status != 200:
            print(create_account_resp.text)
            return None

        auth_cookie = s.cookies.get("oai-client-auth-session")
        if not auth_cookie:
            print("[Error] 未能获取到授权 Cookie")
            return None

        auth_json = _decode_jwt_segment(auth_cookie.split(".")[0])
        workspaces = auth_json.get("workspaces") or []
        if not workspaces:
            print("[Error] 授权 Cookie 里没有 workspace 信息")
            return None
        workspace_id = str((workspaces[0] or {}).get("id") or "").strip()
        if not workspace_id:
            print("[Error] 无法解析 workspace_id")
            return None

        select_body = json.dumps({"workspace_id": workspace_id})
        select_resp = s.post(
            "https://auth.openai.com/api/accounts/workspace/select",
            headers={
                "referer": "https://auth.openai.com/sign-in-with-chatgpt/codex/consent",
                "content-type": "application/json",
            },
            data=select_body,
        )

        if select_resp.status_code != 200:
            print(f"[Error] 选择 workspace 失败，状态码: {select_resp.status_code}")
            print(select_resp.text)
            return None

        continue_url = str((select_resp.json() or {}).get("continue_url") or "").strip()
        if not continue_url:
            print("[Error] workspace/select 响应里缺少 continue_url")
            return None

        current_url = continue_url
        for _ in range(6):
            final_resp = s.get(current_url, allow_redirects=False, timeout=15)
            location = final_resp.headers.get("Location") or ""

            if final_resp.status_code not in [301, 302, 303, 307, 308]:
                break
            if not location:
                break

            next_url = urllib.parse.urljoin(current_url, location)
            if "code=" in next_url and "state=" in next_url:
                return submit_callback_url(
                    callback_url=next_url,
                    code_verifier=oauth.code_verifier,
                    redirect_uri=oauth.redirect_uri,
                    expected_state=oauth.state,
                    proxies=proxies,
                )
            current_url = next_url

        print("[Error] 未能在重定向链中捕获到最终 Callback URL")
        return None

    except Exception as e:
        print(f"[Error] 运行时发生错误: {e}")
        return None


def main() -> None:
    parser = argparse.ArgumentParser(description="OpenAI 自动注册脚本")
    parser.add_argument(
        "--proxy", default="http://127.0.0.1:7890", help="代理地址（默认 http://127.0.0.1:7890）"
    )
    parser.add_argument("--once", action="store_true", help="只运行一次")
    parser.add_argument("--sleep-min", type=int, default=5, help="循环模式最短等待秒数")
    parser.add_argument(
        "--sleep-max", type=int, default=30, help="循环模式最长等待秒数"
    )
    parser.add_argument(
        "--mgmt-url", default=DEFAULT_MGMT_URL, help="CLIProxyAPI 管理接口地址"
    )
    parser.add_argument(
        "--mgmt-token", default=os.getenv("MGMT_TOKEN", ""), help="CLIProxyAPI 管理 Token"
    )
    parser.add_argument(
        "--skip-preclean-401",
        action="store_true",
        help="跳过注册前自动检查并删除401账号",
    )
    parser.add_argument(
        "--preclean-target-type",
        default=DEFAULT_PRECHECK_TARGET_TYPE,
        help="注册前401检查时过滤的账号类型",
    )
    parser.add_argument(
        "--preclean-provider",
        default=None,
        help="注册前401检查时过滤的 provider",
    )
    parser.add_argument(
        "--preclean-workers",
        type=int,
        default=DEFAULT_PRECHECK_WORKERS,
        help="注册前401检查并发数",
    )
    parser.add_argument(
        "--preclean-timeout",
        type=int,
        default=DEFAULT_PRECHECK_TIMEOUT,
        help="注册前401检查超时秒数",
    )
    parser.add_argument(
        "--preclean-retries",
        type=int,
        default=DEFAULT_PRECHECK_RETRIES,
        help="注册前401检查重试次数",
    )
    parser.add_argument(
        "--preclean-user-agent",
        default=DEFAULT_PRECHECK_UA,
        help="注册前401检查使用的 User-Agent",
    )
    parser.add_argument(
        "--preclean-chatgpt-account-id",
        default=os.getenv("CHATGPT_ACCOUNT_ID", ""),
        help="注册前401检查使用的 Chatgpt-Account-Id",
    )
    parser.add_argument(
        "--preclean-output-401",
        default=DEFAULT_PRECHECK_OUTPUT_401,
        help="注册前401账号导出文件路径",
    )
    parser.add_argument(
        "--target-account-count",
        type=int,
        default=DEFAULT_TARGET_ACCOUNT_COUNT,
        help="删除401后希望维持的目标账号数",
    )
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

    count = 0
    print("[Info] Yasal's Seamless OpenAI Auto-Registrar Started for ZJH")

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
        )

    while True:
        count += 1
        print(
            f"\n[{datetime.now().strftime('%H:%M:%S')}] >>> 开始第 {count} 次注册流程 <<<"
        )

        try:
            token_json = run(args.proxy)

            if token_json:
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
                    base_name = os.path.basename(file_name)
                    upload_url = f"{args.mgmt_url.rstrip('/')}/v0/management/auth-files?name={base_name}"
                    try:
                        headers = {
                            "Authorization": f"Bearer {args.mgmt_token}",
                            "Content-Type": "application/json"
                        }
                        resp_push = requests.post(upload_url, data=token_json.encode("utf-8"), headers=headers, timeout=15)
                        if resp_push.status_code == 200:
                            print("[*] 自动注入 CLIProxyAPI 成功，API已热加载生效！喵~")
                        else:
                            print(f"[-] 自动注入 CLIProxyAPI 失败: HTTP {resp_push.status_code} {resp_push.text}")
                    except Exception as ex:
                        print(f"[-] 自动注入过程发生错误: {ex}")
            else:
                print("[-] 本次注册失败。")

        except Exception as e:
            print(f"[Error] 发生未捕获异常: {e}")

        if args.once:
            break

        wait_time = random.randint(sleep_min, sleep_max)
        print(f"[*] 休息 {wait_time} 秒...")
        time.sleep(wait_time)


if __name__ == "__main__":
    main()
