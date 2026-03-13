"""OB-1 注册主流程 — 纯 HTTP 协议 + 邮箱 provider 自动接码

流程：
1. 创建 provider 邮箱地址
2. 发起 WorkOS device auth，获取 user_code + verification_uri
3. 用户在浏览器打开链接，并使用脚本生成的邮箱注册/登录
4. 后台通过 providers 统一接口轮询邮箱并提取验证码
5. 轮询 device auth 直到授权完成
6. 获取 access_token + refresh_token
7. 拉取 org 信息
8. 保存到 accounts.json
"""

import asyncio
import json
import os
import sys
import time

import httpx

CURRENT_DIR = os.path.dirname(__file__)
PROJECT_ROOT = os.path.abspath(os.path.join(CURRENT_DIR, ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from providers import EmailProviderFactory

from config import (
    WORKOS_CLIENT_ID,
    WORKOS_DEVICE_AUTH_URL,
    WORKOS_AUTH_URL,
    OB1_API_BASE,
    PROXY_URL,
    ACCOUNTS_JSON,
    EMAIL_PROVIDER,
    EMAIL_PROVIDER_CONFIG,
    EMAIL_CODE_TIMEOUT,
    EMAIL_CHECK_INTERVAL,
    EMAIL_POLL_CHUNK_TIMEOUT,
)


def _http_client() -> httpx.AsyncClient:
    proxy = PROXY_URL or None
    return httpx.AsyncClient(proxy=proxy, timeout=30)


def _create_email_provider():
    """创建邮箱 provider 实例"""
    print(f"[邮箱] 初始化 provider: {EMAIL_PROVIDER}")
    return EmailProviderFactory.create(EMAIL_PROVIDER, **EMAIL_PROVIDER_CONFIG)


def _fetch_latest_email(provider, email_addr: str, timeout: int, check_interval: int) -> dict | None:
    """通过 provider 获取最新邮件

    兼容不同 provider 的方法签名：
    - 优先使用支持 timeout/check_interval 的实现
    - 不支持时退回到仅传邮箱地址
    """
    try:
        return provider.get_latest_email_from_api(
            email_addr,
            timeout=timeout,
            check_interval=check_interval,
        )
    except TypeError:
        return provider.get_latest_email_from_api(email_addr)


async def start_device_auth() -> dict:
    """发起设备授权，返回 device_code, user_code, verification_uri 等"""
    async with _http_client() as client:
        resp = await client.post(
            WORKOS_DEVICE_AUTH_URL,
            data={"client_id": WORKOS_CLIENT_ID},
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        resp.raise_for_status()
        return resp.json()


async def poll_device_auth(device_code: str, interval: int = 5, timeout: int = 300) -> dict | None:
    """轮询设备授权状态，成功返回 token 信息"""
    deadline = time.time() + timeout
    async with _http_client() as client:
        while time.time() < deadline:
            resp = await client.post(
                WORKOS_AUTH_URL,
                data={
                    "grant_type": "urn:ietf:params:oauth:grant-type:device_code",
                    "device_code": device_code,
                    "client_id": WORKOS_CLIENT_ID,
                },
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )
            if resp.status_code == 200:
                return resp.json()

            body = resp.json() if "json" in resp.headers.get("content-type", "") else {}
            error = body.get("error", "")

            if error == "expired_token":
                print("[注册] 授权已过期")
                return None
            if error in ("authorization_pending", "slow_down"):
                wait = interval + (2 if error == "slow_down" else 0)
                await asyncio.sleep(wait)
                continue

            print(f"[注册] 轮询错误: {body.get('error_description', error)}")
            await asyncio.sleep(interval)

    print("[注册] 轮询超时")
    return None


async def fetch_org(access_token: str, user_id: str) -> tuple[str, str]:
    """获取用户的 organization 信息"""
    async with _http_client() as client:
        resp = await client.get(
            f"{OB1_API_BASE}/auth/organizations?user_id={user_id}",
            headers={"Authorization": f"Bearer {access_token}"},
        )
        if resp.status_code == 200:
            orgs = resp.json().get("data", [])
            if orgs:
                return orgs[0].get("organizationId", ""), orgs[0].get("organizationName", "")
    return "", ""


def save_account(account: dict):
    """保存账号到 accounts.json（去重）"""
    accounts = []
    if os.path.exists(ACCOUNTS_JSON):
        try:
            with open(ACCOUNTS_JSON, "r", encoding="utf-8") as f:
                accounts = json.load(f)
            if not isinstance(accounts, list):
                raise ValueError("accounts.json 内容必须是数组")
        except Exception as e:
            print(f"[注册] 读取已有账号文件失败，将重建账号列表: {e}")
            accounts = []

    # 去重：同 email 则更新
    for i, a in enumerate(accounts):
        if a.get("email") == account["email"]:
            accounts[i] = account
            break
    else:
        accounts.append(account)

    os.makedirs(os.path.dirname(ACCOUNTS_JSON), exist_ok=True)
    with open(ACCOUNTS_JSON, "w", encoding="utf-8") as f:
        json.dump(accounts, f, indent=2, ensure_ascii=False)
    print(f"[注册] 已保存到 {ACCOUNTS_JSON}")


async def _poll_email_code(provider, email_addr: str, stop_event: asyncio.Event) -> str | None:
    """后台轮询 provider 邮箱验证码"""
    deadline = time.time() + EMAIL_CODE_TIMEOUT
    attempt = 0

    while time.time() < deadline and not stop_event.is_set():
        attempt += 1
        remaining = max(1, int(deadline - time.time()))
        chunk_timeout = min(EMAIL_POLL_CHUNK_TIMEOUT, remaining)

        print(f"[邮箱] 第 {attempt} 轮检查... (本轮最多 {chunk_timeout}s)")
        email_content = await asyncio.to_thread(
            _fetch_latest_email,
            provider,
            email_addr,
            chunk_timeout,
            EMAIL_CHECK_INTERVAL,
        )

        if stop_event.is_set():
            return None

        code = provider.parse_ob1_code(email_content)
        if code:
            return code

        await asyncio.sleep(1)

    if stop_event.is_set():
        print("[邮箱] 已停止验证码监听")
    else:
        print("[邮箱] 超时，未获取到验证码")
    return None


async def register():
    """主注册流程"""
    print("=" * 50)
    print("OB-1 账号注册工具 (Device Auth + Provider 邮箱接码)")
    print("=" * 50)

    provider = _create_email_provider()
    if provider.needs_browser_page():
        print(f"[错误] 当前 provider {EMAIL_PROVIDER} 需要浏览器页面支持，ob1_register 目前仅支持 API 型 provider")
        return

    # 0. 生成接码邮箱
    print("\n[0] 生成接码邮箱...")
    auth_email = provider.get_email_from_api()
    if not auth_email:
        print("[错误] 无法从 provider 获取邮箱地址")
        return
    print(f"[邮箱] 本次注册邮箱: {auth_email}")

    # 1. 发起设备授权
    print("\n[1] 发起设备授权...")
    auth_info = await start_device_auth()
    user_code = auth_info.get("user_code", "")
    verification_uri = auth_info.get("verification_uri_complete") or auth_info.get("verification_uri", "")
    device_code = auth_info["device_code"]
    interval = auth_info.get("interval", 5)

    print("\n>>> 请在浏览器中打开以下链接，并使用下面这个邮箱注册/登录：")
    print(f"    {verification_uri}")
    print(f"    邮箱: {auth_email}")
    if user_code:
        print(f"    Device Code: {user_code}")

    # 2. 同时启动：邮箱接码 + device auth 轮询
    print("\n    等待授权中（同时监听 provider 邮箱验证码）...")
    stop_event = asyncio.Event()
    email_task = asyncio.create_task(_poll_email_code(provider, auth_email, stop_event))
    auth_task = asyncio.create_task(poll_device_auth(device_code, interval=interval))

    done, _ = await asyncio.wait(
        [email_task, auth_task],
        return_when=asyncio.FIRST_COMPLETED,
    )

    result = None
    if email_task in done and auth_task not in done:
        code = email_task.result()
        if code:
            print(f"\n>>> 邮箱验证码: {code}  ← 请在浏览器中输入")
        result = await auth_task
    elif auth_task in done:
        result = auth_task.result()
        stop_event.set()
        await asyncio.gather(email_task, return_exceptions=True)
    else:
        result = await auth_task

    stop_event.set()

    if not result:
        print("\n[失败] 未能完成授权")
        return

    access_token = result["access_token"]
    refresh_token = result["refresh_token"]
    user = result.get("user", {})
    user_id = user.get("id", "")
    user_email = user.get("email", "") or auth_email

    print(f"\n[2] 授权成功! 邮箱: {user_email}")

    # 3. 获取 org
    print("[3] 获取组织信息...")
    org_id, org_name = await fetch_org(access_token, user_id)
    if org_id:
        print(f"    组织: {org_name} ({org_id})")
    else:
        print("    未找到组织（新用户可能需要先创建）")

    # 4. 保存
    account = {
        "email": user_email,
        "verification_email": auth_email,
        "email_provider": EMAIL_PROVIDER,
        "access_token": access_token,
        "refresh_token": refresh_token,
        "expires_at": time.time() + 604800,
        "org_id": org_id,
        "org_name": org_name,
        "user_id": user_id,
        "user_data": user,
    }
    save_account(account)

    print(f"\n{'=' * 50}")
    print("注册完成!")
    print(f"  邮箱: {user_email}")
    print(f"  验证邮箱: {auth_email}")
    print(f"  Provider: {EMAIL_PROVIDER}")
    print(f"  Token: {access_token[:20]}...")
    if org_id:
        print(f"  API Key: {access_token}:{org_id}")
    print(f"{'=' * 50}")


if __name__ == "__main__":
    asyncio.run(register())
