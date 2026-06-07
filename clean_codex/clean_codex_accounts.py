#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import argparse
import asyncio
import json
import os
import sys
import requests

try:
    import aiohttp
except Exception:
    aiohttp = None

DEFAULT_BASE_URL = "http://152.136.226.46:10291"
DEFAULT_UA = "codex_cli_rs/0.76.0 (Debian 13.0.0; x86_64) WindowsTerminal"
DEFAULT_TIMEOUT = 12
DEFAULT_CONFIG_PATH = "config.json"


# -------------------------
# utils
# -------------------------
def safe_json(resp):
    try:
        return resp.json()
    except Exception:
        return {}


def safe_json_text(text):
    try:
        return json.loads(text)
    except Exception:
        return {}


def mgmt_headers(token):
    return {"Authorization": f"Bearer {token}", "Accept": "application/json"}


def get_item_type(item):
    return item.get("type") or item.get("typo")


def to_float(v):
    if isinstance(v, (int, float)):
        return float(v)
    if isinstance(v, str):
        try:
            return float(v.strip())
        except Exception:
            return None
    return None


def deep_get(d, path, default=None):
    cur = d
    for k in path:
        if not isinstance(cur, dict):
            return default
        cur = cur.get(k)
        if cur is None:
            return default
    return cur


def prompt_int(label, default_value, min_value=0):
    raw = input(f"{label}（默认 {default_value}）: ").strip()
    if not raw:
        return default_value
    try:
        v = int(raw)
        if v < min_value:
            print(f"输入过小，使用最小值 {min_value}")
            return min_value
        return v
    except Exception:
        print("输入无效，使用默认值")
        return default_value


def prompt_float(label, default_value, min_value=0.0, max_value=100.0):
    raw = input(f"{label}（默认 {default_value}）: ").strip()
    if not raw:
        return float(default_value)
    try:
        v = float(raw)
        if v < min_value:
            v = min_value
        if v > max_value:
            v = max_value
        return v
    except Exception:
        print("输入无效，使用默认值")
        return float(default_value)


def prompt_yes_no(label, default=False):
    tip = "Y/n" if default else "y/N"
    raw = input(f"{label}（{tip}）: ").strip().lower()
    if not raw:
        return default
    return raw in {"y", "yes", "1", "true"}


def choose_mode():
    print("\n请选择操作:")
    print("1) 筛选并导出401账号")
    print("2) 检查401并删除")
    print("3) 删除账号（按 auth_index）")
    print("4) 检查账号额度、自动启停(0禁用/>0启用)并导出json（按百分比排序）")
    print("5) 删除低额度，即高百分比占用的账号（used_percent >= 阈值）")
    print("0) 退出")
    while True:
        c = input("请输入选项编号: ").strip()
        if c in {"0", "1", "2", "3", "4", "5"}:
            return c
        print("无效选项，请重输。")


def ensure_aiohttp():
    if aiohttp is None:
        print("请先安装 aiohttp: pip install aiohttp", file=sys.stderr)
        sys.exit(1)


# -------------------------
# api
# -------------------------
def fetch_auth_files(base_url, token, timeout):
    resp = requests.get(
        f"{base_url}/v0/management/auth-files",
        headers=mgmt_headers(token),
        timeout=timeout,
    )
    resp.raise_for_status()
    data = safe_json(resp)
    return data.get("files", [])


def delete_auth_file(base_url, token, name, timeout):
    resp = requests.delete(
        f"{base_url}/v0/management/auth-files",
        params={"name": name},
        headers=mgmt_headers(token),
        timeout=timeout,
    )
    if resp.status_code >= 400:
        raise RuntimeError(f"DELETE {name} 失败: HTTP {resp.status_code} {resp.text[:200]}")
    return True


def toggle_auth_file(base_url, token, name, disabled, timeout):
    resp = requests.patch(
        f"{base_url}/v0/management/auth-files/status",
        json={"name": name, "disabled": bool(disabled)},
        headers=mgmt_headers(token),
        timeout=timeout,
    )
    if resp.status_code >= 400:
        raise RuntimeError(f"PATCH {name} 状态失败: HTTP {resp.status_code} {resp.text[:200]}")
    return True


def build_probe_payload(auth_index, user_agent, chatgpt_account_id=None):
    h = {
        "Authorization": "Bearer $TOKEN$",
        "Content-Type": "application/json",
        "User-Agent": user_agent,
    }
    if chatgpt_account_id:
        h["Chatgpt-Account-Id"] = chatgpt_account_id
    return {
        "authIndex": auth_index,
        "method": "GET",
        "url": "https://chatgpt.com/backend-api/wham/usage",
        "header": h,
    }


def extract_usage_metrics(api_call_resp):
    body = api_call_resp.get("body")
    if isinstance(body, str):
        body = safe_json_text(body)
    if not isinstance(body, dict):
        body = {}

    used_percent = to_float(deep_get(body, ("rate_limit", "primary_window", "used_percent")))
    limit_window_seconds = deep_get(body, ("rate_limit", "primary_window", "limit_window_seconds"))
    reset_after_seconds = deep_get(body, ("rate_limit", "primary_window", "reset_after_seconds"))
    reset_at = deep_get(body, ("rate_limit", "primary_window", "reset_at"))
    limit_reached = deep_get(body, ("rate_limit", "limit_reached"))
    allowed = deep_get(body, ("rate_limit", "allowed"))

    return {
        "plan_type": body.get("plan_type"),
        "used_percent": used_percent,
        "limit_window_seconds": limit_window_seconds,
        "reset_after_seconds": reset_after_seconds,
        "reset_at": reset_at,
        "limit_reached": bool(limit_reached) if limit_reached is not None else None,
        "allowed": bool(allowed) if allowed is not None else None,
        "usage_raw_body": body,
    }


async def probe_account_async(session, semaphore, base_url, token, item, user_agent, chatgpt_account_id, timeout, retries):
    auth_index = item.get("auth_index")
    result = {
        "name": item.get("name") or item.get("id"),
        "account": item.get("account") or item.get("email"),
        "auth_index": auth_index,
        "type": get_item_type(item),
        "provider": item.get("provider"),
        "status_code": None,
        "invalid_401": False,
        "plan_type": None,
        "used_percent": None,
        "limit_window_seconds": None,
        "reset_after_seconds": None,
        "reset_at": None,
        "limit_reached": None,
        "allowed": None,
        "usage_raw_body": None,
        "error": None,
    }

    if not auth_index:
        result["error"] = "missing auth_index"
        return result

    payload = build_probe_payload(auth_index, user_agent, chatgpt_account_id)

    for i in range(retries + 1):
        try:
            async with semaphore:
                async with session.post(
                    f"{base_url}/v0/management/api-call",
                    headers={**mgmt_headers(token), "Content-Type": "application/json"},
                    json=payload,
                    timeout=timeout,
                ) as resp:
                    text = await resp.text()
                    if resp.status >= 400:
                        raise RuntimeError(f"http {resp.status}: {text[:200]}")

                    data = safe_json_text(text)
                    sc = data.get("status_code")
                    result["status_code"] = sc
                    result["invalid_401"] = (sc == 401)

                    if sc == 200:
                        result.update(extract_usage_metrics(data))
                    return result
        except Exception as e:
            result["error"] = str(e)
            if i >= retries:
                return result

    return result


async def run_probe_all(base_url, token, target_type, provider, workers, timeout, retries, user_agent, chatgpt_account_id):
    files = fetch_auth_files(base_url, token, timeout)
    candidates = []
    for f in files:
        if str(get_item_type(f) or "").lower() != target_type.lower():
            continue
        if provider and str(f.get("provider", "")).lower() != provider.lower():
            continue
        candidates.append(f)

    print(f"总账号数: {len(files)}")
    print(f"符合过滤条件账号数: {len(candidates)}")

    if not candidates:
        return []

    connector = aiohttp.TCPConnector(limit=max(1, workers), limit_per_host=max(1, workers))
    client_timeout = aiohttp.ClientTimeout(total=max(1, timeout))
    semaphore = asyncio.Semaphore(max(1, workers))

    results = []
    async with aiohttp.ClientSession(connector=connector, timeout=client_timeout, trust_env=True) as session:
        tasks = [
            asyncio.create_task(
                probe_account_async(session, semaphore, base_url, token, it, user_agent, chatgpt_account_id, timeout, retries)
            )
            for it in candidates
        ]
        done = 0
        total = len(tasks)
        for t in asyncio.as_completed(tasks):
            results.append(await t)
            done += 1
            if done % 100 == 0 or done == total:
                print(f"检测进度: {done}/{total}")

    return results


# -------------------------
# menu actions
# -------------------------
def action_export_401(results, output_401):
    invalid_401 = [r for r in results if r.get("invalid_401")]
    invalid_401.sort(key=lambda x: x.get("name") or "")
    with open(output_401, "w", encoding="utf-8") as f:
        json.dump(invalid_401, f, ensure_ascii=False, indent=2)
    print(f"401账号数: {len(invalid_401)}")
    print(f"已导出: {output_401}")


def action_check_401_and_delete(base_url, token, timeout, results, output_401):
    invalid_401 = [r for r in results if r.get("invalid_401")]
    invalid_401.sort(key=lambda x: x.get("name") or "")

    with open(output_401, "w", encoding="utf-8") as f:
        json.dump(invalid_401, f, ensure_ascii=False, indent=2)

    print(f"检测到401账号: {len(invalid_401)}")
    if not invalid_401:
        print("无需删除。")
        return

    confirm = input("确认删除这些401账号？输入 YES 继续: ").strip()
    if confirm != "YES":
        print("已取消删除。")
        return

    ok, fail = 0, 0
    for r in invalid_401:
        name = r.get("name")
        if not name:
            fail += 1
            continue
        try:
            delete_auth_file(base_url, token, name, timeout)
            ok += 1
        except Exception as e:
            fail += 1
            print(f"[FAIL] {name}: {e}")

    print(f"删除完成: 成功 {ok}，失败 {fail}")


def action_delete_by_auth_index(base_url, token, timeout):
    raw = input("请输入要删除的 auth_index，多个逗号分隔: ").strip()
    if not raw:
        print("未输入，取消。")
        return
    ids = [x.strip() for x in raw.split(",") if x.strip()]
    if not ids:
        print("没有有效 auth_index，取消。")
        return

    print(f"将删除 {len(ids)} 个账号: {ids}")
    confirm = input("输入 YES 确认删除: ").strip()
    if confirm != "YES":
        print("已取消。")
        return

    ok, fail = 0, 0
    for idx in ids:
        try:
            delete_auth_file(base_url, token, idx, timeout)
            ok += 1
            print(f"[OK] {idx}")
        except Exception as e:
            fail += 1
            print(f"[FAIL] {idx}: {e}")
    print(f"删除完成: 成功 {ok}，失败 {fail}")


def action_export_usage(base_url, token, timeout, results, output_usage, export_full=False):
    ok_200 = [r for r in results if r.get("status_code") == 200]

    # Check quotas and update status
    disabled_count = 0
    enabled_count = 0
    fail_count = 0
    
    print("开始自动启停账号...")
    for r in ok_200:
        name = r.get("name")
        if not name:
            continue
        
        limit_reached = r.get("limit_reached")
        used_percent = r.get("used_percent")
        is_num = isinstance(used_percent, (int, float))
        
        should_disable = bool(limit_reached or (is_num and used_percent >= 100.0))
        
        try:
            toggle_auth_file(base_url, token, name, should_disable, timeout)
            if should_disable:
                disabled_count += 1
            else:
                enabled_count += 1
        except Exception as e:
            print(f"[FAIL] 更新状态 {name}: {e}")
            fail_count += 1
            
    print(f"启停处理完毕: 已禁用 {disabled_count} 个，保持/恢复启用 {enabled_count} 个，失败 {fail_count} 个")

    # used_percent 从大到小，None 放最后
    def sort_key_desc(r):
        up = r.get("used_percent")
        is_num = isinstance(up, (int, float))
        return (0 if is_num else 1, -(up if is_num else -1), r.get("name") or "")

    usage_sorted = list(ok_200)
    usage_sorted.sort(key=sort_key_desc)

    if export_full:
        export_data = usage_sorted
    else:
        export_data = [
            {
                "name": r.get("name"),
                "account": r.get("account"),
                "auth_index": r.get("auth_index"),
                "used_percent": r.get("used_percent"),
            }
            for r in usage_sorted
        ]

    with open(output_usage, "w", encoding="utf-8") as f:
        json.dump(export_data, f, ensure_ascii=False, indent=2)

    print(f"200账号数: {len(ok_200)}")
    print(f"已按 used_percent 从大到小排序并导出: {output_usage}")
    print(f"导出模式: {'全部信息' if export_full else '精简(默认，仅含 used_percent 相关字段)'}")


def action_delete_by_threshold(base_url, token, timeout, results):
    threshold = prompt_float("请输入删除阈值 used_percent(0~100)", 80.0, 0.0, 100.0)

    candidates = [
        r for r in results
        if r.get("status_code") == 200 and isinstance(r.get("used_percent"), (int, float)) and r["used_percent"] >= threshold
    ]

    print(f"满足删除条件 used_percent >= {threshold} 的账号数: {len(candidates)}")
    if not candidates:
        print("没有可删除账号。")
        return

    preview_n = min(20, len(candidates))
    print(f"预览前 {preview_n} 个:")
    for r in candidates[:preview_n]:
        print(f" - {r.get('auth_index')} | {r.get('account')} | used_percent={r.get('used_percent')}")

    confirm = input("确认删除以上条件账号？输入 YES 继续: ").strip()
    if confirm != "YES":
        print("已取消删除。")
        return

    ok, fail = 0, 0
    for r in candidates:
        name = r.get("name")
        if not name:
            fail += 1
            continue
        try:
            delete_auth_file(base_url, token, name, timeout)
            ok += 1
        except Exception as e:
            fail += 1
            print(f"[FAIL] {name}: {e}")

    print(f"删除完成: 成功 {ok}，失败 {fail}")


# -------------------------
# main
# -------------------------
def main():
    parser = argparse.ArgumentParser(description="账号管理菜单脚本")
    parser.add_argument("--config", default=DEFAULT_CONFIG_PATH)
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL)
    parser.add_argument("--token", default=os.getenv("MGMT_TOKEN"))
    parser.add_argument("--target-type", default="codex")
    parser.add_argument("--provider", default=None)
    parser.add_argument("--workers", type=int, default=120)
    parser.add_argument("--timeout", type=int, default=DEFAULT_TIMEOUT)
    parser.add_argument("--retries", type=int, default=1)
    parser.add_argument("--user-agent", default=DEFAULT_UA)
    parser.add_argument("--chatgpt-account-id", default=os.getenv("CHATGPT_ACCOUNT_ID"))
    parser.add_argument("--output-401", default="invalid_codex_accounts.json")
    parser.add_argument("--output-usage", default="usage_sorted_accounts.json")
    args = parser.parse_args()

    ensure_aiohttp()

    if os.path.exists(args.config):
        try:
            with open(args.config, "r", encoding="utf-8") as f:
                conf = json.load(f)
            if isinstance(conf, dict):
                if conf.get("base_url") and args.base_url == DEFAULT_BASE_URL:
                    args.base_url = conf["base_url"]
                if conf.get("token") and not args.token:
                    args.token = conf["token"]
                if conf.get("cpa_password") and not args.token:
                    args.token = conf["cpa_password"]
                if conf.get("user_agent") and args.user_agent == DEFAULT_UA:
                    args.user_agent = conf["user_agent"]
                if conf.get("chatgpt_account_id") and not args.chatgpt_account_id:
                    args.chatgpt_account_id = conf["chatgpt_account_id"]
        except Exception as e:
            print(f"读取配置文件失败: {e}")

    if not args.token:
        args.token = input("请输入 token: ").strip()
    if not args.token:
        print("缺少 token", file=sys.stderr)
        sys.exit(1)

    args.base_url = args.base_url.rstrip("/")

    while True:
        mode = choose_mode()
        if mode == "0":
            print("已退出。")
            break

        workers = prompt_int("workers", args.workers, 1)
        timeout = prompt_int("timeout", args.timeout, 1)
        retries = prompt_int("retries", args.retries, 0)

        if mode == "3":
            action_delete_by_auth_index(args.base_url, args.token, timeout)
            continue

        results = asyncio.run(
            run_probe_all(
                args.base_url,
                args.token,
                args.target_type,
                args.provider,
                workers,
                timeout,
                retries,
                args.user_agent,
                args.chatgpt_account_id,
            )
        )

        if mode == "1":
            action_export_401(results, args.output_401)
        elif mode == "2":
            action_check_401_and_delete(args.base_url, args.token, timeout, results, args.output_401)
        elif mode == "4":
            export_full = prompt_yes_no("是否导出全部信息？默认否（仅导出 used_percent 相关字段）", default=False)
            action_export_usage(args.base_url, args.token, timeout, results, args.output_usage, export_full=export_full)
        elif mode == "5":
            action_delete_by_threshold(args.base_url, args.token, timeout, results)


if __name__ == "__main__":
    main()