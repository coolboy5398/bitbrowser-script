#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Chrome浏览器工具类
提供Chrome浏览器的启动、控制和扩展操作功能

功能：
    - 启动Chrome浏览器并启用远程调试
    - 获取Chrome的WebSocket调试地址
    - 通过CDP控制Chrome浏览器
    - 操作Chrome扩展插件

依赖：
    pip install websocket-client

作者: AI Assistant
版本: 1.0
"""

import os
import json
import time
import subprocess
from urllib.request import urlopen
from urllib.error import URLError, HTTPError
from bitbrowser_api import CDPClient


def find_chrome_path():
    """查找Chrome浏览器的安装路径
    
    Returns:
        str: Chrome可执行文件的完整路径，未找到返回None
    """
    print("🔍 正在查找Chrome浏览器...")
    
    # Windows系统的常见Chrome安装路径
    chrome_paths = [
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
        os.path.expanduser(r"~\AppData\Local\Google\Chrome\Application\chrome.exe"),
    ]
    
    # 查找Chrome路径
    for path in chrome_paths:
        if os.path.exists(path):
            print(f"   ✓ 找到Chrome: {path}")
            return path
    
    print("   ✗ 未找到Chrome浏览器")
    print("   💡 提示: 请确保已安装Chrome浏览器")
    return None


def get_chrome_ws_url(port, max_retries=15, retry_delay=0.5):
    """从Chrome调试端口获取WebSocket地址
    
    Args:
        port (int): Chrome远程调试端口
        max_retries (int): 最大重试次数
        retry_delay (float): 重试间隔（秒）
    
    Returns:
        str: WebSocket调试地址，失败返回None
    """
    print(f"🔗 正在获取WebSocket地址（端口: {port}）...")
    
    for i in range(max_retries):
        try:
            # 访问Chrome调试端口获取targets信息
            response = urlopen(f"http://127.0.0.1:{port}/json", timeout=2)
            targets = json.loads(response.read().decode('utf-8'))
            
            # 查找第一个page类型的target
            for target in targets:
                if target.get('type') == 'page':
                    ws_url = target.get('webSocketDebuggerUrl')
                    if ws_url:
                        print(f"   ✓ 获取成功: {ws_url}")
                        return ws_url

            # 未找到page，等待后重试
            if i < max_retries - 1:
                print(f"   ⚠️  未找到page类型的target，等待后重试... ({i+1}/{max_retries})")
                time.sleep(retry_delay)
            else:
                print(f"   ✗ 未找到page类型的target（已重试{max_retries}次）")
            
        except (URLError, HTTPError) as e:
            if i < max_retries - 1:
                print(f"   ⏳ 等待Chrome启动... ({i+1}/{max_retries})")
                time.sleep(retry_delay)
            else:
                print(f"   ✗ 连接失败: {e}")
                return None
        except Exception as e:
            print(f"   ✗ 获取失败: {e}")
            return None
    
    print("   ✗ 超过最大重试次数")
    return None


def open_url_in_chrome(url, incognito=True):
    """使用Chrome浏览器打开URL（简单模式，不启用远程调试）

    这是一个简单的工具函数，用于快速打开Chrome浏览器。
    如果需要控制浏览器或操作扩展，请使用 open_chrome_with_extension 函数。

    Args:
        url (str): 要打开的URL
        incognito (bool): 是否使用无痕模式，默认为True

    Returns:
        bool: 成功返回True，失败返回False

    Example:
        >>> success = open_url_in_chrome("https://www.google.com")
        >>> if success:
        ...     print("浏览器已打开")
    """
    print(f"\n🌐 正在使用Chrome浏览器打开链接...")
    print(f"   🔗 链接: {url}")
    print(f"   🕵️  无痕模式: {'是' if incognito else '否'}")

    # 查找Chrome路径
    chrome_path = find_chrome_path()
    if not chrome_path:
        return False

    try:
        # 构建命令
        cmd = [chrome_path]
        if incognito:
            cmd.append("--incognito")
        cmd.append(url)

        # 启动Chrome
        subprocess.Popen(cmd)
        print("   ✓ Chrome浏览器已启动")
        return True

    except Exception as e:
        print(f"   ✗ 启动Chrome失败: {e}")
        return False


def open_chrome_with_extension(url, extension_id, incognito=True, remote_debugging_port=9222):
    """启动Chrome浏览器并操作扩展插件
    
    此函数会：
    1. 启动Chrome浏览器并启用远程调试
    2. 打开指定的URL
    3. 尝试打开指定的扩展popup页面
    4. 返回CDP连接供后续操作
    
    Args:
        url (str): 要打开的URL
        extension_id (str): Chrome扩展的ID
        incognito (bool): 是否使用无痕模式，默认为True
        remote_debugging_port (int): 远程调试端口，默认为9222
    
    Returns:
        dict: 包含以下键的字典
            - success (bool): 操作是否成功
            - ws_url (str): WebSocket调试地址（成功时）
            - cdp (CDPClient): CDP客户端实例（成功时）
            - error (str): 错误信息（失败时）
    
    Example:
        >>> result = open_chrome_with_extension(
        ...     url="https://www.google.com",
        ...     extension_id="pkpkidlacejcllendmjnfcjdohkjpnae"
        ... )
        >>> if result['success']:
        ...     cdp = result['cdp']
        ...     ws_url = result['ws_url']
        ...     # 使用CDP进行后续操作
        ... else:
        ...     print(f"失败: {result['error']}")
    """
    print("\n" + "=" * 70)
    print("🚀 启动Chrome浏览器并操作扩展")
    print("=" * 70)
    print(f"   🔗 URL: {url}")
    print(f"   🧩 扩展ID: {extension_id}")
    print(f"   🕵️  无痕模式: {'是' if incognito else '否'}")
    print(f"   🔌 调试端口: {remote_debugging_port}")
    
    # 步骤1: 查找Chrome路径
    print("\n📍 步骤1: 查找Chrome浏览器...")
    chrome_path = find_chrome_path()
    if not chrome_path:
        return {
            'success': False,
            'error': '未找到Chrome浏览器'
        }
    
    # 步骤2: 构建启动命令
    print("\n🔧 步骤2: 构建启动命令...")
    cmd = [chrome_path]
    
    # 添加远程调试端口
    cmd.append(f"--remote-debugging-port={remote_debugging_port}")
    
    # 添加无痕模式
    if incognito:
        cmd.append("--incognito")
    
    # 添加URL
    cmd.append(url)
    
    print(f"   ✓ 命令: {' '.join(cmd)}")
    
    # 步骤3: 启动Chrome
    print("\n🚀 步骤3: 启动Chrome浏览器...")
    try:
        subprocess.Popen(cmd)
        print("   ✓ Chrome进程已启动")
    except Exception as e:
        return {
            'success': False,
            'error': f'启动Chrome失败: {e}'
        }
    
    # 步骤4: 等待Chrome启动并获取WebSocket地址
    print("\n⏳ 步骤4: 等待Chrome启动...")
    time.sleep(2)  # 给Chrome一些启动时间
    
    ws_url = get_chrome_ws_url(remote_debugging_port)
    if not ws_url:
        return {
            'success': False,
            'error': '无法获取WebSocket调试地址，Chrome可能未正确启动'
        }
    
    # 步骤5: 连接CDP
    print("\n🔗 步骤5: 连接CDP...")
    try:
        cdp = CDPClient(ws_url)
        print("   ✓ CDP连接成功")
    except Exception as e:
        return {
            'success': False,
            'error': f'CDP连接失败: {e}'
        }
    
    # 步骤6: 尝试打开扩展popup页面
    print("\n🧩 步骤6: 尝试打开扩展...")
    extension_url = f"chrome-extension://{extension_id}/popup.html"
    print(f"   📄 扩展URL: {extension_url}")
    
    try:
        # 尝试创建新的target打开扩展页面
        result = cdp.send("Target.createTarget", {
            "url": extension_url
        })
        
        if result and "result" in result:
            print("   ✓ 扩展页面已打开")
            print("   ⚠️  注意: 这不是真正的'点击图标'，而是直接打开扩展页面")
            print("   💡 如果扩展功能不正常，可能需要手动点击扩展图标")
        else:
            print("   ⚠️  打开扩展页面失败，可能被Chrome阻止")
            print("   💡 建议: 使用返回的CDP连接手动操作")
    except Exception as e:
        print(f"   ⚠️  打开扩展时出错: {e}")
        print("   💡 建议: 使用返回的CDP连接手动操作")
    
    # 返回成功结果
    print("\n✅ 操作完成！")
    print(f"   📡 WebSocket地址: {ws_url}")
    print("   💡 提示: 可以使用返回的CDP客户端进行后续操作")
    
    return {
        'success': True,
        'ws_url': ws_url,
        'cdp': cdp
    }


if __name__ == "__main__":
    # 示例用法
    print("Chrome工具类 - 示例用法")
    print("=" * 70)
    print("\n示例代码:")
    print("""
    from chrome_utils import open_chrome_with_extension
    
    result = open_chrome_with_extension(
        url="https://www.google.com",
        extension_id="pkpkidlacejcllendmjnfcjdohkjpnae",
        incognito=True
    )
    
    if result['success']:
        cdp = result['cdp']
        ws_url = result['ws_url']
        
        # 使用CDP进行后续操作
        # ...
        
        # 完成后关闭连接
        cdp.close()
    else:
        print(f"失败: {result['error']}")
    """)

