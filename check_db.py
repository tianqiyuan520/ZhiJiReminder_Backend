import sqlite3

conn = sqlite3.connect('zhi_ji_xia.db')
cursor = conn.cursor()

# 查看所有表
cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
tables = cursor.fetchall()
print("Tables in database:")
for table in tables:
    print(f"  - {table[0]}")

# 查看reminders表结构（如果存在）
if any('reminders' in table[0] for table in tables):
    cursor.execute("PRAGMA table_info(reminders);")
    columns = cursor.fetchall()
    print("\nReminders table columns:")
    for col in columns:
        print(f"  - {col[1]} ({col[2]})")
    
    # 查看一些数据
    cursor.execute("SELECT id, course, image_url FROM reminders LIMIT 5;")
    rows = cursor.fetchall()
    print("\nSample data from reminders table:")
    for row in rows:
        print(f"  - ID: {row[0]}, Course: {row[1]}, Image URL: {row[2]}")
else:
    print("\nReminders table does not exist!")

conn.close()
