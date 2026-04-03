import requests
import json
import time

BASE_URL = "http://localhost:8002"
USER_ID = "test"

def test_cache_busting():
    """测试缓存破坏参数是否生效"""
    print("=== 测试缓存破坏参数 ===")
    
    # 1. 创建一个带图片的任务
    print("1. 创建带图片的任务...")
    create_url = f"{BASE_URL}/api/reminder"
    test_image_base64 = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg=="
    image_data_url = f"data:image/png;base64,{test_image_base64}"
    
    create_data = {
        "user_id": USER_ID,
        "homework": {
            "course": "缓存测试课程",
            "content": "缓存测试内容",
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
        
        # 2. 获取任务详情，检查图片URL
        print("\n2. 获取任务详情，检查图片URL...")
        get_url = f"{BASE_URL}/api/reminders?user_id={USER_ID}"
        
        response = requests.get(get_url)
        if response.status_code != 200:
            print(f"获取任务失败: {response.status_code} - {response.text}")
            return
        
        tasks = response.json().get("data", [])
        task = next((t for t in tasks if t["id"] == reminder_id), None)
        
        if task:
            image_url = task.get('image_url')
            print(f"图片URL: {image_url}")
            
            # 检查是否包含时间戳参数
            if image_url and '?t=' in image_url:
                print("✅ 图片URL包含时间戳参数（缓存破坏）")
                
                # 提取时间戳
                import urllib.parse
                parsed_url = urllib.parse.urlparse(image_url)
                query_params = urllib.parse.parse_qs(parsed_url.query)
                timestamp = query_params.get('t', [None])[0]
                
                if timestamp:
                    print(f"  时间戳: {timestamp}")
                    current_time = int(time.time())
                    timestamp_int = int(timestamp)
                    
                    # 检查时间戳是否合理（在最近10秒内）
                    if abs(current_time - timestamp_int) <= 10:
                        print("✅ 时间戳是最近的（缓存破坏有效）")
                    else:
                        print(f"⚠️  时间戳可能不是最近的: {timestamp_int}，当前时间: {current_time}")
                else:
                    print("❌ 无法提取时间戳参数")
            else:
                print("❌ 图片URL不包含时间戳参数")
                
                # 检查是否是旧的URL格式
                if image_url and image_url.startswith(f"{BASE_URL}/api/images/"):
                    print("  这是旧的URL格式（无缓存破坏）")
        
        # 3. 等待1秒，然后再次获取，检查时间戳是否更新
        print("\n3. 等待1秒后再次获取，检查时间戳是否更新...")
        time.sleep(1)
        
        response = requests.get(get_url)
        if response.status_code == 200:
            tasks = response.json().get("data", [])
            task = next((t for t in tasks if t["id"] == reminder_id), None)
            
            if task:
                new_image_url = task.get('image_url')
                print(f"新的图片URL: {new_image_url}")
                
                if new_image_url != image_url:
                    print("✅ 图片URL已更新（时间戳改变）")
                    
                    # 检查新的时间戳
                    if new_image_url and '?t=' in new_image_url:
                        parsed_url = urllib.parse.urlparse(new_image_url)
                        query_params = urllib.parse.parse_qs(parsed_url.query)
                        new_timestamp = query_params.get('t', [None])[0]
                        
                        if new_timestamp and new_timestamp != timestamp:
                            print(f"  新的时间戳: {new_timestamp} (之前: {timestamp})")
                            print("✅ 缓存破坏参数正常工作")
                        else:
                            print("❌ 时间戳没有改变")
                    else:
                        print("❌ 新的URL也没有时间戳参数")
                else:
                    print("❌ 图片URL没有改变")
        
        # 4. 清理测试任务
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
    test_cache_busting()
