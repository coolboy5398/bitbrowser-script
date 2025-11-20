"""
Stripe支付测试工具

使用Stripe预定义测试Token进行支付测试
不直接发送原始卡号，符合Stripe安全要求
"""

import asyncio
import aiohttp
import json
import os
from typing import Dict, List, Any, Optional


# ============================================
# 配置加载
# ============================================

def load_config(config_path: str = 'config.json') -> Dict[str, Any]:
    """加载配置文件"""
    script_dir = os.path.dirname(os.path.abspath(__file__))
    full_path = os.path.join(script_dir, config_path)
    
    try:
        with open(full_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError) as e:
        print(f'⚠️ 配置文件错误: {e}')
        return {}


def load_bins(bins_file: str = 'bins.json') -> List[str]:
    """加载BIN配置文件"""
    script_dir = os.path.dirname(os.path.abspath(__file__))
    full_path = os.path.join(script_dir, bins_file)
    
    try:
        with open(full_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
            return data.get('bins', [])
    except (FileNotFoundError, json.JSONDecodeError) as e:
        print(f'⚠️ BIN配置文件错误: {e}')
        return []


# 加载配置
CONFIG = load_config()
STRIPE_TEST_SECRET_KEY = CONFIG.get('stripe_api_key', 'sk_test_YOUR_KEY_HERE')
STRIPE_API_BASE = 'https://api.stripe.com/v1'
DEFAULT_AMOUNT = CONFIG.get('test_settings', {}).get('amount', 100)
DEFAULT_CURRENCY = CONFIG.get('test_settings', {}).get('currency', 'usd')

# 加载BIN列表
DEFAULT_BINS = load_bins('bins.json')


# ============================================
# Stripe测试Token映射
# ============================================

# BIN到Stripe测试Token的映射
BIN_TO_TOKEN_MAP = {
    # Visa
    '4242': 'tok_visa',
    '424242': 'tok_visa',
    '4000': 'tok_visa',
    '400000': 'tok_visa',
    
    # Visa Debit
    '400005': 'tok_visa_debit',
    
    # Mastercard
    '5555': 'tok_mastercard',
    '555555': 'tok_mastercard',
    '5200': 'tok_mastercard_debit',
    '5105': 'tok_mastercard_prepaid',
    '2223': 'tok_mastercard',
    
    # American Express
    '3782': 'tok_amex',
    '378282': 'tok_amex',
    '3714': 'tok_amex',
    '371449': 'tok_amex',
    
    # Discover
    '6011': 'tok_discover',
    '601111': 'tok_discover',
    
    # Diners Club
    '3056': 'tok_diners',
    '305693': 'tok_diners',
    
    # JCB
    '3566': 'tok_jcb',
    '356600': 'tok_jcb',
    
    # UnionPay
    '6200': 'tok_unionpay',
    '620000': 'tok_unionpay',
    '622126': 'tok_unionpay',
}

# 所有可用的Stripe测试Token
STRIPE_TEST_TOKENS = {
    'tok_visa': {'brand': 'Visa', 'description': 'Visa标准测试卡'},
    'tok_visa_debit': {'brand': 'Visa Debit', 'description': 'Visa借记卡'},
    'tok_mastercard': {'brand': 'Mastercard', 'description': 'Mastercard标准测试卡'},
    'tok_mastercard_debit': {'brand': 'Mastercard Debit', 'description': 'Mastercard借记卡'},
    'tok_mastercard_prepaid': {'brand': 'Mastercard Prepaid', 'description': 'Mastercard预付卡'},
    'tok_amex': {'brand': 'American Express', 'description': 'American Express测试卡'},
    'tok_discover': {'brand': 'Discover', 'description': 'Discover测试卡'},
    'tok_diners': {'brand': 'Diners Club', 'description': 'Diners Club测试卡'},
    'tok_jcb': {'brand': 'JCB', 'description': 'JCB测试卡'},
    'tok_unionpay': {'brand': 'UnionPay', 'description': 'UnionPay测试卡'},
}


# ============================================
# BIN到Token转换
# ============================================

def bin_to_token(bin_prefix: str) -> Optional[str]:
    """
    将BIN前缀转换为Stripe测试Token
    
    Args:
        bin_prefix: BIN前缀
        
    Returns:
        Stripe测试Token，如果没有匹配返回None
    """
    # 尝试精确匹配
    if bin_prefix in BIN_TO_TOKEN_MAP:
        return BIN_TO_TOKEN_MAP[bin_prefix]
    
    # 尝试前缀匹配
    for bin_key, token in BIN_TO_TOKEN_MAP.items():
        if bin_prefix.startswith(bin_key):
            return token
    
    # 默认使用Visa
    print(f'⚠️ BIN {bin_prefix} 没有精确匹配，使用默认Visa Token')
    return 'tok_visa'


def get_token_info(token: str) -> Dict[str, str]:
    """获取Token信息"""
    return STRIPE_TEST_TOKENS.get(token, {
        'brand': 'Unknown',
        'description': '未知测试卡'
    })


# ============================================
# Stripe API调用
# ============================================

async def create_payment_method_from_token(token: str, api_key: str) -> Optional[str]:
    """
    从Stripe测试Token创建PaymentMethod
    
    Args:
        token: Stripe测试Token (如 tok_visa)
        api_key: Stripe API密钥
        
    Returns:
        PaymentMethod ID，失败返回None
    """
    data = {
        'type': 'card',
        'card[token]': token
    }
    
    headers = {
        'Authorization': f'Bearer {api_key}',
        'Content-Type': 'application/x-www-form-urlencoded'
    }
    
    try:
        print(f'\n💳 创建PaymentMethod (Token: {token})...')
        
        async with aiohttp.ClientSession() as session:
            async with session.post(
                f'{STRIPE_API_BASE}/payment_methods',
                headers=headers,
                data=data
            ) as response:
                result = await response.json()
                
                if response.status == 200:
                    pm_id = result['id']
                    card_info = result.get('card', {})
                    print(f'✅ PaymentMethod创建成功: {pm_id}')
                    print(f'   品牌: {card_info.get("brand", "N/A")}')
                    print(f'   后四位: {card_info.get("last4", "N/A")}')
                    return pm_id
                else:
                    error = result.get('error', {})
                    print(f'❌ PaymentMethod创建失败:')
                    print(f'   错误类型: {error.get("type", "unknown")}')
                    print(f'   错误码: {error.get("code", "unknown")}')
                    print(f'   错误信息: {error.get("message", "unknown")}')
                    return None
    except Exception as e:
        print(f'❌ 请求异常: {str(e)}')
        return None


async def create_payment_intent(
    amount: int,
    currency: str,
    payment_method_id: str,
    api_key: str
) -> Dict[str, Any]:
    """
    创建并确认PaymentIntent
    
    Args:
        amount: 金额（最小单位）
        currency: 货币代码
        payment_method_id: PaymentMethod ID
        api_key: Stripe API密钥
        
    Returns:
        测试结果字典
    """
    data = {
        'amount': amount,
        'currency': currency,
        'payment_method': payment_method_id,
        'confirm': 'true',
        'return_url': 'https://example.com/return'
    }
    
    headers = {
        'Authorization': f'Bearer {api_key}',
        'Content-Type': 'application/x-www-form-urlencoded'
    }
    
    try:
        print(f'\n💰 创建PaymentIntent (金额: {amount/100:.2f} {currency.upper()})...')
        
        async with aiohttp.ClientSession() as session:
            async with session.post(
                f'{STRIPE_API_BASE}/payment_intents',
                headers=headers,
                data=data
            ) as response:
                result = await response.json()
                
                if response.status == 200:
                    status = result.get('status')
                    pi_id = result.get('id')
                    
                    print(f'✅ PaymentIntent创建成功: {pi_id}')
                    print(f'   状态: {status}')
                    
                    if status == 'succeeded':
                        print(f'   🎉 支付成功！')
                        return {
                            'success': True,
                            'status': status,
                            'payment_intent_id': pi_id,
                            'message': '支付成功'
                        }
                    elif status == 'requires_action':
                        print(f'   ⚠️ 需要额外验证（如3D Secure）')
                        return {
                            'success': False,
                            'status': status,
                            'payment_intent_id': pi_id,
                            'message': '需要额外验证'
                        }
                    else:
                        print(f'   ⚠️ 状态: {status}')
                        return {
                            'success': False,
                            'status': status,
                            'payment_intent_id': pi_id,
                            'message': f'状态: {status}'
                        }
                else:
                    error = result.get('error', {})
                    error_type = error.get('type', 'unknown')
                    error_code = error.get('code', 'unknown')
                    error_message = error.get('message', 'unknown')
                    decline_code = error.get('decline_code', 'N/A')
                    
                    print(f'❌ PaymentIntent失败:')
                    print(f'   错误类型: {error_type}')
                    print(f'   错误码: {error_code}')
                    print(f'   拒绝码: {decline_code}')
                    print(f'   错误信息: {error_message}')
                    
                    return {
                        'success': False,
                        'error_type': error_type,
                        'error_code': error_code,
                        'decline_code': decline_code,
                        'message': error_message
                    }
    except Exception as e:
        print(f'❌ 请求异常: {str(e)}')
        return {
            'success': False,
            'error': str(e),
            'message': '请求异常'
        }


# ============================================
# 测试流程
# ============================================

async def test_bin_payment(
    bin_prefix: str,
    amount: int = 100,
    currency: str = 'usd',
    api_key: str = None
) -> Dict[str, Any]:
    """
    测试BIN的支付流程
    
    Args:
        bin_prefix: BIN前缀
        amount: 测试金额（美分）
        currency: 货币代码
        api_key: Stripe API密钥
        
    Returns:
        测试结果字典
    """
    print(f'\n{"="*60}')
    print(f'🧪 测试BIN: {bin_prefix}')
    print(f'{"="*60}')
    
    result = {
        'bin': bin_prefix,
        'token_mapped': False,
        'payment_method_created': False,
        'payment_success': False,
        'details': {}
    }
    
    # 使用提供的API密钥或默认密钥
    if api_key is None:
        api_key = STRIPE_TEST_SECRET_KEY
    
    # 检查API密钥
    if api_key == 'sk_test_YOUR_KEY_HERE':
        print('❌ 请先配置Stripe测试API密钥！')
        print('   在config.json中设置 stripe_api_key')
        result['details']['error'] = '未配置API密钥'
        return result
    
    # 步骤1: BIN转Token
    token = bin_to_token(bin_prefix)
    if not token:
        result['details']['error'] = 'BIN无法映射到测试Token'
        return result
    
    token_info = get_token_info(token)
    print(f'\n🎫 映射Token: {token}')
    print(f'   品牌: {token_info["brand"]}')
    print(f'   描述: {token_info["description"]}')
    
    result['token_mapped'] = True
    result['details']['token'] = token
    result['details']['token_info'] = token_info
    
    # 步骤2: 创建PaymentMethod
    pm_id = await create_payment_method_from_token(token, api_key)
    if not pm_id:
        result['details']['error'] = 'PaymentMethod创建失败'
        return result
    
    result['payment_method_created'] = True
    result['details']['payment_method_id'] = pm_id
    
    # 步骤3: 创建并确认PaymentIntent
    payment_result = await create_payment_intent(amount, currency, pm_id, api_key)
    result['details']['payment'] = payment_result
    result['payment_success'] = payment_result.get('success', False)
    
    # 打印总结
    print(f'\n{"="*60}')
    print('📊 测试总结')
    print(f'{"="*60}')
    print(f'BIN: {bin_prefix}')
    print(f'Token映射: {"✅" if result["token_mapped"] else "❌"}')
    print(f'PaymentMethod: {"✅" if result["payment_method_created"] else "❌"}')
    print(f'支付测试: {"✅" if result["payment_success"] else "❌"}')
    
    if result['payment_success']:
        print(f'\n🎉 测试通过！此BIN可以成功支付！')
    else:
        print(f'\n❌ 测试失败: {payment_result.get("message", "未知错误")}')
    
    print(f'{"="*60}\n')
    
    return result


async def batch_test_bins(
    bins: List[str],
    amount: int = 100,
    currency: str = 'usd',
    api_key: str = None
) -> Dict[str, Any]:
    """批量测试多个BIN"""
    print(f'\n{"="*60}')
    print(f'🧪 批量测试 {len(bins)} 个BIN')
    print(f'{"="*60}')
    
    results = {
        'total': len(bins),
        'token_mapped': 0,
        'payment_method_created': 0,
        'payment_success': 0,
        'details': []
    }
    
    for i, bin_prefix in enumerate(bins, 1):
        print(f'\n--- 测试 {i}/{len(bins)} ---')
        
        result = await test_bin_payment(bin_prefix, amount, currency, api_key)
        results['details'].append(result)
        
        if result['token_mapped']:
            results['token_mapped'] += 1
        if result['payment_method_created']:
            results['payment_method_created'] += 1
        if result['payment_success']:
            results['payment_success'] += 1
        
        # 延迟避免API限流
        if i < len(bins):
            await asyncio.sleep(1)
    
    # 打印总结
    print(f'\n{"="*60}')
    print('📊 批量测试总结')
    print(f'{"="*60}')
    print(f'总数: {results["total"]}')
    print(f'✅ Token映射成功: {results["token_mapped"]}')
    print(f'✅ PaymentMethod创建成功: {results["payment_method_created"]}')
    print(f'✅ 支付测试通过: {results["payment_success"]}')
    print(f'成功率: {results["payment_success"]/results["total"]*100:.1f}%')
    print(f'{"="*60}\n')
    
    return results


# ============================================
# 命令行接口
# ============================================

def main():
    """命令行主函数"""
    import argparse
    
    parser = argparse.ArgumentParser(
        description='Stripe支付测试工具 - 使用测试Token测试BIN'
    )
    
    parser.add_argument(
        'bin',
        nargs='?',
        help='要测试的BIN前缀'
    )
    
    parser.add_argument(
        '--batch',
        nargs='+',
        help='批量测试多个BIN'
    )
    
    parser.add_argument(
        '--config',
        action='store_true',
        help='使用config.json中的BIN列表进行批量测试'
    )
    
    parser.add_argument(
        '--list-tokens',
        action='store_true',
        help='列出所有可用的测试Token'
    )
    
    parser.add_argument(
        '--amount',
        type=int,
        default=DEFAULT_AMOUNT,
        help=f'测试金额（美分，默认{DEFAULT_AMOUNT}）'
    )
    
    parser.add_argument(
        '--currency',
        type=str,
        default=DEFAULT_CURRENCY,
        help=f'货币代码（默认{DEFAULT_CURRENCY}）'
    )
    
    parser.add_argument(
        '--api-key',
        type=str,
        help='Stripe测试API密钥'
    )
    
    args = parser.parse_args()
    
    # 列出所有测试Token
    if args.list_tokens:
        print('\n可用的Stripe测试Token:')
        print('='*60)
        for token, info in STRIPE_TEST_TOKENS.items():
            print(f'{token:25} {info["brand"]:20} {info["description"]}')
        print('='*60)
        return
    
    # 使用配置文件中的BIN列表
    if args.config:
        if not DEFAULT_BINS:
            print('❌ config.json中没有配置BIN列表')
            return
        
        print(f'📋 从config.json加载 {len(DEFAULT_BINS)} 个BIN')
        asyncio.run(batch_test_bins(
            DEFAULT_BINS,
            args.amount,
            args.currency,
            args.api_key
        ))
        return
    
    # 批量测试
    if args.batch:
        asyncio.run(batch_test_bins(
            args.batch,
            args.amount,
            args.currency,
            args.api_key
        ))
        return
    
    # 单个测试
    if args.bin:
        asyncio.run(test_bin_payment(
            args.bin,
            args.amount,
            args.currency,
            args.api_key
        ))
        return
    
    # 默认显示帮助
    parser.print_help()
    print('\n示例用法:')
    print('  python stripe_payment_tester.py 424242')
    print('  python stripe_payment_tester.py --batch 424242 552233 378282')
    print('  python stripe_payment_tester.py --config  # 使用config.json中的BIN列表')
    print('  python stripe_payment_tester.py --list-tokens  # 列出所有测试Token')


if __name__ == '__main__':
    main()
