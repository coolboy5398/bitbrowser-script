from mail_service import MailService
from curl_cffi import requests as curl_requests
import base64
import hashlib
import json
import os
import secrets
import time
from datetime import datetime, timedelta, timezone
from concurrent.futures import ThreadPoolExecutor, as_completed

num = input("注册个数：")
threads = input("线程数(默认4)：").strip()
threads = int(threads) if threads else 4

url = "https://chat.qwen.ai/api/v1/auths/signup"

payload = json.dumps(
    {
        "name": "xixilili111",
        # 后续自动补充
        "email": "",
        # AlIlzHZkJ4zG6J
        "password": "3e44fb4816bed138eb46440954b79b3518d6cde7a58248d770410cb6be563c89",
        "agree": True,
        "profile_image_url": "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAGQAAABkCAYAAABw4pVUAAAAAXNSR0IArs4c6QAAAlxJREFUeF7tmbFKHGEURu+4O3FX0AdICq2NETWddgERQQSx3ULfIYVFHiBFXk/fQDsLsZSQsFokCopX5o5n4Ww99/7fnjPfDMs2p5PrP+EHQ6BRCMbFfRCFsHwoBOZDIQqhEYDl8R2iEBgBWBwbohAYAVgcG6IQGAFYHBuiEBgBWBwbohAYAVgcG6IQGAFYHBuiEBgBWBwbohAYAVgcG6IQGAFYHBuiEBgBWBwbohAYAVgcG6IQGAFYHBuiEBgBWBwbohAYAVgcG6KQ7giMRk3s7o3i2+58LC3NRdNEXF3+jh9nN90d0vOmmWvIx0+D2NhqY22tjeWVYYwXmkfIFNLjHXR4NI6Dw3EMh88fqpAehRwdj2P/QCE9In/5qM2tD7H5tY25wb/rpu+RL+tttO3Do8uGvLOu7Z35mJwsxFSMQt5ZxvR4hQAk/B9BIQopJTBzv0Oe0rAhpfdHfrlC8sxKJxRSije/XCF5ZqUTCinFm1+ukDyz0gmFlOLNL1dInlnphEJK8eaXKyTPrHRCIaV488sVkmdWOqGQUrz55QrJMyudUEgp3vxyheSZlU4opBRvfrlC8sw6mfh+thirn9s377o4v4tfP2/fPN/X4Mz8hauQvm6JV56jkFeC8rJuCczMI6vbr83dphCYG4UoBEYAFseGKARGABbHhigERgAWx4YoBEYAFseGKARGABbHhigERgAWx4YoBEYAFseGKARGABbHhigERgAWx4YoBEYAFseGKARGABbHhigERgAWx4YoBEYAFseGKARGABbHhigERgAWx4YoBEYAFucv1Ia+eKkOMMMAAAAASUVORK5CYII=",
        "oauth_sub": "",
        "oauth_token": "",
        "module": "chat",
    }
)
headers = {"Content-Type": "application/json"}


def _generate_pkce():
    code_verifier = (
        base64.urlsafe_b64encode(secrets.token_bytes(32)).rstrip(b"=").decode("ascii")
    )
    code_challenge = (
        base64.urlsafe_b64encode(hashlib.sha256(code_verifier.encode("ascii")).digest())
        .rstrip(b"=")
        .decode("ascii")
    )
    return code_verifier, code_challenge


def oauth_device_flow(session, email, cookie_header=""):
    token_data = None
    client_id = "f0304373b74a44d2b584a3fb70ca9e56"
    scope = "openid profile email model.completion"

    code_verifier, code_challenge = _generate_pkce()

    device_resp = session.post(
        "https://chat.qwen.ai/api/v1/oauth2/device/code",
        data={
            "client_id": client_id,
            "scope": scope,
            "code_challenge": code_challenge,
            "code_challenge_method": "S256",
        },
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    if device_resp.status_code != 200:
        raise RuntimeError(
            f"Device code request failed [{device_resp.status_code}]: {device_resp.text[:200]}"
        )

    device_data = device_resp.json()
    device_code = device_data["device_code"]
    user_code = device_data.get("user_code", "")
    verification_uri = device_data.get("verification_uri_complete") or device_data.get(
        "verification_uri", ""
    )

    if verification_uri:
        print(f"[INFO] verification_uri: {verification_uri}")
    else:
        print("[WARN] 未返回 verification_uri，请检查响应")

    if user_code and cookie_header:
        auth_headers = {"Content-Type": "application/json", "Cookie": cookie_header}
        auth_resp = session.post(
            "https://chat.qwen.ai/api/v2/oauth2/authorize",
            json={"approved": True, "user_code": user_code},
            headers=auth_headers,
        )
        if auth_resp.status_code != 200:
            print(
                f"[WARN] authorize failed [{auth_resp.status_code}]: {auth_resp.text[:200]}"
            )
        else:
            print("[INFO] authorize ok")
    else:
        print("[WARN] 缺少 user_code 或 Cookie，未执行 authorize")

    grant_type = "urn:ietf:params:oauth:grant-type:device_code"
    for attempt in range(60):
        time.sleep(5)
        token_resp = session.post(
            "https://chat.qwen.ai/api/v1/oauth2/token",
            data={
                "grant_type": grant_type,
                "client_id": client_id,
                "device_code": device_code,
                "code_verifier": code_verifier,
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )

        if token_resp.status_code == 200:
            oauth_data = token_resp.json()
            now = datetime.now(timezone(timedelta(hours=8)))
            expires_in = oauth_data.get("expires_in", 21600)
            expired = now + timedelta(seconds=expires_in)
            token_data = {
                "type": "qwen",
                "email": email,
                "expired": expired.isoformat(),
                "access_token": oauth_data["access_token"],
                "last_refresh": now.isoformat(),
                "resource_url": oauth_data.get("resource_url", "portal.qwen.ai"),
                "refresh_token": oauth_data.get("refresh_token", ""),
            }
            print(f"[INFO] OAuth token obtained (attempt {attempt + 1})")
            break

        try:
            err_data = token_resp.json()
            err_code = err_data.get("error", "")
        except Exception:
            err_code = ""

        if err_code == "authorization_pending":
            continue
        if err_code == "slow_down":
            time.sleep(5)
            continue
        if err_code in ("expired_token", "access_denied"):
            print(f"[WARN] OAuth token denied: {err_code}")
            break

        print(
            f"[WARN] Token poll unexpected [{token_resp.status_code}]: {token_resp.text[:200]}"
        )
        break

    return token_data


def _cookies_to_header(cookies):
    if hasattr(cookies, "get_dict"):
        cookie_dict = cookies.get_dict()
    else:
        try:
            cookie_dict = dict(cookies)
        except Exception:
            return str(cookies)
    return "; ".join([f"{k}={v}" for k, v in cookie_dict.items()])


def regup():
    email_addr = ""
    print("正在获取邮箱")

    s = MailService()
    email = s.request_email()
    if email.success != True:
        print("[ERROR]邮箱获取失败：" + email.error)
        return
    else:
        email_addr = email.email or ""
        print("[INFO]邮箱获取成功：" + email_addr)
    _payload = json.loads(payload)
    _payload["email"] = email_addr

    with curl_requests.Session(impersonate="chrome119") as session:
        n = session.post(url, json=_payload)
        cookie = n.cookies
        session.cookies.update(cookie)
        print(cookie)
        vurl = s.poll_code(email_addr)
        print(vurl)
        session.get(url=vurl, cookies=cookie)

        cookie_header = _cookies_to_header(session.cookies)
        print(f"[INFO] Email: {email_addr} Cookie header: {cookie_header}")

        try:
            token_data = oauth_device_flow(
                session, email_addr, cookie_header=cookie_header
            )
        except Exception as e:
            print(f"[WARN] Token extraction failed: {e}")
            token_data = None

    if token_data:
        os.makedirs("tokens", exist_ok=True)
        token_file = os.path.join("tokens", f"{email_addr}.json")
        with open(token_file, "w", encoding="utf-8") as f:
            json.dump(token_data, f, ensure_ascii=False, indent=2)
        print(f"[INFO] Token saved to {token_file}")


def main():
    total = int(num)
    if total <= 0:
        return

    max_workers = max(1, min(threads, total))
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = [executor.submit(regup) for _ in range(total)]
        for future in as_completed(futures):
            try:
                future.result()
            except Exception as e:
                print(f"[ERROR] 线程任务异常: {e}")


if __name__ == "__main__":
    main()
