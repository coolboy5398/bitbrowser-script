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
    2. 运行此脚本: python bitbrowser_create_window.py
    3. 脚本会自动创建、打开窗口，并显示WebSocket地址

作者: AI Assistant
版本: 1.0
"""

import json
import time
import random
import re
import websocket
from datetime import datetime
from urllib.request import urlopen, Request
from urllib.error import URLError, HTTPError
from urllib.parse import quote


# 比特浏览器本地API地址
BIT_BASE_URL = "http://127.0.0.1:54345"


def human_delay(base_seconds, jitter_percent=0.3):
    """模拟人类操作的延迟，添加随机抖动

    Args:
        base_seconds: 基础延迟时间（秒）
        jitter_percent: 抖动百分比，默认30%

    Returns:
        实际延迟时间
    """
    jitter = base_seconds * jitter_percent
    delay = base_seconds + random.uniform(-jitter, jitter)
    # 确保延迟不小于0.1秒
    delay = max(0.1, delay)
    time.sleep(delay)
    return delay


class CDPClient:
    """简易 CDP 客户端"""
    def __init__(self, ws_url: str, timeout: float = 10.0):
        self.ws = websocket.create_connection(ws_url, timeout=timeout, suppress_origin=True)
        self.ws.settimeout(timeout)
        self._id = 0

    def send(self, method: str, params: dict = None, session_id: str = None):
        """发送 CDP 命令"""
        self._id += 1
        msg = {"id": self._id, "method": method, "params": params or {}}
        if session_id:
            msg["sessionId"] = session_id

        self.ws.send(json.dumps(msg))

        # 等待响应
        deadline = time.time() + 10.0
        while time.time() < deadline:
            try:
                raw = self.ws.recv()
                resp = json.loads(raw)
                if resp.get("id") == self._id:
                    return resp
            except Exception:
                return None
        return None

    def close(self):
        """关闭连接"""
        try:
            self.ws.close()
        except Exception:
            pass


def create_browser_window(name, platform="https://www.google.com", **kwargs):
    """创建比特浏览器窗口

    Args:
        name (str): 窗口名称
        platform (str): 平台URL，默认为Google
        **kwargs: 其他可选参数
            - remark (str): 备注
            - url (str): 额外打开的URL
            - proxyType (str): 代理类型，可选值: 'noproxy', 'http', 'https', 'socks5'
            - host (str): 代理主机地址
            - port (int): 代理端口
            - proxyUserName (str): 代理用户名（如果需要认证）
            - proxyPassword (str): 代理密码（如果需要认证）

    Returns:
        str: 创建成功返回浏览器窗口ID，失败返回None

    Example:
        >>> # 不使用代理
        >>> browser_id = create_browser_window("测试窗口", "https://www.facebook.com")
        >>>
        >>> # 使用SOCKS5代理
        >>> browser_id = create_browser_window(
        >>>     name="测试窗口",
        >>>     platform="https://www.facebook.com",
        >>>     proxyType="socks5",
        >>>     host="127.0.0.1",
        >>>     port=7890
        >>> )
    """
    print(f"🔨 正在创建窗口: {name}")
    
    # 构建请求数据
    data = {
        "name": name,
        "platform": platform,
        "browserFingerPrint": {},  # 空对象表示使用随机指纹
        "proxyMethod": 2,  # 2表示自定义代理
        "proxyType": kwargs.get("proxyType", "noproxy"),
    }

    # 添加代理配置
    if "host" in kwargs:
        data["host"] = kwargs["host"]
    if "port" in kwargs:
        data["port"] = kwargs["port"]
    if "proxyUserName" in kwargs:
        data["proxyUserName"] = kwargs["proxyUserName"]
    if "proxyPassword" in kwargs:
        data["proxyPassword"] = kwargs["proxyPassword"]

    # 添加其他可选参数
    if "remark" in kwargs:
        data["remark"] = kwargs["remark"]
    if "url" in kwargs:
        data["url"] = kwargs["url"]
    
    try:
        # 发送创建请求
        url = f"{BIT_BASE_URL}/browser/update"
        json_data = json.dumps(data).encode("utf-8")
        headers = {"Content-Type": "application/json"}
        
        req = Request(url, data=json_data, headers=headers, method="POST")
        response = urlopen(req, timeout=10)
        result = json.loads(response.read().decode("utf-8"))
        
        if result.get("success"):
            browser_id = result.get("data", {}).get("id")
            print(f"✅ 窗口创建成功！")
            print(f"   窗口ID: {browser_id}")
            return browser_id
        else:
            print(f"❌ 创建失败: {result.get('msg', '未知错误')}")
            return None
            
    except HTTPError as e:
        print(f"❌ HTTP错误: {e.code} - {e.reason}")
        return None
    except URLError as e:
        print(f"❌ 连接错误: {e.reason}")
        print("   提示: 请确保比特浏览器客户端正在运行")
        return None
    except Exception as e:
        print(f"❌ 创建失败: {e}")
        return None


def open_browser_window(browser_id):
    """打开比特浏览器窗口
    
    Args:
        browser_id (str): 浏览器窗口ID
    
    Returns:
        dict: 成功返回包含ws、http、driver等信息的字典，失败返回None
        
    Example:
        >>> result = open_browser_window(browser_id)
        >>> if result:
        >>>     print(f"WebSocket: {result['ws']}")
        >>>     print(f"HTTP: {result['http']}")
    """
    print(f"\n🚀 正在打开窗口: {browser_id}")
    
    try:
        # 发送打开请求
        url = f"{BIT_BASE_URL}/browser/open"
        data = json.dumps({"id": browser_id}).encode("utf-8")
        headers = {"Content-Type": "application/json"}
        
        req = Request(url, data=data, headers=headers, method="POST")
        response = urlopen(req, timeout=30)  # 打开窗口可能需要较长时间
        result = json.loads(response.read().decode("utf-8"))
        
        if result.get("success"):
            data = result.get("data", {})
            print(f"✅ 窗口打开成功！")
            print(f"   WebSocket: {data.get('ws')}")
            print(f"   HTTP: {data.get('http')}")
            print(f"   内核版本: {data.get('coreVersion')}")
            return data
        else:
            print(f"❌ 打开失败: {result.get('msg', '未知错误')}")
            return None
            
    except HTTPError as e:
        print(f"❌ HTTP错误: {e.code} - {e.reason}")
        return None
    except URLError as e:
        print(f"❌ 连接错误: {e.reason}")
        return None
    except Exception as e:
        print(f"❌ 打开失败: {e}")
        return None


def close_browser_window(browser_id):
    """关闭比特浏览器窗口
    
    Args:
        browser_id (str): 浏览器窗口ID
    
    Returns:
        bool: 成功返回True，失败返回False
        
    Example:
        >>> success = close_browser_window(browser_id)
        >>> if success:
        >>>     print("窗口已关闭")
    """
    print(f"\n🔒 正在关闭窗口: {browser_id}")
    
    try:
        # 发送关闭请求
        url = f"{BIT_BASE_URL}/browser/close"
        data = json.dumps({"id": browser_id}).encode("utf-8")
        headers = {"Content-Type": "application/json"}
        
        req = Request(url, data=data, headers=headers, method="POST")
        response = urlopen(req, timeout=10)
        result = json.loads(response.read().decode("utf-8"))
        
        if result.get("success"):
            print(f"✅ 窗口关闭成功！")
            return True
        else:
            print(f"❌ 关闭失败: {result.get('msg', '未知错误')}")
            return False
            
    except HTTPError as e:
        print(f"❌ HTTP错误: {e.code} - {e.reason}")
        return False
    except URLError as e:
        print(f"❌ 连接错误: {e.reason}")
        return False
    except Exception as e:
        print(f"❌ 关闭失败: {e}")
        return False


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


def save_email_to_file(email):
    """保存邮箱地址到文件

    Args:
        email (str): 邮箱地址

    Returns:
        str: 保存的文件名，失败返回None
    """
    print(f"\n💾 正在保存邮箱地址...")

    access_url = f"https://mail.chatgpt.org.uk/{email}"

    content = f"""GPTMail 临时邮箱地址
===================

生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
网站地址: https://mail.chatgpt.org.uk/

邮箱地址: {email}

访问链接: {access_url}

说明:
- 此邮箱为临时邮箱，1天后自动删除
- 收件箱会自动刷新（30秒）
- 可以通过访问链接直接查看该邮箱的收件箱
"""

    filename = f"临时邮箱_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"

    try:
        with open(filename, 'w', encoding='utf-8') as f:
            f.write(content)
        print(f"   ✓ 邮箱地址已保存到: {filename}")
        return filename
    except Exception as e:
        print(f"   ✗ 保存失败: {e}")
        return None


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

        # 步骤7: 查找并填写work mail输入框
        print("   ✍️  步骤7: 填写work mail...")

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

        # 步骤8: 点击Cloudflare验证框
        print("   🛡️  步骤8: 处理Cloudflare验证...")
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

        # 步骤9: 点击Continue按钮
        print("   ➡️  步骤9: 查找并点击Continue按钮...")
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
    
    # 1. 创建窗口（使用SOCKS5代理）
    browser_id = create_browser_window(
        name="Augment注册",
        platform="https://mail.chatgpt.org.uk/",
        url="https://login.augmentcode.com/",
        remark="Augment注册",
        proxyType="socks5",
        host="127.0.0.1",
        port=7890
    )
    
    if not browser_id:
        print("\n❌ 创建窗口失败，程序退出")
        return
    
    # 2. 打开窗口
    result = open_browser_window(browser_id)
    
    if not result:
        print("\n❌ 打开窗口失败，程序退出")
        return
    
    # 3. 获取邮箱地址
    ws_url = result.get("ws")
    email = get_email_from_browser(ws_url)

    # 4. 保存邮箱地址
    if email:
        filename = save_email_to_file(email)
        if filename:
            print(f"\n✅ 邮箱获取成功！")
            print(f"   邮箱地址: {email}")
            print(f"   访问链接: https://mail.chatgpt.org.uk/{email}")
            print(f"   保存文件: {filename}")
    else:
        print("\n⚠️  未能自动获取邮箱地址")
        print("   提示: 请手动从浏览器窗口中复制邮箱地址")

    # 5. 切换到Augment页面并点击Sign in，填写邮箱
    if email:
        success = switch_to_augment_and_signin(ws_url, email)
        if success:
            print("\n✅ 已切换到Augment登录页面，点击Sign in并填写邮箱!")
        else:
            print("\n⚠️  自动操作失败，请手动完成剩余步骤")
            email = None  # 标记失败，跳过后续步骤

    # 6. 获取验证码并填写
    if email:
        code_success = fill_verification_code(ws_url, email)
        if code_success:
            print("\n✅ 验证码已自动填写!")
        else:
            print("\n⚠️  验证码填写失败，请手动完成")

    # 7. 等待用户操作（可选）
    input("\n按回车键关闭窗口...")

    # 8. 关闭窗口
    close_browser_window(browser_id)

    print("\n✨ 所有操作完成！")


if __name__ == "__main__":
    main()

