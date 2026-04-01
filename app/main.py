from fastapi import FastAPI, File, UploadFile, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import uuid
from datetime import datetime
import sqlite3
import json
import os

from app.models import HomeworkInfo, SaveReminderRequest, UserInfo, ImageUploadRequest
from app.ocr import ocr_image
from app.llm import parse_homework_info, analyze_homework as analyze_homework_ai

app = FastAPI(title="智记侠作业提醒API")

# 跨域，允许小程序访问
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 初始化SQLite数据库
def init_db():
    conn = sqlite3.connect('zhi_ji_xia.db')
    cursor = conn.cursor()
    
    # 创建用户表
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS users (
        user_id TEXT PRIMARY KEY,
        openid TEXT UNIQUE,
        nick_name TEXT,
        avatar_url TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    ''')
    
    # 创建提醒表
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS reminders (
        id TEXT PRIMARY KEY,
        user_id TEXT,
        course TEXT NOT NULL,
        content TEXT NOT NULL,
        start_time TEXT,
        deadline TEXT NOT NULL,
        difficulty TEXT DEFAULT '中',
        status TEXT DEFAULT 'pending',
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (user_id) REFERENCES users (user_id)
    )
    ''')
    
    conn.commit()
    conn.close()

# 初始化数据库
init_db()

@app.post("/api/upload")
async def upload_homework_base64(request: dict):
    """上传截图（base64格式），OCR识别 + 大模型解析，返回作业信息"""
    try:
        import base64
        # 获取base64图片数据
        image_base64 = request.get("image", "")
        if not image_base64:
            raise HTTPException(400, "图片数据为空")
        
        # 解码base64图片
        image_data = base64.b64decode(image_base64)
        # OCR
        ocr_text = ocr_image(image_data)
        if not ocr_text:
            raise HTTPException(400, "OCR识别失败，请确保图片清晰")
        # 大模型解析
        info = await parse_homework_info(ocr_text)
        return {
            "success": True,
            "data": {
                "course": info.get("course", "未知课程"),
                "content": info.get("content", "未知作业"),
                "deadline": info.get("deadline", "未指定")
            }
        }
    except Exception as e:
        raise HTTPException(500, f"处理失败: {str(e)}")

@app.post("/api/upload-file")
async def upload_homework_file(file: UploadFile = File(...)):
    """上传截图（文件格式），OCR识别 + 大模型解析，返回作业信息"""
    if not file.content_type.startswith("image/"):
        raise HTTPException(400, "请上传图片文件")
    try:
        contents = await file.read()
        # OCR
        ocr_text = ocr_image(contents)
        if not ocr_text:
            raise HTTPException(400, "OCR识别失败，请确保图片清晰")
        # 大模型解析
        info = await parse_homework_info(ocr_text)
        return {
            "success": True,
            "data": {
                "course": info.get("course", "未知课程"),
                "content": info.get("content", "未知作业"),
                "deadline": info.get("deadline", "未指定")
            }
        }
    except Exception as e:
        raise HTTPException(500, f"处理失败: {str(e)}")

@app.post("/api/analyze")
async def analyze_homework(homework: HomeworkInfo):
    """分析作业，提供拖延风险预测和微习惯拆解"""
    try:
        analysis = await analyze_homework_ai(homework.dict())
        return {
            "success": True,
            "data": analysis
        }
    except Exception as e:
        raise HTTPException(500, f"分析失败: {str(e)}")

@app.post("/api/reminder")
async def create_reminder(req: SaveReminderRequest):
    """保存提醒到数据库"""
    reminder_id = str(uuid.uuid4())
    
    conn = sqlite3.connect('zhi_ji_xia.db')
    cursor = conn.cursor()
    
    try:
        cursor.execute('''
        INSERT INTO reminders (id, user_id, course, content, start_time, deadline, difficulty, status)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            reminder_id,
            req.user_id,
            req.homework.course,
            req.homework.content,
            req.homework.start_time,
            req.homework.deadline,
            req.homework.difficulty,
            'pending'
        ))
        
        conn.commit()
        
        return {
            "success": True,
            "reminder_id": reminder_id,
            "message": "提醒已创建"
        }
    except Exception as e:
        conn.rollback()
        raise HTTPException(500, f"保存失败: {str(e)}")
    finally:
        conn.close()

@app.get("/api/reminders")
async def get_reminders(user_id: str):
    """获取某用户的所有提醒"""
    conn = sqlite3.connect('zhi_ji_xia.db')
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    try:
        cursor.execute('''
        SELECT id, user_id, course, content, start_time, deadline, difficulty, status, created_at
        FROM reminders 
        WHERE user_id = ?
        ORDER BY created_at DESC
        ''', (user_id,))
        
        reminders = []
        for row in cursor.fetchall():
            reminder = dict(row)
            # 计算剩余时间（天、小时、分钟）
            if reminder['deadline'] and reminder['status'] == 'pending':
                try:
                    deadline_str = reminder['deadline']
                    # 解析截止时间
                    deadline = datetime.strptime(deadline_str, '%Y-%m-%d %H:%M')
                    now = datetime.now()
                    
                    # 调试信息
                    print(f"调试 - 截止时间字符串: {deadline_str}")
                    print(f"调试 - 解析后截止时间: {deadline}")
                    print(f"调试 - 当前时间: {now}")
                    
                    # 直接比较datetime对象
                    if deadline <= now:
                        # 已过期
                        print(f"调试 - 状态: 已过期")
                        reminder['days_left'] = 0
                        reminder['hours_left'] = 0
                        reminder['minutes_left'] = 0
                        reminder['time_left_display'] = "已过期"
                    else:
                        # 计算时间差
                        diff = deadline - now
                        total_seconds = int(diff.total_seconds())
                        
                        print(f"调试 - 时间差: {diff}, 总秒数: {total_seconds}")
                        
                        # 计算天、小时、分钟
                        days = total_seconds // (24 * 3600)
                        hours = (total_seconds % (24 * 3600)) // 3600
                        minutes = (total_seconds % 3600) // 60
                        
                        print(f"调试 - 计算: {days}天 {hours}小时 {minutes}分钟")
                        
                        # 保存到reminder对象
                        reminder['days_left'] = days
                        reminder['hours_left'] = hours
                        reminder['minutes_left'] = minutes
                        
                        # 格式化显示字符串
                        if days > 0:
                            reminder['time_left_display'] = f"{days}天{hours}小时{minutes}分钟"
                        elif hours > 0:
                            reminder['time_left_display'] = f"{hours}小时{minutes}分钟"
                        elif minutes > 0:
                            reminder['time_left_display'] = f"{minutes}分钟"
                        else:
                            reminder['time_left_display'] = "即将到期"
                        
                except Exception as e:
                    print(f"计算剩余时间错误: {e}, 截止时间字符串: {reminder.get('deadline', '无')}")
                    reminder['days_left'] = 0
                    reminder['hours_left'] = 0
                    reminder['minutes_left'] = 0
                    reminder['time_left_display'] = "时间计算错误"
            else:
                # 已完成或没有截止时间的任务
                reminder['days_left'] = 0
                reminder['hours_left'] = 0
                reminder['minutes_left'] = 0
                reminder['time_left_display'] = "已完成"
            
            reminders.append(reminder)
        
        return {"success": True, "data": reminders}
    except Exception as e:
        raise HTTPException(500, f"查询失败: {str(e)}")
    finally:
        conn.close()

@app.post("/api/reminders/{reminder_id}/complete")
async def complete_reminder(reminder_id: str):
    """标记提醒为已完成"""
    conn = sqlite3.connect('zhi_ji_xia.db')
    cursor = conn.cursor()
    
    try:
        cursor.execute('''
        UPDATE reminders 
        SET status = 'completed'
        WHERE id = ?
        ''', (reminder_id,))
        
        if cursor.rowcount == 0:
            raise HTTPException(404, "提醒不存在")
        
        conn.commit()
        
        return {
            "success": True,
            "message": "任务已完成"
        }
    except HTTPException:
        raise
    except Exception as e:
        conn.rollback()
        raise HTTPException(500, f"更新失败: {str(e)}")
    finally:
        conn.close()

@app.delete("/api/reminders/all")
async def delete_all_reminders(user_id: str):
    """删除用户的所有任务"""
    conn = sqlite3.connect('zhi_ji_xia.db')
    cursor = conn.cursor()
    
    try:
        cursor.execute('''
        DELETE FROM reminders 
        WHERE user_id = ?
        ''', (user_id,))
        
        conn.commit()
        
        return {
            "success": True,
            "message": "已删除所有任务",
            "deleted_count": cursor.rowcount
        }
    except Exception as e:
        conn.rollback()
        raise HTTPException(500, f"删除失败: {str(e)}")
    finally:
        conn.close()

@app.delete("/api/reminders/completed")
async def delete_completed_reminders(user_id: str):
    """删除用户的所有已完成任务"""
    conn = sqlite3.connect('zhi_ji_xia.db')
    cursor = conn.cursor()
    
    try:
        cursor.execute('''
        DELETE FROM reminders 
        WHERE user_id = ? AND status = 'completed'
        ''', (user_id,))
        
        conn.commit()
        
        return {
            "success": True,
            "message": "已删除所有已完成任务",
            "deleted_count": cursor.rowcount
        }
    except Exception as e:
        conn.rollback()
        raise HTTPException(500, f"删除失败: {str(e)}")
    finally:
        conn.close()

@app.delete("/api/reminders/expired")
async def delete_expired_reminders(user_id: str):
    """删除用户的所有已过期任务（pending状态但已过截止时间）"""
    conn = sqlite3.connect('zhi_ji_xia.db')
    cursor = conn.cursor()
    
    try:
        # 获取所有pending任务
        cursor.execute('''
        SELECT id, deadline FROM reminders 
        WHERE user_id = ? AND status = 'pending'
        ''', (user_id,))
        
        expired_ids = []
        now = datetime.now()
        
        for row in cursor.fetchall():
            task_id, deadline_str = row
            if deadline_str:
                try:
                    deadline = datetime.strptime(deadline_str, '%Y-%m-%d %H:%M')
                    if deadline <= now:
                        expired_ids.append(task_id)
                except:
                    # 如果日期解析失败，跳过
                    continue
        
        # 删除已过期任务
        deleted_count = 0
        for task_id in expired_ids:
            cursor.execute('DELETE FROM reminders WHERE id = ?', (task_id,))
            deleted_count += 1
        
        conn.commit()
        
        return {
            "success": True,
            "message": f"已删除{deleted_count}个已过期任务",
            "deleted_count": deleted_count
        }
    except Exception as e:
        conn.rollback()
        raise HTTPException(500, f"删除失败: {str(e)}")
    finally:
        conn.close()

@app.post("/api/user")
async def save_user(user_info: UserInfo):
    """保存或更新用户信息"""
    conn = sqlite3.connect('zhi_ji_xia.db')
    cursor = conn.cursor()
    
    try:
        cursor.execute('''
        INSERT OR REPLACE INTO users (user_id, openid, nick_name, avatar_url)
        VALUES (?, ?, ?, ?)
        ''', (
            user_info.user_id,
            user_info.openid or user_info.user_id,
            user_info.nick_name,
            user_info.avatar_url
        ))
        
        conn.commit()
        
        return {
            "success": True,
            "message": "用户信息已保存"
        }
    except Exception as e:
        conn.rollback()
        raise HTTPException(500, f"保存用户信息失败: {str(e)}")
    finally:
        conn.close()

@app.get("/api/user")
async def get_user(user_id: str):
    """获取用户信息"""
    conn = sqlite3.connect('zhi_ji_xia.db')
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    try:
        cursor.execute('''
        SELECT user_id, openid, nick_name, avatar_url, created_at
        FROM users 
        WHERE user_id = ?
        ''', (user_id,))
        
        row = cursor.fetchone()
        if row:
            return {"success": True, "data": dict(row)}
        else:
            raise HTTPException(404, "用户不存在")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, f"查询用户失败: {str(e)}")
    finally:
        conn.close()

@app.get("/")
async def get_hello():
    return "智记侠API服务运行中"
