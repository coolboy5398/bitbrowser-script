#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Windsurf 自动注册脚本
使用比特浏览器自动完成 Windsurf 账号注册流程

功能：
    - 自动创建临时邮箱
    - 自动填写注册表单
    - 自动获取并填写验证码
    - 自动处理 Cloudflare 验证
    - 保存注册信息

依赖：
    pip install websocket-client requests

使用方法：
    1. 确保比特浏览器客户端正在运行
    2. 运行此脚本: python windsurf_register.py
    3. 脚本会自动完成注册流程

作者: AI Assistant
版本: 1.0
"""

import json
import time
from datetime import datetime
from bitbrowser_api import BitBrowserAPI, CDPClient, human_delay
from providers import EmailProviderFactory
from name_generator import NameGenerator


def get_email_from_browser(ws_url, provider):
    """从浏览器页面获取邮箱地址

    Args:
        ws_url (str): WebSocket地址
        provider (EmailProvider): 邮箱服务提供者

    Returns:
        str: 邮箱地址，失败返回None
    """
    print(f"\n🔍 正在获取邮箱地址...")

    # 检查是否需要打开浏览器页面
    if not provider.needs_browser_page():
        print("   ℹ️  该邮箱服务不需要打开页面，直接通过API创建...")
        # 直接调用API方法获取邮箱
        return provider.get_email_from_api()

    cdp = CDPClient(ws_url)

    try:
        # 步骤1: 获取所有 targets
        print("   📋 步骤1: 查找邮箱页面...")
        result = cdp.send("Target.getTargets", {})
        if not result or "result" not in result:
            print("   ✗ 无法获取 targets")
            return None

        targets = result["result"]["targetInfos"]

        # 根据URL查找邮箱页面（使用provider的域名模式）
        page_target = None
        domain_patterns = provider.get_domain_patterns()

        for target in targets:
            if target.get("type") == "page":
                url = target.get("url", "")
                print(f"   📄 发现页面: {url}")
                # 检查URL是否匹配任一域名模式
                if any(pattern in url for pattern in domain_patterns):
                    page_target = target
                    print(f"   ✓ 找到邮箱页面!")
                    break

        # 如果没找到邮箱页面，使用第一个page
        if not page_target:
            print("   ⚠️  未找到邮箱页面URL，尝试使用第一个page...")
            for target in targets:
                if target.get("type") == "page":
                    page_target = target
                    break

        if not page_target:
            print("   ✗ 未找到任何 page target")
            return None

        target_id = page_target["targetId"]
        print(f"   ✓ 目标页面ID: {target_id}")

        # 步骤2: 激活目标页面
        print("   🎯 步骤2: 激活邮箱页面...")
        cdp.send("Target.activateTarget", {"targetId": target_id})
        human_delay(1.0)  # 等待激活完成（人类化延迟）
        print("   ✓ 页面已激活")

        # 步骤3: 附加到 target
        print("   🔗 步骤3: 连接到页面...")
        result = cdp.send("Target.attachToTarget", {
            "targetId": target_id,
            "flatten": True
        })

        if not result or "result" not in result:
            print("   ✗ 无法附加到 target")
            return None

        session_id = result["result"]["sessionId"]
        print("   ✓ 连接成功")

        # 步骤4: 启用必要的域并等待页面加载
        print("   ⏳ 步骤4: 等待页面加载...")
        cdp.send("Page.enable", {}, session_id=session_id)
        cdp.send("DOM.enable", {}, session_id=session_id)
        cdp.send("Runtime.enable", {}, session_id=session_id)

        # 等待页面加载完成（人类化延迟）
        human_delay(3.0)
        print("   ✓ 页面加载完成")

        # 步骤5: 使用provider获取邮箱地址
        email = provider.get_email_from_page(cdp, session_id)
        return email

    finally:
        cdp.close()


def click_cloudflare_verify(cdp, session_id):
    """点击Cloudflare验证框

    Args:
        cdp: CDPClient实例
        session_id: CDP会话ID

    Returns:
        bool: 成功返回True，失败返回False
    """
    print("   🛡️  查找Cloudflare验证框...")

    # 查找验证框元素
    selectors = [
        'div[id*="ulp-"]',
        'div[class*="ulp-"]',
        'div[id*="captcha"]',
        'div[class*="captcha"]',
        'iframe[src*="challenges.cloudflare.com"]',
        'div[id*="cf-"]',
        'div[class*="cf-"]',
        'input[type="checkbox"][id*="cf"]',
        'iframe[title*="cloudflare"]',
        'iframe[src*="captcha"]',
    ]

    # 获取文档根节点
    result = cdp.send("DOM.getDocument", {"depth": -1}, session_id=session_id)
    if not result or "result" not in result:
        print("   ✗ 无法获取 DOM 文档")
        return False

    root_node_id = result["result"]["root"]["nodeId"]

    # 尝试查找验证框
    node_id = None
    matched_selector = None
    for selector in selectors:
        result = cdp.send("DOM.querySelectorAll", {
            "nodeId": root_node_id,
            "selector": selector
        }, session_id=session_id)

        if result and "result" in result and result["result"].get("nodeIds"):
            node_ids = result["result"]["nodeIds"]
            if node_ids:
                node_id = node_ids[0]
                matched_selector = selector
                print(f"   ✓ 找到验证框: {matched_selector}")
                break

    if not node_id:
        print("   ⚠️  未找到验证框元素")
        return False

    # 获取元素位置
    result = cdp.send("DOM.getBoxModel", {"nodeId": node_id}, session_id=session_id)
    if not result or "result" not in result:
        # 使用JavaScript点击
        result = cdp.send("Runtime.evaluate", {
            "expression": f"""
                (() => {{
                    const selectors = {selectors};
                    for (const selector of selectors) {{
                        const element = document.querySelector(selector);
                        if (element) {{
                            element.click();
                            return true;
                        }}
                    }}
                    return false;
                }})()
            """,
            "returnByValue": True
        }, session_id=session_id)

        if result and "result" in result and "result" in result["result"]:
            success = result["result"]["result"].get("value")
            if success:
                print("   ✓ JavaScript点击成功")
                return True
        return False

    box_model = result["result"]["model"]
    content = box_model["content"]
    x = (content[0] + content[4]) / 2
    y = (content[1] + content[5]) / 2

    # 发送CDP鼠标点击事件
    cdp.send("Input.dispatchMouseEvent", {
        "type": "mouseMoved",
        "x": x,
        "y": y
    }, session_id=session_id)
    human_delay(0.1, jitter_percent=0.5)

    cdp.send("Input.dispatchMouseEvent", {
        "type": "mousePressed",
        "x": x,
        "y": y,
        "button": "left",
        "clickCount": 1
    }, session_id=session_id)
    human_delay(0.05, jitter_percent=0.5)

    cdp.send("Input.dispatchMouseEvent", {
        "type": "mouseReleased",
        "x": x,
        "y": y,
        "button": "left",
        "clickCount": 1
    }, session_id=session_id)

    print("   ✓ CDP点击完成")
    return True


def get_verification_code_from_email(email, provider, ws_url=None):
    """从临时邮箱获取Windsurf验证码（新架构）

    使用新的两步流程：
    1. 获取最新邮件（从页面或API）
    2. 解析Windsurf验证码

    Args:
        email: 邮箱地址
        provider (EmailProvider): 邮箱服务提供者
        ws_url: WebSocket地址（可选），如果提供则尝试从页面读取

    Returns:
        str: 验证码，失败返回None
    """
    email_content = None

    # 步骤1: 获取最新邮件
    # 优先尝试从页面读取（如果provider支持且提供了ws_url）
    if ws_url and provider.needs_browser_page():
        print("   💡 尝试从页面获取邮件...")

        # 连接到浏览器获取session_id
        cdp = CDPClient(ws_url)
        try:
            # 查找邮箱页面
            result = cdp.send("Target.getTargets", {})
            if result and "result" in result:
                targets = result["result"]["targetInfos"]
                domain_patterns = provider.get_domain_patterns()

                for target in targets:
                    if target.get("type") == "page":
                        url = target.get("url", "")
                        if any(pattern in url for pattern in domain_patterns):
                            target_id = target["targetId"]

                            # 附加到页面
                            result = cdp.send("Target.attachToTarget", {
                                "targetId": target_id,
                                "flatten": True
                            })

                            if result and "result" in result:
                                session_id = result["result"]["sessionId"]

                                # 从页面获取邮件
                                email_content = provider.get_latest_email_from_page(cdp, session_id, email)
                                break
        finally:
            cdp.close()

        if email_content:
            print("   ✓ 从页面获取邮件成功")
        else:
            print("   ⚠️  页面读取失败，尝试降级到API方式...")

    # 降级到API方式
    if not email_content:
        print("   💡 使用API方式获取邮件...")
        email_content = provider.get_latest_email_from_api(email)

    if not email_content:
        print("   ✗ 未能获取邮件")
        return None

    # 步骤2: 解析Windsurf验证码
    print("   🔍 解析Windsurf验证码...")
    code = provider.parse_windsurf_code(email_content)

    return code


def click_button_by_text(cdp, session_id, button_texts):
    """根据文本内容点击按钮

    Args:
        cdp: CDPClient实例
        session_id: CDP会话ID
        button_texts: 按钮文本列表（如 ["Continue", "Next", "Submit"]）

    Returns:
        bool: 成功返回True，失败返回False
    """
    print(f"   🔍 查找按钮: {button_texts}...")

    # 方法1: JavaScript文本匹配点击
    text_conditions = " || ".join([f"text.includes('{text.lower()}')" for text in button_texts])
    result = cdp.send("Runtime.evaluate", {
        "expression": f"""
            (() => {{
                const elements = Array.from(document.querySelectorAll('button, a, input[type="submit"], input[type="button"]'));
                for (const el of elements) {{
                    const text = (el.textContent || el.value || '').toLowerCase();
                    if ({text_conditions}) {{
                        el.click();
                        return true;
                    }}
                }}
                return false;
            }})()
        """,
        "returnByValue": True
    }, session_id=session_id)

    if result and "result" in result and "result" in result["result"]:
        success = result["result"]["result"].get("value")
        if success:
            print(f"   ✓ JavaScript点击成功")
            return True

    print(f"   ✗ 未找到按钮")
    return False


def fill_windsurf_register_form(ws_url, email, first_name="Test", last_name="User"):
    """填写 Windsurf 注册表单

    Args:
        ws_url (str): WebSocket地址
        email (str): 邮箱地址
        first_name (str): 名字（默认 "Test"）
        last_name (str): 姓氏（默认 "User"）

    Returns:
        bool: 成功返回True，失败返回False
    """
    print(f"\n📝 正在填写 Windsurf 注册表单...")

    cdp = CDPClient(ws_url)

    try:
        # 步骤1: 查找 Windsurf 注册页面
        print("   📋 步骤1: 查找 Windsurf 注册页面...")
        result = cdp.send("Target.getTargets", {})
        if not result or "result" not in result:
            print("   ✗ 无法获取 targets")
            return False

        targets = result["result"]["targetInfos"]

        # 查找 Windsurf 页面
        windsurf_target = None
        for target in targets:
            if target.get("type") == "page":
                url = target.get("url", "")
                print(f"   📄 发现页面: {url}")
                if "windsurf.com" in url:
                    windsurf_target = target
                    print(f"   ✓ 找到 Windsurf 注册页面!")
                    break

        if not windsurf_target:
            print("   ✗ 未找到 Windsurf 注册页面")
            return False

        target_id = windsurf_target["targetId"]

        # 步骤2: 激活页面
        print("   🎯 步骤2: 激活 Windsurf 页面...")
        cdp.send("Target.activateTarget", {"targetId": target_id})
        human_delay(1.0)
        print("   ✓ 页面已激活")

        # 步骤3: 附加到 target
        print("   🔗 步骤3: 连接到页面...")
        result = cdp.send("Target.attachToTarget", {
            "targetId": target_id,
            "flatten": True
        })

        if not result or "result" not in result:
            print("   ✗ 无法附加到 target")
            return False

        session_id = result["result"]["sessionId"]
        print("   ✓ 连接成功")

        # 步骤4: 启用必要的域
        print("   ⏳ 步骤4: 等待页面加载...")
        cdp.send("Page.enable", {}, session_id=session_id)
        cdp.send("DOM.enable", {}, session_id=session_id)
        cdp.send("Runtime.enable", {}, session_id=session_id)
        human_delay(2.0)
        print("   ✓ 页面加载完成")

        # 步骤5: 填写 First name（使用 React 兼容的方式）
        print("   ✍️  步骤5: 填写 First name...")
        result = cdp.send("Runtime.evaluate", {
            "expression": f"""
                (() => {{
                    const input = document.querySelector('input[placeholder*="first name" i]');
                    if (input) {{
                        // 聚焦输入框
                        input.focus();
                        
                        // 设置值并触发 React 的 setter
                        const nativeInputValueSetter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value').set;
                        nativeInputValueSetter.call(input, '{first_name}');
                        
                        // 触发所有必要的事件
                        input.dispatchEvent(new Event('input', {{ bubbles: true }}));
                        input.dispatchEvent(new Event('change', {{ bubbles: true }}));
                        input.dispatchEvent(new Event('blur', {{ bubbles: true }}));
                        
                        return true;
                    }}
                    return false;
                }})()
            """,
            "returnByValue": True
        }, session_id=session_id)

        if result and "result" in result and "result" in result["result"]:
            success = result["result"]["result"].get("value")
            if success:
                print(f"   ✓ 成功填写 First name: {first_name}")
            else:
                print("   ✗ 未能填写 First name")
                return False

        human_delay(0.5)

        # 步骤6: 填写 Last name（使用 React 兼容的方式）
        print("   ✍️  步骤6: 填写 Last name...")
        result = cdp.send("Runtime.evaluate", {
            "expression": f"""
                (() => {{
                    const input = document.querySelector('input[placeholder*="last name" i]');
                    if (input) {{
                        input.focus();
                        const nativeInputValueSetter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value').set;
                        nativeInputValueSetter.call(input, '{last_name}');
                        input.dispatchEvent(new Event('input', {{ bubbles: true }}));
                        input.dispatchEvent(new Event('change', {{ bubbles: true }}));
                        input.dispatchEvent(new Event('blur', {{ bubbles: true }}));
                        return true;
                    }}
                    return false;
                }})()
            """,
            "returnByValue": True
        }, session_id=session_id)

        if result and "result" in result and "result" in result["result"]:
            success = result["result"]["result"].get("value")
            if success:
                print(f"   ✓ 成功填写 Last name: {last_name}")
            else:
                print("   ✗ 未能填写 Last name")
                return False

        human_delay(0.5)

        # 步骤7: 填写 Email（使用 React 兼容的方式）
        print("   ✍️  步骤7: 填写 Email...")
        result = cdp.send("Runtime.evaluate", {
            "expression": f"""
                (() => {{
                    const input = document.querySelector('input[placeholder*="email" i]');
                    if (input) {{
                        input.focus();
                        const nativeInputValueSetter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value').set;
                        nativeInputValueSetter.call(input, '{email}');
                        input.dispatchEvent(new Event('input', {{ bubbles: true }}));
                        input.dispatchEvent(new Event('change', {{ bubbles: true }}));
                        input.dispatchEvent(new Event('blur', {{ bubbles: true }}));
                        return true;
                    }}
                    return false;
                }})()
            """,
            "returnByValue": True
        }, session_id=session_id)

        if result and "result" in result and "result" in result["result"]:
            success = result["result"]["result"].get("value")
            if success:
                print(f"   ✓ 成功填写 Email: {email}")
            else:
                print("   ✗ 未能填写 Email")
                return False

        human_delay(1.0)

        # 步骤8: 勾选同意条款复选框
        print("   ☑️  步骤8: 勾选同意条款...")
        result = cdp.send("Runtime.evaluate", {
            "expression": """
                (() => {
                    const checkbox = document.querySelector('input[type="checkbox"]');
                    if (checkbox && !checkbox.checked) {
                        checkbox.click();
                        return true;
                    }
                    return false;
                })()
            """,
            "returnByValue": True
        }, session_id=session_id)

        if result and "result" in result and "result" in result["result"]:
            success = result["result"]["result"].get("value")
            if success:
                print("   ✓ 已勾选同意条款")
            else:
                print("   ⚠️  复选框可能已勾选或未找到")

        human_delay(1.0)

        # 步骤9: 处理 Cloudflare 验证
        print("   🛡️  步骤9: 处理验证...")
        verify_success = click_cloudflare_verify(cdp, session_id)
        if verify_success:
            print("   ✓ 验证框已点击")
            human_delay(5.0, jitter_percent=0.2)
        else:
            print("   ⚠️  未找到验证框或已完成验证")

        # 步骤10: 点击 Continue 按钮
        print("   ➡️  步骤10: 点击 Continue 按钮...")
        human_delay(1.0)

        result = cdp.send("Runtime.evaluate", {
            "expression": """
                (() => {
                    const buttons = Array.from(document.querySelectorAll('button'));
                    const continueBtn = buttons.find(b => b.textContent.toLowerCase().includes('continue'));
                    if (continueBtn && !continueBtn.disabled) {
                        continueBtn.click();
                        return true;
                    }
                    return false;
                })()
            """,
            "returnByValue": True
        }, session_id=session_id)

        if result and "result" in result and "result" in result["result"]:
            success = result["result"]["result"].get("value")
            if success:
                print("   ✓ Continue 按钮已点击")
            else:
                print("   ⚠️  Continue 按钮可能被禁用或未找到")
                return False

        print("   ✓ 表单填写完成!")
        return True

    finally:
        cdp.close()


def fill_verification_code(ws_url, email, provider):
    """获取验证码并填写

    Args:
        ws_url (str): WebSocket地址
        email (str): 邮箱地址
        provider (EmailProvider): 邮箱服务提供者

    Returns:
        bool: 成功返回True，失败返回False
    """
    print(f"\n🔐 正在获取并填写验证码...")

    # 1. 获取验证码（传递ws_url以支持页面读取）
    verification_code = get_verification_code_from_email(email, provider, ws_url)

    if not verification_code:
        print("   ✗ 未能获取验证码")
        return False

    print(f"   ✓ 验证码: {verification_code}")

    # 2. 连接到浏览器
    cdp = CDPClient(ws_url)

    try:
        # 3. 获取 Windsurf 页面
        print("   🔍 查找 Windsurf 页面...")
        result = cdp.send("Target.getTargets", {})
        if not result or "result" not in result:
            print("   ✗ 无法获取 targets")
            return False

        targets = result["result"]["targetInfos"]

        # 查找 Windsurf 页面
        windsurf_target = None
        for target in targets:
            if target.get("type") == "page":
                url = target.get("url", "")
                if "windsurf.com" in url:
                    windsurf_target = target
                    print(f"   ✓ 找到 Windsurf 页面: {url}")
                    break

        if not windsurf_target:
            print("   ✗ 未找到 Windsurf 页面")
            return False

        target_id = windsurf_target["targetId"]

        # 4. 激活页面
        print("   🎯 激活 Windsurf 页面...")
        cdp.send("Target.activateTarget", {"targetId": target_id})
        human_delay(1.0)

        # 5. 附加到 target
        result = cdp.send("Target.attachToTarget", {
            "targetId": target_id,
            "flatten": True
        })

        if not result or "result" not in result:
            print("   ✗ 无法附加到 target")
            return False

        session_id = result["result"]["sessionId"]

        # 6. 启用必要的域
        cdp.send("Runtime.enable", {}, session_id=session_id)
        cdp.send("DOM.enable", {}, session_id=session_id)

        # 7. 查找并填写验证码输入框（Windsurf 使用 6 个独立输入框）
        print("   ✍️  填写验证码...")

        # Windsurf 验证码页面使用 6 个独立的输入框
        # 需要将验证码拆分成单个字符，分别填入每个输入框
        result = cdp.send("Runtime.evaluate", {
            "expression": f"""
                (() => {{
                    // 查找所有验证码输入框
                    const inputs = document.querySelectorAll('input[type="text"]');
                    
                    // 验证码字符串
                    const code = '{verification_code}';
                    
                    // 检查是否找到 6 个输入框
                    if (inputs.length < 6) {{
                        return {{ success: false, message: 'Found ' + inputs.length + ' inputs, expected 6' }};
                    }}
                    
                    // 将验证码拆分并填入每个输入框
                    for (let i = 0; i < 6 && i < code.length; i++) {{
                        const input = inputs[i];
                        
                        // 聚焦输入框
                        input.focus();
                        
                        // 设置值并触发 React 的 setter
                        const nativeInputValueSetter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value').set;
                        nativeInputValueSetter.call(input, code[i]);
                        
                        // 触发所有必要的事件
                        input.dispatchEvent(new Event('input', {{ bubbles: true }}));
                        input.dispatchEvent(new Event('change', {{ bubbles: true }}));
                        input.dispatchEvent(new KeyboardEvent('keydown', {{ key: code[i], bubbles: true }}));
                        input.dispatchEvent(new KeyboardEvent('keyup', {{ key: code[i], bubbles: true }}));
                    }}
                    
                    return {{ success: true, message: 'Filled 6 inputs' }};
                }})()
            """,
            "returnByValue": True
        }, session_id=session_id)

        if result and "result" in result and "result" in result["result"]:
            result_data = result["result"]["result"].get("value")
            if result_data and result_data.get("success"):
                print(f"   ✓ 成功填写验证码: {verification_code}")
                print(f"   ℹ️  {result_data.get('message')}")
            else:
                error_msg = result_data.get("message") if result_data else "Unknown error"
                print(f"   ✗ 填写验证码失败: {error_msg}")
                return False
        else:
            print("   ✗ 未能执行验证码填写脚本")
            return False

        # 8. 点击提交按钮
        print("   ⏳ 等待页面更新...")
        human_delay(2.0)

        print("   ➡️  点击提交按钮...")
        # Windsurf 验证码页面的按钮是 "Create account"
        submit_success = click_button_by_text(cdp, session_id, ["Create account", "Verify", "Continue", "Submit", "Confirm"])
        if submit_success:
            print("   ✓ 提交按钮已点击")
        else:
            print("   ⚠️  未找到提交按钮")

        print("   ✓ 验证码填写完成!")
        return True

    finally:
        cdp.close()


def wait_for_password_page(ws_url, max_wait_seconds=30):
    """等待密码页面加载

    Args:
        ws_url (str): WebSocket地址
        max_wait_seconds (int): 最大等待时间（秒）

    Returns:
        bool: 成功返回True，超时返回False
    """
    print(f"\n⏳ 等待密码页面加载...")

    cdp = CDPClient(ws_url)

    try:
        start_time = time.time()

        while time.time() - start_time < max_wait_seconds:
            # 获取所有页面
            result = cdp.send("Target.getTargets", {})
            if not result or "result" not in result:
                human_delay(1.0)
                continue

            targets = result["result"]["targetInfos"]

            # 查找 Windsurf 页面
            for target in targets:
                if target.get("type") == "page":
                    url = target.get("url", "")
                    if "windsurf.com" in url:
                        # 附加到页面检查密码框是否存在
                        target_id = target.get("targetId")
                        cdp.send("Target.activateTarget", {"targetId": target_id})
                        
                        result = cdp.send("Target.attachToTarget", {
                            "targetId": target_id,
                            "flatten": True
                        })
                        
                        if result and "result" in result:
                            session_id = result["result"]["sessionId"]
                            cdp.send("Runtime.enable", {}, session_id=session_id)
                            
                            # 检查密码框是否存在
                            check_result = cdp.send("Runtime.evaluate", {
                                "expression": """
                                    (() => {
                                        const passwordInput = document.querySelector('input[id="password"]');
                                        return passwordInput !== null;
                                    })()
                                """,
                                "returnByValue": True
                            }, session_id=session_id)
                            
                            if check_result and "result" in check_result and "result" in check_result["result"]:
                                found = check_result["result"]["result"].get("value")
                                if found:
                                    elapsed = int(time.time() - start_time)
                                    print(f"   ✓ 密码页面已加载（用时{elapsed}秒）")
                                    return True

            # 显示等待进度
            elapsed = int(time.time() - start_time)
            if elapsed % 5 == 0:  # 每5秒显示一次
                print(f"   ⏳ 等待中... ({elapsed}秒)")
            human_delay(2.0)

        print(f"   ✗ 等待超时（{max_wait_seconds}秒）")
        return False

    finally:
        cdp.close()


def fill_password(ws_url, password="1qaz@WSX"):
    """填写密码

    Args:
        ws_url (str): WebSocket地址
        password (str): 密码（默认 "1qaz@WSX"）

    Returns:
        bool: 成功返回True，失败返回False
    """
    print(f"\n🔐 正在填写密码...")

    cdp = CDPClient(ws_url)

    try:
        # 1. 获取 Windsurf 页面
        print("   🔍 查找 Windsurf 页面...")
        result = cdp.send("Target.getTargets", {})
        if not result or "result" not in result:
            print("   ✗ 无法获取 targets")
            return False

        targets = result["result"]["targetInfos"]

        # 查找 Windsurf 页面
        windsurf_target = None
        for target in targets:
            if target.get("type") == "page":
                url = target.get("url", "")
                if "windsurf.com" in url:
                    windsurf_target = target
                    print(f"   ✓ 找到 Windsurf 页面: {url}")
                    break

        if not windsurf_target:
            print("   ✗ 未找到 Windsurf 页面")
            return False

        target_id = windsurf_target["targetId"]

        # 2. 激活页面
        print("   🎯 激活 Windsurf 页面...")
        cdp.send("Target.activateTarget", {"targetId": target_id})
        human_delay(1.0)

        # 3. 附加到 target
        result = cdp.send("Target.attachToTarget", {
            "targetId": target_id,
            "flatten": True
        })

        if not result or "result" not in result:
            print("   ✗ 无法附加到 target")
            return False

        session_id = result["result"]["sessionId"]

        # 4. 启用必要的域
        cdp.send("Runtime.enable", {}, session_id=session_id)
        cdp.send("DOM.enable", {}, session_id=session_id)

        # 5. 填写密码（使用 React 兼容的方式）
        print("   ✍️  填写密码...")
        result = cdp.send("Runtime.evaluate", {
            "expression": f"""
                (() => {{
                    const input = document.querySelector('input[id="password"]');
                    if (input) {{
                        input.focus();
                        const nativeInputValueSetter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value').set;
                        nativeInputValueSetter.call(input, '{password}');
                        input.dispatchEvent(new Event('input', {{ bubbles: true }}));
                        input.dispatchEvent(new Event('change', {{ bubbles: true }}));
                        input.dispatchEvent(new Event('blur', {{ bubbles: true }}));
                        return true;
                    }}
                    return false;
                }})()
            """,
            "returnByValue": True
        }, session_id=session_id)

        if result and "result" in result and "result" in result["result"]:
            success = result["result"]["result"].get("value")
            if success:
                print(f"   ✓ 成功填写密码")
            else:
                print("   ✗ 未能填写密码")
                return False

        human_delay(0.5)

        # 6. 填写密码确认（使用 React 兼容的方式）
        print("   ✍️  填写密码确认...")
        result = cdp.send("Runtime.evaluate", {
            "expression": f"""
                (() => {{
                    const input = document.querySelector('input[id="passwordConfirmation"]');
                    if (input) {{
                        input.focus();
                        const nativeInputValueSetter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value').set;
                        nativeInputValueSetter.call(input, '{password}');
                        input.dispatchEvent(new Event('input', {{ bubbles: true }}));
                        input.dispatchEvent(new Event('change', {{ bubbles: true }}));
                        input.dispatchEvent(new Event('blur', {{ bubbles: true }}));
                        return true;
                    }}
                    return false;
                }})()
            """,
            "returnByValue": True
        }, session_id=session_id)

        if result and "result" in result and "result" in result["result"]:
            success = result["result"]["result"].get("value")
            if success:
                print(f"   ✓ 成功填写密码确认")
            else:
                print("   ✗ 未能填写密码确认")
                return False

        human_delay(1.0)

        # 7. 点击 Continue 按钮
        print("   ➡️  点击 Continue 按钮...")
        result = cdp.send("Runtime.evaluate", {
            "expression": """
                (() => {
                    const buttons = Array.from(document.querySelectorAll('button'));
                    const continueBtn = buttons.find(b => b.textContent.toLowerCase().includes('continue'));
                    if (continueBtn && !continueBtn.disabled) {
                        continueBtn.click();
                        return true;
                    }
                    return false;
                })()
            """,
            "returnByValue": True
        }, session_id=session_id)

        if result and "result" in result and "result" in result["result"]:
            success = result["result"]["result"].get("value")
            if success:
                print("   ✓ Continue 按钮已点击")
            else:
                print("   ⚠️  Continue 按钮可能被禁用或未找到")
                return False

        print("   ✓ 密码填写完成!")
        return True

    finally:
        cdp.close()


def save_registration_info(email, first_name=None, last_name=None, filename_prefix="windsurf_register"):
    """保存注册信息到文件

    Args:
        email (str): 邮箱地址
        first_name (str): 名字
        last_name (str): 姓氏
        filename_prefix (str): 文件名前缀

    Returns:
        str: 保存的文件名
    """
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    filename = f"{filename_prefix}_{timestamp}.txt"

    try:
        with open(filename, 'w', encoding='utf-8') as f:
            f.write(f"Windsurf 注册信息\n")
            f.write(f"=" * 50 + "\n")
            f.write(f"注册时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            if first_name and last_name:
                f.write(f"姓名: {first_name} {last_name}\n")
            f.write(f"邮箱地址: {email}\n")
            f.write(f"=" * 50 + "\n")

        print(f"   💾 注册信息已保存到: {filename}")
        return filename
    except Exception as e:
        print(f"   ⚠️  保存注册信息失败: {e}")
        return None


def main():
    """主函数"""
    start_time = time.time()

    print("=" * 70)
    print("Windsurf 自动注册脚本 v1.0")
    print("=" * 70)

    # 1. 初始化邮箱服务
    provider = EmailProviderFactory.create('domain-imap')
    print(f"\n📧 使用邮箱服务: ChatGPT临时邮箱")
    print(f"   🔗 页面地址: {provider.get_page_url()}")

    # 2. 创建浏览器窗口
    browser_id = BitBrowserAPI.create_window(
        name="Windsurf注册",
        remark="Windsurf注册",
        proxyType="socks5",
        host="127.0.0.1",
        port=7890
    )

    if not browser_id:
        print("\n❌ 创建窗口失败，程序退出")
        return

    # 3. 打开窗口
    result = BitBrowserAPI.open_window(browser_id)
    if not result:
        print("\n❌ 打开窗口失败，程序退出")
        return

    ws_url = result.get("ws")

    # 4. 打开标签页
    print("\n📑 正在打开标签页...")
    cdp = CDPClient(ws_url)

    try:
        # 打开邮箱页面（如果需要）
        if provider.needs_browser_page():
            print("   📧 打开邮箱页面...")
            result = cdp.send("Target.createTarget", {
                "url": provider.get_page_url()
            })
            if result and "result" in result:
                print("   ✓ 邮箱页面已打开")
            human_delay(1.0)
        else:
            print("   ℹ️  该邮箱服务不需要打开页面")

        # 打开 Windsurf 注册页面
        print("   🌊 打开 Windsurf 注册页面...")
        result = cdp.send("Target.createTarget", {
            "url": "https://windsurf.com/account/register"
        })
        if result and "result" in result:
            print("   ✓ 注册页面已打开")

        human_delay(3.0)

    finally:
        cdp.close()

    # 5. 获取邮箱地址
    email = get_email_from_browser(ws_url, provider)

    if email:
        print(f"\n✅ 邮箱获取成功！")
        print(f"   邮箱地址: {email}")
    else:
        print("\n⚠️  未能自动获取邮箱地址")
        email = None

    # 6. 生成随机姓名
    first_name = None
    last_name = None
    if email:
        first_name, last_name = NameGenerator.generate_full_name()
        print(f"\n🎲 生成随机姓名: {first_name} {last_name}")

    # 7. 填写注册表单
    if email:
        form_success = fill_windsurf_register_form(ws_url, email, first_name=first_name, last_name=last_name)
        if form_success:
            print("\n✅ 注册表单已填写!")
        else:
            print("\n⚠️  表单填写失败")
            email = None

    # 8. 等待密码页面加载
    if email:
        wait_success = wait_for_password_page(ws_url, max_wait_seconds=30)
        if not wait_success:
            print("\n⚠️  密码页面加载超时")
            email = None

    # 9. 填写密码
    if email:
        password_success = fill_password(ws_url, password="1qaz@WSX")
        if password_success:
            print("\n✅ 密码已填写!")
        else:
            print("\n⚠️  密码填写失败")
            email = None

    # 10. 获取并填写验证码
    if email:
        code_success = fill_verification_code(ws_url, email, provider)
        if code_success:
            print("\n✅ 验证码已填写!")
        else:
            print("\n⚠️  验证码填写失败")
            email = None

    # 11. 保存注册信息
    if email:
        save_registration_info(email, first_name, last_name)

        # 计算总耗时
        end_time = time.time()
        total_seconds = end_time - start_time

        print(f"\n🎉 注册流程完成!")
        if total_seconds >= 60:
            minutes = int(total_seconds // 60)
            seconds = total_seconds % 60
            print(f"   ⏱️  总耗时: {minutes}分{seconds:.1f}秒")
        else:
            print(f"   ⏱️  总耗时: {total_seconds:.1f}秒")

        print("\n✨ 所有操作完成！")
    else:
        print("\n⚠️  注册流程未完成")
        input("\n按回车键手动关闭窗口...")
        BitBrowserAPI.close_window(browser_id)


if __name__ == "__main__":
    main()
