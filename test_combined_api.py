#!/usr/bin/env python3
"""
测试合并的API功能：
1. 调用 /api/reminder 同时上传图片和保存提醒
2. 验证只创建一个提醒
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

def test_combined_api():
    """测试合并的API功能"""
    print("=== 测试合并的API功能（同时上传图片和保存提醒） ===")
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
    
    # 2. 调用合并的API：同时上传图片和保存提醒
    print("2. 调用合并的API：同时上传图片和保存提醒")
    
    request_data = {
        "user_id": user_id,
        "homework": {
            "course": "测试课程",
            "content": "测试作业内容",
            "start_time": "",
            "deadline": "2026-04-10 23:59",
            "difficulty": "中",
            "image_url": ""  # 图片将通过image字段上传
        },
        "image": f"data:image/png;base64,{image_base64}"  # 包含图片数据
        # 注意：没有传递reminder_id，所以应该创建新提醒
    }
    
    try:
        response = requests.post(
            f"{base_url}/api/reminder",
            json=request_data,
            timeout=30
        )
        
        print(f"   请求URL: {base_url}/api/reminder")
        print(f"   用户ID: {user_id}")
        print(f"   状态码: {response.status_code}")
        
        if response.status_code == 200:
            result = response.json()
            print(f"   响应成功: {result.get('success', False)}")
            print(f"   消息: {result.get('message', '')}")
            
            reminder_id = result.get('reminder_id')
            print(f"   创建的提醒ID: {reminder_id}")
            print()
            
            # 3. 验证数据库中的提醒
            print("3. 验证数据库中的提醒")
            
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
                    image_data = row.get('image_data')
                    if image_data:
                        print(f"     图片大小: {len(image_data)} bytes")
                    else:
                        print(f"     图片大小: 0 bytes (无图片)")
                
                # 检查是否有空课程的提醒
                empty_courses = [r for r in db_result if r.get('course') == ""]
                if empty_courses:
                    print(f"   ⚠️ 发现 {len(empty_courses)} 个空课程的提醒")
                
                # 检查是否有"未知课程"的提醒
                unknown_courses = [r for r in db_result if r.get('course') == "未知课程"]
                if unknown_courses:
                    print(f"   ⚠️ 发现 {len(unknown_courses)} 个'未知课程'的提醒")
                
                # 检查是否有"待填写课程"的提醒
                pending_courses = [r for r in db_result if r.get('course') == "待填写课程"]
                if pending_courses:
                    print(f"   ⚠️ 发现 {len(pending_courses)} 个'待填写课程'的提醒")
                
                if len(db_result) == 1:
                    print("   ✅ 只创建了一个提醒（正确）")
                    
                    # 验证提醒内容
                    reminder = db_result[0]
                    if reminder.get('course') == "测试课程":
                        print("   ✅ 提醒课程正确: '测试课程'")
                    else:
                        print(f"   ❌ 提醒课程不正确: {reminder.get('course')}")
                        return False
                    
                    if reminder.get('image_data'):
                        print(f"   ✅ 提醒包含图片数据: {len(reminder.get('image_data'))} bytes")
                    else:
                        print("   ❌ 提醒没有图片数据")
                        return False
                    
                    return True
                else:
                    print(f"   ❌ 创建了 {len(db_result)} 个提醒（应该有1个）")
                    return False
            else:
                print("   ❌ 用户没有提醒")
                return False
        else:
            print(f"   请求失败: {response.status_code}")
            print(f"   响应: {response.text[:500]}")
            return False
            
    except Exception as e:
        print(f"❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_update_with_reminder_id():
    """测试使用reminder_id更新提醒"""
    print()
    print("=== 测试使用reminder_id更新提醒 ===")
    print()
    
    # 服务器地址
    base_url = "http://localhost:8002"
    
    # 1. 先创建一个提醒（包含图片）
    user_id = "test_user_" + str(uuid.uuid4())[:8]
    
    # 读取测试图片
    test_image_path = "downloaded_test_image.png"
    try:
        with open(test_image_path, "rb") as f:
            image_data = f.read()
        image_base64 = base64.b64encode(image_data).decode('utf-8')
    except Exception as e:
        print(f"❌ 读取测试图片失败: {e}")
        return False
    
    # 创建提醒
    create_data = {
        "user_id": user_id,
        "homework": {
            "course": "初始课程",
            "content": "初始内容",
            "start_time": "",
            "deadline": "2026-04-05 23:59",
            "difficulty": "低",
            "image_url": ""
        },
        "image": f"data:image/png;base64,{image_base64}"
    }
    
    try:
        create_response = requests.post(
            f"{base_url}/api/reminder",
            json=create_data,
            timeout=30
        )
        
        if create_response.status_code != 200:
            print(f"❌ 创建提醒失败: {create_response.status_code}")
            return False
        
        create_result = create_response.json()
        reminder_id = create_result.get('reminder_id')
        print(f"1. 创建提醒成功: {reminder_id}")
        
        # 2. 使用reminder_id更新提醒（不包含图片）
        update_data = {
            "user_id": user_id,
            "homework": {
                "course": "更新后的课程",
                "content": "更新后的内容",
                "start_time": "",
                "deadline": "2026-04-15 23:59",
                "difficulty": "高",
                "image_url": ""
            },
            "reminder_id": reminder_id
            # 注意：没有传递image字段，所以图片应该保持不变
        }
        
        update_response = requests.post(
            f"{base_url}/api/reminder",
            json=update_data,
            timeout=30
        )
        
        print(f"2. 更新提醒请求")
        print(f"   状态码: {update_response.status_code}")
        
        if update_response.status_code == 200:
            update_result = update_response.json()
            print(f"   响应成功: {update_result.get('success', False)}")
            print(f"   消息: {update_result.get('message', '')}")
            
            returned_reminder_id = update_result.get('reminder_id')
            if returned_reminder_id == reminder_id:
                print(f"   ✅ 返回的提醒ID与原始ID相同: {reminder_id}")
            else:
                print(f"   ❌ 返回的提醒ID不同: {returned_reminder_id}")
                return False
            
            # 3. 验证更新后的提醒
            query = """
            SELECT id, user_id, course, content, deadline, difficulty, image_data
            FROM reminders 
            WHERE user_id = %s
            ORDER BY created_at DESC
            """
            
            db_result = db_config.execute_query(query, (user_id,))
            
            if db_result and len(db_result) == 1:
                reminder = db_result[0]
                print(f"3. 验证更新后的提醒:")
                print(f"   课程: {reminder.get('course')} (应该是'更新后的课程')")
                print(f"   内容: {reminder.get('content')} (应该是'更新后的内容')")
                print(f"   截止时间: {reminder.get('deadline')} (应该是'2026-04-15 23:59')")
                print(f"   难度: {reminder.get('difficulty')} (应该是'高')")
                print(f"   图片大小: {len(reminder.get('image_data', b''))} bytes (应该保持不变)")
                
                if (reminder.get('course') == "更新后的课程" and 
                    reminder.get('content') == "更新后的内容" and
                    reminder.get('deadline') == "2026-04-15 23:59" and
                    reminder.get('difficulty') == "高" and
                    len(reminder.get('image_data', b'')) > 0):
                    print("   ✅ 提醒更新成功，图片数据保持不变")
                    return True
                else:
                    print("   ❌ 提醒更新失败")
                    return False
            else:
                print(f"   ❌ 用户有 {len(db_result) if db_result else 0} 条提醒（应该有1条）")
                return False
        else:
            print(f"   更新失败: {update_response.status_code}")
            print(f"   响应: {update_response.text[:500]}")
            return False
            
    except Exception as e:
        print(f"❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    print("开始测试合并的API功能...")
    print()
    
    # 测试1：同时上传图片和保存提醒
    success1 = test_combined_api()
    
    if success1:
        print()
        print("✅ 测试1通过：合并的API可以同时上传图片和保存提醒")
        print()
    else:
        print()
        print("❌ 测试1失败")
        sys.exit(1)
    
    # 测试2：使用reminder_id更新提醒
    success2 = test_update_with_reminder_id()
    
    if success2:
        print()
        print("✅ 测试2通过：可以使用reminder_id更新提醒")
        print()
    else:
        print()
        print("❌ 测试2失败")
        sys.exit(1)
    
    print("🎉 所有测试通过！")
    print()
    print("总结：")
    print("1. /api/reminder 现在可以同时处理图片上传和提醒保存")
    print("2. 前端可以：")
    print("   - 调用 /api/reminder 并传递 image 字段来同时上传图片和保存提醒")
    print("   - 或者：先调用 /api/upload-image-only 获取 reminder_id，然后调用 /api/reminder 传递 reminder_id 来更新提醒")
    print("3. 这样避免了创建重复的提醒")
    
    sys.exit(0)
