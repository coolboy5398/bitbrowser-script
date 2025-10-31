#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
邮箱工具类
提供邮箱相关的实用工具方法

功能：
    - 保存邮箱后缀到JSON文件（自动去重）
    - 获取所有已保存的邮箱后缀
    - 统计邮箱后缀数量
    - 未来可扩展更多邮箱相关功能

作者: AI Assistant
版本: 1.0
"""

import json
import os


class EmailUtils:
    """邮箱相关工具类
    
    提供静态方法处理邮箱相关操作，无需实例化即可使用
    
    示例:
        >>> from email_utils import EmailUtils
        >>> 
        >>> # 保存邮箱后缀
        >>> EmailUtils.save_suffix("test@example.com")
        >>> 
        >>> # 获取所有后缀
        >>> suffixes = EmailUtils.get_all_suffixes()
        >>> print(suffixes)
        ['@example.com', '@gmail.com']
        >>> 
        >>> # 获取后缀数量
        >>> count = EmailUtils.get_suffix_count()
        >>> print(f"共有 {count} 个不同的后缀")
    """
    
    @staticmethod
    def save_suffix(email, filename='email_suffixes.json'):
        """保存邮箱后缀到JSON文件（自动去重）
        
        Args:
            email (str): 邮箱地址，如 "test@example.com"
            filename (str): JSON文件名，默认为 'email_suffixes.json'
        
        Returns:
            bool: 成功返回True，失败返回False
        
        Example:
            >>> EmailUtils.save_suffix("user@gmail.com")
            True
        """
        print(f"\n📝 正在保存邮箱后缀...")
        
        # 1. 提取邮箱后缀
        suffix = EmailUtils._extract_suffix(email)
        if not suffix:
            print(f"   ✗ 邮箱格式错误: {email}")
            return False
        
        print(f"   📧 邮箱后缀: {suffix}")
        
        # 2. 加载现有数据
        data = EmailUtils._load_data(filename)
        
        # 3. 去重添加
        if suffix in data["suffixes"]:
            print(f"   ℹ️  后缀已存在，跳过添加")
            return True
        else:
            data["suffixes"].append(suffix)
            print(f"   ✓ 新后缀已添加")
        
        # 4. 保存到文件
        if EmailUtils._save_data(filename, data):
            print(f"   ✓ 后缀已保存到: {filename}")
            print(f"   📊 当前共有 {len(data['suffixes'])} 个不同的后缀")
            return True
        else:
            return False
    
    @staticmethod
    def get_all_suffixes(filename='email_suffixes.json'):
        """获取所有已保存的邮箱后缀
        
        Args:
            filename (str): JSON文件名，默认为 'email_suffixes.json'
        
        Returns:
            list: 邮箱后缀列表，如 ['@example.com', '@gmail.com']
                  如果文件不存在或为空，返回空列表
        
        Example:
            >>> suffixes = EmailUtils.get_all_suffixes()
            >>> print(suffixes)
            ['@example.com', '@gmail.com']
        """
        data = EmailUtils._load_data(filename)
        return data.get("suffixes", [])
    
    @staticmethod
    def get_suffix_count(filename='email_suffixes.json'):
        """获取邮箱后缀总数
        
        Args:
            filename (str): JSON文件名，默认为 'email_suffixes.json'
        
        Returns:
            int: 后缀总数
        
        Example:
            >>> count = EmailUtils.get_suffix_count()
            >>> print(f"共有 {count} 个不同的后缀")
        """
        suffixes = EmailUtils.get_all_suffixes(filename)
        return len(suffixes)
    
    # ==================== 私有辅助方法 ====================
    
    @staticmethod
    def _extract_suffix(email):
        """从邮箱地址中提取后缀
        
        Args:
            email (str): 邮箱地址
        
        Returns:
            str: 邮箱后缀（包含@），如 "@example.com"
                 如果格式错误返回None
        """
        if not email or '@' not in email:
            return None
        
        parts = email.split('@')
        if len(parts) != 2 or not parts[1]:
            return None
        
        return '@' + parts[1]
    
    @staticmethod
    def _load_data(filename):
        """从JSON文件加载数据
        
        Args:
            filename (str): JSON文件名
        
        Returns:
            dict: 包含suffixes列表的字典
        """
        try:
            if os.path.exists(filename):
                with open(filename, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    # 确保数据结构正确
                    if 'suffixes' not in data:
                        data = {"suffixes": []}
                    return data
            else:
                # 文件不存在，返回空数据
                return {"suffixes": []}
        except json.JSONDecodeError:
            # JSON格式错误，返回空数据
            print(f"   ⚠️  JSON格式错误，将重建文件")
            return {"suffixes": []}
        except Exception as e:
            print(f"   ✗ 读取文件失败: {e}")
            return {"suffixes": []}
    
    @staticmethod
    def _save_data(filename, data):
        """保存数据到JSON文件
        
        Args:
            filename (str): JSON文件名
            data (dict): 要保存的数据
        
        Returns:
            bool: 成功返回True，失败返回False
        """
        try:
            with open(filename, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            return True
        except Exception as e:
            print(f"   ✗ 保存失败: {e}")
            return False


# ==================== 未来可扩展的方法 ====================
# 
# 以下是一些可能的扩展方向，供参考：
#
# @staticmethod
# def validate_email(email):
#     """验证邮箱格式是否正确"""
#     pass
#
# @staticmethod
# def extract_domain(email):
#     """提取邮箱的域名部分（不含@）"""
#     pass
#
# @staticmethod
# def generate_random_email(suffix):
#     """生成指定后缀的随机邮箱地址"""
#     pass
#
# @staticmethod
# def is_temporary_email(email):
#     """判断是否为临时邮箱"""
#     pass

