#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ChatGPT临时邮箱服务提供者

实现 https://mail.chatgpt.org.uk/ 临时邮箱服务

作者: AI Assistant
版本: 1.0
"""

import re
from urllib.request import urlopen, Request
from urllib.error import URLError, HTTPError
from urllib.parse import quote
import json

from .email_provider import EmailProvider


class ChatGPTMailProvider(EmailProvider):
    """ChatGPT临时邮箱服务提供者
    
    实现 https://mail.chatgpt.org.uk/ 临时邮箱服务
    """
    
    def __init__(self):
        self.base_url = "https://mail.chatgpt.org.uk"
        self.api_url = f"{self.base_url}/api/emails"

    def needs_browser_page(self) -> bool:
        """ChatGPT邮箱需要打开浏览器页面获取邮箱"""
        return True

    def get_page_url(self) -> str:
        """获取邮箱页面URL"""
        return f"{self.base_url}/"

    def get_domain_patterns(self) -> list:
        """获取域名匹配模式

        返回用于识别ChatGPT邮箱页面的域名模式
        """
        return ["chatgpt.org.uk"]

    def _detect_cloudflare(self, cdp, session_id) -> bool:
        """检测页面是否有Cloudflare验证

        Args:
            cdp: CDPClient实例
            session_id: CDP会话ID

        Returns:
            bool: True表示检测到Cloudflare验证，False表示没有
        """
        print("   🔍 检测Cloudflare验证...")

        try:
            # 使用JavaScript检查页面特征
            result = cdp.send("Runtime.evaluate", {
                "expression": """
                    (() => {
                        // 检查页面标题
                        const title = document.title || '';
                        if (title.includes('Just a moment')) {
                            return 'title';
                        }

                        // 检查页面文本内容
                        const bodyText = document.body.innerText || document.body.textContent || '';
                        if (bodyText.includes('Enable JavaScript and cookies to continue')) {
                            return 'text';
                        }
                        if (bodyText.includes('Checking your browser')) {
                            return 'text';
                        }

                        // 检查Cloudflare特征元素
                        const cfElements = document.querySelectorAll('[id*="cf-"], [class*="cf-"]');
                        if (cfElements.length > 0) {
                            return 'element';
                        }

                        return null;
                    })()
                """,
                "returnByValue": True
            }, session_id=session_id)

            if result and "result" in result and "result" in result["result"]:
                detection = result["result"]["result"].get("value")
                if detection:
                    print(f"   ✓ 检测到Cloudflare验证（特征：{detection}）")
                    return True

            print("   ✓ 未检测到Cloudflare验证")
            return False

        except Exception as e:
            print(f"   ⚠️  检测出错: {e}，假设无Cloudflare")
            return False

    def _bypass_cloudflare(self, cdp, session_id, timeout=30) -> bool:
        """自动绕过Cloudflare验证

        Args:
            cdp: CDPClient实例
            session_id: CDP会话ID
            timeout: 超时时间（秒），默认30秒

        Returns:
            bool: True表示绕过成功，False表示失败
        """
        print("   🔓 开始绕过Cloudflare验证...")

        try:
            import time

            # 0. 先等待一下，让页面完全加载
            print("   ⏳ 等待页面加载...")
            time.sleep(2)

            # 1. 启用DOM域
            cdp.send("DOM.enable", {}, session_id=session_id)

            # 2. 查找Cloudflare验证框元素
            print("   🔍 查找验证框元素...")
            result = cdp.send("DOM.getDocument", {"depth": -1}, session_id=session_id)
            if not result or "result" not in result:
                print("   ✗ 无法获取DOM文档")
                return False

            root_node_id = result["result"]["root"]["nodeId"]

            # 支持多种Cloudflare验证框选择器（按优先级排序）
            selectors = [
                'input[type="checkbox"]',       # Cloudflare checkbox（最优先）
                'iframe[src*="challenges.cloudflare.com"]',  # Cloudflare iframe
                'div[id*="cf-"][id*="challenge"]',  # 同时包含cf和challenge
                'div[class*="cf-"][class*="challenge"]',
                'div[id*="cf-"]',               # Cloudflare元素
                'div[class*="cf-"]',
            ]

            node_id = None
            found_selector = None

            for selector in selectors:
                result = cdp.send("DOM.querySelectorAll", {
                    "nodeId": root_node_id,
                    "selector": selector
                }, session_id=session_id)

                if result and "result" in result and result["result"].get("nodeIds"):
                    node_ids = result["result"]["nodeIds"]
                    if node_ids:
                        # 尝试每个找到的元素，直到找到可以获取位置的
                        for nid in node_ids:
                            # 先检查能否获取位置
                            box_result = cdp.send("DOM.getBoxModel", {"nodeId": nid}, session_id=session_id)
                            if box_result and "result" in box_result:
                                node_id = nid
                                found_selector = selector
                                print(f"   ✓ 找到可用验证框元素（选择器：{selector}）")
                                break

                        if node_id:
                            break

            if not node_id:
                print("   ⚠️  未找到可用验证框元素")
                print("   💡 尝试使用JavaScript直接点击...")

                # 尝试使用JavaScript直接查找并点击
                js_result = cdp.send("Runtime.evaluate", {
                    "expression": """
                        (() => {
                            // 查找Cloudflare验证框
                            const checkbox = document.querySelector('input[type="checkbox"]');
                            if (checkbox && checkbox.offsetParent !== null) {
                                checkbox.click();
                                return 'clicked_checkbox';
                            }

                            // 查找可点击的验证区域
                            const cfElements = document.querySelectorAll('[id*="cf-"], [class*="cf-"]');
                            for (const el of cfElements) {
                                if (el.offsetParent !== null && el.offsetWidth > 0 && el.offsetHeight > 0) {
                                    el.click();
                                    return 'clicked_element';
                                }
                            }

                            return null;
                        })()
                    """,
                    "returnByValue": True
                }, session_id=session_id)

                if js_result and "result" in js_result and "result" in js_result["result"]:
                    click_result = js_result["result"]["result"].get("value")
                    if click_result:
                        print(f"   ✓ JavaScript点击成功（{click_result}）")
                        # 等待验证完成
                        time.sleep(3)
                        # 跳到验证检查步骤
                        node_id = -1  # 标记为已处理
                    else:
                        print("   ⚠️  JavaScript未找到可点击元素，可能验证已完成")
                        time.sleep(3)
                        return True
                else:
                    print("   ⚠️  JavaScript执行失败，可能验证已完成")
                    time.sleep(3)
                    return True

            # 3. 获取元素位置（仅当通过DOM找到元素时）
            if node_id > 0:
                print("   📍 获取元素位置...")
                result = cdp.send("DOM.getBoxModel", {"nodeId": node_id}, session_id=session_id)
                if not result or "result" not in result:
                    print("   ✗ 无法获取元素位置（元素可能不可见）")
                    print("   💡 尝试等待页面完全加载...")
                    time.sleep(3)
                    return True  # 可能验证已自动完成

                box_model = result["result"]["model"]
                content = box_model["content"]
                x = (content[0] + content[4]) / 2
                y = (content[1] + content[5]) / 2
                width = content[4] - content[0]
                height = content[5] - content[1]

                print(f"   ✓ 元素位置: ({x:.1f}, {y:.1f}), 大小: {width:.1f}x{height:.1f}")

                # 4. 点击验证框
                print("   🖱️  点击验证框...")

                # 鼠标移动
                cdp.send("Input.dispatchMouseEvent", {
                    "type": "mouseMoved",
                    "x": x,
                    "y": y
                }, session_id=session_id)

                # 鼠标按下
                cdp.send("Input.dispatchMouseEvent", {
                    "type": "mousePressed",
                    "x": x,
                    "y": y,
                    "button": "left",
                    "clickCount": 1
                }, session_id=session_id)

                # 鼠标释放
                cdp.send("Input.dispatchMouseEvent", {
                    "type": "mouseReleased",
                    "x": x,
                    "y": y,
                    "button": "left",
                    "clickCount": 1
                }, session_id=session_id)

                print("   ✓ 点击完成")

            # 5. 等待验证完成
            print(f"   ⏳ 等待验证完成（最多{timeout}秒）...")
            start_time = time.time()

            while time.time() - start_time < timeout:
                # 检查页面是否还有Cloudflare特征
                if not self._detect_cloudflare(cdp, session_id):
                    elapsed = time.time() - start_time
                    print(f"   ✅ 验证完成！（耗时{elapsed:.1f}秒）")
                    return True

                time.sleep(1)

            print(f"   ⚠️  验证超时（{timeout}秒）")
            return False

        except Exception as e:
            print(f"   ✗ 绕过Cloudflare出错: {e}")
            return False

    def _wait_for_email_element(self, cdp, session_id, timeout=30) -> bool:
        """智能等待邮箱元素出现

        Args:
            cdp: CDPClient实例
            session_id: CDP会话ID
            timeout: 超时时间（秒），默认30秒

        Returns:
            bool: True表示找到邮箱元素，False表示超时
        """
        print(f"   ⏳ 等待邮箱元素出现（最多{timeout}秒）...")

        import time
        start_time = time.time()
        attempt = 0

        while time.time() - start_time < timeout:
            attempt += 1
            try:
                # 检查是否有包含@符号的元素
                result = cdp.send("Runtime.evaluate", {
                    "expression": """
                        (() => {
                            // 查找所有可能包含邮箱的元素
                            const selectors = [
                                'input[type="text"]',
                                'input[type="email"]',
                                'input[readonly]',
                                'div[class*="email"]',
                                'span[class*="email"]',
                                'p[class*="email"]',
                                'code',
                                'pre'
                            ];

                            for (const selector of selectors) {
                                const elements = document.querySelectorAll(selector);
                                for (const el of elements) {
                                    const text = el.value || el.textContent || el.innerText;
                                    if (text && text.includes('@')) {
                                        return true;
                                    }
                                }
                            }

                            // 检查整个页面文本
                            const bodyText = document.body.innerText || document.body.textContent;
                            if (bodyText && bodyText.includes('@')) {
                                return true;
                            }

                            return false;
                        })()
                    """,
                    "returnByValue": True
                }, session_id=session_id)

                if result and "result" in result and "result" in result["result"]:
                    found = result["result"]["result"].get("value")
                    if found:
                        elapsed = time.time() - start_time
                        print(f"   ✓ 找到邮箱元素（耗时{elapsed:.1f}秒，尝试{attempt}次）")
                        return True

                # 每次等待1秒
                if attempt % 5 == 0:
                    print(f"   ⏳ 继续等待... ({attempt}次尝试，已用{time.time() - start_time:.1f}秒)")
                time.sleep(1)

            except Exception as e:
                print(f"   ⚠️  检查出错: {e}")
                time.sleep(1)

        print(f"   ✗ 等待超时（{timeout}秒）")
        return False

    def _extract_email(self, cdp, session_id) -> str:
        """从页面提取邮箱地址

        使用双策略提取邮箱：
        1. 策略1：查找特定元素中的邮箱
        2. 策略2：等待后再次尝试

        Args:
            cdp: CDPClient实例
            session_id: CDP会话ID

        Returns:
            str: 邮箱地址，失败返回None
        """
        print("   📧 提取邮箱地址...")

        try:
            # 策略1: 使用JavaScript查找包含@的文本内容
            print("   📝 尝试策略1: 查找包含@符号的文本...")
            result = cdp.send("Runtime.evaluate", {
                "expression": """
                    (() => {
                        // 查找所有可能包含邮箱的元素
                        const selectors = [
                            'input[type="text"]',
                            'input[type="email"]',
                            'input[readonly]',
                            'div[class*="email"]',
                            'span[class*="email"]',
                            'p[class*="email"]',
                            'code',
                            'pre'
                        ];

                        // 遍历所有选择器
                        for (const selector of selectors) {
                            const elements = document.querySelectorAll(selector);
                            for (const el of elements) {
                                const text = el.value || el.textContent || el.innerText;
                                if (text && text.includes('@')) {
                                    // 使用正则提取邮箱地址
                                    const emailMatch = text.match(/[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\\.[a-zA-Z]{2,}/);
                                    if (emailMatch) {
                                        return emailMatch[0];
                                    }
                                }
                            }
                        }

                        // 策略2: 查找整个页面文本中的邮箱
                        const bodyText = document.body.innerText || document.body.textContent;
                        const emailMatch = bodyText.match(/[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\\.[a-zA-Z]{2,}/);
                        if (emailMatch) {
                            return emailMatch[0];
                        }

                        return null;
                    })()
                """,
                "returnByValue": True
            }, session_id=session_id)

            if result and "result" in result and "result" in result["result"]:
                email = result["result"]["result"].get("value")
                if email:
                    print(f"   ✓ 成功提取邮箱: {email}")
                    return email

            print("   ⚠️  策略1未找到邮箱")

            # 策略2: 等待页面动态加载后再次尝试
            print("   ⏳ 等待页面动态加载...")
            from bitbrowser_api import human_delay
            human_delay(2.0)

            print("   📝 尝试策略2: 再次查找邮箱...")
            result = cdp.send("Runtime.evaluate", {
                "expression": """
                    (() => {
                        const bodyText = document.body.innerText || document.body.textContent;
                        const emailMatch = bodyText.match(/[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\\.[a-zA-Z]{2,}/);
                        return emailMatch ? emailMatch[0] : null;
                    })()
                """,
                "returnByValue": True
            }, session_id=session_id)

            if result and "result" in result and "result" in result["result"]:
                email = result["result"]["result"].get("value")
                if email:
                    print(f"   ✓ 成功提取邮箱: {email}")
                    return email

            print("   ✗ 无法从页面提取邮箱地址")
            print("   💡 提示: 请检查页面是否正确加载")
            return None

        except Exception as e:
            print(f"   ✗ 提取邮箱出错: {e}")
            return None

    def get_email_from_page(self, cdp, session_id) -> str:
        """从浏览器页面获取邮箱地址（增强版）

        完整流程：
        1. 检测Cloudflare验证
        2. 如果有验证，自动绕过
        3. 等待邮箱元素出现
        4. 提取邮箱地址

        Args:
            cdp: CDPClient实例
            session_id: CDP会话ID

        Returns:
            str: 邮箱地址，失败返回None
        """
        print("   🔍 步骤5: 从页面获取邮箱地址（增强版）...")

        try:
            # 步骤1: 检测Cloudflare验证
            print("\n   📋 步骤5.1: 检测Cloudflare验证")
            has_cloudflare = self._detect_cloudflare(cdp, session_id)

            # 步骤2: 如果有Cloudflare，尝试绕过
            if has_cloudflare:
                print("\n   📋 步骤5.2: 绕过Cloudflare验证")
                if not self._bypass_cloudflare(cdp, session_id, timeout=30):
                    print("   ✗ Cloudflare绕过失败")
                    return None
                print("   ✓ Cloudflare绕过成功")
            else:
                print("   ✓ 无需Cloudflare验证")

            # 步骤3: 等待邮箱元素出现
            print("\n   📋 步骤5.3: 等待邮箱元素出现")
            if not self._wait_for_email_element(cdp, session_id, timeout=30):
                print("   ✗ 邮箱元素未出现")
                return None

            # 步骤4: 提取邮箱地址
            print("\n   📋 步骤5.4: 提取邮箱地址")
            email = self._extract_email(cdp, session_id)

            if email:
                print(f"\n   ✅ 成功获取邮箱: {email}")
                return email
            else:
                print("\n   ✗ 邮箱提取失败")
                return None

        except Exception as e:
            print(f"\n   ✗ 获取邮箱出错: {e}")
            import traceback
            traceback.print_exc()
            return None
    
    def get_verification_code(self, email: str) -> str:
        """从临时邮箱API获取验证码"""
        print(f"\n📧 正在从邮箱获取验证码...")
        print(f"   📮 邮箱地址: {email}")
        
        # URL编码邮箱地址
        encoded_email = quote(email)
        api_url = f"{self.api_url}?email={encoded_email}"
        
        print(f"   🔗 API地址: {api_url}")
        
        # 最多尝试10次,每次间隔3秒
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
                    print(f"   ⏳ 暂无邮件,等待3秒后重试...")
                    from bitbrowser_api import human_delay
                    human_delay(3.0)
                    continue
                
                emails = data['emails']
                print(f"   ✓ 找到 {len(emails)} 封邮件")
                
                # 查找来自 support@augmentcode.com 的邮件
                for email_data in emails:
                    from_addr = email_data.get('from_address', '')
                    subject = email_data.get('subject', '')
                    content = email_data.get('content', '')
                    
                    print(f"   📧 邮件: {from_addr} - {subject}")
                    
                    if 'augmentcode.com' in from_addr.lower():
                        print(f"   ✓ 找到Augment邮件")
                        
                        # 从内容中提取验证码
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
                
                print(f"   ⚠️  未找到Augment邮件,等待3秒后重试...")
                from bitbrowser_api import human_delay
                human_delay(3.0)
                
            except HTTPError as e:
                print(f"   ✗ HTTP错误: {e.code} {e.reason}")
                if attempt < max_retries - 1:
                    from bitbrowser_api import human_delay
                    human_delay(3.0)
            except URLError as e:
                print(f"   ✗ 网络错误: {e.reason}")
                if attempt < max_retries - 1:
                    from bitbrowser_api import human_delay
                    human_delay(3.0)
            except Exception as e:
                print(f"   ✗ 错误: {e}")
                if attempt < max_retries - 1:
                    from bitbrowser_api import human_delay
                    human_delay(3.0)
        
        print(f"   ✗ 获取验证码失败（已尝试{max_retries}次）")
        return None

    def get_verification_code_from_page(self, ws_url, email: str) -> str:
        """从邮箱页面直接获取验证码（新实现）

        Args:
            ws_url: WebSocket地址
            email: 邮箱地址

        Returns:
            str: 验证码，失败返回None
        """
        print(f"\n📧 正在从邮箱页面获取验证码...")
        print(f"   📮 邮箱地址: {email}")

        from bitbrowser_api import CDPClient, human_delay
        import time

        # 1. 连接到浏览器
        cdp = CDPClient(ws_url)

        try:
            # 2. 查找邮箱页面
            print("   🔍 查找邮箱页面...")
            result = cdp.send("Target.getTargets", {})
            if not result or "result" not in result:
                print("   ✗ 无法获取 targets")
                return None

            targets = result["result"]["targetInfos"]

            # 查找邮箱页面
            email_target = None
            for target in targets:
                if target.get("type") == "page":
                    url = target.get("url", "")
                    if "chatgpt.org.uk" in url:
                        email_target = target
                        print(f"   ✓ 找到邮箱页面: {url}")
                        break

            if not email_target:
                print("   ✗ 未找到邮箱页面")
                print("   💡 提示: 邮箱页面可能已关闭")
                return None

            target_id = email_target["targetId"]

            # 3. 激活页面
            print("   🎯 激活邮箱页面...")
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

            # 5. 启用必要的域
            cdp.send("Runtime.enable", {}, session_id=session_id)
            cdp.send("DOM.enable", {}, session_id=session_id)

            # 6. 等待邮件到达并提取验证码
            print("   ⏳ 等待邮件到达...")
            max_retries = 20  # 最多等待60秒（20次 x 3秒）

            for attempt in range(max_retries):
                print(f"   🔄 第 {attempt + 1}/{max_retries} 次尝试...")

                try:
                    # 使用JavaScript查找邮件和验证码
                    result = cdp.send("Runtime.evaluate", {
                        "expression": """
                            (() => {
                                // 查找所有可能包含邮件的元素
                                const emailElements = document.querySelectorAll(
                                    'div[class*="email"], div[class*="message"], ' +
                                    'div[class*="mail"], li[class*="email"], ' +
                                    'tr[class*="email"], .email-item, .message-item'
                                );

                                // 遍历所有邮件元素
                                for (const el of emailElements) {
                                    const text = el.textContent || el.innerText || '';

                                    // 检查是否来自augmentcode.com
                                    if (text.includes('augmentcode.com') ||
                                        text.includes('support@augment') ||
                                        text.includes('Augment')) {

                                        // 尝试提取验证码（6位数字）
                                        const patterns = [
                                            /verification code is[:\\s]*([0-9]{6})/i,
                                            /code is[:\\s]*([0-9]{6})/i,
                                            /code[:\\s]*([0-9]{6})/i,
                                            /([0-9]{6})/
                                        ];

                                        for (const pattern of patterns) {
                                            const match = text.match(pattern);
                                            if (match && match[1]) {
                                                return match[1];
                                            }
                                        }
                                    }
                                }

                                // 如果没找到，尝试直接在整个页面查找6位数字
                                const bodyText = document.body.textContent || document.body.innerText;
                                if (bodyText.includes('augmentcode') || bodyText.includes('Augment')) {
                                    const match = bodyText.match(/([0-9]{6})/);
                                    if (match && match[1]) {
                                        return match[1];
                                    }
                                }

                                return null;
                            })()
                        """,
                        "returnByValue": True
                    }, session_id=session_id)

                    if result and "result" in result and "result" in result["result"]:
                        code = result["result"]["result"].get("value")
                        if code:
                            print(f"   ✓ 找到验证码: {code}")
                            return code

                    print(f"   ⏳ 暂未找到验证码，等待3秒后重试...")
                    human_delay(3.0)

                except Exception as e:
                    print(f"   ⚠️  检查出错: {e}")
                    human_delay(3.0)

            print(f"   ✗ 获取验证码超时（已尝试{max_retries}次）")
            return None

        except Exception as e:
            print(f"   ✗ 获取验证码出错: {e}")
            import traceback
            traceback.print_exc()
            return None

        finally:
            cdp.close()



