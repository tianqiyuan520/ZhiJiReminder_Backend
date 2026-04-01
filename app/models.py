from pydantic import BaseModel
from typing import Optional, List

class OCRResult(BaseModel):
    text: str

class ImageUploadRequest(BaseModel):
    image: str  # base64编码的图片
    user_id: Optional[str] = ""

class HomeworkInfo(BaseModel):
    course: str          # 课程名
    content: str         # 作业内容
    start_time: Optional[str] = ""  # 开始时间
    deadline: str        # 截止时间，如 "2025-12-31 23:59"
    difficulty: Optional[str] = "中"  # 难度自评

class SaveReminderRequest(BaseModel):
    user_id: str
    homework: HomeworkInfo

class UserInfo(BaseModel):
    user_id: str
    openid: Optional[str] = ""
    nick_name: str
    avatar_url: str

class MicroTask(BaseModel):
    day: int
    task: str
    duration_minutes: int

class HomeworkAnalysis(BaseModel):
    procrastination_risk: str  # 拖延风险：高/中/低
    micro_tasks: List[MicroTask]  # 微习惯拆解
    suggestion: str  # 个性化建议
