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
    无需额外安装，使用Python标准库

使用方法：
    1. 确保比特浏览器客户端正在运行
    2. 运行此脚本: python bitbrowser_create_window.py
    3. 脚本会自动创建、打开窗口，并显示WebSocket地址

作者: AI Assistant
版本: 1.0
"""

import json
from urllib.request import urlopen, Request
from urllib.error import URLError, HTTPError


# 比特浏览器本地API地址
BIT_BASE_URL = "http://127.0.0.1:54345"


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
    
    # 3. 显示WebSocket地址（可用于后续自动化操作）
    ws_url = result.get("ws")
    print(f"\n💡 提示: 你可以使用以下WebSocket地址进行自动化操作:")
    print(f"   {ws_url}")
    
    # 4. 等待用户操作（可选）
    input("\n按回车键关闭窗口...")
    
    # 5. 关闭窗口
    close_browser_window(browser_id)
    
    print("\n✨ 所有操作完成！")


if __name__ == "__main__":
    main()

