import requests
import json

BASE_URL = "http://localhost:8002"
USER_ID = "test"

def debug_image_data():
    """调试图片数据问题"""
    print("=== 调试图片数据问题 ===")
    
    # 1. 创建一个带图片的任务
    print("1. 创建带图片的任务...")
    create_url = f"{BASE_URL}/api/reminder"
    test_image_base64 = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg=="
    image_data_url = f"data:image/png;base64,{test_image_base64}"
    
    create_data = {
        "user_id": USER_ID,
        "homework": {
            "course": "调试课程",
            "content": "调试内容",
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
        print(f"创建任务成功，ID: {reminder_id}")
        
        # 2. 直接查询数据库（通过API）
        print("\n2. 获取任务详情...")
        get_url = f"{BASE_URL}/api/reminders?user_id={USER_ID}"
        
        response = requests.get(get_url)
        if response.status_code != 200:
            print(f"获取任务失败: {response.status_code} - {response.text}")
            return
        
        tasks = response.json().get("data", [])
        task = next((t for t in tasks if t["id"] == reminder_id), None)
        
        if task:
            print(f"任务详情:")
            print(f"  - ID: {task.get('id')}")
            print(f"  - 课程: {task.get('course')}")
            print(f"  - 图片URL: {task.get('image_url')}")
            
            # 检查图片URL格式
            image_url = task.get('image_url')
            if image_url:
                print(f"  - 图片URL格式分析:")
                print(f"    * 是否包含时间戳参数: {'?t=' in image_url}")
                print(f"    * URL: {image_url}")
                
                # 检查是否是API URL
                if image_url.startswith(f"{BASE_URL}/api/images/"):
                    print(f"    * 是API URL")
                    
                    # 检查是否有查询参数
                    if '?' in image_url:
                        print(f"    * 有查询参数")
                        # 提取查询参数
                        import urllib.parse
                        parsed_url = urllib.parse.urlparse(image_url)
                        print(f"    * 查询参数: {parsed_url.query}")
                    else:
                        print(f"    * 没有查询参数")
                else:
                    print(f"    * 不是API URL")
            else:
                print(f"  - 图片URL为空")
        
        # 3. 直接访问图片API
        print("\n3. 直接访问图片API...")
        direct_image_url = f"{BASE_URL}/api/images/{reminder_id}"
        print(f"  - 直接URL: {direct_image_url}")
        
        try:
            direct_response = requests.get(direct_image_url)
            if direct_response.status_code == 200:
                print(f"  - 直接访问成功")
                print(f"  - 图片大小: {len(direct_response.content)} bytes")
                print(f"  - 内容类型: {direct_response.headers.get('content-type')}")
            elif direct_response.status_code == 404:
                print(f"  - 直接访问失败: 404 - 图片不存在")
            else:
                print(f"  - 直接访问失败: {direct_response.status_code}")
                print(f"  - 响应: {direct_response.text[:200]}")
        except Exception as e:
            print(f"  - 直接访问异常: {e}")
        
        # 4. 检查数据库中的image_data字段（通过直接SQL查询）
        print("\n4. 检查数据库状态...")
        # 注意：这里我们无法直接访问数据库，但可以通过API间接检查
        
        # 5. 清理测试任务
        print("\n5. 清理测试任务...")
        delete_url = f"{BASE_URL}/api/reminders/{reminder_id}"
        response = requests.delete(delete_url)
        if response.status_code == 200:
            print("测试任务已删除")
        else:
            print(f"删除任务失败: {response.status_code}")
            
    except Exception as e:
        print(f"调试过程中出现异常: {e}")
        import traceback
        traceback.print_exc()

def check_existing_tasks():
    """检查现有任务的图片URL"""
    print("\n\n=== 检查现有任务的图片URL ===")
    
    get_url = f"{BASE_URL}/api/reminders?user_id={USER_ID}"
    
    try:
        response = requests.get(get_url)
        if response.status_code != 200:
            print(f"获取任务失败: {response.status_code} - {response.text}")
            return
        
        tasks = response.json().get("data", [])
        print(f"用户 {USER_ID} 共有 {len(tasks)} 个任务")
        
        for i, task in enumerate(tasks):
            print(f"\n任务 {i+1}:")
            print(f"  - ID: {task.get('id')}")
            print(f"  - 课程: {task.get('course')}")
            print(f"  - 图片URL: {task.get('image_url')}")
            
            image_url = task.get('image_url')
            if image_url:
                if '?t=' in image_url:
                    print(f"  - ✅ 包含时间戳参数")
                else:
                    print(f"  - ❌ 不包含时间戳参数")
            else:
                print(f"  - 没有图片URL")
                
    except Exception as e:
        print(f"检查现有任务失败: {e}")

if __name__ == "__main__":
    debug_image_data()
    check_existing_tasks()
