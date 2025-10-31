#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
比特浏览器API公共类
提供统一的比特浏览器API调用接口

功能：
    - 创建浏览器窗口
    - 打开浏览器窗口
    - 关闭浏览器窗口
    - 查找WebSocket地址
    - CDP客户端封装

依赖：
    pip install websocket-client

作者: AI Assistant
版本: 1.0
"""

import json
import time
import random
import websocket
from urllib.request import urlopen, Request
from urllib.error import URLError, HTTPError


class CDPClient:
    """Chrome DevTools Protocol 客户端
    
    用于通过WebSocket与浏览器进行CDP通信
    """
    
    def __init__(self, ws_url: str, timeout: float = 10.0):
        """初始化CDP客户端
        
        Args:
            ws_url: WebSocket调试地址
            timeout: 超时时间（秒）
        """
        self.ws = websocket.create_connection(ws_url, timeout=timeout, suppress_origin=True)
        self.ws.settimeout(timeout)
        self._id = 0

    def send(self, method: str, params: dict = None, session_id: str = None):
        """发送CDP命令
        
        Args:
            method: CDP方法名，如 "Page.navigate"
            params: 方法参数字典
            session_id: 会话ID（可选）
            
        Returns:
            dict: CDP响应结果，失败返回None
        """
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
        """关闭WebSocket连接"""
        try:
            self.ws.close()
        except Exception:
            pass


class BitBrowserAPI:
    """比特浏览器API封装类
    
    提供统一的比特浏览器本地API调用接口
    """
    
    BASE_URL = "http://127.0.0.1:54345"
    
    @staticmethod
    def create_window(name, platform=None, **kwargs):
        """创建比特浏览器窗口

        Args:
            name (str): 窗口名称
            platform (str, optional): 平台URL，默认不设置
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
            >>> # 不使用代理，不设置platform
            >>> browser_id = BitBrowserAPI.create_window("测试窗口")
            >>>
            >>> # 使用SOCKS5代理
            >>> browser_id = BitBrowserAPI.create_window(
            >>>     name="测试窗口",
            >>>     proxyType="socks5",
            >>>     host="127.0.0.1",
            >>>     port=7890
            >>> )
        """
        print(f"🔨 正在创建窗口: {name}")

        # 构建请求数据
        data = {
            "name": name,
            "browserFingerPrint": {},  # 空对象表示使用随机指纹
            "proxyMethod": 2,  # 2表示自定义代理
            "proxyType": kwargs.get("proxyType", "noproxy"),
        }

        # 只在platform有值时才添加
        if platform:
            data["platform"] = platform

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
            url = f"{BitBrowserAPI.BASE_URL}/browser/update"
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

    @staticmethod
    def open_window(browser_id):
        """打开比特浏览器窗口
        
        Args:
            browser_id (str): 浏览器窗口ID
        
        Returns:
            dict: 成功返回包含ws、http、driver等信息的字典，失败返回None
            
        Example:
            >>> result = BitBrowserAPI.open_window(browser_id)
            >>> if result:
            >>>     print(f"WebSocket: {result['ws']}")
            >>>     print(f"HTTP: {result['http']}")
        """
        print(f"\n🚀 正在打开窗口: {browser_id}")
        
        try:
            # 发送打开请求
            url = f"{BitBrowserAPI.BASE_URL}/browser/open"
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

    @staticmethod
    def close_window(browser_id):
        """关闭比特浏览器窗口
        
        Args:
            browser_id (str): 浏览器窗口ID
        
        Returns:
            bool: 成功返回True，失败返回False
            
        Example:
            >>> success = BitBrowserAPI.close_window(browser_id)
            >>> if success:
            >>>     print("窗口已关闭")
        """
        print(f"\n🔒 正在关闭窗口: {browser_id}")
        
        try:
            # 发送关闭请求
            url = f"{BitBrowserAPI.BASE_URL}/browser/close"
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

    @staticmethod
    def find_websocket():
        """自动查找比特浏览器的WebSocket地址
        
        通过调用比特浏览器本地API获取已打开窗口的WebSocket地址
        
        Returns:
            str: WebSocket地址，失败返回None
            
        Example:
            >>> ws_url = BitBrowserAPI.find_websocket()
            >>> if ws_url:
            >>>     print(f"WebSocket: {ws_url}")
        """
        print("🔍 正在查找比特浏览器...")

        try:
            # 调用 /browser/ports API 获取所有已打开窗口的端口
            url = f"{BitBrowserAPI.BASE_URL}/browser/ports"
            data = json.dumps({}).encode("utf-8")
            headers = {"Content-Type": "application/json"}

            req = Request(url, data=data, headers=headers, method="POST")
            response = urlopen(req, timeout=5)
            result = json.loads(response.read().decode("utf-8"))

            if result.get("success") != True:
                print("✗ 比特浏览器 API 调用失败")
                return None

            ports_data = result.get("data") or {}
            if not isinstance(ports_data, dict) or not ports_data:
                print("✗ 未找到已打开的比特浏览器窗口")
                print("提示: 请先在比特浏览器中打开一个窗口")
                return None

            # 遍历所有端口，获取 WebSocket 地址
            for browser_id, port in ports_data.items():
                try:
                    port_num = int(str(port).strip())
                    ws_url = BitBrowserAPI.get_websocket_by_port(port_num)
                    if ws_url:
                        print(f"✓ 找到比特浏览器窗口: {browser_id}")
                        print(f"  WebSocket: {ws_url}")
                        return ws_url
                except Exception:
                    continue

            print("✗ 未能获取 WebSocket 地址")
            return None

        except URLError as e:
            print("✗ 无法连接到比特浏览器本地服务")
            print(f"  错误: {e}")
            print("提示: 请确保比特浏览器客户端正在运行")
            return None
        except Exception as e:
            print(f"✗ 查找失败: {e}")
            return None

    @staticmethod
    def get_websocket_by_port(port: int, timeout: float = 3.0):
        """通过端口号获取WebSocket地址
        
        Args:
            port: 浏览器调试端口号
            timeout: 超时时间（秒）
            
        Returns:
            str: WebSocket地址，失败返回None
        """
        url = f"http://127.0.0.1:{port}/json/version"
        try:
            response = urlopen(url, timeout=timeout)
            data = json.loads(response.read().decode("utf-8"))
            ws = data.get("webSocketDebuggerUrl")
            if isinstance(ws, str) and ws.startswith("ws://"):
                return ws
        except Exception:
            pass
        return None


def human_delay(base_seconds, jitter_percent=0.3):
    """模拟人类操作的延迟，添加随机抖动
    
    Args:
        base_seconds: 基础延迟时间（秒）
        jitter_percent: 抖动百分比，默认30%
    
    Returns:
        float: 实际延迟时间
        
    Example:
        >>> # 延迟2秒，±30%抖动
        >>> actual_delay = human_delay(2.0)
        >>> # 延迟1秒，±50%抖动
        >>> actual_delay = human_delay(1.0, jitter_percent=0.5)
    """
    jitter = base_seconds * jitter_percent
    delay = base_seconds + random.uniform(-jitter, jitter)
    # 确保延迟不小于0.1秒
    delay = max(0.1, delay)
    time.sleep(delay)
    return delay

