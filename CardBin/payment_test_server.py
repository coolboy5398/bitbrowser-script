"""
Stripe支付测试服务器

提供后端API用于完整的支付测试流程：
1. 接收Token
2. 创建PaymentIntent
3. 确认支付
"""

from flask import Flask, request, jsonify
from flask_cors import CORS
import stripe
import json
import os

# 加载配置
def load_config():
    try:
        with open('config.json', 'r', encoding='utf-8') as f:
            return json.load(f)
    except:
        return {}

CONFIG = load_config()
stripe.api_key = CONFIG.get('stripe_api_key', 'sk_test_YOUR_KEY_HERE')

app = Flask(__name__)
CORS(app)  # 允许跨域请求


@app.route('/health', methods=['GET'])
def health():
    """健康检查"""
    return jsonify({'status': 'ok', 'message': 'Server is running'})


@app.route('/api/test-payment', methods=['POST'])
def test_payment():
    """
    测试支付接口
    
    接收参数：
    - token: Stripe Token ID
    - amount: 金额（美分）
    - currency: 货币代码
    
    返回：
    - success: 是否成功
    - payment_intent_id: PaymentIntent ID
    - status: 支付状态
    - message: 消息
    """
    try:
        data = request.json
        token = data.get('token')
        amount = data.get('amount', 100)
        currency = data.get('currency', 'usd')
        
        if not token:
            return jsonify({
                'success': False,
                'error': '缺少Token参数'
            }), 400
        
        # 步骤1: 从Token创建PaymentMethod
        print(f'创建PaymentMethod (Token: {token})...')
        payment_method = stripe.PaymentMethod.create(
            type='card',
            card={'token': token}
        )
        pm_id = payment_method.id
        print(f'PaymentMethod创建成功: {pm_id}')
        
        # 步骤2: 创建PaymentIntent
        print(f'创建PaymentIntent (金额: {amount/100:.2f} {currency.upper()})...')
        payment_intent = stripe.PaymentIntent.create(
            amount=amount,
            currency=currency,
            payment_method=pm_id,
            confirm=True,
            return_url='https://example.com/return'
        )
        
        pi_id = payment_intent.id
        status = payment_intent.status
        print(f'PaymentIntent创建成功: {pi_id}, 状态: {status}')
        
        # 判断支付结果
        if status == 'succeeded':
            return jsonify({
                'success': True,
                'payment_intent_id': pi_id,
                'payment_method_id': pm_id,
                'status': status,
                'message': '支付成功',
                'amount': amount,
                'currency': currency,
                'card': {
                    'brand': payment_method.card.brand,
                    'last4': payment_method.card.last4,
                    'exp_month': payment_method.card.exp_month,
                    'exp_year': payment_method.card.exp_year
                }
            })
        elif status == 'requires_action':
            return jsonify({
                'success': False,
                'payment_intent_id': pi_id,
                'status': status,
                'message': '需要额外验证（如3D Secure）',
                'next_action': payment_intent.next_action
            })
        else:
            return jsonify({
                'success': False,
                'payment_intent_id': pi_id,
                'status': status,
                'message': f'支付状态: {status}'
            })
        
    except stripe.error.CardError as e:
        # 卡被拒绝
        return jsonify({
            'success': False,
            'error_type': 'card_error',
            'error_code': e.code,
            'decline_code': e.error.get('decline_code'),
            'message': e.user_message
        }), 400
        
    except stripe.error.InvalidRequestError as e:
        # 无效请求
        return jsonify({
            'success': False,
            'error_type': 'invalid_request',
            'message': str(e)
        }), 400
        
    except Exception as e:
        # 其他错误
        print(f'错误: {str(e)}')
        return jsonify({
            'success': False,
            'error_type': 'server_error',
            'message': str(e)
        }), 500


@app.route('/api/batch-test', methods=['POST'])
def batch_test():
    """
    批量测试接口
    
    接收参数：
    - cards: 卡号信息列表
    
    返回：
    - results: 测试结果列表
    """
    try:
        data = request.json
        cards = data.get('cards', [])
        
        if not cards:
            return jsonify({
                'success': False,
                'error': '缺少卡号列表'
            }), 400
        
        results = []
        
        for card in cards:
            try:
                # 创建Token
                token = stripe.Token.create(
                    card={
                        'number': card['cardNumber'].replace(' ', ''),
                        'exp_month': card['expiryDate'].split('/')[0],
                        'exp_year': '20' + card['expiryDate'].split('/')[1],
                        'cvc': card['cvc']
                    }
                )
                
                # 测试支付
                payment_method = stripe.PaymentMethod.create(
                    type='card',
                    card={'token': token.id}
                )
                
                payment_intent = stripe.PaymentIntent.create(
                    amount=100,
                    currency='usd',
                    payment_method=payment_method.id,
                    confirm=True,
                    return_url='https://example.com/return'
                )
                
                results.append({
                    'card': card,
                    'success': payment_intent.status == 'succeeded',
                    'token_id': token.id,
                    'payment_intent_id': payment_intent.id,
                    'status': payment_intent.status
                })
                
            except Exception as e:
                results.append({
                    'card': card,
                    'success': False,
                    'error': str(e)
                })
        
        return jsonify({
            'success': True,
            'total': len(cards),
            'results': results
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


if __name__ == '__main__':
    # 检查API密钥
    if stripe.api_key == 'sk_test_YOUR_KEY_HERE':
        print('❌ 请在config.json中配置stripe_api_key')
        exit(1)
    
    print('='*60)
    print('🚀 Stripe支付测试服务器')
    print('='*60)
    print(f'Stripe API Key: {stripe.api_key[:20]}...')
    print('服务器地址: http://localhost:5000')
    print('健康检查: http://localhost:5000/health')
    print('测试接口: POST http://localhost:5000/api/test-payment')
    print('='*60)
    print('按 Ctrl+C 停止服务器')
    print('='*60)
    
    app.run(host='0.0.0.0', port=5000, debug=True)
