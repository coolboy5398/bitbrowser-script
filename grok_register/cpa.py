#!/usr/bin/env python3
"""
SSO cookie → ~/.grok/auth.json 格式（纯 HTTP Device Flow）

用法:
  # 单个 / 批量 SSO，写出多个独立 auth 文件（每个可直接 cp 到 ~/.grok/auth.json）
  python3 sso_to_auth_json.py --sso sso_list.txt --out-dir ./auth_out

  # 合并到一个 json（key 带 user_id 后缀，避免覆盖）
  python3 sso_to_auth_json.py --sso sso_list.txt --out auth_merged.json --merge

  # 单行 sso
  python3 sso_to_auth_json.py --sso-cookie 'eyJ...' --out ~/.grok/auth.json
"""
from __future__ import annotations

import argparse
import base64
import json
import os
import secrets
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

from curl_cffi import requests

CLIENT_ID = "b1a00492-073a-47ea-816f-4c329264a828"
OIDC_ISSUER = "https://auth.x.ai"
AUTH_KEY = f"{OIDC_ISSUER}::{CLIENT_ID}"
SCOPES = (
    "openid profile email offline_access grok-cli:access "
    "api:access conversations:read conversations:write"
)

# --- CLIProxyAPI (CPA) 扁平格式常量 ------------------------------------------
# CPA 的 internal/auth/xai/token.go TokenStorage 读的是扁平字段。
# Build/CLI token（scope 含 grok-cli:access）必须走 cli-chat-proxy.grok.com，
# 不能用默认 api.x.ai/v1（那是计费通道，会 402）。
CPA_TOKEN_ENDPOINT = f"{OIDC_ISSUER}/oauth2/token"
CPA_GROK_BASE_URL = "https://cli-chat-proxy.grok.com/v1"
CPA_REDIRECT_URI = "http://127.0.0.1:56121/callback"
CPA_GROK_HEADERS = {
    "X-XAI-Token-Auth": "xai-grok-cli",
    "x-grok-client-version": "0.2.93",
    "x-grok-client-identifier": "grok-shell",
}


def b64url_decode(seg: str) -> bytes:
    seg += "=" * (-len(seg) % 4)
    return base64.urlsafe_b64decode(seg)


def decode_jwt_payload(token: str) -> dict:
    try:
        return json.loads(b64url_decode(token.split(".")[1]))
    except Exception:
        return {}


def rfc3339_ns(ts: float | None = None) -> str:
    """2026-07-10T01:00:00.000000000Z"""
    if ts is None:
        ts = time.time()
    dt = datetime.fromtimestamp(ts, tz=timezone.utc)
    return dt.strftime("%Y-%m-%dT%H:%M:%S") + ".000000000Z"


def _urlopen(req, proxy: str = "", timeout: int = 15):
    """urllib 请求，proxy 非空时走代理。"""
    if proxy:
        opener = urllib.request.build_opener(
            urllib.request.ProxyHandler({"http": proxy, "https": proxy})
        )
        return opener.open(req, timeout=timeout)
    return urllib.request.urlopen(req, timeout=timeout)


def request_device_code(proxy: str = "", log=print) -> dict | None:
    data = urllib.parse.urlencode({"client_id": CLIENT_ID, "scope": SCOPES}).encode()
    req = urllib.request.Request(
        f"{OIDC_ISSUER}/oauth2/device/code",
        data=data,
        method="POST",
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    try:
        with _urlopen(req, proxy=proxy, timeout=15) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        log(f"  ❌ device/code HTTP {e.code}: {e.read().decode()[:200]}")
        return None


def poll_token(device_code: str, interval: int, expires_in: int, timeout: int = 60, proxy: str = "", log=print) -> dict | None:
    deadline = time.time() + min(expires_in, timeout)
    while time.time() < deadline:
        time.sleep(interval)
        data = urllib.parse.urlencode(
            {
                "grant_type": "urn:ietf:params:oauth:grant-type:device_code",
                "client_id": CLIENT_ID,
                "device_code": device_code,
            }
        ).encode()
        req = urllib.request.Request(
            f"{OIDC_ISSUER}/oauth2/token",
            data=data,
            method="POST",
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        try:
            with _urlopen(req, proxy=proxy, timeout=15) as resp:
                return json.loads(resp.read())
        except urllib.error.HTTPError as e:
            err = json.loads(e.read())
            error = err.get("error", "")
            if error == "authorization_pending":
                continue
            if error == "slow_down":
                interval += 5
                continue
            log(f"  ❌ token: {error}")
            return None
    log("  ❌ 轮询超时")
    return None


def sso_to_token(sso_cookie: str, proxy: str = "", log=print) -> dict | None:
    """SSO cookie → token dict (access/refresh/expires_in)。proxy 非空时全程走代理。"""
    proxies = {"http": proxy, "https": proxy} if proxy else None
    s = requests.Session()
    if proxies:
        s.proxies = proxies
    s.cookies.set("sso", sso_cookie, domain=".x.ai")

    try:
        r = s.get("https://accounts.x.ai/", impersonate="chrome", timeout=15)
    except Exception as e:
        log(f"  ❌ 网络错误: {e}")
        return None
    if "sign-in" in r.url or "sign-up" in r.url:
        log("  ❌ sso 无效")
        return None
    log("  ✅ sso 有效")

    log("  🔑 Device Flow...")
    dc = request_device_code(proxy=proxy, log=log)
    if not dc:
        return None
    log(f"  📋 user_code: {dc.get('user_code')}")

    try:
        s.get(dc["verification_uri_complete"], impersonate="chrome", timeout=15)
        r = s.post(
            f"{OIDC_ISSUER}/oauth2/device/verify",
            data={"user_code": dc["user_code"]},
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            impersonate="chrome",
            timeout=15,
            allow_redirects=True,
        )
        if "consent" not in r.url:
            log(f"  ❌ verify 失败: {r.url}")
            return None
    except Exception as e:
        log(f"  ❌ verify 异常: {e}")
        return None

    try:
        r = s.post(
            f"{OIDC_ISSUER}/oauth2/device/approve",
            data={
                "user_code": dc["user_code"],
                "action": "allow",
                "principal_type": "User",
                "principal_id": "",
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            impersonate="chrome",
            timeout=15,
            allow_redirects=True,
        )
        if "done" not in r.url:
            log(f"  ❌ approve 失败: {r.url}")
            return None
        log("  ✅ 授权确认")
    except Exception as e:
        log(f"  ❌ approve 异常: {e}")
        return None

    token = poll_token(
        dc["device_code"],
        dc.get("interval", 5),
        dc.get("expires_in", 1800),
        proxy=proxy,
        log=log,
    )
    if not token:
        return None
    log(
        f"  ✅ access_token (expires_in={token.get('expires_in')}s)"
        + (" + refresh_token" if token.get("refresh_token") else "")
    )
    token["mint_method"] = "device"
    return token


class PKCEMintError(RuntimeError):
    """PKCE protocol path failed; caller may fall back to device flow."""


def _pkce_b64url(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _pkce_code_verifier() -> str:
    return _pkce_b64url(secrets.token_bytes(48))


def _pkce_code_challenge(verifier: str) -> str:
    import hashlib

    return _pkce_b64url(hashlib.sha256(verifier.encode("ascii")).digest())


def _pkce_session(proxy: str = ""):
    kwargs = {"impersonate": "chrome131"}
    if proxy:
        kwargs["proxies"] = {"http": proxy, "https": proxy}
    return requests.Session(**kwargs)


def _pkce_set_sso_cookie(session, sso_cookie: str) -> None:
    sso_cookie = (sso_cookie or "").strip()
    if not sso_cookie:
        raise PKCEMintError("empty sso cookie")
    for domain in ("accounts.x.ai", ".accounts.x.ai", ".x.ai", "auth.x.ai"):
        for name in ("sso", "sso-rw"):
            try:
                session.cookies.set(name, sso_cookie, domain=domain, path="/")
            except Exception:
                pass


def _pkce_grpc_headers(referer: str) -> dict[str, str]:
    return {
        "content-type": "application/grpc-web+proto",
        "x-grpc-web": "1",
        "x-user-agent": "connect-es/2.1.1",
        "accept": "*/*",
        "origin": "https://accounts.x.ai",
        "referer": referer,
        "sec-fetch-site": "same-origin",
        "sec-fetch-mode": "cors",
        "sec-fetch-dest": "empty",
    }


def _pkce_extract_urls_from_fields(fields: list[dict]) -> list[str]:
    import cpa_grpcweb as grpcweb

    urls: list[str] = []
    for field in fields:
        if field.get("type") == "string":
            value = str(field.get("value") or "")
            if value.startswith(("http://", "https://")):
                urls.append(value)
        elif field.get("type") == "bytes" and field.get("hex"):
            try:
                urls.extend(
                    _pkce_extract_urls_from_fields(
                        grpcweb.decode_message(bytes.fromhex(field["hex"]))
                    )
                )
            except Exception:
                pass
    return urls


def _pkce_parse_grpc_error(headers: dict[str, str], body: bytes) -> tuple[int | None, str]:
    import cpa_grpcweb as grpcweb

    status = headers.get("grpc-status")
    message = urllib.parse.unquote(headers.get("grpc-message") or "")
    if status is not None:
        try:
            return int(status), message
        except ValueError:
            return None, message
    try:
        parsed = grpcweb.parse_response(body)
    except Exception:
        return None, message
    if parsed.get("grpc_status") is not None:
        return int(parsed["grpc_status"]), message or str(parsed.get("trailers") or "")
    return None, message


def _pkce_build_authorization_url(
    *,
    state: str,
    nonce: str,
    code_challenge: str,
    redirect_uri: str = CPA_REDIRECT_URI,
) -> str:
    params = {
        "client_id": CLIENT_ID,
        "code_challenge": code_challenge,
        "code_challenge_method": "S256",
        "nonce": nonce,
        "plan": "generic",
        "redirect_uri": redirect_uri,
        "referrer": "cli-proxy-api",
        "response_type": "code",
        "scope": SCOPES,
        "state": state,
    }
    return f"{OIDC_ISSUER}/oauth2/authorize?" + urllib.parse.urlencode(params)


def _pkce_code_from_url(url: str, state: str) -> str:
    qs = urllib.parse.parse_qs(urllib.parse.urlparse(url).query)
    if (qs.get("state") or [""])[0] != state:
        raise PKCEMintError("authorization failed: state mismatch")
    code = (qs.get("code") or [""])[0]
    if not code:
        raise PKCEMintError(f"authorization failed: missing code in {url[:200]}")
    return code


def _pkce_create_cookie_setter_link(session, success_url: str) -> str:
    import cpa_grpcweb as grpcweb

    accounts_origin = "https://accounts.x.ai"
    rpc = f"{accounts_origin}/auth_mgmt.AuthManagement/CreateCookieSetterLink"
    msg = grpcweb.encode_string(1, success_url) + grpcweb.encode_string(2, f"{accounts_origin}/sign-in")
    resp = session.post(
        rpc,
        headers=_pkce_grpc_headers(f"{accounts_origin}/sign-in?redirect=oauth2-provider"),
        data=grpcweb.frame_request(msg),
        timeout=45,
    )
    hdrs = {k.lower(): v for k, v in resp.headers.items()}
    header_status, header_msg = _pkce_parse_grpc_error(hdrs, resp.content)
    try:
        parsed = grpcweb.parse_response(resp.content)
    except Exception:
        parsed = {"messages": [], "trailers": {}, "grpc_status": None}
    grpc_status = parsed.get("grpc_status")
    if grpc_status is None:
        grpc_status = header_status
    grpc_msg = header_msg or urllib.parse.unquote(
        str((parsed.get("trailers") or {}).get("grpc-message") or "")
    )
    fields = parsed["messages"][0] if parsed.get("messages") else []
    urls = _pkce_extract_urls_from_fields(fields)
    cookie_setter = next((u for u in urls if "set-cookie" in u), None) or (urls[0] if urls else "")
    if grpc_status not in (None, 0) or not cookie_setter:
        raise PKCEMintError(grpc_msg or "CreateCookieSetterLink failed")
    return cookie_setter


def _pkce_submit_consent(
    session,
    *,
    page_url: str,
    page_html: str,
    state: str,
    code_challenge: str,
    nonce: str,
    redirect_uri: str = CPA_REDIRECT_URI,
) -> str:
    import re

    action_id = "4005315a1d7e426de592990bb54bb37471f39dd6d2"
    match = re.search(r'createServerReference\)\("([a-f0-9]{40,44})"[^)]*submitOAuth2Consent', page_html)
    if not match:
        match = re.search(r'createServerReference\)\("([a-f0-9]{40,44})"', page_html)
    if match:
        action_id = match.group(1)

    accounts_origin = "https://accounts.x.ai"
    router_tree = (
        '["",{"children":["(app)",{"children":["(auth)",{"children":["oauth2",'
        '{"children":["consent",{"children":["__PAGE__",{}]}]}]}]}]},'
        '"$undefined","$undefined",16]'
    )
    payload = [
        {
            "action": "allow",
            "clientId": CLIENT_ID,
            "redirectUri": redirect_uri,
            "scope": SCOPES,
            "state": state,
            "codeChallenge": code_challenge,
            "codeChallengeMethod": "S256",
            "nonce": nonce,
            "principalType": "User",
            "principalId": "",
            "referrer": "",
        }
    ]
    headers = {
        "accept": "text/x-component",
        "content-type": "text/plain;charset=UTF-8",
        "next-action": action_id,
        "next-router-state-tree": urllib.parse.quote(router_tree, safe=""),
        "origin": accounts_origin,
        "referer": page_url,
        "sec-fetch-site": "same-origin",
        "sec-fetch-mode": "cors",
        "sec-fetch-dest": "empty",
    }
    body = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    post_url = page_url.split("?")[0] if "consent" in page_url else page_url
    resp = session.post(post_url, headers=headers, data=body, timeout=45)
    text = resp.text or ""
    if resp.status_code >= 400 or ("error" in text[:200].lower() and "code" not in text):
        resp = session.post(page_url, headers=headers, data=body, timeout=45)
        text = resp.text or ""

    match = re.search(r'"code"\s*:\s*"([^"]+)"', text)
    if match:
        return match.group(1)
    match = re.search(r"code=([A-Za-z0-9._~\-]+)", text)
    if match and "error" not in match.group(0):
        return match.group(1)
    loc = resp.headers.get("location") or resp.headers.get("Location") or ""
    if "code=" in loc:
        return _pkce_code_from_url(urllib.parse.urljoin(page_url, loc), state)
    raise PKCEMintError(f"submitOAuth2Consent failed HTTP {resp.status_code}: {text[:300]}")


def _pkce_exchange_code_for_token(session, *, code: str, verifier: str, redirect_uri: str = CPA_REDIRECT_URI) -> dict:
    resp = session.post(
        CPA_TOKEN_ENDPOINT,
        data={
            "grant_type": "authorization_code",
            "client_id": CLIENT_ID,
            "code": code,
            "redirect_uri": redirect_uri,
            "code_verifier": verifier,
        },
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        timeout=45,
    )
    if resp.status_code != 200:
        raise PKCEMintError(f"token exchange failed HTTP {resp.status_code}: {resp.text[:300]}")
    token = resp.json()
    if not token.get("access_token") or not token.get("refresh_token"):
        raise PKCEMintError("token exchange response missing access_token/refresh_token")
    return token


def sso_to_token_pkce(sso_cookie: str, proxy: str = "", log=print, email: str = "") -> dict | None:
    """SSO cookie → token dict via PKCE authorization-code flow (recommended for chat)."""
    try:
        session = _pkce_session(proxy)
        _pkce_set_sso_cookie(session, sso_cookie)

        state = secrets.token_hex(16)
        nonce = secrets.token_hex(16)
        verifier = _pkce_code_verifier()
        challenge = _pkce_code_challenge(verifier)
        auth_url = _pkce_build_authorization_url(state=state, nonce=nonce, code_challenge=challenge)
        consent_url = (
            "https://accounts.x.ai/oauth2/consent?"
            + urllib.parse.urlencode(
                {
                    "response_type": "code",
                    "client_id": CLIENT_ID,
                    "redirect_uri": CPA_REDIRECT_URI,
                    "scope": SCOPES,
                    "state": state,
                    "code_challenge": challenge,
                    "code_challenge_method": "S256",
                    "nonce": nonce,
                }
            )
        )

        session.get(auth_url, allow_redirects=False, timeout=30)
        setter = _pkce_create_cookie_setter_link(session, consent_url)
        log("  ✅ PKCE cookie-setter ok")

        current = setter
        code = ""
        for _ in range(6):
            if "code=" in current and (current.startswith(CPA_REDIRECT_URI) or "127.0.0.1" in current):
                code = _pkce_code_from_url(current, state)
                break
            if "set-cookie" not in current:
                break
            resp = session.get(current, allow_redirects=False, timeout=30)
            loc = resp.headers.get("location") or resp.headers.get("Location") or ""
            if not loc:
                break
            current = urllib.parse.urljoin(current, loc)

        if not code:
            if "consent" not in current:
                raise PKCEMintError(f"cookie-setter did not reach consent/code: {current[:180]}")
            page = session.get(current, allow_redirects=False, timeout=30)
            loc = page.headers.get("location") or page.headers.get("Location") or ""
            if loc and "code=" in loc:
                code = _pkce_code_from_url(urllib.parse.urljoin(current, loc), state)
            else:
                code = _pkce_submit_consent(
                    session,
                    page_url=current,
                    page_html=page.text or "",
                    state=state,
                    code_challenge=challenge,
                    nonce=nonce,
                )
        log(f"  ✅ PKCE authorization code ok{f' ({email})' if email else ''}")

        token = _pkce_exchange_code_for_token(session, code=code, verifier=verifier)
        token["mint_method"] = "pkce"
        log(
            f"  ✅ PKCE access_token (expires_in={token.get('expires_in')}s)"
            + (" + refresh_token" if token.get("refresh_token") else "")
        )
        return token
    except PKCEMintError as exc:
        log(f"  ❌ PKCE: {exc}")
        return None
    except Exception as exc:
        log(f"  ❌ PKCE 异常: {exc}")
        return None


def sso_to_token_with_fallback(
    sso_cookie: str,
    proxy: str = "",
    log=print,
    email: str = "",
    prefer_pkce: bool = True,
) -> dict | None:
    """Try PKCE first, fall back to device flow."""
    if prefer_pkce:
        log("  🔑 PKCE authorization-code flow...")
        token = sso_to_token_pkce(sso_cookie, proxy=proxy, log=log, email=email)
        if token:
            return token
        log("  ↩ PKCE 失败，回退 Device Flow...")
    return sso_to_token(sso_cookie, proxy=proxy, log=log)


def probe_models(access_token: str, proxy: str = "", timeout: float = 30.0) -> dict:
    """Probe /v1/models for grok-4.5 availability."""
    url = f"{CPA_GROK_BASE_URL}/models"
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Accept": "application/json",
        **CPA_GROK_HEADERS,
    }
    req = urllib.request.Request(url, headers=headers, method="GET")
    try:
        with _urlopen(req, proxy=proxy, timeout=int(timeout)) as resp:
            body = json.loads(resp.read().decode("utf-8"))
            ids = [x.get("id") for x in body.get("data") or [] if isinstance(x, dict)]
            return {
                "ok": True,
                "status": getattr(resp, "status", 200),
                "model_ids": ids,
                "has_grok_45": any(i == "grok-4.5" for i in ids),
            }
    except urllib.error.HTTPError as e:
        return {
            "ok": False,
            "status": e.code,
            "error": e.read().decode("utf-8", errors="replace")[:500],
            "model_ids": [],
            "has_grok_45": False,
        }
    except Exception as e:
        return {
            "ok": False,
            "status": 0,
            "error": str(e),
            "model_ids": [],
            "has_grok_45": False,
        }


def probe_mini_chat(access_token: str, proxy: str = "", timeout: float = 60.0) -> dict:
    """Minimal /v1/responses chat probe."""
    url = f"{CPA_GROK_BASE_URL}/responses"
    payload = {
        "model": "grok-4.5",
        "stream": False,
        "input": "Reply with exactly MINT_OK",
        "reasoning": {"effort": "low"},
    }
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json",
        "Accept": "application/json",
        **CPA_GROK_HEADERS,
    }
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers=headers, method="POST")
    try:
        with _urlopen(req, proxy=proxy, timeout=int(timeout)) as resp:
            body = json.loads(resp.read().decode("utf-8"))
            texts: list[str] = []
            for item in body.get("output") or []:
                if item.get("type") == "message":
                    for c in item.get("content") or []:
                        if c.get("type") == "output_text":
                            texts.append(c.get("text") or "")
            return {
                "ok": True,
                "status": getattr(resp, "status", 200),
                "model": body.get("model"),
                "text": "\n".join(texts),
            }
    except urllib.error.HTTPError as e:
        return {
            "ok": False,
            "status": e.code,
            "error": e.read().decode("utf-8", errors="replace")[:800],
        }
    except Exception as e:
        return {"ok": False, "status": 0, "error": str(e)}


def probe_cpa_token(
    access_token: str,
    proxy: str = "",
    probe_chat: bool = True,
    log=print,
) -> bool:
    """Return True if token passes probe checks."""
    pr = probe_models(access_token, proxy=proxy)
    log(
        f"  probe models: ok={pr.get('ok')} has_grok_45={pr.get('has_grok_45')} "
        f"ids={pr.get('model_ids')}"
    )
    if not pr.get("has_grok_45"):
        return False
    if probe_chat:
        ch = probe_mini_chat(access_token, proxy=proxy)
        log(f"  probe chat: ok={ch.get('ok')} text={ch.get('text')!r}")
        return bool(ch.get("ok"))
    return True


def token_to_auth_entry(token: dict, email: str = "") -> tuple[str, dict]:
    """
    返回 (top_level_key, entry)
    top_level_key 固定为 issuer::client_id（与 ~/.grok/auth.json 一致）
    """
    access = token.get("access_token") or token.get("key") or ""
    refresh = token.get("refresh_token") or ""
    payload = decode_jwt_payload(access)

    user_id = payload.get("sub") or payload.get("principal_id") or ""
    principal_id = payload.get("principal_id") or user_id
    principal_type = payload.get("principal_type") or "User"

    expires_in = int(token.get("expires_in") or 21600)
    # 优先用 JWT exp
    if "exp" in payload:
        expires_at = rfc3339_ns(float(payload["exp"]))
    else:
        expires_at = rfc3339_ns(time.time() + expires_in)

    iat = payload.get("iat")
    create_time = rfc3339_ns(float(iat) if iat else time.time())

    entry = {
        "key": access,
        "auth_mode": "oidc",
        "create_time": create_time,
        "user_id": user_id,
        "email": email or "",
        "principal_type": principal_type,
        "principal_id": principal_id,
        "refresh_token": refresh,
        "expires_at": expires_at,
        "oidc_issuer": OIDC_ISSUER,
        "oidc_client_id": CLIENT_ID,
    }
    return AUTH_KEY, entry


def _iso_utc_from_unix(ts) -> str:
    """unix 秒 → CPA 认的 RFC3339（秒级，带 Z）。"""
    try:
        return datetime.fromtimestamp(int(ts), tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    except Exception:
        return ""


def _safe_email_for_filename(email: str) -> str:
    safe = "".join(ch if ch.isalnum() or ch in "._-@" else "_" for ch in email)
    return safe or "unknown"


def token_to_cpa_record(token: dict, email: str = "") -> dict:
    """token dict → CLIProxyAPI 扁平 xai auth 记录。

    对齐 CPA internal/auth/xai/token.go 的 TokenStorage 字段，以及
    grok-build-auth build_cliproxyapi_auth_record 的输出。
    """
    access = token.get("access_token") or token.get("key") or ""
    refresh = token.get("refresh_token") or ""
    id_token = token.get("id_token") or ""
    payload = decode_jwt_payload(access)
    id_payload = decode_jwt_payload(id_token) if id_token else {}

    if not email:
        email = id_payload.get("email") or payload.get("email") or ""
    sub = payload.get("sub") or id_payload.get("sub") or ""

    # expired: 优先 access token 的 exp，其次 expires_in 推算
    expired = ""
    if "exp" in payload:
        expired = _iso_utc_from_unix(payload["exp"])
    elif token.get("expires_in") is not None:
        try:
            expired = _iso_utc_from_unix(int(time.time()) + int(token["expires_in"]))
        except Exception:
            expired = ""

    return {
        "type": "xai",
        "auth_kind": "oauth",
        "email": email or "",
        "sub": sub,
        "access_token": access,
        "refresh_token": refresh,
        "id_token": id_token,
        "token_type": token.get("token_type", "Bearer"),
        "expires_in": token.get("expires_in", None),
        "expired": expired,
        "last_refresh": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "redirect_uri": CPA_REDIRECT_URI,
        "token_endpoint": CPA_TOKEN_ENDPOINT,
        "base_url": CPA_GROK_BASE_URL,
        "disabled": False,
        "headers": dict(CPA_GROK_HEADERS),
    }


def cpa_auth_filename(record: dict) -> str:
    """生成 CPA auth 文件名：xai-<email>.json。"""
    ident = str(record.get("email") or "").strip() or str(record.get("sub") or "").strip()
    safe = _safe_email_for_filename(ident)
    # 避免 email 本地部分已是 xai 时出现 "xai-xai..."
    fname = safe if safe.lower().startswith("xai") else f"xai-{safe}"
    return f"{fname}.json"


def write_cpa_auth(auth_dir: Path, record: dict) -> Path:
    """写出 CPA 可热加载的 xai-<email>.json（原子替换）。

    无 email 时用 sub(user_id) 命名，避免多个无 email 账号写成同一个
    xai-unknown.json 互相覆盖。
    """
    auth_dir.mkdir(parents=True, exist_ok=True)
    path = auth_dir / cpa_auth_filename(record)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(record, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(tmp, path)
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass
    return path


def upload_cpa_auth_remote(
    base_url: str,
    management_key: str,
    record: dict,
    timeout: int = 30,
) -> str:
    """通过 CPA Management API 上传 auth 文件到远程实例。

    POST /v0/management/auth-files?name=<file.json>
    Header: Authorization: Bearer <management_key>
    Body: raw JSON auth record
    """
    import requests

    base = str(base_url or "").strip().rstrip("/")
    key = str(management_key or "").strip()
    if not base:
        raise ValueError("cpa_remote_url 为空")
    if not key:
        raise ValueError("cpa_management_key 为空")

    name = cpa_auth_filename(record)
    url = f"{base}/v0/management/auth-files"
    resp = requests.post(
        url,
        params={"name": name},
        headers={
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
        },
        data=json.dumps(record, ensure_ascii=False).encode("utf-8"),
        timeout=timeout,
    )
    if resp.status_code >= 400:
        body = (resp.text or "").strip()
        if len(body) > 300:
            body = body[:300] + "..."
        raise RuntimeError(f"远程上传失败 HTTP {resp.status_code}: {body or resp.reason}")
    return name


def write_auth_json(path: Path, auth_key: str, entry: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    data = {auth_key: entry}
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    os.replace(tmp, path)


def merge_auth_json(path: Path, auth_key: str, entry: dict, unique: bool = True) -> None:
    """
    合并写入。unique=True 时 key 变成 issuer::client_id::user_id，避免多账号互相覆盖。
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    existing: dict = {}
    if path.exists():
        try:
            existing = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            existing = {}
    key = auth_key
    if unique and entry.get("user_id"):
        key = f"{auth_key}::{entry['user_id']}"
    existing[key] = entry
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(existing, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    os.replace(tmp, path)


def load_sso_list(path: str | None, single: str | None) -> list[str]:
    if single:
        return [single.strip()]
    if not path:
        return []
    out = []
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        # 兼容 邮箱----密码----sso
        if "----" in line:
            parts = line.split("----")
            line = parts[-1].strip()
        out.append(line)
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description="SSO cookie → grok auth.json (纯 HTTP)")
    ap.add_argument("--sso", metavar="FILE", help="sso 列表文件（一行一个 JWT，或 邮箱----密码----sso）")
    ap.add_argument("--sso-cookie", metavar="JWT", help="单个 sso cookie")
    ap.add_argument("--out", default=None, help="输出 auth.json 路径（单账号或 --merge）")
    ap.add_argument(
        "--out-dir",
        default=None,
        help="批量时每个账号写一个 {user_id}.json（可直接 cp 到 ~/.grok/auth.json）",
    )
    ap.add_argument(
        "--merge",
        action="store_true",
        help="合并到 --out，key 用 issuer::client_id::user_id",
    )
    ap.add_argument("--delay", type=int, default=0, help="每个间隔秒数")
    ap.add_argument("--email", default="", help="写入 entry.email（可选）")
    ap.add_argument(
        "--cpa-auth-dir",
        default=None,
        help="额外写出 CLIProxyAPI 扁平格式 xai-<email>.json 到该目录（CPA 热加载）",
    )
    ap.add_argument(
        "--cpa-remote-url",
        default=None,
        help="远程 CPA 地址，如 http://你的CPA地址:8317；配合 --cpa-management-key 通过 Management API 上传",
    )
    ap.add_argument(
        "--cpa-management-key",
        default=None,
        help="远程 CPA 管理密钥（remote-management.secret-key 明文）",
    )
    ap.add_argument("--proxy", default="", help="device-flow 走代理，如 http://127.0.0.1:7890")
    ap.add_argument(
        "--prefer-pkce",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="优先 PKCE authorization-code（默认开启）；关闭则仅用 Device Flow",
    )
    ap.add_argument(
        "--probe",
        action="store_true",
        help="写出 CPA 后探测 /v1/models 是否含 grok-4.5",
    )
    args = ap.parse_args()

    cookies = load_sso_list(args.sso, args.sso_cookie)
    if not cookies:
        ap.error("需要 --sso 或 --sso-cookie")

    if args.cpa_remote_url and not args.cpa_management_key:
        ap.error("使用 --cpa-remote-url 时必须同时提供 --cpa-management-key")
    if args.cpa_management_key and not args.cpa_remote_url:
        ap.error("使用 --cpa-management-key 时必须同时提供 --cpa-remote-url")

    if len(cookies) > 1 and not args.out_dir and not args.merge:
        # 默认批量写目录
        args.out_dir = args.out_dir or "./auth_out"
        print(f"批量模式默认 --out-dir {args.out_dir}")

    # 只指定 CPA 目标时不再默认写官方 ~/.grok/auth.json
    if (
        args.out is None
        and args.out_dir is None
        and not args.cpa_auth_dir
        and not args.cpa_remote_url
        and len(cookies) == 1
    ):
        args.out = str(Path.home() / ".grok" / "auth.json")

    print(f"🚀 SSO → auth.json: {len(cookies)} 个, delay={args.delay}s")
    ok = 0
    fail = 0

    for i, sso in enumerate(cookies, 1):
        print(f"\n{'=' * 60}\n[{i}/{len(cookies)}] ...\n{'=' * 60}")
        try:
            token = sso_to_token_with_fallback(
                sso,
                proxy=args.proxy,
                prefer_pkce=args.prefer_pkce,
            )
            if not token:
                fail += 1
                print(f"  ❌ [{i}] 失败")
                continue
            key, entry = token_to_auth_entry(token, email=args.email)
            uid = entry.get("user_id") or secrets.token_hex(4)

            if args.out_dir:
                p = Path(args.out_dir) / f"{uid}.json"
                write_auth_json(p, key, entry)
                print(f"  💾 {p}")
            if args.out:
                if args.merge or len(cookies) > 1:
                    merge_auth_json(Path(args.out), key, entry, unique=True)
                    print(f"  💾 merge → {args.out}")
                else:
                    write_auth_json(Path(args.out), key, entry)
                    print(f"  💾 {args.out}")

            if args.cpa_auth_dir or args.cpa_remote_url:
                record = token_to_cpa_record(token, email=args.email)
                if args.cpa_auth_dir:
                    cp = write_cpa_auth(Path(args.cpa_auth_dir), record)
                    print(f"  💾 CPA 本地 → {cp}")
                if args.cpa_remote_url:
                    name = upload_cpa_auth_remote(
                        args.cpa_remote_url,
                        args.cpa_management_key,
                        record,
                    )
                    print(f"  💾 CPA 远程 → {args.cpa_remote_url.rstrip('/')}/.../{name}")
                if args.probe:
                    access = record.get("access_token") or ""
                    if access and not probe_cpa_token(access, proxy=args.proxy, log=print):
                        print("  ⚠ probe 未通过（grok-4.5 不可用）")
                    elif access:
                        print("  ✅ probe 通过")

            ok += 1
            print(f"  ✅ [{i}] 完成 user_id={uid[:12]}...")
        except Exception as e:
            fail += 1
            print(f"  ❌ [{i}] 异常: {e}")

        if args.delay > 0 and i < len(cookies):
            time.sleep(args.delay)

    print(f"\n{'=' * 60}\n📊 完成: {ok}/{len(cookies)} 成功, {fail} 失败")
    return 0 if fail == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
