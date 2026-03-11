// ==UserScript==
// @name         ChatGPT Team 绑卡页面生成器
// @namespace    https://chatgpt.com/
// @version      1.0.0
// @description  在 ChatGPT 页面生成 Team 套餐绑卡页面 (Custom Checkout)
// @author       Your Name
// @match        https://chatgpt.com/*
// @match        https://chat.openai.com/*
// @icon         https://chat.openai.com/favicon.ico
// @grant        GM_registerMenuCommand
// @grant        GM_notification
// @grant        GM_setClipboard
// @run-at       document-idle
// ==/UserScript==

(function() {
    'use strict';

    // ============ 配置参数 (可自定义修改) ============
    const CONFIG = {
        // 工作区名称
        workspace_name: "zhizhishu",
        // 计费周期: "month" 或 "year"
        price_interval: "month",
        // 座位数量
        seat_quantity: 5,
        // 国家代码
        country: "US",
        // 货币
        currency: "USD",
        // 优惠活动 ID
        promo_campaign_id: "team-1-month-free",
        // 页面模式: "new" = 新页面(嵌入式), "old" = 老页面(跳转链接)
        page_mode: "new"
    };

    // API 端点
    const API = {
        checkout: "https://chatgpt.com/backend-api/payments/checkout",
        promo_check: "https://chatgpt.com/backend-api/promo_campaign/check_coupon"
    };

    // ============ 工具函数 ============

    // 获取 Access Token
    async function getAccessToken() {
        try {
            const response = await fetch("https://chatgpt.com/api/auth/session");
            const data = await response.json();
            if (data.accessToken) {
                console.log("[TeamPay] ✅ Token 获取成功");
                return data.accessToken;
            }
            throw new Error("未找到 accessToken");
        } catch (error) {
            console.error("[TeamPay] ❌ Token 获取失败:", error);
            showNotification("错误", "获取 Token 失败，请确保已登录");
            return null;
        }
    }

    // 显示通知
    function showNotification(title, text) {
        if (typeof GM_notification !== 'undefined') {
            GM_notification({
                title: title,
                text: text,
                timeout: 3000
            });
        } else {
            alert(`${title}: ${text}`);
        }
    }

    // 复制到剪贴板
    function copyToClipboard(text) {
        if (typeof GM_setClipboard !== 'undefined') {
            GM_setClipboard(text);
        } else {
            navigator.clipboard.writeText(text);
        }
    }

    // 从 Token 提取邮箱前缀作为工作区名称
    function extractEmailPrefix(token) {
        try {
            const parts = token.split('.');
            if (parts.length >= 2) {
                let payload = parts[1];
                // Base64 URL 解码
                payload = payload.replace(/-/g, '+').replace(/_/g, '/');
                while (payload.length % 4) payload += '=';
                const decoded = JSON.parse(atob(payload));

                // 尝试多种邮箱字段
                let email = decoded.email ||
                    decoded['https://api.openai.com/profile']?.email ||
                    decoded['https://api.openai.com/auth']?.email;

                if (email && email.includes('@')) {
                    return email.split('@')[0];
                }
            }
        } catch (e) {
            console.error("[TeamPay] 解析 Token 失败:", e);
        }
        return "MyTeam";
    }

    // ============ API 调用 ============

    // 生成 Checkout (支持新/老两种模式)
    async function generateCheckout(token, mode) {
        const isNewMode = mode === "new";

        const payload = {
            plan_name: "chatgptteamplan",
            team_plan_data: {
                workspace_name: CONFIG.workspace_name,
                price_interval: CONFIG.price_interval,
                seat_quantity: CONFIG.seat_quantity
            },
            billing_details: {
                country: CONFIG.country,
                currency: CONFIG.currency.toUpperCase()
            },
            cancel_url: "https://chatgpt.com/#pricing",
            promo_campaign: {
                promo_campaign_id: CONFIG.promo_campaign_id,
                is_coupon_from_query_param: false
            },
            checkout_ui_mode: isNewMode ? "custom" : "redirect"
        };

        try {
            const response = await fetch(API.checkout, {
                method: "POST",
                headers: {
                    "Authorization": `Bearer ${token}`,
                    "Content-Type": "application/json",
                    "Accept": "application/json"
                },
                body: JSON.stringify(payload)
            });

            const data = await response.json();

            if (response.ok) {
                if (isNewMode && data.checkout_session_id) {
                    // 新页面：拼接 ChatGPT checkout URL
                    const processor = data.processor_entity || "openai_llc";
                    const newUrl = `https://chatgpt.com/checkout/${processor}/${data.checkout_session_id}`;
                    return {
                        success: true,
                        mode: "new",
                        url: newUrl,
                        checkout_session_id: data.checkout_session_id
                    };
                } else if (!isNewMode && data.url) {
                    return { success: true, mode: "old", url: data.url };
                }
            }

            console.error("[TeamPay] API 错误:", data);
            return { success: false, error: data.detail || "API 请求失败" };
        } catch (error) {
            console.error("[TeamPay] 请求异常:", error);
            return { success: false, error: error.message };
        }
    }

    // ============ UI 创建 ============

    // 创建悬浮按钮
    function createFloatingButton() {
        // 检查是否已存在
        if (document.getElementById('team-pay-btn')) return;

        const btn = document.createElement('div');
        btn.id = 'team-pay-btn';
        btn.innerHTML = '💳';
        btn.title = '生成 Team 绑卡页面';
        btn.style.cssText = `            position: fixed;             bottom: 100px;             right: 20px;             width: 50px;             height: 50px;             background: linear-gradient(135deg, #10a37f 0%, #1a7f5a 100%);             border-radius: 50%;             display: flex;             align-items: center;             justify-content: center;             font-size: 24px;             cursor: pointer;             box-shadow: 0 4px 15px rgba(16, 163, 127, 0.4);             z-index: 99999;             transition: all 0.3s ease;             user-select: none;        `;

        btn.onmouseover = () => {
            btn.style.transform = 'scale(1.1)';
            btn.style.boxShadow = '0 6px 20px rgba(16, 163, 127, 0.6)';
        };
        btn.onmouseout = () => {
            btn.style.transform = 'scale(1)';
            btn.style.boxShadow = '0 4px 15px rgba(16, 163, 127, 0.4)';
        };

        btn.onclick = showConfigPanel;

        document.body.appendChild(btn);
    }

    // 创建配置面板
    function showConfigPanel() {
        // 移除已存在的面板
        const existing = document.getElementById('team-pay-panel');
        if (existing) {
            existing.remove();
            return;
        }

        const panel = document.createElement('div');
        panel.id = 'team-pay-panel';
        panel.innerHTML = `            <div id="tp-overlay" style="                 position: fixed;                 top: 0;                 left: 0;                 right: 0;                 bottom: 0;                 background: rgba(0,0,0,0.5);                 z-index: 100000;                 display: flex;                 align-items: center;                 justify-content: center;             ">                 <div style="                     background: white;                     border-radius: 16px;                     width: 400px;                     max-width: 90vw;                     box-shadow: 0 25px 50px -12px rgba(0, 0, 0, 0.25);                     overflow: hidden;                 " onclick="event.stopPropagation()">                     <div style="                         background: linear-gradient(135deg, #10a37f 0%, #1a7f5a 100%);                         color: white;                         padding: 20px;                         text-align: center;                     ">                         <h2 style="margin: 0; font-size: 20px;">ChatGPT Team 绑卡</h2>                         <p style="margin: 8px 0 0; opacity: 0.9; font-size: 14px;">1个月免费试用</p>                     </div>                     <div style="padding: 24px;">                         <div style="margin-bottom: 16px;">                             <label style="display: block; margin-bottom: 6px; font-weight: 500; color: #333;">页面样式</label>                             <select id="tp-mode" style="                                 width: 100%;                                 padding: 10px 12px;                                 border: 1px solid #ddd;                                 border-radius: 8px;                                 font-size: 14px;                                 box-sizing: border-box;                             ">                                 <option value="new" ${CONFIG.page_mode === 'new' ? 'selected' : ''}>🆕 新页面</option>                                 <option value="old" ${CONFIG.page_mode === 'old' ? 'selected' : ''}>📎 老页面</option>                             </select>                         </div>                         <div style="                             background: #f0fdf4;                             border-radius: 8px;                             padding: 12px;                             margin-bottom: 20px;                             font-size: 13px;                             color: #166534;                         ">                             ✨ <strong>优惠:</strong> team-1-month-free (1个月免费)<br>                             💰 <strong>今日应付:</strong> $0.00                         </div>                         <button id="tp-generate" style="                             width: 100%;                             padding: 14px;                             background: linear-gradient(135deg, #10a37f 0%, #1a7f5a 100%);                             color: white;                             border: none;                             border-radius: 8px;                             font-size: 16px;                             font-weight: 500;                             cursor: pointer;                             transition: all 0.3s;                         ">                             🚀 生成                         </button>                         <div id="tp-status" style="                             margin-top: 16px;                             padding: 12px;                             border-radius: 8px;                             font-size: 13px;                             display: none;                         "></div>                     </div>                 </div>             </div>        `;

        document.body.appendChild(panel);

        // 绑定生成按钮事件
        document.getElementById('tp-generate').onclick = async function() {
            const btn = this;
            const statusEl = document.getElementById('tp-status');

            // 更新配置
            CONFIG.page_mode = document.getElementById('tp-mode').value;

            // 显示加载状态
            btn.disabled = true;
            btn.innerHTML = '⏳ 生成中...';
            statusEl.style.display = 'block';
            statusEl.style.background = '#f3f4f6';
            statusEl.style.color = '#666';
            statusEl.innerHTML = '正在获取 Token...';

            try {
                // 获取 Token
                const token = await getAccessToken();
                if (!token) {
                    throw new Error("获取 Token 失败，请确保已登录");
                }

                // 自动提取邮箱前缀作为工作区名称
                CONFIG.workspace_name = extractEmailPrefix(token);
                statusEl.innerHTML = `正在生成... (${CONFIG.workspace_name})`;

                // 生成 Checkout
                const result = await generateCheckout(token, CONFIG.page_mode);

                if (result.success) {
                    // 两种模式都有 URL 了，统一处理
                    statusEl.style.background = '#f0fdf4';
                    statusEl.style.color = '#166534';
                    statusEl.innerHTML = `                        ✅ <strong>生成成功!</strong> (${result.mode === 'new' ? '新页面' : '老页面'})<br><br>                         <strong>绑卡链接:</strong><br>                         <input type="text" id="tp-url" value="${result.url}" readonly style="                             width: 100%;                             padding: 8px;                             border: 1px solid #10a37f;                             border-radius: 6px;                             font-size: 11px;                             margin: 8px 0;                             background: #fff;                         " onclick="this.select()">                         <div style="display: flex; gap: 8px; margin-top: 8px;">                             <button id="tp-copy" style="                                 flex: 1;                                 padding: 8px;                                 background: #10a37f;                                 color: white;                                 border: none;                                 border-radius: 6px;                                 cursor: pointer;                                 font-size: 13px;                             ">📋 复制链接</button>                             <button id="tp-open" style="                                 flex: 1;                                 padding: 8px;                                 background: #667eea;                                 color: white;                                 border: none;                                 border-radius: 6px;                                 cursor: pointer;                                 font-size: 13px;                             ">🔗 打开链接</button>                         </div>                    `;

                    document.getElementById('tp-copy').onclick = () => {
                        copyToClipboard(result.url);
                        showNotification("成功", "链接已复制到剪贴板!");
                        document.getElementById('tp-copy').innerHTML = '✅ 已复制';
                    };
                    document.getElementById('tp-open').onclick = () => {
                        window.open(result.url, '_blank');
                    };

                    showNotification("成功", "绑卡链接已生成!");
                } else {
                    throw new Error(result.error);
                }
            } catch (error) {
                statusEl.style.background = '#fef2f2';
                statusEl.style.color = '#dc2626';
                statusEl.innerHTML = `❌ <strong>失败:</strong> ${error.message}`;
            } finally {
                btn.disabled = false;
                btn.innerHTML = '🚀 生成';
            }
        };

        // 点击空白处关闭弹窗
        document.getElementById('tp-overlay').onclick = function(e) {
            if (e.target === this) {
                panel.remove();
            }
        };
    }

    // ============ 初始化 ============

    // 注册油猴菜单命令
    if (typeof GM_registerMenuCommand !== 'undefined') {
        GM_registerMenuCommand('🚀 生成 Team 绑卡页面', showConfigPanel);
        GM_registerMenuCommand('⚙️ 显示/隐藏悬浮按钮', () => {
            const btn = document.getElementById('team-pay-btn');
            if (btn) {
                btn.style.display = btn.style.display === 'none' ? 'flex' : 'none';
            }
        });
    }

    // 页面加载完成后创建悬浮按钮
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', createFloatingButton);
    } else {
        createFloatingButton();
    }

    console.log('[TeamPay] 💳 ChatGPT Team 绑卡脚本已加载');
    console.log('[TeamPay] 点击右下角悬浮按钮或油猴菜单使用');

})();