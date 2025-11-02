#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
邮箱工具类
提供邮箱相关的实用工具方法

功能：
    - 保存邮箱后缀到JSON文件（自动去重）
    - 获取所有已保存的邮箱后缀
    - 统计邮箱后缀数量
    - 生成随机邮箱地址（单个或批量）
    - 未来可扩展更多邮箱相关功能

作者: AI Assistant
版本: 1.1
"""

import json
import os
import random
import string


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
        >>>
        >>> # 生成随机邮箱
        >>> email = EmailUtils.generate_random_email()
        >>> print(email)
        'k7m2n9p4@example.com'
        >>>
        >>> # 批量生成随机邮箱
        >>> emails = EmailUtils.generate_random_emails(count=5)
        >>> print(emails)
        ['a1b2c3d4@example.com', 'x9y8z7w6@gmail.com', ...]
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
            print(f"   ℹ️  后缀：{suffix}已存在，跳过添加")
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

    @staticmethod
    def generate_random_email(filename='email_suffixes.json', username_length=8, use_numbers=True, use_dots=False):
        """生成随机邮箱地址

        从JSON文件中随机选择一个邮箱后缀，并生成随机用户名

        Args:
            filename (str): JSON文件名，默认为 'email_suffixes.json'
            username_length (int): 用户名长度，默认为8
            use_numbers (bool): 是否在用户名中包含数字，默认为True
            use_dots (bool): 是否在用户名中随机添加点号，默认为False

        Returns:
            str: 随机生成的邮箱地址，如 "abc12def@example.com"
                 如果没有可用的后缀，返回None

        Example:
            >>> email = EmailUtils.generate_random_email()
            >>> print(email)
            'k7m2n9p4@milnerinstitute.org'

            >>> email = EmailUtils.generate_random_email(username_length=10, use_numbers=False)
            >>> print(email)
            'abcdefghij@zumuntahassociationuk.org'

            >>> email = EmailUtils.generate_random_email(use_dots=True)
            >>> print(email)
            'abc.def.123@lbatrust.co.uk'
        """
        # 1. 获取所有后缀
        suffixes = EmailUtils.get_all_suffixes(filename)

        if not suffixes:
            print(f"   ✗ 没有可用的邮箱后缀，请先添加后缀")
            return None

        # 2. 随机选择一个后缀
        suffix = random.choice(suffixes)

        # 3. 生成随机用户名
        username = EmailUtils._generate_username(username_length, use_numbers, use_dots)

        # 4. 组合成完整邮箱
        email = username + suffix

        return email

    @staticmethod
    def generate_random_emails(count=1, filename='email_suffixes.json', username_length=8, use_numbers=True, use_dots=False):
        """批量生成随机邮箱地址

        Args:
            count (int): 要生成的邮箱数量，默认为1
            filename (str): JSON文件名，默认为 'email_suffixes.json'
            username_length (int): 用户名长度，默认为8
            use_numbers (bool): 是否在用户名中包含数字，默认为True
            use_dots (bool): 是否在用户名中随机添加点号，默认为False

        Returns:
            list: 随机生成的邮箱地址列表

        Example:
            >>> emails = EmailUtils.generate_random_emails(count=5)
            >>> for email in emails:
            ...     print(email)
            'a1b2c3d4@milnerinstitute.org'
            'x9y8z7w6@zumuntahassociationuk.org'
            ...
        """
        emails = []
        for _ in range(count):
            email = EmailUtils.generate_random_email(filename, username_length, use_numbers, use_dots)
            if email:
                emails.append(email)

        return emails
    
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

    @staticmethod
    def _generate_username(length=8, use_numbers=True, use_dots=False):
        """生成随机用户名

        Args:
            length (int): 用户名长度
            use_numbers (bool): 是否包含数字
            use_dots (bool): 是否随机添加点号

        Returns:
            str: 随机生成的用户名
        """
        # 定义字符集
        chars = string.ascii_lowercase
        if use_numbers:
            chars += string.digits

        # 生成随机字符
        username = ''.join(random.choice(chars) for _ in range(length))

        # 如果需要添加点号
        if use_dots and length > 3:
            # 在随机位置插入1-2个点号
            num_dots = random.randint(1, 2)
            username_list = list(username)

            for _ in range(num_dots):
                # 避免在开头、结尾或连续位置插入点号
                valid_positions = [i for i in range(1, len(username_list) - 1)
                                   if username_list[i-1] != '.' and username_list[i+1] != '.']
                if valid_positions:
                    pos = random.choice(valid_positions)
                    username_list.insert(pos, '.')

            username = ''.join(username_list)

        return username


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

