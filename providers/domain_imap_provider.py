#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
域名邮箱 + IMAP接收服务提供者

通过自定义域名生成邮箱地址,并使用QQ邮箱IMAP接收邮件

作者: AI Assistant
版本: 1.0
"""

import imaplib
import email
import time
import random
import string
import re
from email.header import decode_header
from email.utils import parseaddr

from .email_provider import EmailProvider


class DomainIMAPProvider(EmailProvider):
    """域名邮箱 + IMAP接收服务提供者
    
    功能：
    - 使用自定义域名生成随机邮箱地址
    - 通过IMAP连接QQ邮箱接收转发的邮件
    - 支持HTML和纯文本邮件解析
    """
    
    # 可用域名列表（硬编码）
    AVAILABLE_DOMAINS = [
        "xuanmu000001.xyz"
    ]
    
    def __init__(self, imap_config: dict = None):
        """初始化域名IMAP服务
        
        Args:
            imap_config: IMAP配置字典，包含host, port, user, password
                        如果不提供则使用默认配置
        """
        # 使用提供的配置或默认配置
        if imap_config:
            self.imap_host = imap_config.get('host', 'imap.qq.com')
            self.imap_port = imap_config.get('port', 993)
            self.imap_user = imap_config.get('user', '276326143@qq.com')
            self.imap_password = imap_config.get('password', 'pobdbnrumwetbjgd')
        else:
            # 默认QQ邮箱配置
            self.imap_host = 'imap.qq.com'
            self.imap_port = 993
            self.imap_user = '276326143@qq.com'
            self.imap_password = 'pobdbnrumwetbjgd'
        
        # 缓存生成的邮箱地址
        self.generated_email = None
        
        # IMAP连接对象
        self.imap_connection = None
    
    def needs_browser_page(self) -> bool:
        """不需要打开浏览器页面,直接通过IMAP接收"""
        return False
    
    def get_page_url(self) -> str:
        """获取邮箱页面URL（域名邮箱没有页面）"""
        return ""
    
    def get_domain_patterns(self) -> list:
        """获取域名匹配模式"""
        return self.AVAILABLE_DOMAINS
    
    # ==================== 邮箱地址生成 ====================
    
    def _generate_random_username(self, length: int = 10) -> str:
        """生成随机用户名
        
        Args:
            length: 用户名长度,默认10
            
        Returns:
            str: 随机用户名
        """
        # 使用小写字母和数字
        chars = string.ascii_lowercase + string.digits
        return ''.join(random.choice(chars) for _ in range(length))
    
    def _select_random_domain(self) -> str:
        """随机选择一个可用域名
        
        Returns:
            str: 域名
        """
        return random.choice(self.AVAILABLE_DOMAINS)
    
    def get_email_from_page(self, cdp, session_id) -> str:
        """从网页提取邮箱地址
        
        域名邮箱不支持从网页提取,请使用get_email_from_api
        """
        print("   ⚠️  域名邮箱不支持从网页提取")
        print("   💡 请使用get_email_from_api()方法")
        return None
    
    def get_email_from_api(self) -> str:
        """生成随机邮箱地址
        
        Returns:
            str: 邮箱地址,格式为 random_username@domain.com
        """
        print("   🎲 生成随机邮箱地址...")
        
        try:
            # 生成随机用户名
            username = self._generate_random_username()
            
            # 选择域名
            domain = self._select_random_domain()
            
            # 组合邮箱地址
            email_address = f"{username}@{domain}"
            
            # 缓存生成的邮箱
            self.generated_email = email_address
            
            print(f"   ✓ 生成邮箱: {email_address}")
            return email_address
            
        except Exception as e:
            print(f"   ✗ 生成邮箱失败: {e}")
            return None
    
    # ==================== IMAP连接管理 ====================
    
    def _connect_imap(self) -> imaplib.IMAP4_SSL:
        """连接到IMAP服务器
        
        Returns:
            IMAP4_SSL: IMAP连接对象,失败返回None
        """
        try:
            print(f"   📡 连接IMAP服务器: {self.imap_host}:{self.imap_port}")
            
            # 创建SSL连接
            imap = imaplib.IMAP4_SSL(self.imap_host, self.imap_port)
            
            # 登录
            print(f"   🔐 登录邮箱: {self.imap_user}")
            imap.login(self.imap_user, self.imap_password)
            
            print("   ✓ IMAP连接成功")
            return imap
            
        except imaplib.IMAP4.error as e:
            print(f"   ✗ IMAP连接失败: {e}")
            return None
        except Exception as e:
            print(f"   ✗ 连接出错: {e}")
            return None
    
    def _disconnect_imap(self, imap):
        """断开IMAP连接
        
        Args:
            imap: IMAP连接对象
        """
        try:
            if imap:
                imap.close()
                imap.logout()
                print("   ✓ IMAP连接已关闭")
        except:
            pass
    
    # ==================== 邮件内容获取 ====================
    
    def _decode_email_header(self, header_value) -> str:
        """解码邮件头部
        
        Args:
            header_value: 邮件头部原始值
            
        Returns:
            str: 解码后的字符串
        """
        if not header_value:
            return ""
        
        try:
            decoded_parts = decode_header(header_value)
            result = []
            
            for part, encoding in decoded_parts:
                if isinstance(part, bytes):
                    if encoding:
                        result.append(part.decode(encoding))
                    else:
                        result.append(part.decode('utf-8', errors='ignore'))
                else:
                    result.append(str(part))
            
            return ''.join(result)
        except:
            return str(header_value)
    
    def _extract_email_content(self, msg) -> dict:
        """从邮件对象提取内容
        
        Args:
            msg: email.message.Message对象
            
        Returns:
            dict: {'subject': str, 'content': str, 'html': str, 'from': str}
        """
        # 提取发件人
        from_header = msg.get('From', '')
        from_name, from_addr = parseaddr(from_header)
        from_addr = self._decode_email_header(from_addr)
        
        # 提取主题
        subject = self._decode_email_header(msg.get('Subject', ''))
        
        # 提取正文
        text_content = ""
        html_content = ""
        
        if msg.is_multipart():
            # 多部分邮件
            for part in msg.walk():
                content_type = part.get_content_type()
                content_disposition = str(part.get('Content-Disposition', ''))
                
                # 跳过附件
                if 'attachment' in content_disposition:
                    continue
                
                try:
                    payload = part.get_payload(decode=True)
                    if payload:
                        charset = part.get_content_charset() or 'utf-8'
                        decoded_payload = payload.decode(charset, errors='ignore')
                        
                        if content_type == 'text/plain':
                            text_content += decoded_payload
                        elif content_type == 'text/html':
                            html_content += decoded_payload
                except:
                    continue
        else:
            # 单部分邮件
            try:
                payload = msg.get_payload(decode=True)
                if payload:
                    charset = msg.get_content_charset() or 'utf-8'
                    decoded_payload = payload.decode(charset, errors='ignore')
                    
                    content_type = msg.get_content_type()
                    if content_type == 'text/plain':
                        text_content = decoded_payload
                    elif content_type == 'text/html':
                        html_content = decoded_payload
            except:
                pass
        
        return {
            'from': from_addr,
            'subject': subject,
            'content': text_content,
            'html': html_content
        }
    
    def get_latest_email_from_page(self, cdp, session_id, email: str) -> dict:
        """从网页获取最新邮件内容
        
        域名邮箱不支持从网页获取,请使用get_latest_email_from_api
        """
        print("   ⚠️  域名邮箱不支持从网页获取邮件")
        print("   💡 请使用get_latest_email_from_api()方法")
        return None
    
    def get_latest_email_from_api(self, email: str, timeout: int = 60, check_interval: int = 3) -> dict:
        """通过IMAP获取发送到指定邮箱的最新邮件
        
        Args:
            email: 邮箱地址（用于筛选收件人）
            timeout: 超时时间（秒）,默认60秒
            check_interval: 检查间隔（秒）,默认3秒
            
        Returns:
            dict: 邮件内容字典 {'subject': str, 'content': str, 'html': str, 'from': str}
                  失败返回None
        """
        print(f"   📬 等待邮件发送到: {email}")
        print(f"   ⏳ 超时时间: {timeout}秒, 检查间隔: {check_interval}秒")
        
        imap = None
        start_time = time.time()
        
        try:
            # 连接IMAP
            imap = self._connect_imap()
            if not imap:
                return None
            
            # 选择收件箱
            print("   📂 选择收件箱...")
            imap.select('INBOX')
            
            # 循环检查新邮件
            attempt = 0
            while time.time() - start_time < timeout:
                attempt += 1
                elapsed = time.time() - start_time
                print(f"   🔍 第{attempt}次检查（已等待{elapsed:.1f}秒）...")
                
                # 搜索发送到指定邮箱的邮件
                # 使用TO搜索条件
                search_criteria = f'(TO "{email}")'
                
                try:
                    # 搜索邮件
                    status, message_ids = imap.search(None, search_criteria)
                    
                    if status != 'OK':
                        print(f"   ⚠️  搜索失败: {status}")
                        time.sleep(check_interval)
                        continue
                    
                    # 获取邮件ID列表
                    id_list = message_ids[0].split()
                    
                    if not id_list:
                        print(f"   💤 暂无邮件，继续等待...")
                        time.sleep(check_interval)
                        continue
                    
                    # 获取最新的邮件
                    latest_id = id_list[-1]
                    print(f"   ✓ 找到邮件！邮件ID: {latest_id.decode()}")
                    
                    # 获取邮件内容
                    status, msg_data = imap.fetch(latest_id, '(RFC822)')
                    
                    if status != 'OK':
                        print(f"   ⚠️  获取邮件失败: {status}")
                        time.sleep(check_interval)
                        continue
                    
                    # 解析邮件
                    raw_email = msg_data[0][1]
                    msg = email.message_from_bytes(raw_email)
                    
                    # 提取邮件内容
                    email_content = self._extract_email_content(msg)
                    
                    print(f"   ✓ 邮件解析成功")
                    print(f"   📧 发件人: {email_content['from']}")
                    print(f"   📝 主题: {email_content['subject']}")
                    
                    return email_content
                    
                except imaplib.IMAP4.error as e:
                    print(f"   ⚠️  IMAP操作出错: {e}")
                    time.sleep(check_interval)
                    continue
            
            # 超时
            print(f"   ⏰ 等待邮件超时（{timeout}秒）")
            return None
            
        except Exception as e:
            print(f"   ✗ 获取邮件出错: {e}")
            import traceback
            traceback.print_exc()
            return None
            
        finally:
            # 断开连接
            self._disconnect_imap(imap)
    
    # ==================== 验证码解析（继承自基类） ====================
    # parse_augment_code() 和 parse_windsurf_code() 继承自 EmailProvider


# 便捷函数
def create_domain_imap_provider(imap_config: dict = None) -> DomainIMAPProvider:
    """创建域名IMAP邮箱服务实例（便捷函数）
    
    Args:
        imap_config: IMAP配置字典
        
    Returns:
        DomainIMAPProvider: 邮箱服务实例
    """
    return DomainIMAPProvider(imap_config)


# 测试代码
if __name__ == "__main__":
    print("=" * 60)
    print("域名IMAP邮箱服务测试")
    print("=" * 60)
    
    # 创建服务实例
    provider = DomainIMAPProvider()
    
    # 测试1: 生成邮箱地址
    print("\n📧 测试1: 生成邮箱地址")
    email_addr = provider.get_email_from_api()
    print(f"生成的邮箱: {email_addr}")
    
    # 测试2: 等待邮件（实际使用时需要先发送邮件）
    print("\n📬 测试2: 等待邮件（10秒超时）")
    email_content = provider.get_latest_email_from_api(email_addr, timeout=10)
    if email_content:
        print("收到邮件:")
        print(f"  发件人: {email_content['from']}")
        print(f"  主题: {email_content['subject']}")
        print(f"  内容: {email_content['content'][:100]}...")
    else:
        print("未收到邮件（这是正常的，因为没有实际发送测试邮件）")
    
    print("\n" + "=" * 60)
