# 🧪 Stripe卡号测试工具套件

完整的银行卡号生成和测试工具集

## 📦 文件说明

### 核心文件

1. **card_generator.py** - 卡号生成器
   - 生成符合Luhn算法的银行卡号
   - BIN验证
   - 支持多种卡品牌

2. **auto_test_cards.py** - 自动化批量测试工具 ⭐推荐
   - 自动生成卡号
   - 使用Selenium自动化浏览器测试
   - 批量测试多个BIN
   - 生成测试报告

3. **test_card.html** - 手动测试页面
   - 在浏览器中手动测试单张卡号
   - 美观的用户界面
   - 实时反馈

4. **stripe_payment_tester.py** - 命令行测试工具
   - 使用Stripe预定义Token测试
   - 测试BIN对应的品牌

5. **config.json** - 配置文件
   - Stripe API密钥
   - 测试BIN列表
   - 测试参数

## 🚀 快速开始

### 1. 安装依赖

```bash
pip install selenium aiohttp
```

### 2. 配置Stripe密钥

编辑 `config.json`：

```json
{
  "stripe_publishable_key": "pk_test_你的密钥",
  "bins_to_test": ["424242", "552233", "378282"]
}
```

从 https://dashboard.stripe.com/test/apikeys 获取密钥

### 3. 安装ChromeDriver

下载并安装ChromeDriver：
- Windows: https://chromedriver.chromium.org/downloads
- 或使用: `pip install webdriver-manager`

### 4. 运行自动化测试

```bash
# 使用配置文件中的BIN列表
python auto_test_cards.py --config

# 测试指定的BIN
python auto_test_cards.py --bins 424242 552233 378282

# 无头模式（不显示浏览器）
python auto_test_cards.py --config --headless
```

## 📖 详细使用说明

### 方法1: 自动化批量测试（推荐）

**优点：**
- ✅ 完全自动化
- ✅ 批量测试
- ✅ 生成报告
- ✅ 测试真实生成的卡号

**使用步骤：**

1. 配置 `config.json`：
```json
{
  "stripe_publishable_key": "pk_test_你的密钥",
  "bins_to_test": ["424242", "552233", "378282", "622126"]
}
```

2. 运行测试：
```bash
python auto_test_cards.py --config
```

3. 查看结果：
- 终端显示实时进度
- 生成 `test_report.json` 报告

**输出示例：**
```
🎲 生成 4 张卡号...
  [1/4] ✅ BIN 424242: 4242 4242 4242 4242
  [2/4] ✅ BIN 552233: 5522 3344 5566 7788
  ...

🧪 开始批量测试 4 张卡号
--- 测试 1/4 ---
卡号: 4242 4242 4242 4242
✅ 测试通过

📊 批量测试总结
总数: 4
✅ 成功: 3
❌ 失败: 1
成功率: 75.0%
```

### 方法2: 手动测试单张卡号

**使用步骤：**

1. 生成卡号：
```python
from card_generator import generate_card_info
card = generate_card_info('424242')
print(card)
```

2. 打开 `test_card.html` 在浏览器中

3. 输入Stripe Publishable Key

4. 输入生成的卡号信息

5. 点击"开始测试"

### 方法3: 命令行测试BIN品牌

```bash
# 测试单个BIN
python stripe_payment_tester.py 424242

# 批量测试
python stripe_payment_tester.py --batch 424242 552233 378282

# 使用配置文件
python stripe_payment_tester.py --config
```

## 📊 测试报告

自动化测试会生成 `test_report.json`：

```json
{
  "total": 4,
  "success": 3,
  "failed": 1,
  "details": [
    {
      "card": {
        "cardNumber": "4242 4242 4242 4242",
        "expiryDate": "12/34",
        "cvc": "123",
        "cardBrand": "Visa"
      },
      "success": true,
      "message": "测试通过",
      "details": {
        "payment_method_id": "pm_xxxxx"
      }
    }
  ]
}
```

## ⚙️ 配置选项

### config.json 完整配置

```json
{
  "stripe_api_key": "sk_test_...",
  "stripe_publishable_key": "pk_test_...",
  "test_settings": {
    "amount": 100,
    "currency": "usd"
  },
  "bins_to_test": [
    "424242",
    "552233",
    "378282",
    "622126"
  ]
}
```

### 命令行参数

**auto_test_cards.py:**
- `--bins` - 指定BIN列表
- `--config` - 使用配置文件
- `--key` - 指定Publishable Key
- `--headless` - 无头模式
- `--no-report` - 不保存报告

**stripe_payment_tester.py:**
- `--batch` - 批量测试
- `--config` - 使用配置文件
- `--list-tokens` - 列出测试Token
- `--amount` - 测试金额
- `--currency` - 货币代码

## 🔧 故障排除

### 问题1: ChromeDriver错误

**错误：** `selenium.common.exceptions.WebDriverException`

**解决：**
```bash
# 方法1: 手动下载ChromeDriver
# 下载地址: https://chromedriver.chromium.org/downloads
# 将chromedriver.exe放到PATH路径

# 方法2: 使用webdriver-manager
pip install webdriver-manager
```

### 问题2: Stripe密钥错误

**错误：** `未配置Publishable Key`

**解决：**
1. 登录 https://dashboard.stripe.com/test/apikeys
2. 复制 "Publishable key" (pk_test_开头)
3. 粘贴到 `config.json` 的 `stripe_publishable_key`

### 问题3: 卡号生成失败

**错误：** `BIN校验失败`

**解决：**
- 确保BIN至少4位数字
- 使用常见的BIN前缀（如424242、552233）
- 检查BIN是否属于银行金融类别

### 问题4: 测试页面加载失败

**错误：** `测试页面不存在`

**解决：**
- 确保 `test_card.html` 在同一目录
- 使用绝对路径
- 检查文件权限

## 📝 注意事项

1. **仅用于测试环境**
   - 只能使用Stripe测试密钥（pk_test_开头）
   - 不会产生真实扣款

2. **API限流**
   - 批量测试会自动延迟
   - 避免过快请求

3. **浏览器要求**
   - 需要Chrome浏览器
   - 需要ChromeDriver

4. **网络要求**
   - 需要访问Stripe API
   - 需要稳定的网络连接

## 🎯 最佳实践

1. **测试前准备**
   - 先测试1-2个BIN验证配置
   - 使用无头模式提高效率
   - 定期清理测试报告

2. **BIN选择**
   - 使用常见的测试BIN
   - 避免使用真实的生产BIN
   - 测试多种卡品牌

3. **结果分析**
   - 查看测试报告
   - 分析失败原因
   - 优化BIN列表

## 📚 相关资源

- [Stripe测试文档](https://stripe.com/docs/testing)
- [Stripe API文档](https://stripe.com/docs/api)
- [Selenium文档](https://selenium-python.readthedocs.io/)

## 🐱 技术支持

如有问题，请检查：
1. Python版本 >= 3.7
2. 依赖包已安装
3. Stripe密钥正确
4. ChromeDriver已安装

---

**喵~ 祝测试顺利！** 🎨✨
