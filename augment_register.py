#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
比特浏览器窗口创建脚本 - 简单快速版
快速创建、打开、关闭比特浏览器窗口

功能：
    - https://doc2.bitbrowser.cn/jiekou.html
    - 创建浏览器窗口（使用随机指纹）
    - 打开浏览器窗口并获取WebSocket地址
    - 关闭浏览器窗口

依赖：
    pip install websocket-client

使用方法：
    1. 确保比特浏览器客户端正在运行
    2. 运行此脚本: python augment_register.py
    3. 脚本会自动创建、打开窗口，并显示WebSocket地址

作者: AI Assistant
版本: 1.0
"""

import json
import time
import re
from datetime import datetime
from urllib.request import urlopen, Request
from urllib.error import URLError, HTTPError
from urllib.parse import quote
from email_utils import EmailUtils
from bitbrowser_api import BitBrowserAPI, CDPClient, human_delay





def get_email_from_browser(ws_url):
    """从浏览器页面获取邮箱地址

    Args:
        ws_url (str): WebSocket地址

    Returns:
        str: 邮箱地址，失败返回None
    """
    print(f"\n🔍 正在从页面获取邮箱地址...")

    cdp = CDPClient(ws_url)

    try:
        # 步骤1: 获取所有 targets
        print("   📋 步骤1: 查找邮箱页面...")
        result = cdp.send("Target.getTargets", {})
        if not result or "result" not in result:
            print("   ✗ 无法获取 targets")
            return None

        targets = result["result"]["targetInfos"]

        # 根据URL查找邮箱页面
        page_target = None
        for target in targets:
            if target.get("type") == "page":
                url = target.get("url", "")
                print(f"   📄 发现页面: {url}")
                if "mail.chatgpt.org.uk" in url:
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

        # 步骤5: 多次尝试获取邮箱地址
        print("   🔍 步骤5: 查找邮箱地址...")
        max_retries = 3
        for attempt in range(max_retries):
            if attempt > 0:
                print(f"   🔄 第 {attempt + 1} 次尝试...")
                human_delay(2.0)  # 重试间隔（人类化延迟）

            # 方法1: 使用JavaScript查找
            result = cdp.send("Runtime.evaluate", {
                "expression": """
                    (() => {
                        // 方法1: 查找所有包含@的文本节点
                        const walker = document.createTreeWalker(
                            document.body,
                            NodeFilter.SHOW_TEXT,
                            null,
                            false
                        );

                        let node;
                        while(node = walker.nextNode()) {
                            const text = node.textContent.trim();
                            if (text.includes('@') && (text.includes('chatgptuk.pp.ua') || text.includes('chatgpt.org.uk'))) {
                                // 使用正则提取邮箱
                                const match = text.match(/[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\\.[a-zA-Z]{2,}/);
                                if (match) {
                                    return match[0];
                                }
                            }
                        }

                        // 方法2: 查找特定的元素
                        const selectors = [
                            'input[type="text"]',
                            'input[readonly]',
                            'div[class*="email"]',
                            'span[class*="email"]',
                            'p',
                            'div'
                        ];

                        for (const selector of selectors) {
                            const elements = document.querySelectorAll(selector);
                            for (const el of elements) {
                                const text = el.textContent || el.value || '';
                                if (text.includes('@') && (text.includes('chatgptuk.pp.ua') || text.includes('chatgpt.org.uk'))) {
                                    const match = text.match(/[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\\.[a-zA-Z]{2,}/);
                                    if (match) {
                                        return match[0];
                                    }
                                }
                            }
                        }

                        return null;
                    })()
                """,
                "returnByValue": True
            }, session_id=session_id)

            if result and "result" in result and "result" in result["result"]:
                email = result["result"]["result"].get("value")
                if email:
                    print(f"   ✓ 找到邮箱地址: {email}")
                    return email

        print("   ✗ 未找到邮箱地址")
        return None

    finally:
        cdp.close()


def click_cloudflare_verify(cdp, session_id):
    """点击Cloudflare验证框 "Verify you are human"

    Args:
        cdp: CDPClient实例
        session_id: CDP会话ID

    Returns:
        bool: 成功返回True，失败返回False
    """
    print("   🛡️  查找Cloudflare验证框...")

    # 1. 查找验证框元素（按照cloudflare_bypass的选择器顺序）
    selectors = [
        'div[id*="ulp-"]',                           # Auth0 验证框（优先）
        'div[class*="ulp-"]',
        'div[id*="captcha"]',                        # 通用验证码
        'div[class*="captcha"]',
        'iframe[src*="challenges.cloudflare.com"]',  # Cloudflare iframe
        'div[id*="cf-"]',                            # Cloudflare 元素
        'div[class*="cf-"]',
        'input[type="checkbox"][id*="cf"]',          # Cloudflare checkbox
        'iframe[title*="cloudflare"]',
        'iframe[src*="captcha"]',
    ]

    # 获取文档根节点
    result = cdp.send("DOM.getDocument", {"depth": -1}, session_id=session_id)
    if not result or "result" not in result:
        print("   ✗ 无法获取 DOM 文档")
        return False

    root_node_id = result["result"]["root"]["nodeId"]
    print(f"   ✓ 获取根节点: {root_node_id}")

    # 尝试查找验证框
    node_id = None
    matched_selector = None
    for selector in selectors:
        print(f"   🔍 尝试选择器: {selector}")
        result = cdp.send("DOM.querySelectorAll", {
            "nodeId": root_node_id,
            "selector": selector
        }, session_id=session_id)

        if result and "result" in result and result["result"].get("nodeIds"):
            node_ids = result["result"]["nodeIds"]
            if node_ids:
                node_id = node_ids[0]
                matched_selector = selector
                print(f"   ✓ 找到 {len(node_ids)} 个元素，使用第一个")
                break

    if not node_id:
        print("   ⚠️  未找到验证框元素")
        print("   💡 提示: 验证框可能还未加载，或已经完成验证")
        return False

    print(f"   ✓ 找到验证框: {matched_selector}, NodeID={node_id}")

    # 2. 获取元素位置
    print("   📏 获取元素位置...")
    result = cdp.send("DOM.getBoxModel", {"nodeId": node_id}, session_id=session_id)
    if not result or "result" not in result:
        print("   ✗ 无法获取元素位置，尝试使用JavaScript点击...")

        # 备选方案：使用JavaScript点击
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

        print("   ✗ JavaScript点击也失败")
        return False

    box_model = result["result"]["model"]
    content = box_model["content"]
    x = (content[0] + content[4]) / 2
    y = (content[1] + content[5]) / 2
    width = content[4] - content[0]
    height = content[5] - content[1]

    print(f"   ✓ 元素位置: x={x:.1f}, y={y:.1f}, 大小={width:.0f}x{height:.0f}")

    # 3. 发送CDP鼠标点击事件（模拟人类操作）
    print("   🖱️  发送CDP鼠标点击事件...")

    # 鼠标移动
    cdp.send("Input.dispatchMouseEvent", {
        "type": "mouseMoved",
        "x": x,
        "y": y
    }, session_id=session_id)

    # 短暂延迟（模拟人类移动鼠标后的停顿）
    human_delay(0.1, jitter_percent=0.5)

    # 鼠标按下
    cdp.send("Input.dispatchMouseEvent", {
        "type": "mousePressed",
        "x": x,
        "y": y,
        "button": "left",
        "clickCount": 1
    }, session_id=session_id)

    # 短暂延迟（模拟人类按下和释放之间的时间）
    human_delay(0.05, jitter_percent=0.5)

    # 鼠标释放
    cdp.send("Input.dispatchMouseEvent", {
        "type": "mouseReleased",
        "x": x,
        "y": y,
        "button": "left",
        "clickCount": 1
    }, session_id=session_id)

    print("   ✓ CDP点击完成")
    return True


def get_verification_code_from_email(email):
    """从临时邮箱API获取验证码

    Args:
        email: 邮箱地址

    Returns:
        str: 验证码，失败返回None
    """
    print(f"\n📧 正在从邮箱获取验证码...")
    print(f"   📮 邮箱地址: {email}")

    # URL编码邮箱地址
    encoded_email = quote(email)
    api_url = f"https://mail.chatgpt.org.uk/api/get-emails?email={encoded_email}"

    print(f"   🔗 API地址: {api_url}")

    # 最多尝试10次，每次间隔3秒
    max_retries = 10
    for attempt in range(max_retries):
        try:
            print(f"   🔄 第 {attempt + 1}/{max_retries} 次尝试...")

            # 发送HTTP请求
            req = Request(api_url)
            req.add_header('User-Agent', 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36')

            response = urlopen(req, timeout=10)
            data = json.loads(response.read().decode('utf-8'))

            # 检查是否有邮件
            if not data.get('emails'):
                print(f"   ⏳ 暂无邮件，等待3秒后重试...")
                human_delay(3.0)
                continue

            emails = data['emails']
            print(f"   ✓ 找到 {len(emails)} 封邮件")

            # 查找来自 support@augmentcode.com 的邮件
            for email_data in emails:
                from_addr = email_data.get('from', '')
                subject = email_data.get('subject', '')
                content = email_data.get('content', '')

                print(f"   📧 邮件: {from_addr} - {subject}")

                if 'augmentcode.com' in from_addr.lower():
                    print(f"   ✓ 找到Augment邮件")

                    # 从内容中提取验证码
                    # 匹配格式: "Your verification code is: 529891"
                    patterns = [
                        r'verification code is:\s*(\d{6})',
                        r'verification code is:\s*<b>(\d{6})</b>',
                        r'code is:\s*(\d{6})',
                        r'code:\s*(\d{6})',
                        r'(\d{6})',  # 最后尝试匹配任意6位数字
                    ]

                    for pattern in patterns:
                        match = re.search(pattern, content, re.IGNORECASE)
                        if match:
                            code = match.group(1)
                            print(f"   ✓ 找到验证码: {code}")
                            return code

                    print(f"   ⚠️  未能从邮件内容中提取验证码")
                    print(f"   📄 邮件内容预览: {content[:200]}...")

            print(f"   ⚠️  未找到Augment邮件，等待3秒后重试...")
            human_delay(3.0)

        except HTTPError as e:
            print(f"   ✗ HTTP错误: {e.code} {e.reason}")
            if attempt < max_retries - 1:
                human_delay(3.0)
        except URLError as e:
            print(f"   ✗ 网络错误: {e.reason}")
            if attempt < max_retries - 1:
                human_delay(3.0)
        except Exception as e:
            print(f"   ✗ 错误: {e}")
            if attempt < max_retries - 1:
                human_delay(3.0)

    print(f"   ✗ 获取验证码失败（已尝试{max_retries}次）")
    return None


def click_continue_button(cdp, session_id):
    """点击Continue按钮

    Args:
        cdp: CDPClient实例
        session_id: CDP会话ID

    Returns:
        bool: 成功返回True，失败返回False
    """
    print("   🔍 查找Continue按钮...")

    # 方法1: JavaScript文本匹配点击
    result = cdp.send("Runtime.evaluate", {
        "expression": """
            (() => {
                // 查找所有可能的按钮元素
                const elements = Array.from(document.querySelectorAll('button, a, input[type="submit"], input[type="button"]'));

                for (const el of elements) {
                    const text = (el.textContent || el.value || '').toLowerCase();
                    const ariaLabel = (el.getAttribute('aria-label') || '').toLowerCase();

                    // 匹配 "continue" 或 "next"
                    if (text.includes('continue') || text.includes('next') ||
                        ariaLabel.includes('continue') || ariaLabel.includes('next')) {
                        el.click();
                        return true;
                    }
                }

                return false;
            })()
        """,
        "returnByValue": True
    }, session_id=session_id)

    if result and "result" in result and "result" in result["result"]:
        success = result["result"]["result"].get("value")
        if success:
            print("   ✓ JavaScript点击Continue成功")
            return True

    # 方法2: 使用DOM API查找并点击
    print("   🔍 尝试使用DOM API...")

    result = cdp.send("DOM.getDocument", {"depth": -1}, session_id=session_id)
    if not result or "result" not in result:
        print("   ✗ 无法获取DOM文档")
        return False

    root_node_id = result["result"]["root"]["nodeId"]

    # 查找所有button和a元素
    result = cdp.send("DOM.querySelectorAll", {
        "nodeId": root_node_id,
        "selector": "button, a, input[type='submit'], input[type='button']"
    }, session_id=session_id)

    if not result or "result" not in result or not result["result"].get("nodeIds"):
        print("   ✗ 未找到任何按钮元素")
        return False

    node_ids = result["result"]["nodeIds"]
    print(f"   📋 找到 {len(node_ids)} 个可点击元素")

    # 遍历所有元素，查找包含"continue"或"next"的
    for node_id in node_ids:
        # 获取元素的外部HTML
        result = cdp.send("DOM.getOuterHTML", {"nodeId": node_id}, session_id=session_id)

        if result and "result" in result:
            html = result["result"].get("outerHTML", "").lower()
            if "continue" in html or "next" in html:
                print(f"   ✓ 找到Continue按钮")

                # 获取元素位置并点击
                box_result = cdp.send("DOM.getBoxModel", {"nodeId": node_id}, session_id=session_id)

                if box_result and "result" in box_result:
                    box_model = box_result["result"]["model"]
                    content = box_model["content"]
                    x = (content[0] + content[4]) / 2
                    y = (content[1] + content[5]) / 2

                    print(f"   📍 按钮位置: ({x:.1f}, {y:.1f})")

                    # 发送点击事件（人类化）
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

                    print("   ✓ CDP点击Continue完成")
                    return True

    print("   ✗ 未找到Continue按钮")
    return False


def switch_to_augment_and_signin(ws_url, email):
    """切换到Augment登录页面，点击Sign in并填写邮箱

    Args:
        ws_url (str): WebSocket地址
        email (str): 要填写的邮箱地址

    Returns:
        bool: 成功返回True，失败返回False
    """
    print(f"\n🔄 正在切换到Augment登录页面...")

    cdp = CDPClient(ws_url)

    try:
        # 步骤1: 查找Augment登录页面
        print("   📋 步骤1: 查找Augment登录页面...")
        result = cdp.send("Target.getTargets", {})
        if not result or "result" not in result:
            print("   ✗ 无法获取 targets")
            return False

        targets = result["result"]["targetInfos"]

        # 根据URL查找Augment页面
        augment_target = None
        for target in targets:
            if target.get("type") == "page":
                url = target.get("url", "")
                print(f"   📄 发现页面: {url}")
                if "login.augmentcode.com" in url or "augmentcode.com" in url:
                    augment_target = target
                    print(f"   ✓ 找到Augment登录页面!")
                    break

        if not augment_target:
            print("   ✗ 未找到Augment登录页面")
            return False

        target_id = augment_target["targetId"]
        print(f"   ✓ 目标页面ID: {target_id}")

        # 步骤2: 激活Augment页面
        print("   🎯 步骤2: 激活Augment页面...")
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
            return False

        session_id = result["result"]["sessionId"]
        print("   ✓ 连接成功")

        # 步骤4: 启用必要的域
        print("   ⏳ 步骤4: 等待页面加载...")
        cdp.send("Page.enable", {}, session_id=session_id)
        cdp.send("DOM.enable", {}, session_id=session_id)
        cdp.send("Runtime.enable", {}, session_id=session_id)
        human_delay(2.0)  # 等待页面加载（人类化延迟）
        print("   ✓ 页面加载完成")

        # 步骤5: 查找并点击Sign in按钮
        print("   🖱️  步骤5: 查找Sign in按钮...")

        # 尝试多种选择器
        selectors = [
            'button:contains("Sign in")',
            'button:contains("sign in")',
            'a:contains("Sign in")',
            'a:contains("sign in")',
            'button[type="submit"]',
            'input[type="submit"]',
            'button',
            'a[href*="login"]',
            'a[href*="signin"]'
        ]

        clicked = False
        for selector in selectors:
            # 使用JavaScript查找并点击按钮
            result = cdp.send("Runtime.evaluate", {
                "expression": f"""
                    (() => {{
                        // 方法1: 使用文本内容查找
                        const buttons = Array.from(document.querySelectorAll('button, a, input[type="submit"]'));
                        for (const btn of buttons) {{
                            const text = btn.textContent || btn.value || '';
                            if (text.toLowerCase().includes('sign in') || text.toLowerCase().includes('signin')) {{
                                btn.click();
                                return true;
                            }}
                        }}

                        // 方法2: 查找特定选择器
                        const element = document.querySelector('{selector}');
                        if (element) {{
                            element.click();
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
                    print(f"   ✓ 成功点击Sign in按钮!")
                    clicked = True
                    break

        if not clicked:
            print("   ⚠️  未找到Sign in按钮，尝试使用DOM API...")

            # 使用DOM API查找按钮
            result = cdp.send("DOM.getDocument", {"depth": -1}, session_id=session_id)
            if result and "result" in result:
                root_node_id = result["result"]["root"]["nodeId"]

                # 查找所有button元素
                result = cdp.send("DOM.querySelectorAll", {
                    "nodeId": root_node_id,
                    "selector": "button, a, input[type='submit']"
                }, session_id=session_id)

                if result and "result" in result and result["result"].get("nodeIds"):
                    node_ids = result["result"]["nodeIds"]
                    print(f"   📋 找到 {len(node_ids)} 个可点击元素")

                    # 遍历所有元素，查找包含"sign in"的
                    for node_id in node_ids:
                        # 获取元素的外部HTML
                        result = cdp.send("DOM.getOuterHTML", {
                            "nodeId": node_id
                        }, session_id=session_id)

                        if result and "result" in result:
                            html = result["result"].get("outerHTML", "").lower()
                            if "sign in" in html or "signin" in html:
                                # 获取元素位置并点击
                                box_result = cdp.send("DOM.getBoxModel", {
                                    "nodeId": node_id
                                }, session_id=session_id)

                                if box_result and "result" in box_result:
                                    box_model = box_result["result"]["model"]
                                    content = box_model["content"]
                                    x = (content[0] + content[4]) / 2
                                    y = (content[1] + content[5]) / 2

                                    # 发送点击事件
                                    cdp.send("Input.dispatchMouseEvent", {
                                        "type": "mouseMoved",
                                        "x": x,
                                        "y": y
                                    }, session_id=session_id)

                                    cdp.send("Input.dispatchMouseEvent", {
                                        "type": "mousePressed",
                                        "x": x,
                                        "y": y,
                                        "button": "left",
                                        "clickCount": 1
                                    }, session_id=session_id)

                                    cdp.send("Input.dispatchMouseEvent", {
                                        "type": "mouseReleased",
                                        "x": x,
                                        "y": y,
                                        "button": "left",
                                        "clickCount": 1
                                    }, session_id=session_id)

                                    print(f"   ✓ 成功点击Sign in按钮!")
                                    clicked = True
                                    break

        if not clicked:
            print("   ✗ 未能点击Sign in按钮")
            return False

        # 步骤6: 等待页面跳转并填写work mail
        print("   ⏳ 步骤6: 等待页面跳转...")
        human_delay(3.0)  # 等待页面跳转（人类化延迟）
        print("   ✓ 页面跳转完成")

        # 步骤7: 等待并检测work mail输入框加载
        print("   ⏳ 步骤7: 等待work mail输入框加载...")

        # 尝试多种选择器查找work mail输入框
        selectors = [
            'input[name*="email"]',
            'input[type="email"]',
            'input[placeholder*="email"]',
            'input[placeholder*="Email"]',
            'input[placeholder*="work"]',
            'input[placeholder*="Work"]',
            'input[id*="email"]',
            'input[id*="Email"]',
            'input[name="email"]',
            'input[type="text"]'
        ]

        # 轮询检测输入框是否加载（最多等待10秒）
        input_loaded = False
        max_wait = 10
        for attempt in range(max_wait):
            for selector in selectors:
                result = cdp.send("Runtime.evaluate", {
                    "expression": f"""
                        (() => {{
                            const input = document.querySelector('{selector}');
                            return input !== null;
                        }})()
                    """,
                    "returnByValue": True
                }, session_id=session_id)

                if result and "result" in result and "result" in result["result"]:
                    found = result["result"]["result"].get("value")
                    if found:
                        print(f"   ✓ 输入框已加载（用时{attempt + 1}秒）")
                        input_loaded = True
                        break

            if input_loaded:
                break

            # 显示等待进度
            if attempt < max_wait - 1:
                print(f"   ⏳ 等待中... ({attempt + 1}秒)")
                human_delay(1.0)

        if not input_loaded:
            print(f"   ⚠️  输入框未加载（已等待{max_wait}秒）")
            print("   💡 提示: 可能需要手动填写邮箱地址")
            return False

        # 步骤8: 填写work mail输入框
        print("   ✍️  步骤8: 填写work mail...")

        filled = False
        for selector in selectors:
            result = cdp.send("Runtime.evaluate", {
                "expression": f"""
                    (() => {{
                        const input = document.querySelector('{selector}');
                        if (input) {{
                            input.value = '{email}';
                            input.dispatchEvent(new Event('input', {{ bubbles: true }}));
                            input.dispatchEvent(new Event('change', {{ bubbles: true }}));
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
                    print(f"   ✓ 成功填写邮箱: {email}")
                    filled = True
                    break

        if not filled:
            print("   ⚠️  未找到work mail输入框，尝试使用DOM API...")

            # 使用DOM API查找输入框
            result = cdp.send("DOM.getDocument", {"depth": -1}, session_id=session_id)
            if result and "result" in result:
                root_node_id = result["result"]["root"]["nodeId"]

                # 查找所有input元素
                result = cdp.send("DOM.querySelectorAll", {
                    "nodeId": root_node_id,
                    "selector": "input"
                }, session_id=session_id)

                if result and "result" in result and result["result"].get("nodeIds"):
                    node_ids = result["result"]["nodeIds"]
                    print(f"   📋 找到 {len(node_ids)} 个输入框")

                    # 遍历所有输入框，查找包含"email"或"work"的
                    for node_id in node_ids:
                        # 获取元素的外部HTML
                        result = cdp.send("DOM.getOuterHTML", {
                            "nodeId": node_id
                        }, session_id=session_id)

                        if result and "result" in result:
                            html = result["result"].get("outerHTML", "").lower()
                            if "email" in html or "work" in html or 'type="text"' in html:
                                # 使用JavaScript设置值
                                result = cdp.send("Runtime.evaluate", {
                                    "expression": f"""
                                        (() => {{
                                            const inputs = document.querySelectorAll('input');
                                            for (const input of inputs) {{
                                                const html = input.outerHTML.toLowerCase();
                                                if (html.includes('email') || html.includes('work') || input.type === 'text' || input.type === 'email') {{
                                                    input.value = '{email}';
                                                    input.dispatchEvent(new Event('input', {{ bubbles: true }}));
                                                    input.dispatchEvent(new Event('change', {{ bubbles: true }}));
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
                                        print(f"   ✓ 成功填写邮箱: {email}")
                                        filled = True
                                        break

        if not filled:
            print("   ✗ 未能填写work mail")
            print("   💡 提示: 请手动填写邮箱地址")
            return False

        # 步骤9: 点击Cloudflare验证框
        print("   🛡️  步骤9: 处理Cloudflare验证...")
        print("   ⏳ 等待验证框加载...")
        human_delay(5.0, jitter_percent=0.2)  # 等待验证框加载（人类化延迟，5秒±20%）

        verify_success = click_cloudflare_verify(cdp, session_id)
        if verify_success:
            print("   ✓ Cloudflare验证框已点击")
            # 等待验证完成
            print("   ⏳ 等待验证完成...")
            human_delay(5.0, jitter_percent=0.2)  # 等待验证完成（人类化延迟，5秒±20%）
        else:
            print("   ⚠️  未找到验证框或点击失败")
            print("   💡 提示: 验证框可能还未加载，或已经完成验证，或需要手动操作")

        # 步骤10: 点击Continue按钮
        print("   ➡️  步骤10: 查找并点击Continue按钮...")
        human_delay(2.0)  # 等待页面更新

        continue_success = click_continue_button(cdp, session_id)
        if continue_success:
            print("   ✓ Continue按钮已点击")
        else:
            print("   ⚠️  未找到Continue按钮")
            print("   💡 提示: 可能需要手动点击Continue")

        print("   ✓ 所有操作完成!")
        return True

    finally:
        cdp.close()


def wait_for_onboard_redirect(ws_url, max_wait_seconds=60):
    """等待login页面跳转到onboard页面

    Args:
        ws_url (str): WebSocket地址
        max_wait_seconds (int): 最大等待时间（秒）

    Returns:
        bool: 成功跳转返回True，超时返回False
    """
    print(f"\n⏳ 等待页面从login跳转到onboard...")

    cdp = CDPClient(ws_url)

    try:
        start_time = time.time()
        last_url = ""

        while time.time() - start_time < max_wait_seconds:
            # 获取所有页面
            result = cdp.send("Target.getTargets", {})
            if not result or "result" not in result:
                human_delay(1.0)
                continue

            targets = result["result"]["targetInfos"]

            # 查找login或onboard页面
            for target in targets:
                if target.get("type") == "page":
                    url = target.get("url", "")

                    # 检查是否跳转到onboard
                    if "app.augmentcode.com/onboard" in url:
                        print(f"   ✓ 页面已跳转到: {url}")
                        return True

                    # 显示当前login页面URL（如果变化了）
                    if "login.augmentcode.com" in url and url != last_url:
                        print(f"   📍 当前页面: login.augmentcode.com/...")
                        last_url = url

            # 显示等待进度
            elapsed = int(time.time() - start_time)
            if elapsed % 5 == 0:  # 每5秒显示一次
                print(f"   ⏳ 等待中... ({elapsed}秒)")
            human_delay(2.0)

        print(f"   ✗ 等待超时（{max_wait_seconds}秒）")
        return False

    finally:
        cdp.close()


def get_payment_method_link(ws_url):
    """从onboard页面点击Add Payment Method按钮并获取跳转链接

    Args:
        ws_url (str): WebSocket地址

    Returns:
        str: 支付方法链接，失败返回None
    """
    print(f"\n🔍 点击Add Payment Method按钮获取链接...")

    cdp = CDPClient(ws_url)

    try:
        # 1. 获取所有页面
        print("   📄 步骤1: 获取所有页面...")
        result = cdp.send("Target.getTargets", {})
        if not result or "result" not in result:
            print("   ✗ 无法获取页面列表")
            return None

        targets = result["result"]["targetInfos"]

        # 2. 查找onboard页面
        print("   🔍 步骤2: 查找onboard页面...")
        onboard_target_id = None
        for target in targets:
            if target.get("type") == "page":
                url = target.get("url", "")
                if "app.augmentcode.com/onboard" in url:
                    onboard_target_id = target.get("targetId")
                    print(f"   ✓ 找到onboard页面: {url}")
                    break

        if not onboard_target_id:
            print("   ✗ 未找到onboard页面")
            return None

        # 3. 激活onboard页面
        print("   🎯 步骤3: 激活onboard页面...")
        cdp.send("Target.activateTarget", {"targetId": onboard_target_id})
        human_delay(1.0)

        # 4. 附加到页面
        print("   🔗 步骤4: 附加到onboard页面...")
        result = cdp.send("Target.attachToTarget", {
            "targetId": onboard_target_id,
            "flatten": True
        })
        if not result or "result" not in result:
            print("   ✗ 无法附加到页面")
            return None

        session_id = result["result"]["sessionId"]
        print(f"   ✓ 已附加到页面 (sessionId: {session_id})")

        # 5. 启用必要的域
        print("   ⚙️  步骤5: 启用必要的域...")
        cdp.send("DOM.enable", {}, session_id=session_id)
        cdp.send("Runtime.enable", {}, session_id=session_id)
        cdp.send("Page.enable", {}, session_id=session_id)
        cdp.send("Network.enable", {}, session_id=session_id)

        # 等待页面完全加载
        print("   ⏳ 等待页面加载...")
        human_delay(3.0)

        # 6. 查找并点击Add Payment Method按钮
        print("   🔍 步骤6: 查找Add Payment Method按钮...")

        # 先尝试查找按钮
        result = cdp.send("Runtime.evaluate", {
            "expression": """
            (function() {
                const buttons = Array.from(document.querySelectorAll('button'));
                const btn = buttons.find(b => b.textContent.includes('Add Payment Method'));
                if (btn) {
                    return btn.outerHTML;
                }
                return null;
            })()
            """,
            "returnByValue": True
        }, session_id=session_id)

        if result and "result" in result and "result" in result["result"]:
            value = result["result"]["result"].get("value")
            if value:
                print(f"   ✓ 找到按钮")
                print(f"   📝 按钮HTML: {value[:100]}...")
            else:
                print("   ✗ 未找到Add Payment Method按钮")
                return None
        else:
            print("   ✗ 未找到Add Payment Method按钮")
            return None

        # 7. 点击按钮并监听导航
        print("   🖱️  步骤7: 点击按钮...")

        # 点击按钮
        click_result = cdp.send("Runtime.evaluate", {
            "expression": """
            (function() {
                const buttons = Array.from(document.querySelectorAll('button'));
                const btn = buttons.find(b => b.textContent.includes('Add Payment Method'));
                if (btn) {
                    btn.click();
                    return true;
                }
                return false;
            })()
            """,
            "returnByValue": True
        }, session_id=session_id)

        if click_result and "result" in click_result and "result" in click_result["result"]:
            clicked = click_result["result"]["result"].get("value")
            if clicked:
                print("   ✓ 按钮已点击")
            else:
                print("   ✗ 点击按钮失败")
                return None
        else:
            print("   ✗ 点击按钮失败")
            return None

        # 8. 等待页面导航并获取新URL
        print("   ⏳ 步骤8: 等待页面导航...")
        human_delay(2.0)  # 等待导航开始

        # 轮询检测URL变化（最多等待10秒）
        payment_link = None
        max_wait = 10
        for attempt in range(max_wait):
            # 获取当前所有页面
            result = cdp.send("Target.getTargets", {})
            if result and "result" in result:
                targets = result["result"]["targetInfos"]

                # 查找新打开的页面或URL变化的页面
                for target in targets:
                    if target.get("type") == "page":
                        url = target.get("url", "")

                        # 检查是否是支付相关页面
                        if "payment" in url.lower() or "billing" in url.lower() or "stripe" in url.lower():
                            payment_link = url
                            print(f"   ✓ 检测到导航到支付页面（用时{attempt + 1}秒）")
                            print(f"   🔗 链接: {payment_link}")
                            return payment_link

                        # 检查是否URL发生了变化（不再是onboard页面）
                        if "app.augmentcode.com" in url and "onboard" not in url:
                            payment_link = url
                            print(f"   ✓ 检测到页面跳转（用时{attempt + 1}秒）")
                            print(f"   🔗 链接: {payment_link}")
                            return payment_link

            # 显示等待进度
            if attempt < max_wait - 1:
                print(f"   ⏳ 等待导航... ({attempt + 1}秒)")
                human_delay(1.0)

        print(f"   ⚠️  未检测到页面导航（已等待{max_wait}秒）")
        print("   💡 提示: 按钮可能没有触发导航，或导航速度较慢")
        return None

    except Exception as e:
        print(f"   ✗ 获取支付方法链接时出错: {e}")
        import traceback
        traceback.print_exc()
        return None

    finally:
        cdp.close()


def get_session_cookie(ws_url):
    """获取session cookie

    Args:
        ws_url (str): WebSocket地址

    Returns:
        str: session值，失败返回None
    """
    print(f"\n🍪 正在获取session cookie...")

    # 1. 连接到浏览器
    cdp = CDPClient(ws_url)

    try:
        # 2. 创建新标签页打开auth页面
        print("   📄 打开auth.augmentcode.com页面...")
        result = cdp.send("Target.createTarget", {
            "url": "https://auth.augmentcode.com"
        })

        if not result or "result" not in result:
            print("   ✗ 无法创建新标签页")
            return None

        target_id = result["result"]["targetId"]
        print(f"   ✓ 新标签页已创建")

        # 等待页面加载
        print("   ⏳ 等待页面加载...")
        human_delay(3.0)

        # 3. 激活页面
        print("   🎯 激活auth页面...")
        cdp.send("Target.activateTarget", {"targetId": target_id})
        human_delay(1.0)

        # 4. 附加到 target
        result = cdp.send("Target.attachToTarget", {
            "targetId": target_id,
            "flatten": True
        })

        if not result or "result" not in result:
            print("   ✗ 无法附加到 target")
            return None

        session_id = result["result"]["sessionId"]

        # 5. 启用Network域以获取cookies
        cdp.send("Network.enable", {}, session_id=session_id)

        # 6. 获取所有cookies
        print("   🍪 获取cookies...")
        result = cdp.send("Network.getAllCookies", {}, session_id=session_id)

        if not result or "result" not in result:
            print("   ✗ 无法获取cookies")
            return None

        cookies = result["result"]["cookies"]
        print(f"   📋 找到 {len(cookies)} 个cookies")

        # 7. 查找session cookie
        session_value = None
        for cookie in cookies:
            name = cookie.get("name", "")
            domain = cookie.get("domain", "")
            value = cookie.get("value", "")

            print(f"   🍪 Cookie: {name} = {value[:20]}... (domain: {domain})")

            if name.lower() == "session" and "augmentcode.com" in domain:
                session_value = value
                print(f"   ✓ 找到session cookie!")
                print(f"   📝 Session值: {session_value}")
                break

        if not session_value:
            print("   ⚠️  未找到session cookie")
            print("   💡 提示: 可能需要等待登录完成")
            return None

        return session_value

    finally:
        cdp.close()


def fill_verification_code(ws_url, email):
    """获取验证码并填写

    Args:
        ws_url (str): WebSocket地址
        email (str): 邮箱地址

    Returns:
        bool: 成功返回True，失败返回False
    """
    print(f"\n🔐 正在获取并填写验证码...")

    # 1. 获取验证码
    verification_code = get_verification_code_from_email(email)

    if not verification_code:
        print("   ✗ 未能获取验证码")
        return False

    print(f"   ✓ 验证码: {verification_code}")

    # 2. 连接到浏览器
    cdp = CDPClient(ws_url)

    try:
        # 3. 获取Augment页面
        print("   🔍 查找Augment页面...")
        result = cdp.send("Target.getTargets", {})
        if not result or "result" not in result:
            print("   ✗ 无法获取 targets")
            return False

        targets = result["result"]["targetInfos"]

        # 根据URL查找Augment页面
        augment_target = None
        for target in targets:
            if target.get("type") == "page":
                url = target.get("url", "")
                if "augmentcode.com" in url:
                    augment_target = target
                    print(f"   ✓ 找到Augment页面: {url}")
                    break

        if not augment_target:
            print("   ✗ 未找到Augment页面")
            return False

        target_id = augment_target["targetId"]

        # 4. 激活页面
        print("   🎯 激活Augment页面...")
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

        # 7. 查找并填写验证码输入框
        print("   ✍️  填写验证码...")

        # 尝试多种选择器
        selectors = [
            'input[type="text"]',
            'input[type="number"]',
            'input[name*="code"]',
            'input[name*="verification"]',
            'input[placeholder*="code"]',
            'input[placeholder*="verification"]',
            'input[id*="code"]',
            'input[id*="verification"]',
        ]

        filled = False
        for selector in selectors:
            result = cdp.send("Runtime.evaluate", {
                "expression": f"""
                    (() => {{
                        const input = document.querySelector('{selector}');
                        if (input) {{
                            input.value = '{verification_code}';
                            input.dispatchEvent(new Event('input', {{ bubbles: true }}));
                            input.dispatchEvent(new Event('change', {{ bubbles: true }}));
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
                    print(f"   ✓ 成功填写验证码: {verification_code}")
                    filled = True
                    break

        if not filled:
            print("   ⚠️  未找到验证码输入框")
            print("   💡 提示: 请手动填写验证码")
            return False

        print("   ✓ 验证码填写完成!")

        # 8. 等待一下，然后点击Continue按钮
        print("   ⏳ 等待页面更新...")
        human_delay(2.0)

        print("   ➡️  点击Continue按钮...")
        continue_success = click_continue_button(cdp, session_id)
        if continue_success:
            print("   ✓ Continue按钮已点击")
        else:
            print("   ⚠️  未找到Continue按钮")
            print("   💡 提示: 可能需要手动点击Continue")

        print("   ✓ 所有操作完成!")
        return True

    finally:
        cdp.close()


def main():
    """主函数 - 演示如何使用脚本"""
    print("=" * 70)
    print("比特浏览器窗口创建脚本 v1.0")
    print("=" * 70)

    # 1. 创建窗口（使用SOCKS5代理，不设置platform和url）
    browser_id = BitBrowserAPI.create_window(
        name="Augment注册",
        remark="Augment注册",
        proxyType="socks5",
        host="127.0.0.1",
        port=7890
    )

    if not browser_id:
        print("\n❌ 创建窗口失败，程序退出")
        return

    # 2. 打开窗口
    result = BitBrowserAPI.open_window(browser_id)

    if not result:
        print("\n❌ 打开窗口失败，程序退出")
        return

    # 3. 获取WebSocket地址
    ws_url = result.get("ws")

    # 4. 使用CDP打开标签页
    print("\n📑 正在打开标签页...")
    cdp = CDPClient(ws_url)

    try:
        # 先打开邮箱页面
        print("   📧 打开邮箱页面...")
        result = cdp.send("Target.createTarget", {
            "url": "https://mail.chatgpt.org.uk/"
        })
        if result and "result" in result:
            print("   ✓ 邮箱页面已打开")
        else:
            print("   ✗ 邮箱页面打开失败")

        # 等待一下
        human_delay(1.0)

        # 再打开登录页面
        print("   🔐 打开登录页面...")
        result = cdp.send("Target.createTarget", {
            "url": "https://login.augmentcode.com/"
        })
        if result and "result" in result:
            print("   ✓ 登录页面已打开")
        else:
            print("   ✗ 登录页面打开失败")

        # 等待页面加载
        print("   ⏳ 等待页面加载...")
        human_delay(3.0)

    finally:
        cdp.close()

    # 5. 获取邮箱地址
    email = get_email_from_browser(ws_url)

    # 6. 保存邮箱地址
    if email:
        EmailUtils.save_suffix(email)  # 保存邮箱后缀到JSON文件
        filename = EmailUtils.save_email_to_file(email)
        if filename:
            print(f"\n✅ 邮箱获取成功！")
            print(f"   邮箱地址: {email}")
            print(f"   访问链接: https://mail.chatgpt.org.uk/{email}")
            print(f"   保存文件: {filename}")
    else:
        print("\n⚠️  未能自动获取邮箱地址")
        print("   提示: 请手动从浏览器窗口中复制邮箱地址")

    # 7. 切换到Augment页面并点击Sign in，填写邮箱
    if email:
        success = switch_to_augment_and_signin(ws_url, email)
        if success:
            print("\n✅ 已切换到Augment登录页面，点击Sign in并填写邮箱!")
        else:
            print("\n⚠️  自动操作失败，请手动完成剩余步骤")
            email = None  # 标记失败，跳过后续步骤

    # 8. 获取验证码并填写
    if email:
        code_success = fill_verification_code(ws_url, email)
        if code_success:
            print("\n✅ 验证码已自动填写!")
        else:
            print("\n⚠️  验证码填写失败，请手动完成")
            email = None  # 标记失败，跳过后续步骤

    # 9. 等待页面跳转到onboard
    if email:
        redirect_success = wait_for_onboard_redirect(ws_url, max_wait_seconds=60)
        if redirect_success:
            print("\n✅ 页面已成功跳转到onboard!")
        else:
            print("\n⚠️  页面未跳转到onboard")
            print("   💡 提示: 可能需要手动完成验证或等待更长时间")
            email = None  # 标记失败，跳过后续步骤

    # 10. 获取Add Payment Method按钮链接
    payment_link_success = False
    if email:
        payment_link = get_payment_method_link(ws_url)
        if payment_link:
            print(f"\n✅ 支付方法链接获取成功!")
            print(f"   🔗 链接: {payment_link}")

            # 保存链接到文件
            link_filename = f"payment_link_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
            try:
                with open(link_filename, 'w', encoding='utf-8') as f:
                    f.write(payment_link)
                print(f"   💾 链接已保存到: {link_filename}")
                payment_link_success = True
            except Exception as e:
                print(f"   ⚠️  保存链接失败: {e}")
        else:
            print("\n⚠️  支付方法链接获取失败")
            print("   💡 提示: 可能需要等待页面加载或手动查找")

    # 11. 获取session cookie
    session_success = False
    if email:
        session = get_session_cookie(ws_url)
        if session:
            print(f"\n✅ Session cookie获取成功!")
            print(f"   📝 Session值: {session}")

            # 保存session到文件
            session_filename = f"session_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
            try:
                with open(session_filename, 'w', encoding='utf-8') as f:
                    f.write(session)
                print(f"   💾 Session已保存到: {session_filename}")
                session_success = True
            except Exception as e:
                print(f"   ⚠️  保存session失败: {e}")
        else:
            print("\n⚠️  Session cookie获取失败")
            print("   💡 提示: 可能需要等待更长时间或手动获取")

    # 12. 判断是否自动关闭窗口
    should_auto_close = payment_link_success and session_success

    if should_auto_close:
        print("\n🎉 所有关键信息获取成功！")
        print("   ✓ 支付方法链接已获取")
        print("   ✓ Session cookie已获取")
        print("\n🔒 自动关闭浏览器窗口...")
        BitBrowserAPI.close_window(browser_id)
        print("\n✨ 所有操作完成！")
    else:
        print("\n⚠️  部分信息获取失败，窗口保持打开状态")
        if not payment_link_success:
            print("   ✗ 支付方法链接获取失败")
        if not session_success:
            print("   ✗ Session cookie获取失败")

        # 等待用户操作
        input("\n按回车键手动关闭窗口...")
        BitBrowserAPI.close_window(browser_id)
        print("\n✨ 操作完成！")


if __name__ == "__main__":
    main()

