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
import websocket
from datetime import datetime
from urllib.request import urlopen, Request
from urllib.error import URLError, HTTPError


# 比特浏览器本地API地址
BIT_BASE_URL = "http://127.0.0.1:54345"


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
        # 等待页面加载
        print("   ⏳ 等待页面加载...")
        time.sleep(3)

        # 获取当前活动的 page
        result = cdp.send("Target.getTargets", {})
        if not result or "result" not in result:
            print("   ✗ 无法获取 targets")
            return None

        targets = result["result"]["targetInfos"]
        page_target = None
        for target in targets:
            if target.get("type") == "page":
                page_target = target
                break

        if not page_target:
            print("   ✗ 未找到 page target")
            return None

        target_id = page_target["targetId"]

        # 附加到 target
        result = cdp.send("Target.attachToTarget", {
            "targetId": target_id,
            "flatten": True
        })

        if not result or "result" not in result:
            print("   ✗ 无法附加到 target")
            return None

        session_id = result["result"]["sessionId"]

        # 启用必要的域
        cdp.send("DOM.enable", {}, session_id=session_id)
        cdp.send("Runtime.enable", {}, session_id=session_id)

        # 使用JavaScript获取邮箱地址
        result = cdp.send("Runtime.evaluate", {
            "expression": """
                (() => {
                    // 查找所有包含@的文本节点
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


def main():
    """主函数 - 演示如何使用脚本"""
    print("=" * 70)
    print("比特浏览器窗口创建脚本 v1.0")
    print("=" * 70)
    
    # 1. 创建窗口（使用SOCKS5代理）
    browser_id = create_browser_window(
        name="Augment注册",
        platform="https://mail.chatgpt.org.uk/",
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
            print(f"\n✅ 成功！")
            print(f"   邮箱地址: {email}")
            print(f"   访问链接: https://mail.chatgpt.org.uk/{email}")
            print(f"   保存文件: {filename}")
    else:
        print("\n⚠️  未能自动获取邮箱地址")
        print("   提示: 请手动从浏览器窗口中复制邮箱地址")

    # 5. 等待用户操作（可选）
    input("\n按回车键关闭窗口...")

    # 6. 关闭窗口
    close_browser_window(browser_id)

    print("\n✨ 所有操作完成！")


if __name__ == "__main__":
    main()

