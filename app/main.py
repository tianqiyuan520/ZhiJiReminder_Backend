from fastapi import FastAPI, File, UploadFile, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import uuid
from datetime import datetime
import json
import os
import logging

from app.models import HomeworkInfo, SaveReminderRequest, UserInfo, ImageUploadRequest
from app.ocr import ocr_image
from app.llm import parse_homework_info, analyze_homework as analyze_homework_ai
from app.database import db_config, init_database, get_db, close_db
from app.admin import router as admin_router

# 配置日志
import os
log_level = os.getenv("LOG_LEVEL", "INFO").upper()
logging.basicConfig(
    level=getattr(logging, log_level, logging.INFO),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# 减少asyncio连接错误的日志噪音
asyncio_logger = logging.getLogger('asyncio')
asyncio_logger.setLevel(logging.WARNING)

app = FastAPI(title="智记侠作业提醒API")

# 跨域配置
# 生产环境应该指定具体的前端域名，这里暂时允许所有
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 生产环境应替换为具体域名
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 初始化数据库
init_database()

# 注册管理路由
app.include_router(admin_router)

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
    
    # 首先确保用户存在（创建默认用户）
    try:
        # 检查用户是否存在
        check_user_query = "SELECT user_id FROM users WHERE user_id = %s"
        users_data = db_config.execute_query(check_user_query, (req.user_id,))
        
        if not users_data:
            # 用户不存在，创建默认用户
            logger.info(f"用户 {req.user_id} 不存在，创建默认用户")
            
            if db_config.db_type == "postgresql":
                create_user_query = """
                INSERT INTO users (user_id, openid, nick_name, avatar_url)
                VALUES (%s, %s, %s, %s)
                ON CONFLICT (user_id) DO NOTHING
                """
            else:
                create_user_query = """
                INSERT OR IGNORE INTO users (user_id, openid, nick_name, avatar_url)
                VALUES (?, ?, ?, ?)
                """
            
            user_params = (
                req.user_id,
                req.user_id,  # 使用user_id作为openid
                f"用户{req.user_id[-4:]}",  # 默认昵称
                ""  # 空头像
            )
            
            db_config.execute_query(create_user_query, user_params)
            logger.info(f"已创建默认用户: {req.user_id}")
    except Exception as user_error:
        logger.warning(f"创建用户失败，继续尝试创建提醒: {user_error}")
        # 继续尝试创建提醒，如果外键约束失败会抛出异常
    
    # 创建提醒
    query = """
    INSERT INTO reminders (id, user_id, course, content, start_time, deadline, difficulty, status)
    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
    """
    
    params = (
        reminder_id,
        req.user_id,
        req.homework.course,
        req.homework.content,
        req.homework.start_time,
        req.homework.deadline,
        req.homework.difficulty,
        'pending'
    )
    
    try:
        db_config.execute_query(query, params)
        logger.info(f"创建提醒成功: {reminder_id}, 用户: {req.user_id}")
        
        return {
            "success": True,
            "reminder_id": reminder_id,
            "message": "提醒已创建"
        }
    except Exception as e:
        logger.error(f"创建提醒失败: {e}")
        raise HTTPException(500, f"保存失败: {str(e)}")

@app.get("/api/reminders")
async def get_reminders(user_id: str):
    """获取某用户的所有提醒"""
    query = """
    SELECT id, user_id, course, content, start_time, deadline, difficulty, status, created_at
    FROM reminders 
    WHERE user_id = %s
    ORDER BY created_at DESC
    """
    
    try:
        reminders_data = db_config.execute_query(query, (user_id,))
        reminders = []
        
        for row in reminders_data:
            reminder = dict(row)
            # 计算剩余时间（天、小时、分钟）- 使用北京时间（UTC+8）
            if reminder['deadline'] and reminder['status'] == 'pending':
                try:
                    deadline_str = reminder['deadline']
                    # 解析截止时间，假设输入的是北京时间
                    deadline = datetime.strptime(deadline_str, '%Y-%m-%d %H:%M')
                    
                    # 获取当前北京时间（UTC+8）
                    import pytz
                    from datetime import datetime, timezone, timedelta
                    
                    # 创建北京时间时区
                    beijing_tz = pytz.timezone('Asia/Shanghai')
                    now_beijing = datetime.now(beijing_tz)
                    
                    # 将deadline转换为带有时区信息的datetime（假设是北京时间）
                    deadline_beijing = beijing_tz.localize(deadline)
                    
                    # 直接比较datetime对象
                    if deadline_beijing <= now_beijing:
                        # 已过期
                        reminder['days_left'] = 0
                        reminder['hours_left'] = 0
                        reminder['minutes_left'] = 0
                        reminder['time_left_display'] = "已过期"
                    else:
                        # 计算时间差
                        diff = deadline_beijing - now_beijing
                        total_seconds = int(diff.total_seconds())
                        
                        # 计算天、小时、分钟
                        days = total_seconds // (24 * 3600)
                        hours = (total_seconds % (24 * 3600)) // 3600
                        minutes = (total_seconds % 3600) // 60
                        
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
                    logger.error(f"计算剩余时间错误: {e}, 截止时间字符串: {reminder.get('deadline', '无')}")
                    # 如果时区计算失败，使用简单计算（假设本地时间就是北京时间）
                    try:
                        # 重新导入datetime以避免命名冲突
                        from datetime import datetime as dt
                        deadline = dt.strptime(deadline_str, '%Y-%m-%d %H:%M')
                        now = dt.now()
                        diff = deadline - now
                        total_seconds = int(diff.total_seconds()) if diff.total_seconds() > 0 else 0
                        
                        days = total_seconds // (24 * 3600)
                        hours = (total_seconds % (24 * 3600)) // 3600
                        minutes = (total_seconds % 3600) // 60
                        
                        reminder['days_left'] = days
                        reminder['hours_left'] = hours
                        reminder['minutes_left'] = minutes
                        
                        if days > 0:
                            reminder['time_left_display'] = f"{days}天{hours}小时{minutes}分钟"
                        elif hours > 0:
                            reminder['time_left_display'] = f"{hours}小时{minutes}分钟"
                        elif minutes > 0:
                            reminder['time_left_display'] = f"{minutes}分钟"
                        else:
                            reminder['time_left_display'] = "已过期" if total_seconds <= 0 else "即将到期"
                    except:
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
        
        logger.info(f"获取用户 {user_id} 的提醒，共 {len(reminders)} 条")
        return {"success": True, "data": reminders}
    except Exception as e:
        logger.error(f"查询提醒失败: {e}")
        raise HTTPException(500, f"查询失败: {str(e)}")

@app.post("/api/reminders/{reminder_id}/complete")
async def complete_reminder(reminder_id: str):
    """标记提醒为已完成"""
    query = """
    UPDATE reminders 
    SET status = 'completed'
    WHERE id = %s
    """
    
    try:
        rowcount = db_config.execute_query(query, (reminder_id,))
        
        if rowcount == 0:
            raise HTTPException(404, "提醒不存在")
        
        logger.info(f"完成任务: {reminder_id}")
        
        return {
            "success": True,
            "message": "任务已完成"
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"完成任务失败: {e}")
        raise HTTPException(500, f"更新失败: {str(e)}")

@app.delete("/api/reminders/all")
async def delete_all_reminders(user_id: str):
    """删除用户的所有任务"""
    query = """
    DELETE FROM reminders 
    WHERE user_id = %s
    """
    
    try:
        deleted_count = db_config.execute_query(query, (user_id,))
        logger.info(f"删除用户 {user_id} 的所有任务，共 {deleted_count} 条")
        
        return {
            "success": True,
            "message": "已删除所有任务",
            "deleted_count": deleted_count
        }
    except Exception as e:
        logger.error(f"删除所有任务失败: {e}")
        raise HTTPException(500, f"删除失败: {str(e)}")

@app.delete("/api/reminders/completed")
async def delete_completed_reminders(user_id: str):
    """删除用户的所有已完成任务"""
    query = """
    DELETE FROM reminders 
    WHERE user_id = %s AND status = 'completed'
    """
    
    try:
        deleted_count = db_config.execute_query(query, (user_id,))
        logger.info(f"删除用户 {user_id} 的已完成任务，共 {deleted_count} 条")
        
        return {
            "success": True,
            "message": "已删除所有已完成任务",
            "deleted_count": deleted_count
        }
    except Exception as e:
        logger.error(f"删除已完成任务失败: {e}")
        raise HTTPException(500, f"删除失败: {str(e)}")

@app.delete("/api/reminders/expired")
async def delete_expired_reminders(user_id: str):
    """删除用户的所有已过期任务（pending状态但已过截止时间）"""
    try:
        # 获取所有pending任务
        query_select = """
        SELECT id, deadline FROM reminders 
        WHERE user_id = %s AND status = 'pending'
        """
        
        reminders_data = db_config.execute_query(query_select, (user_id,))
        expired_ids = []
        now = datetime.now()
        
        for row in reminders_data:
            task_id = row['id']
            deadline_str = row['deadline']
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
            query_delete = "DELETE FROM reminders WHERE id = %s"
            db_config.execute_query(query_delete, (task_id,))
            deleted_count += 1
        
        logger.info(f"删除用户 {user_id} 的已过期任务，共 {deleted_count} 条")
        
        return {
            "success": True,
            "message": f"已删除{deleted_count}个已过期任务",
            "deleted_count": deleted_count
        }
    except Exception as e:
        logger.error(f"删除已过期任务失败: {e}")
        raise HTTPException(500, f"删除失败: {str(e)}")

@app.post("/api/user")
async def save_user(user_info: UserInfo):
    """保存或更新用户信息"""
    # 根据数据库类型使用不同的语法
    if db_config.db_type == "postgresql":
        # PostgreSQL的UPSERT语法
        query = """
        INSERT INTO users (user_id, openid, nick_name, avatar_url)
        VALUES (%s, %s, %s, %s)
        ON CONFLICT (user_id) DO UPDATE SET
            openid = EXCLUDED.openid,
            nick_name = EXCLUDED.nick_name,
            avatar_url = EXCLUDED.avatar_url
        """
    else:
        # SQLite的INSERT OR REPLACE语法
        query = """
        INSERT OR REPLACE INTO users (user_id, openid, nick_name, avatar_url)
        VALUES (?, ?, ?, ?)
        """
    
    params = (
        user_info.user_id,
        user_info.openid or user_info.user_id,
        user_info.nick_name,
        user_info.avatar_url
    )
    
    try:
        db_config.execute_query(query, params)
        logger.info(f"保存用户信息: {user_info.user_id}")
        
        return {
            "success": True,
            "message": "用户信息已保存"
        }
    except Exception as e:
        logger.error(f"保存用户信息失败: {e}")
        raise HTTPException(500, f"保存用户信息失败: {str(e)}")

@app.get("/api/user")
async def get_user(user_id: str):
    """获取用户信息"""
    query = """
    SELECT user_id, openid, nick_name, avatar_url, created_at
    FROM users 
    WHERE user_id = %s
    """
    
    try:
        users_data = db_config.execute_query(query, (user_id,))
        
        if users_data:
            user_info = users_data[0]
            logger.info(f"获取用户信息: {user_id}")
            return {"success": True, "data": dict(user_info)}
        else:
            logger.warning(f"用户不存在: {user_id}")
            raise HTTPException(404, "用户不存在")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"查询用户失败: {e}")
        raise HTTPException(500, f"查询用户失败: {str(e)}")

@app.get("/")
async def get_hello():
    return "智记侠API服务运行中"


# 导入微信订阅消息模块
from app.wechat import check_due_reminders, add_last_notified_column

# 添加last_notified列（如果不存在）
add_last_notified_column()

@app.get("/api/check-due-reminders")
async def api_check_due_reminders():
    """手动触发检查即将到期的提醒并发送订阅消息"""
    try:
        sent_count = check_due_reminders()
        return {
            "success": True,
            "message": f"已检查并发送 {sent_count} 条订阅消息",
            "sent_count": sent_count
        }
    except Exception as e:
        logger.error(f"检查到期提醒失败: {e}")
        raise HTTPException(500, f"检查失败: {str(e)}")


@app.post("/api/subscribe-message/test")
async def test_subscribe_message(user_id: str):
    """测试订阅消息发送功能"""
    try:
        from app.wechat import wechat_message
        
        # 获取用户信息
        query = "SELECT openid FROM users WHERE user_id = %s"
        users_data = db_config.execute_query(query, (user_id,))
        
        if not users_data or not users_data[0].get("openid"):
            raise HTTPException(404, "用户不存在或没有openid")
        
        openid = users_data[0]["openid"]
        
        # 测试消息数据
        test_data = {
            "thing1": {"value": "测试课程"},
            "thing2": {"value": "测试作业内容"},
            "time3": {"value": "2026-04-01 23:59"},
            "thing4": {"value": "测试紧急程度"}
        }
        
        # 发送测试消息
        success = wechat_message.send_subscribe_message(
            openid, 
            wechat_message.template_ids["reminder_due"], 
            test_data
        )
        
        if success:
            return {
                "success": True,
                "message": "测试订阅消息发送成功"
            }
        else:
            return {
                "success": False,
                "message": "测试订阅消息发送失败"
            }
            
    except Exception as e:
        logger.error(f"测试订阅消息失败: {e}")
        raise HTTPException(500, f"测试失败: {str(e)}")
