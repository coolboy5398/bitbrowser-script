"""
提供卡号生成、BIN验证、Luhn算法等核心功能
"""

import asyncio
import time
import random
from typing import Dict, List, Tuple, Optional, Any
from datetime import datetime
import aiohttp


# ============================================
# 延迟工具函数
# ============================================

async def sleep(ms: int) -> None:
    """
    简单的延迟函数
    
    Args:
        ms: 延迟毫秒数
    """
    await asyncio.sleep(ms / 1000)


async def robust_sleep(ms: int) -> None:
    """
    更精确的延迟函数，使用轮询确保准确性
    
    Args:
        ms: 延迟毫秒数
    """
    start_time = time.time()
    end_time = start_time + (ms / 1000)
    
    while time.time() < end_time:
        remaining = end_time - time.time()
        await asyncio.sleep(min(0.1, remaining))


# ============================================
# Luhn算法 - 银行卡号校验
# ============================================

def calculate_luhn_check_digit(card_number: str) -> str:
    """
    计算Luhn校验位
    
    Args:
        card_number: 不含校验位的卡号
        
    Returns:
        校验位（0-9）
    """
    total = 0
    should_double = True
    
    # 从右向左遍历
    for i in range(len(card_number) - 1, -1, -1):
        digit = int(card_number[i])
        
        if should_double:
            digit *= 2
            if digit > 9:
                digit -= 9
        
        total += digit
        should_double = not should_double
    
    check_digit = (10 - (total % 10)) % 10
    return str(check_digit)


def is_valid_luhn(card_number: str) -> bool:
    """
    验证卡号是否通过Luhn校验
    
    Args:
        card_number: 完整卡号
        
    Returns:
        是否有效
    """
    total = 0
    should_double = False
    
    # 从右向左遍历
    for i in range(len(card_number) - 1, -1, -1):
        digit = int(card_number[i])
        
        if should_double:
            digit *= 2
            if digit > 9:
                digit -= 9
        
        total += digit
        should_double = not should_double
    
    return total % 10 == 0


# 别名函数
calculate_check_digit = calculate_luhn_check_digit
is_valid_card_number = is_valid_luhn


# ============================================
# BIN验证 - 银行卡前缀验证
# ============================================

# MII（主要行业标识符）定义
MII_DEFINITIONS = {
    '0': 'ISO/TC 68 and other industry assignments',
    '1': 'Airlines',
    '2': 'Airlines and other future industry assignments',
    '3': 'Travel and Entertainment (American Express, Diners Club, JCB, etc.)',
    '4': 'Banking and Financial (Visa)',
    '5': 'Banking and Financial (MasterCard)',
    '6': 'Merchandising and Banking/Financial (Discover, UnionPay)',
    '7': 'Petroleum and other future industry assignments',
    '8': 'Healthcare, Telecommunications and other future industry assignments',
    '9': 'National assignment'
}

# 有效的BIN范围定义
VALID_BIN_RANGES = {
    'Visa': [{'start': '4', 'length': 1}],
    'MasterCard': [
        {'start': '51', 'end': '55'},
        {'start': '2221', 'end': '2720'}
    ],
    'American Express': [
        {'start': '34', 'length': 2},
        {'start': '37', 'length': 2}
    ],
    'Diners Club': [
        {'start': '36', 'length': 2},
        {'start': '38', 'length': 2},
        {'start': '300', 'end': '305'},
        {'start': '309', 'length': 3}
    ],
    'Discover': [
        {'start': '6011', 'length': 4},
        {'start': '622126', 'end': '622925'},
        {'start': '644', 'end': '649'},
        {'start': '65', 'length': 2}
    ],
    'JCB': [{'start': '3528', 'end': '3589'}],
    'UnionPay': [{'start': '62', 'length': 2}]
}


def validate_bin_format(bin_str: str) -> Dict[str, Any]:
    """
    验证BIN格式
    
    Args:
        bin_str: BIN前缀
        
    Returns:
        验证结果字典
    """
    bin_str = str(bin_str).strip()
    
    # 检查长度
    if not bin_str or len(bin_str) < 4:
        return {
            'valid': False,
            'error': 'BIN长度至少需要4位数字',
            'code': 'BIN_TOO_SHORT'
        }
    
    if len(bin_str) > 10:
        return {
            'valid': False,
            'error': 'BIN长度不应超过10位数字',
            'code': 'BIN_TOO_LONG'
        }
    
    # 检查是否只包含数字
    if not bin_str.isdigit():
        return {
            'valid': False,
            'error': 'BIN只能包含数字',
            'code': 'BIN_INVALID_CHARS'
        }
    
    # 检查MII
    mii = bin_str[0]
    if mii not in MII_DEFINITIONS:
        return {
            'valid': False,
            'error': f'无效的主要行业标识符（MII）: {mii}',
            'code': 'INVALID_MII'
        }
    
    # 检查是否属于银行金融类别
    if mii not in ['3', '4', '5', '6']:
        return {
            'valid': False,
            'error': f'MII {mii} 不属于银行金融类别，应该是3、4、5或6开头',
            'code': 'NON_BANKING_MII',
            'miiType': MII_DEFINITIONS[mii]
        }
    
    return {
        'valid': True,
        'mii': mii,
        'miiType': MII_DEFINITIONS[mii],
        'binLength': len(bin_str)
    }


def validate_bin_range(bin_str: str) -> Dict[str, Any]:
    """
    验证BIN是否在已知品牌范围内
    
    Args:
        bin_str: BIN前缀
        
    Returns:
        验证结果字典
    """
    matched_brands = []
    
    # 遍历所有品牌规则
    for brand, ranges in VALID_BIN_RANGES.items():
        for range_rule in ranges:
            # 精确长度匹配
            if 'length' in range_rule:
                if bin_str.startswith(range_rule['start']):
                    matched_brands.append(brand)
                    break
            # 范围匹配
            elif 'end' in range_rule:
                prefix = bin_str[:len(range_rule['start'])]
                range_start = int(range_rule['start'])
                range_end = int(range_rule['end'])
                prefix_num = int(prefix)
                
                if range_start <= prefix_num <= range_end:
                    matched_brands.append(brand)
                    break
    
    if matched_brands:
        return {
            'valid': True,
            'matchedBrands': matched_brands,
            'primaryBrand': matched_brands[0]
        }
    
    return {
        'valid': False,
        'error': 'BIN不匹配任何已知的银行卡品牌范围',
        'code': 'UNKNOWN_BIN_RANGE'
    }


def validate_bin(bin_value: str) -> Dict[str, Any]:
    """
    完整的BIN验证
    
    Args:
        bin_value: BIN前缀
        
    Returns:
        验证结果字典
    """
    bin_str = str(bin_value).strip()
    print(f'\n🔍 开始校验BIN: {bin_str}')
    
    # 格式验证
    format_result = validate_bin_format(bin_str)
    if not format_result['valid']:
        print(f"❌ BIN格式校验失败: {format_result['error']}")
        return format_result
    
    print('✅ BIN格式校验通过')
    print(f"   - MII: {format_result['mii']} ({format_result['miiType']})")
    print(f"   - BIN长度: {format_result['binLength']}位")
    
    # 范围验证
    range_result = validate_bin_range(bin_str)
    if not range_result['valid']:
        print(f"⚠️ BIN范围校验失败: {range_result['error']}")
        print('   该BIN可能不是常见银行卡品牌，但仍可尝试生成')
        return {
            'valid': True,
            'warning': range_result['error'],
            'mii': format_result['mii'],
            'miiType': format_result['miiType'],
            'isUnknownBrand': True
        }
    
    print('✅ BIN范围校验通过')
    print(f"   - 匹配品牌: {', '.join(range_result['matchedBrands'])}")
    print(f"   - 主要品牌: {range_result['primaryBrand']}")
    
    return {
        'valid': True,
        'mii': format_result['mii'],
        'miiType': format_result['miiType'],
        'binLength': format_result['binLength'],
        'matchedBrands': range_result['matchedBrands'],
        'primaryBrand': range_result['primaryBrand']
    }



# ============================================
# 卡号生成 - 银行卡信息生成
# ============================================

def detect_card_brand(bin_str: str) -> Dict[str, Any]:
    """
    检测卡品牌
    
    Args:
        bin_str: BIN前缀
        
    Returns:
        卡品牌信息字典
    """
    # Visa: 以4开头
    if bin_str.startswith('4'):
        return {'name': 'Visa', 'length': 16, 'cvvLength': 3}
    
    # MasterCard: 51-55 或 2221-2720
    if bin_str.startswith('5') and len(bin_str) >= 2:
        if bin_str[1] in '12345':
            return {'name': 'MasterCard', 'length': 16, 'cvvLength': 3}
    
    if bin_str.startswith('2') and len(bin_str) >= 4:
        prefix = int(bin_str[:4])
        if 2221 <= prefix <= 2720:
            return {'name': 'MasterCard', 'length': 16, 'cvvLength': 3}
    
    # American Express: 34或37开头
    if bin_str.startswith('34') or bin_str.startswith('37'):
        return {'name': 'American Express', 'length': 15, 'cvvLength': 4}
    
    # UnionPay: 62开头
    if bin_str.startswith('62'):
        return {'name': 'UnionPay', 'length': 16, 'cvvLength': 3}
    
    # Discover: 6011, 644-649, 65开头
    if bin_str.startswith('6011'):
        return {'name': 'Discover', 'length': 16, 'cvvLength': 3}
    
    if len(bin_str) >= 3 and bin_str.startswith('64'):
        if bin_str[2] in '456789':
            return {'name': 'Discover', 'length': 16, 'cvvLength': 3}
    
    if bin_str.startswith('65'):
        return {'name': 'Discover', 'length': 16, 'cvvLength': 3}
    
    # Diners Club: 36或38开头
    if bin_str.startswith('36') or bin_str.startswith('38'):
        return {'name': 'Diners Club', 'length': 14, 'cvvLength': 3}
    
    # JCB: 3528-3589
    if len(bin_str) >= 3 and bin_str.startswith('35'):
        if bin_str[2] in '2345678':
            return {'name': 'JCB', 'length': 16, 'cvvLength': 3}
    
    # 默认
    return {'name': 'Unknown', 'length': 16, 'cvvLength': 3}


def get_realistic_random_digit() -> int:
    """
    生成符合真实分布的随机数字
    
    Returns:
        0-9的数字
    """
    # 真实卡号中各数字出现的概率分布
    distribution = [0.09, 0.1, 0.11, 0.1, 0.1, 0.11, 0.1, 0.09, 0.1, 0.1]
    rand = random.random()
    
    cumulative = 0
    for i, prob in enumerate(distribution):
        cumulative += prob
        if rand < cumulative:
            return i
    
    return 5  # 默认返回5


def generate_bank_standard_account_segment(position: int, current_segment: str, total_length: int) -> str:
    """
    生成银行标准账户段
    
    Args:
        position: 当前位置
        current_segment: 当前已生成的段
        total_length: 总长度
        
    Returns:
        单个数字字符串
    """
    # 不同位置的数字分布
    distributions = {
        0: [0.05, 0.15, 0.15, 0.1, 0.1, 0.1, 0.1, 0.1, 0.1, 0.05],
        1: [0.1, 0.1, 0.1, 0.1, 0.1, 0.1, 0.1, 0.1, 0.1, 0.1],
    }
    default_dist = [0.08, 0.11, 0.11, 0.11, 0.11, 0.11, 0.11, 0.11, 0.11, 0.04]
    
    distribution = distributions.get(position, default_dist)
    rand = random.random()
    
    cumulative = 0
    for i, prob in enumerate(distribution):
        cumulative += prob
        if rand < cumulative:
            return str(i)
    
    return '5'


def weighted_random(weights: List[float]) -> int:
    """
    加权随机选择
    
    Args:
        weights: 权重数组
        
    Returns:
        选中的索引
    """
    rand = random.random()
    cumulative = 0
    
    for i, weight in enumerate(weights):
        cumulative += weight
        if rand < cumulative:
            return i
    
    return len(weights) - 1


def generate_advanced_account_segment(length: int, bin_prefix: str) -> str:
    """
    生成高级账户段
    
    Args:
        length: 需要生成的长度
        bin_prefix: BIN前缀
        
    Returns:
        生成的账户段
    """
    segment = ''
    
    # 基于BIN生成初始段
    bin_seed = int(bin_prefix[-4:]) % 1000
    seed_str = str(bin_seed // 10 % 100).zfill(2)
    
    # 选择生成策略
    strategies = [0.7, 0.2, 0.1]  # 标准、变体、随机
    strategy = weighted_random(strategies)
    
    # 生成前两位（如果长度>=2）
    if length >= 2:
        offset = random.randint(0, 9)
        segment += str((int(seed_str[0]) + offset) % 10)
        segment += str((int(seed_str[1]) + random.randint(0, 2)) % 10)
    
    # 生成剩余位
    remaining = length - len(segment)
    for i in range(remaining):
        current_pos = len(segment)
        
        if strategy == 0:
            # 标准策略
            segment += generate_bank_standard_account_segment(current_pos, segment, length)
        elif strategy == 1:
            # 变体策略
            if current_pos == 2:
                segment += str(weighted_random([0.1, 0.1, 0.3, 0.3, 0.1, 0.05, 0.05, 0, 0, 0]))
            else:
                segment += generate_bank_standard_account_segment(current_pos, segment, length)
        else:
            # 随机策略
            if current_pos < 4:
                segment += str(random.randint(0, 9))
            else:
                segment += generate_bank_standard_account_segment(current_pos, segment, length)
    
    return segment


def generate_realistic_expiry_date() -> Dict[str, str]:
    """
    生成真实的有效期
    
    Returns:
        包含expMonth和expYear的字典
    """
    now = datetime.now()
    current_year = now.year
    current_month = now.month
    
    # 3-5年后过期
    years_to_add = random.randint(3, 5)
    exp_year = current_year + years_to_add
    
    # 70%概率选择季度末月份（3, 6, 9, 12）
    if random.random() < 0.7:
        quarter_months = [3, 6, 9, 12]
        exp_month = random.choice(quarter_months)
    else:
        exp_month = random.randint(1, 12)
    
    # 确保不会生成已过期的日期
    if exp_year == current_year and exp_month <= current_month:
        exp_year += 1
    
    return {
        'expMonth': str(exp_month).zfill(2),
        'expYear': str(exp_year)[-2:]
    }


def generate_cvv(bin_str: str, is_amex: bool, cvv_length: int = 3) -> str:
    """
    生成CVV码
    
    Args:
        bin_str: BIN前缀
        is_amex: 是否为美国运通卡
        cvv_length: CVV长度
        
    Returns:
        CVV码
    """
    if is_amex or cvv_length == 4:
        # 美国运通卡使用4位CVV
        return str(random.randint(1000, 9999))
    else:
        # 其他卡使用3位CVV，避免三位相同
        while True:
            cvv = random.randint(100, 999)
            cvv_str = str(cvv)
            if cvv_str[0] != cvv_str[1] or cvv_str[1] != cvv_str[2]:
                return cvv_str


def format_card_number(card_number: str, is_amex: bool) -> str:
    """
    格式化卡号
    
    Args:
        card_number: 原始卡号
        is_amex: 是否为美国运通卡
        
    Returns:
        格式化后的卡号
    """
    if is_amex:
        # 美国运通卡: 4-6-5格式
        return f"{card_number[:4]} {card_number[4:10]} {card_number[10:]}"
    else:
        # 其他卡: 4-4-4-4格式
        return ' '.join([card_number[i:i+4] for i in range(0, len(card_number), 4)])


def generate_card_info(bin_prefix: str) -> Dict[str, str]:
    """
    生成完整的卡号信息
    
    Args:
        bin_prefix: BIN前缀
        
    Returns:
        卡号信息字典
        
    Raises:
        ValueError: 当BIN验证失败或无法生成有效卡号时
    """
    if not bin_prefix:
        raise ValueError('必须提供BIN前缀')
    
    # 清理BIN前缀
    clean_bin = ''.join(c for c in str(bin_prefix) if c.isdigit())
    
    # 验证BIN
    bin_validation = validate_bin(clean_bin)
    if not bin_validation['valid']:
        raise ValueError(f"BIN校验失败: {bin_validation['error']} (错误码: {bin_validation['code']})")
    
    if 'warning' in bin_validation:
        print(f"⚠️ BIN校验警告: {bin_validation['warning']}")
    
    # 检测卡品牌
    card_brand = detect_card_brand(clean_bin)
    card_length = card_brand['length']
    is_amex = card_brand['name'] == 'American Express'
    
    # 计算需要生成的账户段长度（总长度 - BIN长度 - 校验位）
    account_length = card_length - len(clean_bin) - 1
    
    if account_length <= 0:
        raise ValueError(f'BIN长度过长，无法生成{card_length}位卡号')
    
    # 尝试生成有效卡号（最多50次）
    max_attempts = 50
    
    for attempt in range(max_attempts):
        try:
            # 生成账户段
            card_number = clean_bin
            if account_length > 0:
                account_segment = generate_advanced_account_segment(account_length, clean_bin)
                card_number += account_segment
            
            # 添加校验位
            check_digit = calculate_check_digit(card_number)
            full_card_number = card_number + check_digit
            
            # 验证长度
            if len(full_card_number) != card_length:
                print(f"❌ 卡号长度错误: 期望{card_length}位，实际{len(full_card_number)}位 {full_card_number}")
                print(f"BIN长度: {len(clean_bin)}, 账户段长度: {account_length}, 校验位: 1位")
                raise ValueError(f'生成的卡号长度不正确: 期望{card_length}位，实际{len(full_card_number)}位')
            
            # 验证Luhn
            if not is_valid_card_number(full_card_number):
                print(f'生成的卡号未通过Luhn校验: {full_card_number}')
                continue
            
            # 生成有效期和CVV
            expiry = generate_realistic_expiry_date()
            cvc = generate_cvv(clean_bin, is_amex, card_brand['cvvLength'])
            
            return {
                'cardNumber': format_card_number(full_card_number, is_amex),
                'expiryDate': f"{expiry['expMonth']}/{expiry['expYear']}",
                'cvc': cvc,
                'cardBrand': card_brand['name']
            }
            
        except Exception as e:
            print(f'生成卡号尝试 {attempt + 1} 失败: {str(e)}')
    
    raise ValueError('无法生成符合要求的高质量卡号，请尝试更换BIN或稍后重试')



# ============================================
# API调用函数
# ============================================

async def get_checkout_url(tier: str = 'pro') -> Dict[str, Any]:
    """
    获取Cursor绑卡页面URL
    
    Args:
        tier: 订阅等级，默认'pro'
        
    Returns:
        包含success、url和error的字典
    """
    print('💳 获取绑卡页面URL...')
    
    headers = {
        'Accept': '*/*',
        'Accept-Encoding': 'gzip, deflate, br, zstd',
        'Accept-Language': 'zh-CN,zh;q=0.9',
        'Content-Type': 'application/json',
        'Origin': 'https://cursor.com',
        'Priority': 'u=1, i',
        'Referer': 'https://cursor.com/dashboard',
        'Sec-Ch-Ua-Arch': '"x86"',
        'Sec-Ch-Ua-Bitness': '"64"',
        'Sec-Ch-Ua-Mobile': '?0',
        'Sec-Ch-Ua-Platform': '"Windows"',
        'Sec-Fetch-Dest': 'empty',
        'Sec-Fetch-Mode': 'cors',
        'Sec-Fetch-Site': 'same-origin',
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
    }
    
    request_data = {
        'allowAutomaticPayment': True,
        'allowTrial': True,
        'tier': tier
    }
    
    try:
        print('📡 发送POST请求到: https://cursor.com/api/checkout')
        print(f'📦 请求数据: {request_data}')
        
        async with aiohttp.ClientSession() as session:
            async with session.post(
                'https://cursor.com/api/checkout',
                headers=headers,
                json=request_data
            ) as response:
                print(f'🔍 绑卡响应状态: {response.status}')
                
                if response.status == 200:
                    try:
                        checkout_url = await response.json()
                        print('✅ 绑卡页面请求成功!')
                        print(f'🔗 绑卡页面URL: {checkout_url}')
                        
                        if checkout_url and 'checkout.stripe.com' in str(checkout_url):
                            print('✅ 检测到Stripe支付页面')
                            return {'success': True, 'url': checkout_url, 'error': None}
                        else:
                            print('⚠️ 返回的URL不是预期的Stripe支付页面')
                            return {'success': False, 'url': None, 'error': 'Invalid checkout URL'}
                    except Exception as parse_error:
                        response_text = await response.text()
                        print(f"⚠️ 响应解析失败: {response_text[:200]}...")
                        return {'success': False, 'url': None, 'error': 'Response parse error'}
                else:
                    error_text = await response.text()
                    print(f'❌ 绑卡页面请求失败: {response.status}')
                    print(f'📄 错误响应: {error_text[:200]}...')
                    return {
                        'success': False,
                        'url': None,
                        'error': f'HTTP {response.status}: {error_text[:100]}'
                    }
    except Exception as error:
        print(f'❌ 绑卡请求异常: {str(error)}')
        return {'success': False, 'url': None, 'error': str(error)}


# ============================================
# 测试代码
# ============================================

if __name__ == '__main__':
    # 测试Luhn算法
    print('\n=== 测试Luhn算法 ===')
    test_card = '424242424242424'
    check_digit = calculate_luhn_check_digit(test_card)
    print(f'卡号: {test_card}')
    print(f'校验位: {check_digit}')
    full_card = test_card + check_digit
    print(f'完整卡号: {full_card}')
    print(f'Luhn验证: {is_valid_luhn(full_card)}')
    
    # 测试BIN验证
    print('\n=== 测试BIN验证 ===')
    test_bins = ['424242', '552233', '378282', '622126']
    for bin_test in test_bins:
        result = validate_bin(bin_test)
        print(f'\nBIN: {bin_test}')
        print(f'验证结果: {result}')
    
    # 测试卡号生成
    print('\n=== 测试卡号生成 ===')
    try:
        card_info = generate_card_info('424242')
        print(f'\n生成的卡号信息:')
        print(f'卡号: {card_info["cardNumber"]}')
        print(f'有效期: {card_info["expiryDate"]}')
        print(f'CVV: {card_info["cvc"]}')
        print(f'品牌: {card_info["cardBrand"]}')
    except Exception as e:
        print(f'生成失败: {str(e)}')
    
    # 测试异步函数
    print('\n=== 测试异步函数 ===')
    async def test_async():
        print('测试延迟函数...')
        start = time.time()
        await sleep(1000)  # 1秒
        print(f'sleep(1000) 耗时: {time.time() - start:.2f}秒')
        
        start = time.time()
        await robust_sleep(1000)  # 1秒
        print(f'robust_sleep(1000) 耗时: {time.time() - start:.2f}秒')
    
    asyncio.run(test_async())
