import sqlite3

def check_tables():
    conn = sqlite3.connect('zhi_ji_xia.db')
    cursor = conn.cursor()
    
    # 获取所有表
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
    tables = cursor.fetchall()
    
    print("数据库中的表:")
    if tables:
        for table in tables:
            print(f"  - {table[0]}")
    else:
        print("  没有表")
    
    conn.close()

if __name__ == "__main__":
    check_tables()
