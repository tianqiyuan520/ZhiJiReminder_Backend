import sqlite3
import os

def check_database_time():
    """检查数据库时间设置"""
    db_path = "zhi_ji_xia.db"
    
    if not os.path.exists(db_path):
        print(f"数据库文件不存在: {db_path}")
        return
    
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    print("=== 数据库时间检查 ===")
    
    # 1. 检查当前数据库时间
    cursor.execute("SELECT datetime('now', 'localtime') as beijing_time, datetime('now') as utc_time")
    time_result = cursor.fetchone()
    print(f"1. 当前数据库时间:")
    print(f"   - 北京时间 (localtime): {time_result['beijing_time']}")
    print(f"   - UTC时间: {time_result['utc_time']}")
    
    # 2. 检查reminders表是否存在
    cursor.execute("SELECT COUNT(*) as count FROM sqlite_master WHERE type='table' AND name='reminders'")
    table_exists = cursor.fetchone()['count'] > 0
    
    if not table_exists:
        print("2. reminders表不存在")
        return
    
    print("2. reminders表存在")
    
    # 3. 检查表结构
    cursor.execute("PRAGMA table_info(reminders)")
    columns = cursor.fetchall()
    print("3. reminders表结构:")
    for col in columns:
        col_name = col[1]
        col_type = col[2]
        print(f"   - {col_name}: {col_type}")
    
    # 4. 检查created_at字段的默认值
    print("4. created_at字段分析:")
    
    # 查找created_at字段的默认值
    for col in columns:
        if col[1] == 'created_at':
            default_value = col[4]
            print(f"   - 默认值: {default_value}")
            if default_value and 'CURRENT_TIMESTAMP' in str(default_value):
                print("   - 使用CURRENT_TIMESTAMP，这是数据库服务器的系统时间")
    
    # 5. 查看示例数据
    cursor.execute("SELECT id, created_at FROM reminders ORDER BY created_at DESC LIMIT 3")
    rows = cursor.fetchall()
    
    if rows:
        print("5. 最新的3条任务创建时间:")
        for row in rows:
            task_id = row['id']
            created_at = row['created_at']
            print(f"   - 任务ID: {task_id}")
            print(f"     创建时间: {created_at}")
            
            # 检查是否是北京时间格式 (YYYY-MM-DD HH:MM:SS)
            if created_at and len(created_at) == 19:
                # 提取小时部分
                hour = int(created_at[11:13])
                if 0 <= hour <= 23:
                    print(f"     小时部分: {hour}时")
                    # 北京时间通常在8-23时（UTC+8）
                    if 8 <= hour <= 23:
                        print(f"     → 看起来像北京时间（{hour}时在白天）")
                    else:
                        print(f"     → 可能不是北京时间（{hour}时在夜间）")
    else:
        print("5. 没有任务数据")
    
    # 6. 检查时区偏移
    print("6. 时区分析:")
    cursor.execute("SELECT datetime('now', 'localtime') as local, datetime('now') as utc")
    times = cursor.fetchone()
    local_time = times['local']
    utc_time = times['utc']
    
    # 计算时差
    if local_time and utc_time:
        local_hour = int(local_time[11:13])
        utc_hour = int(utc_time[11:13])
        time_diff = (local_hour - utc_hour) % 24
        print(f"   - 本地时间: {local_time}")
        print(f"   - UTC时间: {utc_time}")
        print(f"   - 时差: {time_diff}小时")
        if time_diff == 8:
            print(f"   - ✅ 数据库使用北京时间（UTC+8）")
        else:
            print(f"   - ⚠️  数据库使用UTC+{time_diff}，不是北京时间")
    
    conn.close()
    print("\n=== 检查完成 ===")

if __name__ == "__main__":
    check_database_time()
