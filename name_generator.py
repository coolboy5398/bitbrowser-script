#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
随机姓名生成器
生成随机的英文姓名用于注册

作者: AI Assistant
版本: 1.0
"""

import random


class NameGenerator:
    """随机姓名生成器"""

    # 常见英文名字（First Names）
    FIRST_NAMES = [
        # 男性名字
        "James", "John", "Robert", "Michael", "William",
        "David", "Richard", "Joseph", "Thomas", "Charles",
        "Christopher", "Daniel", "Matthew", "Anthony", "Mark",
        "Donald", "Steven", "Paul", "Andrew", "Joshua",
        "Kenneth", "Kevin", "Brian", "George", "Edward",
        "Ryan", "Nicholas", "Eric", "Jacob", "Jonathan",
        "Justin", "Tyler", "Aaron", "Adam", "Alexander",
        
        # 女性名字
        "Mary", "Patricia", "Jennifer", "Linda", "Elizabeth",
        "Barbara", "Susan", "Jessica", "Sarah", "Karen",
        "Nancy", "Lisa", "Betty", "Margaret", "Sandra",
        "Ashley", "Dorothy", "Kimberly", "Emily", "Donna",
        "Michelle", "Carol", "Amanda", "Melissa", "Deborah",
        "Stephanie", "Rebecca", "Laura", "Sharon", "Cynthia",
        "Kathleen", "Amy", "Shirley", "Angela", "Helen",
        
        # 中性名字
        "Alex", "Jordan", "Taylor", "Morgan", "Casey",
        "Riley", "Avery", "Quinn", "Skylar", "Cameron"
    ]

    # 常见英文姓氏（Last Names）
    LAST_NAMES = [
        "Smith", "Johnson", "Williams", "Brown", "Jones",
        "Garcia", "Miller", "Davis", "Rodriguez", "Martinez",
        "Hernandez", "Lopez", "Gonzalez", "Wilson", "Anderson",
        "Thomas", "Taylor", "Moore", "Jackson", "Martin",
        "Lee", "Perez", "Thompson", "White", "Harris",
        "Sanchez", "Clark", "Ramirez", "Lewis", "Robinson",
        "Walker", "Young", "Allen", "King", "Wright",
        "Scott", "Torres", "Nguyen", "Hill", "Flores",
        "Green", "Adams", "Nelson", "Baker", "Hall",
        "Rivera", "Campbell", "Mitchell", "Carter", "Roberts",
        "Gomez", "Phillips", "Evans", "Turner", "Diaz",
        "Parker", "Cruz", "Edwards", "Collins", "Reyes",
        "Stewart", "Morris", "Morales", "Murphy", "Cook",
        "Rogers", "Gutierrez", "Ortiz", "Morgan", "Cooper",
        "Peterson", "Bailey", "Reed", "Kelly", "Howard",
        "Ramos", "Kim", "Cox", "Ward", "Richardson",
        "Watson", "Brooks", "Chavez", "Wood", "James"
    ]

    @classmethod
    def generate_first_name(cls):
        """生成随机名字

        Returns:
            str: 随机名字
        """
        return random.choice(cls.FIRST_NAMES)

    @classmethod
    def generate_last_name(cls):
        """生成随机姓氏

        Returns:
            str: 随机姓氏
        """
        return random.choice(cls.LAST_NAMES)

    @classmethod
    def generate_full_name(cls):
        """生成完整的随机姓名

        Returns:
            tuple: (first_name, last_name)
        """
        return cls.generate_first_name(), cls.generate_last_name()

    @classmethod
    def generate_username(cls, separator="_"):
        """生成用户名格式的姓名（小写，用分隔符连接）

        Args:
            separator (str): 分隔符，默认为下划线

        Returns:
            str: 用户名格式的姓名，如 "john_smith"
        """
        first_name, last_name = cls.generate_full_name()
        return f"{first_name.lower()}{separator}{last_name.lower()}"

    @classmethod
    def generate_display_name(cls):
        """生成显示名称格式的姓名（首字母大写，空格分隔）

        Returns:
            str: 显示名称，如 "John Smith"
        """
        first_name, last_name = cls.generate_full_name()
        return f"{first_name} {last_name}"


# 便捷函数
def generate_name():
    """生成随机姓名（便捷函数）

    Returns:
        tuple: (first_name, last_name)
    """
    return NameGenerator.generate_full_name()


def generate_username(separator="_"):
    """生成用户名（便捷函数）

    Args:
        separator (str): 分隔符

    Returns:
        str: 用户名
    """
    return NameGenerator.generate_username(separator)


def generate_display_name():
    """生成显示名称（便捷函数）

    Returns:
        str: 显示名称
    """
    return NameGenerator.generate_display_name()


# 测试代码
if __name__ == "__main__":
    print("=" * 50)
    print("随机姓名生成器测试")
    print("=" * 50)

    # 生成10个随机姓名
    print("\n📝 生成10个随机姓名：")
    for i in range(10):
        first_name, last_name = NameGenerator.generate_full_name()
        print(f"   {i+1}. {first_name} {last_name}")

    # 生成5个用户名
    print("\n👤 生成5个用户名格式：")
    for i in range(5):
        username = NameGenerator.generate_username()
        print(f"   {i+1}. {username}")

    # 生成5个显示名称
    print("\n✨ 生成5个显示名称格式：")
    for i in range(5):
        display_name = NameGenerator.generate_display_name()
        print(f"   {i+1}. {display_name}")

    print("\n" + "=" * 50)
