#!/usr/bin/env python3
"""
检查test用户的提醒
"""

import sys
import os

# 设置环境变量确保使用PostgreSQL
os.environ['DB_TYPE'] = 'postgresql'

sys.path.append('.')

from app.database import db_config

def check_test_user_reminders():
    """检查test用户的提醒"""
    print("=== 检查test用户的提醒 ===")
    
    query = """
    SELECT id, user_id, course, content, deadline, created_at, image_data
    FROM reminders 
    WHERE user_id = 'test'
    ORDER BY created_at DESC
    LIMIT 10
    """
    
    result = db_config.execute_query(query)
    
    print(f"找到 {len(result)} 条提醒:")
    print()
    
    for i, row in enumerate(result):
        print(f"{i+1}. ID: {row.get('id')}")
        print(f"   课程: {row.get('course')}")
        print(f"   内容: {row.get('content')}")
        print(f"   截止时间: {row.get('deadline')}")
        image_data = row.get('image_data')
        if image_data:
            print(f"   图片大小: {len(image_data)} bytes")
        else:
            print(f"   图片大小: 0 bytes (无图片)")
        print(f"   创建时间: {row.get('created_at')}")
        print()
    
    # 统计不同类型的提醒
    empty_courses = [r for r in result if r.get('course') == ""]
    unknown_courses = [r for r in result if r.get('course') == "未知课程"]
    pending_courses = [r for r in result if r.get('course') == "待填写课程"]
    
    print("=== 统计 ===")
    print(f"空课程提醒: {len(empty_courses)} 个")
    print(f"'未知课程'提醒: {len(unknown_courses)} 个")
    print(f"'待填写课程'提醒: {len(pending_courses)} 个")
    print(f"其他课程提醒: {len(result) - len(empty_courses) - len(unknown_courses) - len(pending_courses)} 个")
    
    return True

if __name__ == "__main__":
    check_test_user_reminders()
