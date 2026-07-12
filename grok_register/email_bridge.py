#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Grok 注册 — providers 邮箱桥接层。"""

from __future__ import annotations

import os
import re
import sys
import time
import contextlib
import io

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from providers import EmailProviderFactory

_provider_instance = None


@contextlib.contextmanager
def _silence_provider_stdout(log_callback=None):
    """providers 内部 print 含 emoji，Windows GBK 控制台会报错，统一吞掉或转给 log。"""
    buffer = io.StringIO()
    with contextlib.redirect_stdout(buffer):
        yield
    output = buffer.getvalue().strip()
    if output and log_callback:
        for line in output.splitlines():
            text = line.strip()
            if text:
                log_callback(text)


def extract_verification_code(text, subject=""):
    """从 xAI/Grok 邮件正文提取验证码。"""
    if subject:
        match = re.search(r"^([A-Z0-9]{3}-[A-Z0-9]{3})\s+xAI", subject, re.IGNORECASE)
        if match:
            return match.group(1)
    match = re.search(r"\b([A-Z0-9]{3}-[A-Z0-9]{3})\b", text, re.IGNORECASE)
    if match:
        return match.group(1)
    patterns = [
        r"verification\s+code[:\s]+(\d{4,8})",
        r"your\s+code[:\s]+(\d{4,8})",
        r"confirm(?:ation)?\s+code[:\s]+(\d{4,8})",
    ]
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            return match.group(1)
    return None


def _build_provider_kwargs(config: dict) -> tuple[str, dict]:
    name = str(config.get("email_provider", "duckmail") or "duckmail").strip().lower()
    proxy = str(config.get("proxy", "") or "").strip()
    proxies = {"http": proxy, "https": proxy} if proxy else None
    kwargs: dict = {"proxies": proxies, "timeout": 15}

    if name == "duckmail":
        kwargs["bearer_token"] = str(config.get("duckmail_api_key", "") or "").strip()
    elif name == "domain-imap":
        suffixes_file = str(config.get("email_suffixes_file", "") or "").strip()
        if suffixes_file and not os.path.isabs(suffixes_file):
            suffixes_file = os.path.abspath(os.path.join(os.path.dirname(__file__), suffixes_file))
        kwargs["imap_config"] = {
            "host": config.get("imap_host", "imap.qq.com"),
            "port": int(config.get("imap_port", 993) or 993),
            "user": str(config.get("imap_user", "") or "").strip(),
            "password": str(config.get("imap_password", "") or "").strip(),
        }
        if suffixes_file:
            kwargs["suffixes_file"] = suffixes_file
    elif name == "chat-tempmail":
        kwargs["api_key"] = str(config.get("chat_tempmail_api_key", "") or "").strip()

    return name, kwargs


def reset_provider():
    global _provider_instance
    _provider_instance = None


def get_email_and_token(config: dict, log_callback=None):
    """创建邮箱，返回 (address, access_id)。"""
    global _provider_instance
    name, kwargs = _build_provider_kwargs(config)
    with _silence_provider_stdout(log_callback):
        _provider_instance = EmailProviderFactory.create(name, **kwargs)
        email = _provider_instance.get_email_from_api()
    if not email:
        raise Exception(f"{name} 创建邮箱失败")
    access_id = _provider_instance.get_mail_access_identifier() or email
    return email, access_id


def get_oai_code(
    email,
    timeout=180,
    poll_interval=3,
    log_callback=None,
    cancel_callback=None,
    resend_callback=None,
    cancelled_exception=None,
):
    """轮询邮箱并提取 xAI 验证码。"""
    global _provider_instance
    if _provider_instance is None:
        raise Exception("邮箱 provider 未初始化，请先调用 get_email_and_token")

    cancel_exc = cancelled_exception or Exception
    deadline = time.time() + timeout
    seen_keys = set()

    while time.time() < deadline:
        if cancel_callback and cancel_callback():
            raise cancel_exc("用户停止注册")
        if resend_callback:
            try:
                resend_callback()
            except Exception:
                pass

        remaining = max(1, int(min(poll_interval, deadline - time.time())))
        try:
            with _silence_provider_stdout(log_callback):
                try:
                    mail = _provider_instance.get_latest_email_from_api(
                        email,
                        timeout=remaining,
                        check_interval=min(3, remaining),
                    )
                except TypeError:
                    mail = _provider_instance.get_latest_email_from_api(email)
        except Exception as exc:
            if log_callback:
                log_callback(f"[Debug] 拉取邮件异常: {exc}")
            mail = None

        if mail:
            subject = str(mail.get("subject", "") or "")
            content = str(mail.get("content", "") or "") + str(mail.get("html", "") or "")
            dedupe_key = subject or content[:120]
            if dedupe_key and dedupe_key not in seen_keys:
                seen_keys.add(dedupe_key)
                code = extract_verification_code(content, subject)
                if not code and hasattr(_provider_instance, "parse_xai_code"):
                    code = _provider_instance.parse_xai_code(mail)
                if code:
                    if log_callback:
                        log_callback(f"[*] 从邮件中提取到验证码: {code}")
                    return code

        time.sleep(poll_interval)

    provider_name = getattr(_provider_instance, "__class__", type(_provider_instance)).__name__
    raise Exception(f"{provider_name} 在 {timeout}s 内未收到验证码邮件")
