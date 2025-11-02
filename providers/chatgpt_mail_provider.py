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
        self.domain_patterns = ["mail.chatgpt.org.uk", "chatgptuk.pp.ua", "chatgpt.org.uk"]
    
    def get_page_url(self) -> str:
        """获取邮箱页面URL"""
        return f"{self.base_url}/"
    
    def get_domain_patterns(self) -> list:
        """获取域名匹配模式"""
        return self.domain_patterns
    
    def get_email_from_page(self, cdp, session_id) -> str:
        """从页面获取邮箱地址
        
        使用JavaScript在页面中查找邮箱地址
        """
        print("   🔍 步骤5: 查找邮箱地址...")
        
        # 构建域名匹配条件
        domain_checks = " || ".join([f"text.includes('{domain}')" for domain in self.domain_patterns])
        
        max_retries = 3
        for attempt in range(max_retries):
            if attempt > 0:
                print(f"   🔄 第 {attempt + 1} 次尝试...")
                from bitbrowser_api import human_delay
                human_delay(2.0)
            
            # 使用JavaScript查找邮箱
            result = cdp.send("Runtime.evaluate", {
                "expression": f"""
                    (() => {{
                        // 方法1: 查找所有包含@的文本节点
                        const walker = document.createTreeWalker(
                            document.body,
                            NodeFilter.SHOW_TEXT,
                            null,
                            false
                        );

                        let node;
                        while(node = walker.nextNode()) {{
                            const text = node.textContent.trim();
                            if (text.includes('@') && ({domain_checks})) {{
                                // 使用正则提取邮箱
                                const match = text.match(/[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\\.[a-zA-Z]{{2,}}/);
                                if (match) {{
                                    return match[0];
                                }}
                            }}
                        }}

                        // 方法2: 查找特定的元素
                        const selectors = [
                            'input[type="text"]',
                            'input[readonly]',
                            'div[class*="email"]',
                            'span[class*="email"]',
                            'p',
                            'div'
                        ];

                        for (const selector of selectors) {{
                            const elements = document.querySelectorAll(selector);
                            for (const el of elements) {{
                                const text = el.textContent || el.value || '';
                                if (text.includes('@') && ({domain_checks})) {{
                                    const match = text.match(/[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\\.[a-zA-Z]{{2,}}/);
                                    if (match) {{
                                        return match[0];
                                    }}
                                }}
                            }}
                        }}

                        return null;
                    }})()
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

