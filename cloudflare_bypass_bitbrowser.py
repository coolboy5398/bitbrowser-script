#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
比特浏览器 Cloudflare 验证框自动点击脚本
通过 CDP (Chrome DevTools Protocol) 自动点击 Cloudflare 验证框

依赖:
    pip install websocket-client psutil

使用方法:
    1. 先打开比特浏览器窗口
    2. 在浏览器中打开需要验证的页面（如 https://app.augmentcode.com/account/）
    3. 运行此脚本: python cloudflare_bypass_bitbrowser.py
    4. 脚本会自动查找验证框并点击

作者: AI Assistant
版本: 1.0
"""

import json
import time
import websocket
import sys
from urllib.request import urlopen, Request
from urllib.error import URLError, HTTPError


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


def find_bitbrowser_ws():
    """自动查找比特浏览器的 WebSocket 地址（使用比特浏览器 API）

    这个方法比扫描进程更快更准确，因为它直接调用比特浏览器的本地 API。
    """
    print("🔍 正在查找比特浏览器...")

    BIT_BASE_URL = "http://127.0.0.1:54345"

    try:
        # 1. 调用 /browser/ports API 获取所有已打开窗口的端口
        url = f"{BIT_BASE_URL}/browser/ports"
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

        # 2. 遍历所有端口，获取 WebSocket 地址
        for browser_id, port in ports_data.items():
            try:
                port_num = int(str(port).strip())
                ws_url = fetch_ws_via_port(port_num)
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


def fetch_ws_via_port(port: int, timeout: float = 3.0):
    """通过端口号获取 WebSocket 地址"""
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


def find_cloudflare_element(cdp: CDPClient, session_id: str):
    """查找 Cloudflare 验证框元素"""
    print("\n🔍 查找 Cloudflare 验证框...")
    
    # 1. 获取文档根节点
    result = cdp.send("DOM.getDocument", {"depth": -1}, session_id=session_id)
    if not result or "result" not in result:
        print("  ✗ 无法获取 DOM 文档")
        return None
    
    root_node_id = result["result"]["root"]["nodeId"]
    print(f"  ✓ 获取根节点: {root_node_id}")
    
    # 2. 查找验证框元素（支持多种选择器）
    selectors = [
        'div[id*="ulp-"]',           # Auth0 验证框
        'div[class*="ulp-"]',
        'div[id*="captcha"]',        # 通用验证码
        'div[class*="captcha"]',
        'iframe[src*="challenges.cloudflare.com"]',  # Cloudflare iframe
        'div[id*="cf-"]',            # Cloudflare 元素
        'div[class*="cf-"]',
    ]
    
    for selector in selectors:
        print(f"  🔍 尝试选择器: {selector}")
        result = cdp.send("DOM.querySelectorAll", {
            "nodeId": root_node_id,
            "selector": selector
        }, session_id=session_id)
        
        if result and "result" in result and result["result"].get("nodeIds"):
            node_ids = result["result"]["nodeIds"]
            print(f"    ✓ 找到 {len(node_ids)} 个元素")
            return node_ids[0]  # 返回第一个匹配的元素
    
    print("  ✗ 未找到验证框元素")
    return None


def get_element_box(cdp: CDPClient, node_id: int, session_id: str):
    """获取元素的位置和大小"""
    result = cdp.send("DOM.getBoxModel", {"nodeId": node_id}, session_id=session_id)
    if not result or "result" not in result:
        return None
    
    box_model = result["result"]["model"]
    # content 是一个包含 8 个数字的数组: [x1, y1, x2, y2, x3, y3, x4, y4]
    content = box_model["content"]
    x = (content[0] + content[4]) / 2
    y = (content[1] + content[5]) / 2
    width = content[4] - content[0]
    height = content[5] - content[1]
    
    return {"x": x, "y": y, "width": width, "height": height}


def click_element_cdp(cdp: CDPClient, x: float, y: float, session_id: str):
    """使用 CDP 发送鼠标点击事件"""
    print(f"\n🖱️  发送 CDP 鼠标点击事件...")
    print(f"  📍 坐标: ({x:.1f}, {y:.1f})")
    
    # 1. 鼠标移动到目标位置
    cdp.send("Input.dispatchMouseEvent", {
        "type": "mouseMoved",
        "x": x,
        "y": y
    }, session_id=session_id)
    
    # 2. 鼠标按下
    cdp.send("Input.dispatchMouseEvent", {
        "type": "mousePressed",
        "x": x,
        "y": y,
        "button": "left",
        "clickCount": 1
    }, session_id=session_id)
    
    # 3. 鼠标释放
    cdp.send("Input.dispatchMouseEvent", {
        "type": "mouseReleased",
        "x": x,
        "y": y,
        "button": "left",
        "clickCount": 1
    }, session_id=session_id)
    
    print(f"  ✓ CDP 点击完成")


def check_captcha_token(cdp: CDPClient, session_id: str):
    """检查验证是否完成（查找 token）"""
    # 查找包含 captcha token 的 input 元素
    result = cdp.send("DOM.getDocument", {"depth": -1}, session_id=session_id)
    if not result or "result" not in result:
        return None
    
    root_node_id = result["result"]["root"]["nodeId"]
    
    # 查找 name="captcha" 的 input
    result = cdp.send("DOM.querySelectorAll", {
        "nodeId": root_node_id,
        "selector": 'input[name="captcha"]'
    }, session_id=session_id)
    
    if not result or "result" not in result or not result["result"].get("nodeIds"):
        return None
    
    node_id = result["result"]["nodeIds"][0]
    
    # 获取 input 的值
    result = cdp.send("DOM.resolveNode", {"nodeId": node_id}, session_id=session_id)
    if not result or "result" not in result:
        return None
    
    object_id = result["result"]["object"]["objectId"]
    
    # 获取属性
    result = cdp.send("Runtime.callFunctionOn", {
        "objectId": object_id,
        "functionDeclaration": "function() { return this.value; }",
        "returnByValue": True
    }, session_id=session_id)
    
    if result and "result" in result and "result" in result["result"]:
        token = result["result"]["result"].get("value", "")
        if token:
            return token
    
    return None


def main(ws_url: str = None):
    """主函数

    Args:
        ws_url: 可选的 WebSocket 地址，如果不提供则自动查找
    """
    print("=" * 70)
    print("比特浏览器 Cloudflare 验证框自动点击脚本 v1.0")
    print("=" * 70)

    # 1. 查找比特浏览器
    print("\n步骤 1: 查找比特浏览器...")

    if not ws_url:
        ws_url = find_bitbrowser_ws()
    else:
        print(f"✓ 使用指定的 WebSocket 地址: {ws_url}")

    if not ws_url:
        print("\n❌ 失败: 未找到比特浏览器")
        print("\n请确保:")
        print("  1. 比特浏览器已打开")
        print("  2. 浏览器窗口已启动（不是只打开比特浏览器客户端）")
        print("\n或者手动指定 WebSocket 地址:")
        print("  main(ws_url='ws://127.0.0.1:PORT/devtools/browser/ID')")
        return
    
    # 2. 连接到浏览器
    print("\n步骤 2: 连接到浏览器...")
    cdp = CDPClient(ws_url)
    print("✓ 连接成功")
    
    try:
        # 3. 获取当前活动的 page
        print("\n步骤 3: 获取当前活动的 page...")
        result = cdp.send("Target.getTargets", {})
        if not result or "result" not in result:
            print("✗ 无法获取 targets")
            return
        
        targets = result["result"]["targetInfos"]
        page_target = None
        for target in targets:
            if target.get("type") == "page":
                page_target = target
                break
        
        if not page_target:
            print("✗ 未找到 page target")
            return
        
        target_id = page_target["targetId"]
        print(f"✓ 找到 page target: {target_id}")
        
        # 4. 附加到 target
        print("\n步骤 4: 附加到 target...")
        result = cdp.send("Target.attachToTarget", {
            "targetId": target_id,
            "flatten": True
        })
        
        if not result or "result" not in result:
            print("✗ 无法附加到 target")
            return
        
        session_id = result["result"]["sessionId"]
        print(f"✓ 附加成功")
        
        # 5. 启用 DOM 域
        print("\n步骤 5: 启用 DOM 域...")
        cdp.send("DOM.enable", {}, session_id=session_id)
        print("✓ DOM 域已启用")
        
        # 6. 查找验证框元素
        print("\n步骤 6: 查找验证框元素...")
        node_id = find_cloudflare_element(cdp, session_id)
        
        if not node_id:
            print("\n❌ 失败: 未找到验证框元素")
            print("\n可能的原因:")
            print("  1. 页面上没有 Cloudflare 验证框")
            print("  2. 验证框已经完成验证")
            print("  3. 验证框使用了不同的选择器")
            return
        
        print(f"✓ 找到验证框元素: NodeID={node_id}")
        
        # 7. 获取元素位置
        print("\n步骤 7: 获取元素位置...")
        box = get_element_box(cdp, node_id, session_id)
        
        if not box:
            print("✗ 无法获取元素位置")
            return
        
        print(f"✓ 元素位置: x={box['x']:.1f}, y={box['y']:.1f}, 大小={box['width']:.0f}x{box['height']:.0f}")
        
        # 8. 点击元素
        print("\n步骤 8: 点击验证框...")
        click_element_cdp(cdp, box['x'], box['y'], session_id)
        
        # 9. 等待验证完成
        print("\n步骤 9: 等待验证完成...")
        for i in range(10):
            time.sleep(1)
            token = check_captcha_token(cdp, session_id)
            if token:
                print(f"\n✅ 验证成功！")
                print(f"Token (前50字符): {token[:50]}...")
                print(f"Token 长度: {len(token)} 字符")
                break
            print(f"  ⏳ 等待中... ({i+1}/10)")
        else:
            print("\n⚠️  验证超时（10秒）")
            print("可能的原因:")
            print("  1. 验证需要更长时间")
            print("  2. 需要手动完成验证")
            print("  3. 页面结构与预期不同")
    
    finally:
        cdp.close()
        print("\n✓ 连接已关闭")


if __name__ == "__main__":
    main()

