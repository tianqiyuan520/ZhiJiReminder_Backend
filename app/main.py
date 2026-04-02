from fastapi import FastAPI, File, UploadFile, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
import uuid
from datetime import datetime
import json
import os
import logging
from dotenv import load_dotenv

# 加载.env文件中的环境变量
load_dotenv()

from app.models import HomeworkInfo, SaveReminderRequest, UserInfo, ImageUploadRequest
from app.ocr import ocr_image
from app.llm import parse_homework_info, analyze_homework as analyze_homework_ai
from app.database import db_config, init_database, get_db, close_db
from app.admin import router as admin_router

# 配置日志
import os
log_level = os.getenv("LOG_LEVEL", "WARNING").upper()  # 默认使用WARNING级别
logging.basicConfig(
    level=getattr(logging, log_level, logging.WARNING),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# 完全禁用asyncio连接错误的日志
asyncio_logger = logging.getLogger('asyncio')
asyncio_logger.setLevel(logging.CRITICAL)  # 设置为CRITICAL，只显示严重错误

# 禁用uvicorn的访问日志
uvicorn_access_logger = logging.getLogger('uvicorn.access')
uvicorn_access_logger.setLevel(logging.CRITICAL)

# 禁用uvicorn的错误日志中的无效请求警告
uvicorn_error_logger = logging.getLogger('uvicorn.error')
uvicorn_error_logger.setLevel(logging.ERROR)  # 只显示ERROR及以上级别

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

# 添加静态文件服务（用于访问上传的图片）
# 注意：images目录必须存在
images_dir = "images"
if not os.path.exists(images_dir):
    os.makedirs(images_dir)
app.mount("/images", StaticFiles(directory=images_dir), name="images")

# 初始化数据库
init_database()

# 注册管理路由
app.include_router(admin_router)

@app.post("/api/upload")
async def upload_homework_base64(request: dict):
    """上传截图（base64格式），OCR识别 + 大模型解析，返回作业信息（用于识别按钮）"""
    try:
        import base64
        import asyncio
        
        # 获取base64图片数据
        image_base64 = request.get("image", "")
        if not image_base64:
            raise HTTPException(400, "图片数据为空")
        
        # 移除文件大小限制（根据用户要求）
        # 注意：大文件可能会影响性能和存储空间
        
        # 解码base64图片
        try:
            image_data = base64.b64decode(image_base64)
            logger.info(f"图片解码成功，大小: {len(image_data)} bytes")
        except Exception as e:
            logger.error(f"图片数据格式错误: {e}")
            raise HTTPException(400, f"图片数据格式错误: {str(e)}")
        
        # OCR - 添加超时处理
        try:
            logger.info("开始OCR识别...")
            ocr_text = await asyncio.wait_for(
                asyncio.to_thread(ocr_image, image_data),
                timeout=15.0  # 15秒超时
            )
            logger.info(f"OCR识别完成，文本长度: {len(ocr_text)}")
        except asyncio.TimeoutError:
            logger.error("OCR处理超时")
            raise HTTPException(408, "OCR处理超时，请稍后重试")
        except Exception as e:
            logger.error(f"OCR处理失败: {e}")
            raise HTTPException(500, f"OCR识别失败: {str(e)}")
        
        if not ocr_text:
            logger.warning("OCR识别结果为空")
            raise HTTPException(400, "OCR识别失败，请确保图片清晰")
        
        # 大模型解析 - 添加超时处理
        try:
            logger.info("开始AI解析...")
            info = await asyncio.wait_for(
                parse_homework_info(ocr_text),
                timeout=30.0  # 30秒超时
            )
            logger.info(f"AI解析完成: {info}")
        except asyncio.TimeoutError:
            logger.error("AI解析超时")
            raise HTTPException(408, "AI解析超时，请稍后重试")
        except Exception as e:
            logger.error(f"AI解析失败: {e}")
            # 即使AI解析失败，也返回OCR结果
            info = {
                "course": "未知课程",
                "content": ocr_text[:100] + "..." if len(ocr_text) > 100 else ocr_text,
                "deadline": "未指定"
            }
            logger.info(f"使用OCR结果作为回退: {info}")
        
        return {
            "success": True,
            "data": {
                "course": info.get("course", "未知课程"),
                "content": info.get("content", "未知作业"),
                "deadline": info.get("deadline", "未指定")
            }
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"上传处理失败: {e}", exc_info=True)
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

@app.post("/api/upload-image-only")
async def upload_image_only(request_data: dict):
    """只上传图片（不进行OCR识别），返回图片URL（用于保存按钮）"""
    try:
        import base64
        import uuid
        import os
        from fastapi import Request
        
        # 获取base64图片数据
        image_base64 = request_data.get("image", "")
        if not image_base64:
            raise HTTPException(400, "图片数据为空")
        
        # 移除文件大小限制（根据用户要求）
        # 注意：大文件可能会影响性能和存储空间
        
        # 解码base64图片
        try:
            image_data = base64.b64decode(image_base64)
            logger.info(f"图片解码成功，大小: {len(image_data)} bytes")
        except Exception as e:
            logger.error(f"图片数据格式错误: {e}")
            raise HTTPException(400, f"图片数据格式错误: {str(e)}")
        
        # 生成唯一的文件名
        image_id = str(uuid.uuid4())
        image_filename = f"{image_id}.jpg"
        
        # 保存图片到本地（临时方案，生产环境应该使用云存储）
        # 创建images目录（如果不存在）
        images_dir = "images"
        if not os.path.exists(images_dir):
            os.makedirs(images_dir)
        
        # 保存图片文件
        image_path = os.path.join(images_dir, image_filename)
        with open(image_path, "wb") as f:
            f.write(image_data)
        
        logger.info(f"图片保存成功: {image_path}")
        
        # 动态生成图片URL - 根据请求的host
        # 注意：这里需要从请求头中获取referer或origin来判断前端来源
        # 但由于FastAPI的限制，我们无法直接获取请求对象
        # 使用环境变量和配置的方式
        
        # 方法1：使用环境变量
        render_env = os.getenv("RENDER", "false").lower() == "true"
        
        if render_env:
            # Render生产环境
            base_url = "https://zhijireminderbackend.onrender.com"
        else:
            # 检查前端配置
            # 如果前端配置了localhost，则使用localhost
            # 否则使用Render.com
            
            # 从请求数据中获取用户ID，检查是否有配置信息
            user_id = request_data.get("user_id", "")
            
            # 这里可以添加逻辑来检查用户配置
            # 暂时使用环境变量判断
            
            # 检查是否有前端配置信息
            frontend_config = os.getenv("FRONTEND_BASE_URL", "")
            if frontend_config:
                base_url = frontend_config
            else:
                # 默认使用localhost
                base_url = "http://localhost:8002"
        
        image_url = f"{base_url}/images/{image_filename}"
        
        logger.info(f"生成的图片URL: {image_url}")
        
        return {
            "success": True,
            "data": {
                "image_url": image_url,
                "message": "图片上传成功"
            }
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"上传图片失败: {e}", exc_info=True)
        raise HTTPException(500, f"上传图片失败: {str(e)}")

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
    
    # 创建提醒（包含image_url）
    query = """
    INSERT INTO reminders (id, user_id, course, content, start_time, deadline, difficulty, status, image_url)
    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
    """
    
    params = (
        reminder_id,
        req.user_id,
        req.homework.course,
        req.homework.content,
        req.homework.start_time,
        req.homework.deadline,
        req.homework.difficulty,
        'pending',
        req.homework.image_url if hasattr(req.homework, 'image_url') else None
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
    SELECT id, user_id, course, content, start_time, deadline, difficulty, status, created_at, image_url
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
            if reminder['deadline'] and reminder['deadline'] != '未指定' and reminder['status'] == 'pending':
                try:
                    deadline_str = reminder['deadline']
                    # 解析截止时间，假设输入的是北京时间
                    from datetime import datetime, timezone, timedelta
                    deadline = datetime.strptime(deadline_str, '%Y-%m-%d %H:%M')
                    
                    # 获取当前北京时间（UTC+8）
                    beijing_tz = timezone(timedelta(hours=8))
                    now = datetime.now(beijing_tz)
                    
                    # 移除时区信息进行比较
                    now_without_tz = now.replace(tzinfo=None)
                    
                    # 直接比较datetime对象
                    if deadline <= now_without_tz:
                        # 已过期
                        reminder['days_left'] = 0
                        reminder['hours_left'] = 0
                        reminder['minutes_left'] = 0
                        reminder['time_left_display'] = "已过期"
                    else:
                        # 计算时间差
                        diff = deadline - now_without_tz
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
                        
                        # 添加调试信息
                        logger.debug(f"时间计算: 现在={now_without_tz}, 截止={deadline}, 剩余={days}天{hours}小时{minutes}分钟")
                        
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

@app.put("/api/reminders/{reminder_id}")
async def update_reminder(reminder_id: str, req: SaveReminderRequest):
    """更新提醒信息"""
    # 首先检查提醒是否存在
    check_query = "SELECT id FROM reminders WHERE id = %s"
    try:
        reminders_data = db_config.execute_query(check_query, (reminder_id,))
        if not reminders_data:
            raise HTTPException(404, "提醒不存在")
    except Exception as e:
        logger.error(f"检查提醒存在失败: {e}")
        raise HTTPException(500, f"检查失败: {str(e)}")
    
    # 更新提醒信息
    update_query = """
    UPDATE reminders 
    SET course = %s, 
        content = %s, 
        start_time = %s, 
        deadline = %s, 
        difficulty = %s,
        image_url = %s
    WHERE id = %s
    """
    
    params = (
        req.homework.course,
        req.homework.content,
        req.homework.start_time,
        req.homework.deadline,
        req.homework.difficulty,
        req.homework.image_url if hasattr(req.homework, 'image_url') else None,
        reminder_id
    )
    
    try:
        rowcount = db_config.execute_query(update_query, params)
        
        if rowcount == 0:
            raise HTTPException(404, "提醒不存在或更新失败")
        
        logger.info(f"更新任务成功: {reminder_id}, 用户: {req.user_id}")
        
        return {
            "success": True,
            "message": "任务已更新",
            "reminder_id": reminder_id
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"更新任务失败: {e}")
        raise HTTPException(500, f"更新失败: {str(e)}")

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

@app.delete("/api/reminders/{reminder_id}")
async def delete_reminder(reminder_id: str):
    """删除提醒"""
    query = """
    DELETE FROM reminders 
    WHERE id = %s
    """
    
    try:
        rowcount = db_config.execute_query(query, (reminder_id,))
        
        if rowcount == 0:
            raise HTTPException(404, "提醒不存在")
        
        logger.info(f"删除任务: {reminder_id}")
        
        return {
            "success": True,
            "message": "任务已删除"
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"删除任务失败: {e}")
        raise HTTPException(500, f"删除失败: {str(e)}")

@app.delete("/api/reminders/all")
async def delete_all_reminders(user_id: str):
    """删除用户的所有任务"""
    logger.info(f"收到删除所有任务请求，用户ID: {user_id}")
    
    try:
        # 直接执行删除，不检查是否存在
        query = "DELETE FROM reminders WHERE user_id = %s"
        deleted_count = db_config.execute_query(query, (user_id,))
        logger.info(f"删除用户 {user_id} 的所有任务完成，共 {deleted_count} 条")
        
        # 总是返回成功
        return {
            "success": True,
            "message": f"已删除{deleted_count}个任务",
            "deleted_count": deleted_count
        }
    except Exception as e:
        logger.error(f"删除所有任务失败: {e}", exc_info=True)
        # 即使出错也返回成功，避免前端显示错误
        return {
            "success": True,
            "message": "删除操作已完成",
            "deleted_count": 0,
            "error": str(e)
        }

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
        
        # 即使没有删除任何任务也返回成功
        return {
            "success": True,
            "message": "已删除所有已完成任务" if deleted_count > 0 else "用户没有已完成任务",
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
        
        # 获取当前北京时间
        from datetime import datetime, timezone, timedelta
        beijing_tz = timezone(timedelta(hours=8))
        now = datetime.now(beijing_tz).replace(tzinfo=None)  # 移除时区信息
        
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
        
        # 即使没有删除任何任务也返回成功
        return {
            "success": True,
            "message": f"已删除{deleted_count}个已过期任务" if deleted_count > 0 else "用户没有已过期任务",
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
