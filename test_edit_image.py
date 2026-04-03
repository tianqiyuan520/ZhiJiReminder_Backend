import requests
import json
import base64
import os

# 测试配置
BASE_URL = "http://localhost:8002"
USER_ID = "test"

def test_edit_task_with_new_image():
    """测试编辑任务时更新图片"""
    print("=== 测试编辑任务时更新图片 ===")
    
    # 1. 首先创建一个测试任务
    print("1. 创建测试任务...")
    create_url = f"{BASE_URL}/api/reminder"
    create_data = {
        "user_id": USER_ID,
        "homework": {
            "course": "测试课程",
            "content": "测试作业内容",
            "deadline": "2026-12-31 23:59",
            "difficulty": "中"
        }
    }
    
    try:
        response = requests.post(create_url, json=create_data)
        if response.status_code != 200:
            print(f"创建任务失败: {response.status_code} - {response.text}")
            return
        
        create_result = response.json()
        reminder_id = create_result.get("reminder_id")
        print(f"创建任务成功，ID: {reminder_id}")
        
        # 2. 获取任务详情，确认没有图片
        print("\n2. 获取任务详情...")
        get_url = f"{BASE_URL}/api/reminders?user_id={USER_ID}"
        response = requests.get(get_url)
        if response.status_code != 200:
            print(f"获取任务失败: {response.status_code} - {response.text}")
            return
        
        tasks = response.json().get("data", [])
        task = next((t for t in tasks if t["id"] == reminder_id), None)
        if task:
            print(f"任务详情: 图片URL = {task.get('image_url')}")
        
        # 3. 准备测试图片（base64编码）
        print("\n3. 准备测试图片...")
        # 创建一个简单的测试图片（1x1像素的红色PNG）
        test_image_base64 = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg=="
        image_data_url = f"data:image/png;base64,{test_image_base64}"
        
        # 4. 编辑任务，添加图片
        print("\n4. 编辑任务，添加图片...")
        edit_data = {
            "user_id": USER_ID,
            "homework": {
                "course": "更新后的课程",
                "content": "更新后的内容",
                "deadline": "2026-12-31 23:59",
                "difficulty": "难"
            },
            "reminder_id": reminder_id,
            "image": image_data_url
        }
        
        response = requests.post(create_url, json=edit_data)
        if response.status_code != 200:
            print(f"编辑任务失败: {response.status_code} - {response.text}")
            return
        
        print("编辑任务成功")
        
        # 5. 再次获取任务详情，确认图片已更新
        print("\n5. 验证图片是否更新...")
        response = requests.get(get_url)
        if response.status_code != 200:
            print(f"获取任务失败: {response.status_code} - {response.text}")
            return
        
        tasks = response.json().get("data", [])
        task = next((t for t in tasks if t["id"] == reminder_id), None)
        if task:
            print(f"更新后任务详情:")
            print(f"  - 课程: {task.get('course')}")
            print(f"  - 内容: {task.get('content')}")
            print(f"  - 图片URL: {task.get('image_url')}")
            
            # 检查图片API
            if task.get('image_url'):
                image_api_url = task.get('image_url')
                print(f"  - 图片API URL: {image_api_url}")
                
                # 尝试访问图片
                try:
                    image_response = requests.get(image_api_url)
                    if image_response.status_code == 200:
                        print(f"  - 图片访问成功，大小: {len(image_response.content)} bytes")
                        print("✅ 图片更新测试通过")
                    else:
                        print(f"  - 图片访问失败: {image_response.status_code}")
                except Exception as e:
                    print(f"  - 图片访问异常: {e}")
            else:
                print("❌ 图片URL为空，图片可能没有更新")
        
        # 6. 清理：删除测试任务
        print("\n6. 清理测试任务...")
        delete_url = f"{BASE_URL}/api/reminders/{reminder_id}"
        response = requests.delete(delete_url)
        if response.status_code == 200:
            print("测试任务已删除")
        else:
            print(f"删除任务失败: {response.status_code}")
            
    except Exception as e:
        print(f"测试过程中出现异常: {e}")
        import traceback
        traceback.print_exc()

def test_edit_task_without_image():
    """测试编辑任务时不更新图片"""
    print("\n\n=== 测试编辑任务时不更新图片 ===")
    
    # 1. 首先创建一个带图片的测试任务
    print("1. 创建带图片的测试任务...")
    create_url = f"{BASE_URL}/api/reminder"
    test_image_base64 = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg=="
    image_data_url = f"data:image/png;base64,{test_image_base64}"
    
    create_data = {
        "user_id": USER_ID,
        "homework": {
            "course": "带图片的课程",
            "content": "带图片的内容",
            "deadline": "2026-12-31 23:59",
            "difficulty": "中"
        },
        "image": image_data_url
    }
    
    try:
        response = requests.post(create_url, json=create_data)
        if response.status_code != 200:
            print(f"创建任务失败: {response.status_code} - {response.text}")
            return
        
        create_result = response.json()
        reminder_id = create_result.get("reminder_id")
        print(f"创建带图片任务成功，ID: {reminder_id}")
        
        # 2. 编辑任务，不传递图片
        print("\n2. 编辑任务，不传递图片...")
        edit_data = {
            "user_id": USER_ID,
            "homework": {
                "course": "只更新文字",
                "content": "只更新文字内容",
                "deadline": "2026-12-31 23:59",
                "difficulty": "易"
            },
            "reminder_id": reminder_id
            # 注意：不传递image字段
        }
        
        response = requests.post(create_url, json=edit_data)
        if response.status_code != 200:
            print(f"编辑任务失败: {response.status_code} - {response.text}")
            return
        
        print("编辑任务成功")
        
        # 3. 验证图片是否保持不变
        print("\n3. 验证图片是否保持不变...")
        get_url = f"{BASE_URL}/api/reminders?user_id={USER_ID}"
        response = requests.get(get_url)
        if response.status_code != 200:
            print(f"获取任务失败: {response.status_code} - {response.text}")
            return
        
        tasks = response.json().get("data", [])
        task = next((t for t in tasks if t["id"] == reminder_id), None)
        if task:
            print(f"编辑后任务详情:")
            print(f"  - 课程: {task.get('course')} (应该是'只更新文字')")
            print(f"  - 内容: {task.get('content')} (应该是'只更新文字内容')")
            print(f"  - 图片URL: {task.get('image_url')} (应该仍然存在)")
            
            if task.get('image_url'):
                print("✅ 图片保持不变测试通过")
            else:
                print("❌ 图片丢失了！")
        
        # 4. 清理
        print("\n4. 清理测试任务...")
        delete_url = f"{BASE_URL}/api/reminders/{reminder_id}"
        response = requests.delete(delete_url)
        if response.status_code == 200:
            print("测试任务已删除")
        else:
            print(f"删除任务失败: {response.status_code}")
            
    except Exception as e:
        print(f"测试过程中出现异常: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    # 检查服务器是否运行
    try:
        response = requests.get(f"{BASE_URL}/", timeout=5)
        if response.status_code == 200:
            print(f"服务器运行正常: {response.text}")
            test_edit_task_with_new_image()
            test_edit_task_without_image()
        else:
            print(f"服务器响应异常: {response.status_code}")
    except requests.exceptions.ConnectionError:
        print(f"无法连接到服务器 {BASE_URL}，请确保服务器正在运行")
    except Exception as e:
        print(f"检查服务器时出现异常: {e}")
