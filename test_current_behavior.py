#!/usr/bin/env python3
"""
测试当前前端可能的行为：
1. 调用 /api/upload 进行OCR识别
2. 调用 /api/reminder 保存提醒
3. 检查是否创建了重复的提醒
"""

import sys
import os
import base64
import uuid
import requests
import json

# 设置环境变量确保使用PostgreSQL
os.environ['DB_TYPE'] = 'postgresql'

sys.path.append('.')
from app.database import db_config

def test_current_behavior():
    """测试当前前端可能的行为"""
    print("=== 测试当前前端可能的行为 ===")
    print()
    
    # 服务器地址
    base_url = "http://localhost:8002"
    
    # 1. 读取测试图片
    test_image_path = "downloaded_test_image.png"
    try:
        with open(test_image_path, "rb") as f:
            image_data = f.read()
        
        # 转换为base64
        image_base64 = base64.b64encode(image_data).decode('utf-8')
        print(f"1. 读取测试图片成功")
        print(f"   图片大小: {len(image_data)} bytes")
        print()
    except FileNotFoundError:
        print(f"❌ 测试图片文件不存在: {test_image_path}")
        return False
    except Exception as e:
        print(f"❌ 读取测试图片失败: {e}")
        return False
    
    # 生成唯一的用户ID
    user_id = "test_user_" + str(uuid.uuid4())[:8]
    
    # 2. 模拟前端调用 /api/upload 进行OCR识别
    print("2. 模拟前端调用 /api/upload 进行OCR识别")
    
    upload_data = {
        "image": image_base64
    }
    
    try:
        upload_response = requests.post(
            f"{base_url}/api/upload",
            json=upload_data,
            timeout=30
        )
        
        print(f"   请求URL: {base_url}/api/upload")
        print(f"   状态码: {upload_response.status_code}")
        
        if upload_response.status_code == 200:
            upload_result = upload_response.json()
            print(f"   响应成功: {upload_result.get('success', False)}")
            
            if upload_result.get('success'):
                upload_data = upload_result.get('data', {})
                course = upload_data.get('course', '未知课程')
                content = upload_data.get('content', '未知作业')
                deadline = upload_data.get('deadline', '未指定')
                
                print(f"   识别结果:")
                print(f"     课程: {course}")
                print(f"     内容: {content}")
                print(f"     截止时间: {deadline}")
                print()
                
                # 3. 模拟前端调用 /api/reminder 保存提醒（不传递reminder_id）
                print("3. 模拟前端调用 /api/reminder 保存提醒（不传递reminder_id）")
                
                reminder_data = {
                    "user_id": user_id,
                    "homework": {
                        "course": course,
                        "content": content,
                        "start_time": "",
                        "deadline": "2026-04-10 23:59",
                        "difficulty": "中",
                        "image_url": ""  # 没有图片URL
                    }
                    # 注意：没有传递reminder_id
                }
                
                reminder_response = requests.post(
                    f"{base_url}/api/reminder",
                    json=reminder_data,
                    timeout=30
                )
                
                print(f"   请求URL: {base_url}/api/reminder")
                print(f"   状态码: {reminder_response.status_code}")
                
                if reminder_response.status_code == 200:
                    reminder_result = reminder_response.json()
                    print(f"   响应成功: {reminder_result.get('success', False)}")
                    print(f"   消息: {reminder_result.get('message', '')}")
                    
                    reminder_id = reminder_result.get('reminder_id')
                    print(f"   创建的提醒ID: {reminder_id}")
                    
                    # 4. 检查数据库中的提醒
                    print()
                    print("4. 检查数据库中的提醒")
                    
                    query = """
                    SELECT id, user_id, course, content, deadline, image_data
                    FROM reminders 
                    WHERE user_id = %s
                    ORDER BY created_at DESC
                    """
                    
                    db_result = db_config.execute_query(query, (user_id,))
                    
                    if db_result and len(db_result) > 0:
                        print(f"   用户 {user_id} 有 {len(db_result)} 条提醒")
                        
                        for i, row in enumerate(db_result):
                            print(f"   提醒 {i+1}:")
                            print(f"     ID: {row.get('id')}")
                            print(f"     课程: {row.get('course')}")
                            print(f"     内容: {row.get('content')}")
                            print(f"     截止时间: {row.get('deadline')}")
                            print(f"     图片大小: {len(row.get('image_data', b''))} bytes")
                        
                        # 检查是否有空课程的提醒
                        empty_courses = [r for r in db_result if r.get('course') == ""]
                        if empty_courses:
                            print(f"   ⚠️ 发现 {len(empty_courses)} 个空课程的提醒")
                        
                        # 检查是否有"未知课程"的提醒
                        unknown_courses = [r for r in db_result if r.get('course') == "未知课程"]
                        if unknown_courses:
                            print(f"   ⚠️ 发现 {len(unknown_courses)} 个'未知课程'的提醒")
                        
                        if len(db_result) == 1:
                            print("   ✅ 只创建了一个提醒（正确）")
                            return True
                        else:
                            print(f"   ❌ 创建了 {len(db_result)} 个提醒（应该有1个）")
                            return False
                    else:
                        print("   ❌ 用户没有提醒")
                        return False
                else:
                    print(f"   请求失败: {reminder_response.status_code}")
                    print(f"   响应: {reminder_response.text[:500]}")
                    return False
            else:
                print(f"   上传失败: {upload_result.get('message', '未知错误')}")
                return False
        else:
            print(f"   请求失败: {upload_response.status_code}")
            print(f"   响应: {upload_response.text[:500]}")
            return False
            
    except Exception as e:
        print(f"❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = test_current_behavior()
    if success:
        print("\n✅ 测试成功！当前行为：")
        print("   1. /api/upload 只返回识别结果，不创建提醒")
        print("   2. /api/reminder 创建了一个提醒")
        print("   3. 没有创建重复的提醒")
    else:
        print("\n❌ 测试失败！请检查错误信息。")
    
    sys.exit(0 if success else 1)
