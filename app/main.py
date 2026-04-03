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
from fastapi.responses import Response
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

# 注册管理路由
app.include_router(admin_router)

# 在应用启动时初始化数据库
@app.on_event("startup")
async def startup_event():
    """应用启动时初始化数据库"""
    logger.info("应用启动，初始化数据库...")
    init_database()
    logger.info("数据库初始化完成")

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
        
        # 重要：这个端点不创建提醒，只返回识别结果
        # 前端应该使用返回的信息调用 /api/reminder 来创建提醒
        
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
    """只上传图片（不进行OCR识别），保存到临时表并返回临时图片ID（用于保存按钮）"""
    try:
        import base64
        import uuid
        import re
        
        # 获取base64图片数据
        image_base64 = request_data.get("image", "")
        user_id = request_data.get("user_id", "test")
        
        if not image_base64:
            raise HTTPException(400, "图片数据为空")
        
        # 解码base64图片
        try:
            image_data = base64.b64decode(image_base64)
            logger.info(f"图片解码成功，大小: {len(image_data)} bytes")
        except Exception as e:
            logger.error(f"图片数据格式错误: {e}")
            raise HTTPException(400, f"图片数据格式错误: {str(e)}")
        
        # 生成唯一的图片ID（不是提醒ID）
        image_id = str(uuid.uuid4())
        
        # 检测图片类型
        image_type = "image/jpeg"  # 默认类型
        if image_base64.startswith("data:image/"):
            # 从data URL中提取类型
            match = re.match(r'data:(image/[^;]+)', image_base64)
            if match:
                image_type = match.group(1)
        
        # 重要：不创建提醒记录，只保存图片到临时表或直接返回图片数据
        # 这里我们创建一个临时的图片记录，但不关联到提醒
        # 实际上，我们可以直接返回图片ID，让前端在创建提醒时传递这个图片数据
        
        # 为了兼容现有前端，我们仍然返回一个"reminder_id"，但这不是真正的提醒ID
        # 前端应该使用这个ID来获取图片，但在创建提醒时应该传递图片数据而不是这个ID
        
        # 返回图片API URL
        image_api_url = f"/api/temp-images/{image_id}"
        
        # 为了兼容性，也返回完整的URL
        base_url = os.getenv("FRONTEND_BASE_URL", "http://localhost:8002")
        full_image_url = f"{base_url.rstrip('/')}{image_api_url}"
        
        # 将图片数据保存到内存或临时存储（这里简化处理，实际应该保存到数据库或文件系统）
        # 注意：这里只是示例，实际生产环境需要更完善的临时存储方案
        
        return {
            "success": True,
            "data": {
                "image_url": full_image_url,  # 保持字段名不变以兼容前端
                "temp_image_id": image_id,  # 新增：临时图片ID
                "image_data": image_base64,  # 新增：返回图片数据，让前端在创建提醒时传递
                "image_api_url": image_api_url,
                "message": "图片上传成功，请在创建提醒时传递图片数据"
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
async def create_or_update_reminder(req: SaveReminderRequest):
    """保存或更新提醒到数据库"""
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
    
    # 检查是否有图片数据需要保存
    image_data = None
    image_type = None
    
    # 如果请求中包含图片数据，则保存到数据库
    if req.image:
        import base64
        import re
        try:
            # 处理data URL格式
            image_str = req.image
            if image_str.startswith("data:image/"):
                # 提取base64部分（data:image/png;base64,后面的部分）
                match = re.match(r'data:image/[^;]+;base64,(.+)', image_str)
                if match:
                    image_str = match.group(1)
            
            # 解码base64
            image_data = base64.b64decode(image_str)
            logger.info(f"从请求中解码图片成功，大小: {len(image_data)} bytes")
            
            # 检测图片类型
            image_type = "image/jpeg"  # 默认类型
            if req.image.startswith("data:image/"):
                # 从原始data URL中提取类型
                match = re.match(r'data:(image/[^;]+)', req.image)
                if match:
                    image_type = match.group(1)
        except Exception as e:
            logger.error(f"解码图片数据失败: {e}")
            # 继续处理，图片不是必需的
    elif hasattr(req, 'image_data') and req.image_data:
        # 兼容旧版本
        image_data = req.image_data
        image_type = getattr(req, 'image_type', 'image/jpeg')
    
    # 调试日志
    logger.info(f"图片数据处理结果: image_data={'有数据' if image_data else '无数据'}, image_type={image_type}")
    
    # 如果有reminder_id，则更新已有提醒
    if req.reminder_id:
        # 检查提醒是否存在且属于该用户
        check_reminder_query = """
        SELECT id FROM reminders 
        WHERE id = %s AND user_id = %s
        """
        
        try:
            reminders_data = db_config.execute_query(check_reminder_query, (req.reminder_id, req.user_id))
            if not reminders_data:
                raise HTTPException(404, "提醒不存在或不属于该用户")
        except Exception as e:
            logger.error(f"检查提醒存在失败: {e}")
            raise HTTPException(500, f"检查失败: {str(e)}")
        
        # 调试：打印image_data的详细信息
        logger.info(f"更新提醒前检查: image_data类型={type(image_data)}, 长度={len(image_data) if image_data else 0}, 值前20字节={image_data[:20] if image_data else '无'}")
        
        # 如果有图片数据，更新图片字段
        if image_data is not None and len(image_data) > 0:
            # 生成带时间戳的图片URL
            base_url = os.getenv("FRONTEND_BASE_URL", "http://localhost:8002")
            import time
            timestamp = int(time.time())
            image_url_with_timestamp = f"{base_url.rstrip('/')}/api/images/{req.reminder_id}?t={timestamp}"
            
            # 更新提醒信息（包括图片）
            update_query = """
            UPDATE reminders 
            SET course = %s, 
                content = %s, 
                start_time = %s, 
                deadline = %s, 
                difficulty = %s,
                image_url = %s,
                image_data = %s,
                image_type = %s
            WHERE id = %s
            """
            
            params = (
                req.homework.course,
                req.homework.content,
                req.homework.start_time,
                req.homework.deadline,
                req.homework.difficulty,
                image_url_with_timestamp,  # 使用带时间戳的URL
                image_data,
                image_type,
                req.reminder_id
            )
            logger.info(f"更新提醒（包含图片）: 图片大小={len(image_data)} bytes, 图片URL={image_url_with_timestamp}")
        else:
            # 更新提醒信息（不包括图片）
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
                req.reminder_id
            )
            logger.info(f"更新提醒（不包含图片）: image_data={'空' if image_data is None else '空字节串' if len(image_data) == 0 else '有数据'}, 将执行SQL更新")
        
        try:
            rowcount = db_config.execute_query(update_query, params)
            
            if rowcount == 0:
                raise HTTPException(404, "提醒不存在或更新失败")
            
            logger.info(f"更新提醒成功: {req.reminder_id}, 用户: {req.user_id}")
            
            return {
                "success": True,
                "reminder_id": req.reminder_id,
                "message": "提醒已更新"
            }
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"更新提醒失败: {e}")
            raise HTTPException(500, f"更新失败: {str(e)}")
    else:
        # 创建新提醒
        reminder_id = str(uuid.uuid4())
        
        query = """
        INSERT INTO reminders (
            id, user_id, course, content, start_time, deadline, 
            difficulty, status, image_url, image_data, image_type
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
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
            req.homework.image_url if hasattr(req.homework, 'image_url') else None,
            image_data,
            image_type
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
    SELECT id, user_id, course, content, start_time, deadline, difficulty, status, created_at, image_url, image_data
    FROM reminders 
    WHERE user_id = %s
    ORDER BY created_at DESC
    """
    
    try:
        reminders_data = db_config.execute_query(query, (user_id,))
        reminders = []
        
        for row in reminders_data:
            # 手动构建字典，确保所有值都是可序列化的
            reminder = {
                'id': row.get('id'),
                'user_id': row.get('user_id'),
                'course': row.get('course'),
                'content': row.get('content'),
                'start_time': row.get('start_time'),
                'deadline': row.get('deadline'),
                'difficulty': row.get('difficulty'),
                'status': row.get('status'),
                'created_at': str(row.get('created_at')) if row.get('created_at') else None,
                'image_url': row.get('image_url')
            }
            
            # 处理图片URL：如果有image_data，则使用API URL；否则使用原有的image_url
            # 调试：检查image_data字段
            image_data_value = row.get('image_data')
            logger.warning(f"DEBUG: 任务 {reminder['id']} - image_data类型: {type(image_data_value)}, 值: {image_data_value}")
            
            if image_data_value:
                # 如果有图片数据，使用API URL
                # 返回完整的URL，包括协议、主机和端口
                base_url = os.getenv("FRONTEND_BASE_URL", "http://localhost:8002")
                
                # 添加时间戳参数防止缓存
                import time
                timestamp = int(time.time())
                
                new_image_url = f"{base_url.rstrip('/')}/api/images/{reminder['id']}?t={timestamp}"
                # 使用logger.warning确保日志显示
                logger.warning(f"生成带时间戳的图片URL: {new_image_url} (原始image_url: {reminder.get('image_url')})")
                reminder['image_url'] = new_image_url
            elif not reminder.get('image_url'):
                # 既没有image_data也没有image_url
                logger.warning(f"任务 {reminder['id']} 没有图片数据")
                reminder['image_url'] = None
            else:
                logger.warning(f"任务 {reminder['id']} 使用原有的image_url: {reminder.get('image_url')}")
            
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
    
    # 检查是否有图片数据需要保存
    image_data = None
    image_type = None
    
    # 如果请求中包含图片数据，则保存到数据库
    if req.image:
        import base64
        import re
        try:
            # 处理data URL格式
            image_str = req.image
            if image_str.startswith("data:image/"):
                # 提取base64部分（data:image/png;base64,后面的部分）
                match = re.match(r'data:image/[^;]+;base64,(.+)', image_str)
                if match:
                    image_str = match.group(1)
            
            # 解码base64
            image_data = base64.b64decode(image_str)
            logger.info(f"从请求中解码图片成功，大小: {len(image_data)} bytes")
            
            # 检测图片类型
            image_type = "image/jpeg"  # 默认类型
            if req.image.startswith("data:image/"):
                # 从原始data URL中提取类型
                match = re.match(r'data:(image/[^;]+)', req.image)
                if match:
                    image_type = match.group(1)
        except Exception as e:
            logger.error(f"解码图片数据失败: {e}")
            # 继续处理，图片不是必需的
    elif hasattr(req, 'image_data') and req.image_data:
        # 兼容旧版本
        image_data = req.image_data
        image_type = getattr(req, 'image_type', 'image/jpeg')
    
    # 调试日志
    logger.info(f"图片数据处理结果: image_data={'有数据' if image_data else '无数据'}, image_type={image_type}")
    
    # 如果有图片数据，更新图片字段
    if image_data is not None and len(image_data) > 0:
        # 更新提醒信息（包括图片）
        update_query = """
        UPDATE reminders 
        SET course = %s, 
            content = %s, 
            start_time = %s, 
            deadline = %s, 
            difficulty = %s,
            image_url = %s,
            image_data = %s,
            image_type = %s
        WHERE id = %s
        """
        
        params = (
            req.homework.course,
            req.homework.content,
            req.homework.start_time,
            req.homework.deadline,
            req.homework.difficulty,
            req.homework.image_url if hasattr(req.homework, 'image_url') else None,
            image_data,
            image_type,
            reminder_id
        )
        logger.info(f"更新提醒（包含图片）: 图片大小={len(image_data)} bytes, 将执行SQL更新")
    else:
        # 更新提醒信息（不包括图片）
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
        logger.info(f"更新提醒（不包含图片）: image_data={'空' if image_data is None else '空字节串' if len(image_data) == 0 else '有数据'}, 将执行SQL更新")
    
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
        # 返回错误，让前端知道删除失败
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


@app.get("/api/images/{reminder_id}")
async def get_image(reminder_id: str):
    """获取提醒的图片数据"""
    try:
        # 查询图片数据
        query = """
        SELECT image_data, image_type 
        FROM reminders 
        WHERE id = %s AND image_data IS NOT NULL
        """
        
        result = db_config.execute_query(query, (reminder_id,))
        
        if not result:
            raise HTTPException(404, "图片不存在")
        
        image_data = result[0].get('image_data')
        image_type = result[0].get('image_type', 'image/jpeg')
        
        if not image_data:
            raise HTTPException(404, "图片数据为空")
        
        # 返回图片数据
        return Response(
            content=image_data,
            media_type=image_type,
            headers={
                "Cache-Control": "public, max-age=86400",  # 缓存1天
                "Content-Disposition": f'inline; filename="{reminder_id}.jpg"'
            }
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"获取图片失败: {e}")
        raise HTTPException(500, f"获取图片失败: {str(e)}")


@app.post("/api/upload-image-binary")
async def upload_image_binary(request_data: dict):
    """上传图片并保存二进制数据到数据库（用于保存按钮）"""
    try:
        import base64
        import uuid
        
        # 获取base64图片数据
        image_base64 = request_data.get("image", "")
        user_id = request_data.get("user_id", "test")
        
        if not image_base64:
            raise HTTPException(400, "图片数据为空")
        
        # 解码base64图片
        try:
            image_data = base64.b64decode(image_base64)
            logger.info(f"图片解码成功，大小: {len(image_data)} bytes")
        except Exception as e:
            logger.error(f"图片数据格式错误: {e}")
            raise HTTPException(400, f"图片数据格式错误: {str(e)}")
        
        # 生成唯一的提醒ID
        reminder_id = str(uuid.uuid4())
        
        # 检测图片类型
        image_type = "image/jpeg"  # 默认类型
        if image_base64.startswith("data:image/"):
            # 从data URL中提取类型
            import re
            match = re.match(r'data:(image/[^;]+)', image_base64)
            if match:
                image_type = match.group(1)
        
        # 创建提醒记录（只包含图片数据，课程和内容为空）
        query = """
        INSERT INTO reminders (
            id, user_id, course, content, start_time, deadline, 
            difficulty, status, image_data, image_type
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """
        
        params = (
            reminder_id,
            user_id,
            "",  # 空课程，而不是"待填写课程"
            "",  # 空内容，而不是"待填写作业内容"
            "",
            "未指定",
            "中",
            'pending',
            image_data,
            image_type
        )
        
        try:
            db_config.execute_query(query, params)
            logger.info(f"图片保存到数据库成功: {reminder_id}, 用户: {user_id}")
            
            return {
                "success": True,
                "data": {
                    "reminder_id": reminder_id,
                    "image_api_url": f"/api/images/{reminder_id}",
                    "message": "图片上传成功并保存到数据库"
                }
            }
        except Exception as db_error:
            logger.error(f"保存图片到数据库失败: {db_error}")
            raise HTTPException(500, f"保存图片失败: {str(db_error)}")
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"上传图片失败: {e}", exc_info=True)
        raise HTTPException(500, f"上传图片失败: {str(e)}")
