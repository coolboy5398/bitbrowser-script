"""
自动化批量测试卡号工具

使用Selenium自动化浏览器测试card_generator生成的卡号
"""

import json
import time
import os
from typing import List, Dict, Any
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options


# ============================================
# 配置加载
# ============================================

def load_config(config_path: str = 'config.json') -> Dict[str, Any]:
    """加载配置文件"""
    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        print(f'⚠️ 配置文件错误: {e}')
        return {}


CONFIG = load_config()
STRIPE_PUBLISHABLE_KEY = CONFIG.get('stripe_publishable_key', '')
DEFAULT_BINS = CONFIG.get('bins_to_test', [])


# ============================================
# 卡号生成
# ============================================

def generate_cards_from_bins(bins: List[str]) -> List[Dict[str, str]]:
    """
    从BIN列表生成卡号
    
    Args:
        bins: BIN前缀列表
        
    Returns:
        卡号信息列表
    """
    try:
        from card_generator import generate_card_info
    except ImportError:
        print('❌ 无法导入card_generator模块')
        return []
    
    cards = []
    print(f'\n🎲 生成 {len(bins)} 张卡号...')
    
    for i, bin_prefix in enumerate(bins, 1):
        try:
            card = generate_card_info(bin_prefix)
            cards.append(card)
            print(f'  [{i}/{len(bins)}] ✅ BIN {bin_prefix}: {card["cardNumber"]}')
        except Exception as e:
            print(f'  [{i}/{len(bins)}] ❌ BIN {bin_prefix}: {str(e)}')
    
    print(f'\n✅ 成功生成 {len(cards)} 张卡号\n')
    return cards


# ============================================
# 浏览器自动化测试
# ============================================

class CardTester:
    """卡号自动化测试类"""
    
    def __init__(self, publishable_key: str, headless: bool = False):
        """
        初始化测试器
        
        Args:
            publishable_key: Stripe Publishable Key
            headless: 是否使用无头模式
        """
        self.publishable_key = publishable_key
        self.driver = None
        self.headless = headless
        self.test_page_path = None
    
    def setup_driver(self):
        """设置浏览器驱动"""
        print('🌐 启动浏览器...')
        
        options = Options()
        if self.headless:
            options.add_argument('--headless')
        options.add_argument('--disable-gpu')
        options.add_argument('--no-sandbox')
        options.add_argument('--disable-dev-shm-usage')
        options.add_argument('--window-size=1920,1080')
        
        try:
            self.driver = webdriver.Chrome(options=options)
            print('✅ 浏览器启动成功')
        except Exception as e:
            print(f'❌ 浏览器启动失败: {str(e)}')
            print('提示: 请确保已安装Chrome和ChromeDriver')
            raise
    
    def load_test_page(self):
        """加载测试页面"""
        # 获取test_card_full.html的绝对路径
        script_dir = os.path.dirname(os.path.abspath(__file__))
        self.test_page_path = os.path.join(script_dir, 'test_card_full.html')
        
        if not os.path.exists(self.test_page_path):
            raise FileNotFoundError(f'测试页面不存在: {self.test_page_path}')
        
        print(f'📄 加载测试页面: {self.test_page_path}')
        self.driver.get(f'file:///{self.test_page_path}')
        time.sleep(2)
    
    def configure_stripe(self):
        """配置API地址"""
        print('⚙️ 配置API地址...')
        
        try:
            # 检查API地址输入框（test_card_full.html使用apiUrl）
            api_input = self.driver.find_element(By.ID, 'apiUrl')
            # 默认使用localhost:5000，无需修改
            print('✅ API配置完成')
        except Exception as e:
            print(f'⚠️ API配置跳过: {str(e)}')
            # 不是致命错误，继续执行
    
    def test_card(self, card_info: Dict[str, str]) -> Dict[str, Any]:
        """
        测试单张卡号
        
        Args:
            card_info: 卡号信息字典
            
        Returns:
            测试结果字典
        """
        result = {
            'card': card_info,
            'success': False,
            'message': '',
            'details': {}
        }
        
        try:
            # 输入卡号
            card_input = self.driver.find_element(By.ID, 'cardNumber')
            card_input.clear()
            card_input.send_keys(card_info['cardNumber'])
            
            # 输入有效期
            expiry_input = self.driver.find_element(By.ID, 'expiry')
            expiry_input.clear()
            expiry_input.send_keys(card_info['expiryDate'])
            
            # 输入CVV
            cvc_input = self.driver.find_element(By.ID, 'cvc')
            cvc_input.clear()
            cvc_input.send_keys(card_info['cvc'])
            
            # 点击提交按钮
            submit_btn = self.driver.find_element(By.ID, 'submitBtn')
            submit_btn.click()
            
            # 等待结果（最多15秒）
            wait = WebDriverWait(self.driver, 15)
            result_div = wait.until(
                EC.visibility_of_element_located((By.ID, 'result'))
            )
            
            # 获取结果类型
            result_class = result_div.get_attribute('class')
            
            # 获取结果内容
            result_title = self.driver.find_element(By.ID, 'resultTitle').text
            result_content = self.driver.find_element(By.ID, 'resultContent').text
            
            # 判断成功或失败
            if 'success' in result_class:
                result['success'] = True
                result['message'] = '测试通过'
                
                # 提取PaymentMethod ID
                if 'PaymentMethod ID:' in result_content:
                    pm_id = result_content.split('PaymentMethod ID:')[1].split('\n')[0].strip()
                    result['details']['payment_method_id'] = pm_id
                
                # 提取品牌和后四位
                if '品牌:' in result_content:
                    brand = result_content.split('品牌:')[1].split('\n')[0].strip()
                    result['details']['brand'] = brand
                
                if '后四位:' in result_content:
                    last4 = result_content.split('后四位:')[1].split('\n')[0].strip()
                    result['details']['last4'] = last4
            else:
                result['success'] = False
                result['message'] = result_title
                
                # 提取错误详情
                if '错误信息:' in result_content:
                    error_msg = result_content.split('错误信息:')[1].split('\n')[0].strip()
                    result['details']['error_message'] = error_msg
                
                # 分析失败原因
                result['details']['failure_reason'] = self._analyze_failure(result_content)
            
            result['details']['full_result'] = result_content
            
        except Exception as e:
            result['success'] = False
            result['message'] = f'测试异常: {str(e)}'
        
        return result
    
    def batch_test_cards(self, cards: List[Dict[str, str]]) -> Dict[str, Any]:
        """
        批量测试卡号
        
        Args:
            cards: 卡号信息列表
            
        Returns:
            批量测试结果
        """
        print(f'\n{"="*60}')
        print(f'🧪 开始批量测试 {len(cards)} 张卡号')
        print(f'{"="*60}\n')
        
        results = {
            'total': len(cards),
            'success': 0,
            'failed': 0,
            'details': []
        }
        
        for i, card in enumerate(cards, 1):
            print(f'--- 测试 {i}/{len(cards)} ---')
            print(f'卡号: {card["cardNumber"]}')
            print(f'有效期: {card["expiryDate"]}')
            print(f'CVV: {card["cvc"]}')
            print(f'品牌: {card["cardBrand"]}')
            
            result = self.test_card(card)
            results['details'].append(result)
            
            if result['success']:
                results['success'] += 1
                print(f'✅ 测试通过')
                if 'payment_method_id' in result['details']:
                    print(f'   PaymentMethod: {result["details"]["payment_method_id"]}')
            else:
                results['failed'] += 1
                print(f'❌ 测试失败: {result["message"]}')
                if 'failure_reason' in result['details']:
                    print(f'   原因: {result["details"]["failure_reason"]}')
                if 'error_message' in result['details']:
                    print(f'   详情: {result["details"]["error_message"]}')
            
            print()
            
            # 延迟避免过快
            if i < len(cards):
                time.sleep(2)
        
        # 分析失败原因
        failure_reasons = {}
        for detail in results['details']:
            if not detail['success'] and 'failure_reason' in detail['details']:
                reason = detail['details']['failure_reason']
                failure_reasons[reason] = failure_reasons.get(reason, 0) + 1
        
        results['failure_analysis'] = failure_reasons
        
        # 打印总结
        print(f'\n{"="*60}')
        print('📊 批量测试总结')
        print(f'{"="*60}')
        print(f'总数: {results["total"]}')
        print(f'✅ 成功: {results["success"]}')
        print(f'❌ 失败: {results["failed"]}')
        if results["total"] > 0:
            print(f'成功率: {results["success"]/results["total"]*100:.1f}%')
        
        # 打印失败原因分析
        if failure_reasons:
            print(f'\n📋 失败原因分析:')
            for reason, count in sorted(failure_reasons.items(), key=lambda x: x[1], reverse=True):
                print(f'   • {reason}: {count}次')
        
        print(f'{"="*60}\n')
        
        return results
    
    def _analyze_failure(self, error_content: str) -> str:
        """
        分析失败原因
        
        Args:
            error_content: 错误内容
            
        Returns:
            失败原因分析
        """
        error_lower = error_content.lower()
        
        # 卡号相关错误
        if 'incorrect_number' in error_lower or 'invalid number' in error_lower:
            return '卡号格式错误或Luhn校验失败'
        
        if 'card number is invalid' in error_lower:
            return '卡号无效'
        
        # 有效期相关错误
        if 'expired' in error_lower or 'expiry' in error_lower:
            return '有效期错误或已过期'
        
        if 'invalid_expiry' in error_lower:
            return '有效期格式无效'
        
        # CVV相关错误
        if 'cvc' in error_lower or 'cvv' in error_lower:
            return 'CVV格式错误'
        
        if 'incorrect_cvc' in error_lower:
            return 'CVV不正确'
        
        # 拒绝相关错误
        if 'declined' in error_lower or 'card_declined' in error_lower:
            return '卡被拒绝（可能是测试卡限制）'
        
        if 'insufficient_funds' in error_lower:
            return '余额不足（测试场景）'
        
        if 'lost_card' in error_lower:
            return '卡已挂失（测试场景）'
        
        if 'stolen_card' in error_lower:
            return '卡被盗（测试场景）'
        
        # API相关错误
        if 'api_key' in error_lower or 'authentication' in error_lower:
            return 'API密钥错误或认证失败'
        
        if 'rate_limit' in error_lower:
            return 'API请求频率超限'
        
        # 网络相关错误
        if 'network' in error_lower or 'connection' in error_lower:
            return '网络连接错误'
        
        if 'timeout' in error_lower:
            return '请求超时'
        
        # 其他错误
        if 'processing_error' in error_lower:
            return '处理错误'
        
        return '未知错误，请查看详细信息'
    
    def close(self):
        """关闭浏览器"""
        if self.driver:
            print('🔒 关闭浏览器...')
            self.driver.quit()


# ============================================
# 主测试流程
# ============================================

def auto_test_bins(
    bins: List[str],
    publishable_key: str = None,
    headless: bool = False,
    save_report: bool = True
) -> Dict[str, Any]:
    """
    自动化测试BIN列表
    
    Args:
        bins: BIN前缀列表
        publishable_key: Stripe Publishable Key
        headless: 是否使用无头模式
        save_report: 是否保存测试报告
        
    Returns:
        测试结果字典
    """
    # 使用配置文件中的密钥
    if publishable_key is None:
        publishable_key = STRIPE_PUBLISHABLE_KEY
    
    # 检查密钥
    if not publishable_key or publishable_key == '':
        print('❌ 请在config.json中配置stripe_publishable_key')
        return {'error': '未配置Publishable Key'}
    
    # 步骤1: 生成卡号
    cards = generate_cards_from_bins(bins)
    if not cards:
        print('❌ 没有成功生成任何卡号')
        return {'error': '卡号生成失败'}
    
    # 步骤2: 自动化测试
    tester = None
    try:
        tester = CardTester(publishable_key, headless=headless)
        tester.setup_driver()
        tester.load_test_page()
        tester.configure_stripe()
        
        results = tester.batch_test_cards(cards)
        
        # 打印总结
        print(f'\n{"="*60}')
        print('📊 批量测试总结')
        print(f'{"="*60}')
        print(f'总数: {results["total"]}')
        print(f'✅ 成功: {results["success"]}')
        print(f'❌ 失败: {results["failed"]}')
        print(f'成功率: {results["success"]/results["total"]*100:.1f}%')
        print(f'{"="*60}\n')
        
        # 保存报告
        if save_report:
            save_test_report(results)
        
        return results
        
    except Exception as e:
        print(f'❌ 测试过程出错: {str(e)}')
        return {'error': str(e)}
    
    finally:
        if tester:
            tester.close()


def save_test_report(results: Dict[str, Any], filename: str = 'test_report.json'):
    """
    保存测试报告
    
    Args:
        results: 测试结果
        filename: 报告文件名
    """
    try:
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(results, f, ensure_ascii=False, indent=2)
        print(f'📄 测试报告已保存: {filename}')
    except Exception as e:
        print(f'⚠️ 保存报告失败: {str(e)}')


# ============================================
# 命令行接口
# ============================================

def main():
    """命令行主函数"""
    import argparse
    
    parser = argparse.ArgumentParser(
        description='自动化批量测试卡号工具'
    )
    
    parser.add_argument(
        '--bins',
        nargs='+',
        help='要测试的BIN列表'
    )
    
    parser.add_argument(
        '--config',
        action='store_true',
        help='使用config.json中的BIN列表'
    )
    
    parser.add_argument(
        '--key',
        type=str,
        help='Stripe Publishable Key'
    )
    
    parser.add_argument(
        '--headless',
        action='store_true',
        help='使用无头模式（不显示浏览器窗口）'
    )
    
    parser.add_argument(
        '--no-report',
        action='store_true',
        help='不保存测试报告'
    )
    
    args = parser.parse_args()
    
    # 确定要测试的BIN列表
    bins = []
    if args.config:
        if not DEFAULT_BINS:
            print('❌ config.json中没有配置BIN列表')
            return
        bins = DEFAULT_BINS
        print(f'📋 从config.json加载 {len(bins)} 个BIN')
    elif args.bins:
        bins = args.bins
    else:
        parser.print_help()
        print('\n示例用法:')
        print('  python auto_test_cards.py --bins 424242 552233 378282')
        print('  python auto_test_cards.py --config')
        print('  python auto_test_cards.py --config --headless')
        return
    
    # 执行测试
    auto_test_bins(
        bins=bins,
        publishable_key=args.key,
        headless=args.headless,
        save_report=not args.no_report
    )


if __name__ == '__main__':
    main()
