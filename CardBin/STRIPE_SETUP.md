# 🔧 Stripe测试环境配置指南

## ❌ 当前问题

测试时遇到错误：
```
This integration surface is unsupported for publishable key tokenization
```

## ✅ 解决方法

### 方法1: 启用Raw Card Data API（推荐）

1. **登录Stripe Dashboard**
   - 访问：https://dashboard.stripe.com/settings/integration
   - 确保切换到**测试模式**（Test mode）

2. **启用权限**
   - 找到 "Raw card data APIs" 或 "Card tokenization"
   - 点击 "Enable" 或 "Request access"
   - 可能需要填写表单说明用途

3. **等待审核**
   - 测试环境通常立即生效
   - 生产环境可能需要审核

### 方法2: 使用Stripe CLI（开发测试）

如果只是本地测试，可以使用Stripe CLI：

```bash
# 安装Stripe CLI
# Windows: scoop install stripe
# Mac: brew install stripe/stripe-cli/stripe
# Linux: 下载二进制文件

# 登录
stripe login

# 创建测试Token
stripe tokens create --card-number=4242424242424242 --card-exp-month=12 --card-exp-year=2034 --card-cvc=123
```

### 方法3: 使用预定义测试Token（最简单）

不生成卡号，直接使用Stripe提供的测试Token：

```python
# 修改测试逻辑，使用预定义Token
test_tokens = {
    'visa': 'tok_visa',
    'mastercard': 'tok_mastercard',
    'amex': 'tok_amex'
}
```

## 📋 启用步骤详解

### 步骤1: 访问设置页面

```
https://dashboard.stripe.com/settings/integration
```

### 步骤2: 找到相关设置

查找以下任一选项：
- "Raw card data APIs"
- "Card tokenization"
- "Direct API integration"
- "PCI compliance settings"

### 步骤3: 启用并保存

- 点击 "Enable" 按钮
- 可能需要确认PCI合规性
- 保存设置

### 步骤4: 验证

重新运行测试：
```bash
python auto_test_cards.py --config
```

## 🔍 常见问题

### Q1: 找不到"Raw card data APIs"选项？

**A:** 可能在不同位置：
- Settings → Integration
- Settings → API
- Settings → Security
- Settings → Compliance

### Q2: 提示需要PCI认证？

**A:** 测试环境不需要，选择：
- "I'm only testing"
- "Development purposes only"

### Q3: 还是不行？

**A:** 尝试方法3，使用预定义Token：

修改 `stripe_payment_tester.py`：
```python
# 不生成卡号，直接使用Token
python stripe_payment_tester.py --config
```

## 🎯 推荐方案

### 方案A: 完整测试（需要启用权限）
```
生成卡号 → 创建Token → 测试支付
```
**优点：** 测试真实生成的卡号
**缺点：** 需要Stripe权限

### 方案B: 简化测试（无需权限）
```
BIN → 映射到预定义Token → 测试支付
```
**优点：** 无需额外权限
**缺点：** 不测试具体卡号

### 方案C: 本地验证（无需Stripe）
```
生成卡号 → Luhn校验 → BIN验证
```
**优点：** 完全本地，无需API
**缺点：** 不测试实际支付

## 💡 建议

1. **开发阶段：** 使用方案C（本地验证）
2. **集成测试：** 使用方案B（预定义Token）
3. **完整测试：** 使用方案A（需要权限）

## 📞 获取帮助

如果仍有问题：
1. 查看Stripe文档：https://stripe.com/docs/testing
2. 联系Stripe支持：https://support.stripe.com
3. 查看错误链接：https://support.stripe.com/questions/card-tokenization-restrictions-using-publishable-keys

---

**喵~ 希望这能帮到你！** 🎨✨
