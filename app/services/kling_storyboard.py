"""
Kling 可灵 AI 视频生成模块 — 完整 API 集成
============================================
支持：文生视频 / 图生视频 / 画质模式 / 画面比例 / 运镜控制

可灵 API 文档: https://platform.klingai.com/docs/api

用法:
    python -m app.services.kling_storyboard "深海磷虾油广告" --mode pro --ratio 9:16 --scenes 5

工作流:
    主题 → LLM生成分镜JSON → 每场景调Kling → 下载 → TTS配音 → ffmpeg拼接
"""

import json
import time
import os
import base64
import requests
from typing import List, Dict, Optional, Tuple, Literal
from dataclasses import dataclass, field
from loguru import logger

# ============================================================
# 配置
# ============================================================
KLING_API_BASE = "https://api.klingai.com/v1"

def _get_kling_keys() -> Tuple[str, str]:
    """从 config.toml 读取可灵 API 密钥，fallback 到环境变量"""
    try:
        from app.config import config as app_cfg
        ak = app_cfg.app.get("kling_access_key", "") or os.environ.get("KLING_ACCESS_KEY", "")
        sk = app_cfg.app.get("kling_secret_key", "") or os.environ.get("KLING_SECRET_KEY", "")
        return ak, sk
    except Exception:
        return os.environ.get("KLING_ACCESS_KEY", ""), os.environ.get("KLING_SECRET_KEY", "")

KLING_ACCESS_KEY, KLING_SECRET_KEY = _get_kling_keys()

# ============================================================
# 类型定义
# ============================================================

# 画面比例
AspectRatio = Literal["16:9", "9:16", "1:1"]
# 画质模式
QualityMode = Literal["std", "pro"]
# 模型名
ModelName = Literal["kling-v1", "kling-v1-5", "kling-v1-6", "kling-v2", "kling-v2-master"]

@dataclass
class KlingVideoParams:
    """可灵视频生成参数"""
    prompt: str
    duration: int = 5                # 秒 (5 或 10)
    model: ModelName = "kling-v1-6"  # 推荐最新版本
    mode: QualityMode = "std"        # std=标准  pro=高画质(更贵更慢)
    aspect_ratio: AspectRatio = "16:9"
    negative_prompt: str = ""        # 负面提示词
    cfg_scale: float = 0.5           # 提示词相关度 (0~1)
    # 图生视频专用
    image_url: Optional[str] = None  # 参考图 URL (图生视频用)
    image_tail_url: Optional[str] = None  # 尾帧图 URL

@dataclass
class KlingVideoResult:
    """视频生成结果"""
    task_id: str
    video_url: Optional[str] = None
    local_path: Optional[str] = None
    duration: float = 0              # 实际耗时(秒)
    status: str = "pending"


# ============================================================
# Kling API 客户端 (完整)
# ============================================================

class KlingClient:
    """可灵 API 完整客户端
    
    支持:
    - 文生视频 text2video (std/pro, 16:9/9:16/1:1, 运镜)
    - 图生视频 image2video (商品图→动态视频)
    - 任务查询/列表/批量
    """

    def __init__(self, access_key: str = None, secret_key: str = None):
        self.access_key = access_key or KLING_ACCESS_KEY
        self.secret_key = secret_key or KLING_SECRET_KEY
        self._token = None
        self._token_expires = 0

    # ---- 认证 ----

    def _get_token(self) -> str:
        """JWT 认证 (HS256, 30分钟有效期)"""
        if self._token and time.time() < self._token_expires:
            return self._token
        try:
            import jwt as pyjwt
        except ImportError:
            logger.error("请安装 PyJWT: pip install PyJWT")
            raise

        payload = {
            "iss": self.access_key,
            "exp": int(time.time()) + 1800,
            "nbf": int(time.time()) - 5,
        }
        self._token = pyjwt.encode(payload, self.secret_key, algorithm="HS256")
        self._token_expires = time.time() + 1700
        return self._token

    def _headers(self) -> Dict:
        return {
            "Authorization": f"Bearer {self._get_token()}",
            "Content-Type": "application/json",
        }

    # ---- 文生视频 ----

    def text_to_video(
        self,
        prompt: str,
        duration: int = 5,
        model: str = "kling-v1-6",
        mode: str = "std",
        aspect_ratio: str = "16:9",
        negative_prompt: str = "",
        cfg_scale: float = 0.5,
        camera_control: Optional[Dict] = None,
    ) -> str:
        """
        文生视频 — 提交任务，返回 task_id
        
        Args:
            prompt: 画面描述（英文，建议 50-200 字符）
            duration: 视频时长，5 或 10 秒
            model: 模型版本
            mode: std=标准画质(快)  pro=高画质(慢，约3-5分钟/条)
            aspect_ratio: 画面比例 "16:9" | "9:16" | "1:1"
            negative_prompt: 不想出现的元素
            cfg_scale: 提示词遵循度 0~1
            camera_control: 运镜控制，如 {"type": "simple", "config": {"mode": "zoom_in"}}
        
        可灵支持的运镜模式 (camera_control.config.mode):
            - horizontal 水平移动, vertical 垂直移动, 
            - zoom_in 拉近, zoom_out 拉远,
            - pan_left 左移, pan_right 右移, 
            - tilt_up 上移, tilt_down 下移,
            - static 静止
        """
        url = f"{KLING_API_BASE}/videos/text2video"
        payload = {
            "model_name": model,
            "prompt": prompt,
            "mode": mode,
            "duration": str(duration),
            "aspect_ratio": aspect_ratio,
            "negative_prompt": negative_prompt,
            "cfg_scale": cfg_scale,
        }
        if camera_control:
            payload["camera_control"] = camera_control

        resp = requests.post(url, json=payload, headers=self._headers(), timeout=30)
        data = resp.json()
        if data.get("code") != 0:
            raise RuntimeError(f"Kling text2video error [{data.get('code')}]: {data.get('message', data)}")
        task_id = data["data"]["task_id"]
        logger.info(f"🎬 text2video 任务创建: {task_id} | {mode}/{aspect_ratio} | {prompt[:60]}...")
        return task_id

    # ---- 图生视频 ----

    def image_to_video(
        self,
        image: str,
        prompt: str = "",
        duration: int = 5,
        model: str = "kling-v1-6",
        mode: str = "std",
        negative_prompt: str = "",
        cfg_scale: float = 0.5,
        image_tail: Optional[str] = None,
    ) -> str:
        """
        图生视频 — 将静态图片变成动态视频 (电商核心功能!)
        
        Args:
            image: 图片 URL 或本地文件路径（自动转 base64）
            prompt: 画面动态描述，如 "产品缓慢旋转展示，柔和灯光，商业摄影风格"
            duration: 5 或 10 秒
            model: 模型版本
            mode: std/pro
            negative_prompt: 不想出现的，如 "变形, 模糊, 文字扭曲"
            image_tail: 尾帧图（可选），视频结束时的画面
        
        Returns:
            task_id
        """
        # 如果是本地路径，转 base64
        if os.path.isfile(image):
            with open(image, "rb") as f:
                img_b64 = base64.b64encode(f.read()).decode()
            ext = os.path.splitext(image)[1].lower().lstrip(".")
            mime_map = {"jpg": "jpeg", "jpeg": "jpeg", "png": "png", "webp": "webp"}
            mime = mime_map.get(ext, "jpeg")
            image = f"data:image/{mime};base64,{img_b64}"

        url = f"{KLING_API_BASE}/videos/image2video"
        payload = {
            "model_name": model,
            "image": image,
            "prompt": prompt,
            "mode": mode,
            "duration": str(duration),
            "negative_prompt": negative_prompt,
            "cfg_scale": cfg_scale,
        }
        if image_tail:
            if os.path.isfile(image_tail):
                with open(image_tail, "rb") as f:
                    tail_b64 = base64.b64encode(f.read()).decode()
                ext = os.path.splitext(image_tail)[1].lower().lstrip(".")
                mime_map = {"jpg": "jpeg", "jpeg": "jpeg", "png": "png", "webp": "webp"}
                mime = mime_map.get(ext, "jpeg")
                image_tail = f"data:image/{mime};base64,{tail_b64}"
            payload["image_tail"] = image_tail

        resp = requests.post(url, json=payload, headers=self._headers(), timeout=30)
        data = resp.json()
        if data.get("code") != 0:
            raise RuntimeError(f"Kling image2video error [{data.get('code')}]: {data.get('message', data)}")
        task_id = data["data"]["task_id"]
        logger.info(f"🖼️ image2video 任务创建: {task_id} | {mode} | {prompt[:60] if prompt else '(no prompt)'}")
        return task_id

    # ---- 查询 ----

    def query_task(self, task_id: str) -> Dict:
        """查询单个任务状态 (自动判断 text2video / image2video)"""
        # 尝试 text2video
        url = f"{KLING_API_BASE}/videos/text2video/{task_id}"
        resp = requests.get(url, headers=self._headers(), timeout=15)
        data = resp.json()
        if data.get("code") == 0:
            return data
        # 尝试 image2video
        url = f"{KLING_API_BASE}/videos/image2video/{task_id}"
        resp = requests.get(url, headers=self._headers(), timeout=15)
        return resp.json()

    def list_tasks(self, page: int = 1, page_size: int = 20) -> Dict:
        """列出所有视频任务"""
        url = f"{KLING_API_BASE}/videos/text2video"
        params = {"pageNum": page, "pageSize": page_size}
        resp = requests.get(url, params=params, headers=self._headers(), timeout=15)
        return resp.json()

    # ---- 等待完成 ----

    def wait_for_completion(
        self, task_id: str, timeout: int = 900, poll_interval: int = 5
    ) -> Tuple[str, float]:
        """
        等待任务完成，返回 (视频下载URL, 耗时秒数)
        """
        start = time.time()
        while time.time() - start < timeout:
            result = self.query_task(task_id)
            data = result.get("data", {})
            status = data.get("task_status", "")

            if status == "succeed":
                elapsed = time.time() - start
                videos = data.get("task_result", {}).get("videos", [])
                if not videos:
                    raise RuntimeError(f"任务成功但无视频: {task_id}")
                video_url = videos[0]["url"]
                logger.info(f"✅ 任务完成: {task_id} (耗时 {elapsed:.0f}s)")
                return video_url, elapsed
            elif status in ("failed", "error"):
                err_msg = data.get("task_status_msg", str(result))
                raise RuntimeError(f"Kling 任务失败 [{task_id}]: {err_msg}")

            logger.debug(f"⏳ 等待 {task_id}... ({status})")
            time.sleep(poll_interval)

        raise TimeoutError(f"Kling 任务超时 [{task_id}] ({timeout}s)")

    # ---- 下载 ----

    def download_video(self, video_url: str, output_path: str) -> str:
        """下载视频文件"""
        resp = requests.get(video_url, timeout=120)
        os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
        with open(output_path, "wb") as f:
            f.write(resp.content)
        logger.info(f"💾 已保存: {output_path} ({len(resp.content) / 1024 / 1024:.1f}MB)")
        return output_path

    # ---- 一键生成 ----

    def generate_video(
        self,
        params: KlingVideoParams,
        output_path: str,
    ) -> KlingVideoResult:
        """
        完整流程：提交 → 等待 → 下载
        
        Args:
            params: 视频参数
            output_path: 输出路径
        
        Returns:
            KlingVideoResult
        """
        t0 = time.time()

        # 判断图生视频 or 文生视频
        if params.image_url:
            task_id = self.image_to_video(
                image=params.image_url,
                prompt=params.prompt,
                duration=params.duration,
                model=params.model,
                mode=params.mode,
                negative_prompt=params.negative_prompt,
                cfg_scale=params.cfg_scale,
                image_tail=params.image_tail_url,
            )
        else:
            task_id = self.text_to_video(
                prompt=params.prompt,
                duration=params.duration,
                model=params.model,
                mode=params.mode,
                aspect_ratio=params.aspect_ratio,
                negative_prompt=params.negative_prompt,
                cfg_scale=params.cfg_scale,
            )

        video_url, _ = self.wait_for_completion(task_id)
        self.download_video(video_url, output_path)

        return KlingVideoResult(
            task_id=task_id,
            video_url=video_url,
            local_path=output_path,
            duration=time.time() - t0,
            status="succeed",
        )


# ============================================================
# 分镜生成器 (LLM)
# ============================================================

STORYBOARD_PROMPT_TEMPLATE = """你是一个专业的{style}短视频导演。根据用户的视频主题，生成一个分镜脚本。

要求：
1. 生成 {scene_count} 个分镜场景
2. 每个场景包含：
   - scene_id: 序号
   - narration: 该场景的旁白/配音文案 (20-40字中文)
   - visual_prompt: 画面描述，必须是英文，用于AI视频生成 (15-30个单词)
     如果提供了参考图片，visual_prompt 应描述"让图片中的主体如何动起来"，如：
     "The product in the image slowly rotates on a display stand, soft studio lighting, commercial product photography style, clean background"
   - duration: 该场景时长，单位秒 (建议 {duration_per_scene} 秒)
   - camera: 建议的运镜方式 (可选): static/zoom_in/zoom_out/pan_left/pan_right/tilt_up/horizontal
3. 所有场景的 narration 连起来是一个完整流畅的叙事
4. 所有场景的 visual_prompt 必须各不相同，描述不同的画面/角度
5. 返回纯 JSON 数组，不要 markdown 标记

视频主题: {video_subject}
{image_context}

输出格式:
[
  {{
    "scene_id": 1,
    "narration": "第一段旁白文案",
    "visual_prompt": "English visual description for AI video generation",
    "duration": {duration_per_scene},
    "camera": "zoom_in"
  }},
  ...
]

只返回 JSON 数组，不要任何其他文字。"""


def generate_storyboard(
    video_subject: str,
    scene_count: int = 5,
    duration_per_scene: int = 5,
    style: str = "电商广告",
    has_reference_image: bool = False,
) -> List[Dict]:
    """使用 Turbo LLM 生成分镜脚本"""
    from app.services.llm import _generate_response

    image_context = ""
    if has_reference_image:
        image_context = "注意：用户已上传参考图片（如商品图），每个 visual_prompt 应描述基于图片的动态效果。"

    prompt = STORYBOARD_PROMPT_TEMPLATE.format(
        style=style,
        scene_count=scene_count,
        duration_per_scene=duration_per_scene,
        video_subject=video_subject,
        image_context=image_context,
    )

    logger.info(f"🎬 生成分镜: {video_subject} ({scene_count}场景)")

    for attempt in range(3):
        try:
            response = _generate_response(prompt=prompt)
            response = response.strip()
            if response.startswith("```"):
                response = response.split("\n", 1)[1]
                if response.endswith("```"):
                    response = response[:-3]

            storyboard = json.loads(response)
            logger.info(f"✅ 分镜生成: {len(storyboard)} 场景")
            return storyboard
        except json.JSONDecodeError as e:
            logger.warning(f"JSON解析失败 (attempt {attempt+1}): {e}")
            if attempt == 2:
                raise
        except Exception as e:
            logger.error(f"分镜生成失败: {e}")
            raise

    return []


# ============================================================
# 完整视频合成流水线
# ============================================================

def compose_storyboard_video(
    storyboard: List[Dict],
    kling_client: KlingClient,
    output_dir: str,
    mode: QualityMode = "std",
    model: ModelName = "kling-v1-6",
    aspect_ratio: AspectRatio = "16:9",
    reference_image: Optional[str] = None,
    voice_name: str = "zh-CN-XiaoxiaoNeural",
) -> str:
    """
    完整流水线：分镜 → Kling生成 → TTS配音 → ffmpeg拼接
    
    Args:
        storyboard: 分镜列表
        kling_client: Kling 客户端
        output_dir: 输出目录
        mode: std/pro
        model: 模型版本
        aspect_ratio: 画面比例
        reference_image: 参考图片路径 (用于图生视频模式)
        voice_name: TTS 音色
    
    Returns:
        最终视频路径
    """
    import subprocess
    from app.services.voice import tts

    ffmpeg_bin = "ffmpeg"
    try:
        import imageio_ffmpeg
        ffmpeg_bin = imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        pass

    os.makedirs(output_dir, exist_ok=True)
    scene_videos = []

    # ---- Step 1: 每场景生成视频 ----
    for scene in storyboard:
        scene_id = scene["scene_id"]
        visual_prompt = scene["visual_prompt"]
        duration = scene.get("duration", 5)
        camera = scene.get("camera", None)

        video_path = os.path.join(output_dir, f"scene_{scene_id:02d}.mp4")

        if os.path.exists(video_path):
            logger.info(f"⏭️ 场景 {scene_id} 已存在，跳过")
            scene_videos.append(video_path)
            continue

        logger.info(f"🎥 场景 {scene_id}/{len(storyboard)}: {visual_prompt[:60]}...")

        params = KlingVideoParams(
            prompt=visual_prompt,
            duration=duration,
            model=model,
            mode=mode,
            aspect_ratio=aspect_ratio,
            image_url=reference_image,
        )

        # 运镜控制
        camera_map = {
            "zoom_in": {"type": "simple", "config": {"mode": "zoom_in"}},
            "zoom_out": {"type": "simple", "config": {"mode": "zoom_out"}},
            "pan_left": {"type": "simple", "config": {"mode": "pan_left"}},
            "pan_right": {"type": "simple", "config": {"mode": "pan_right"}},
            "tilt_up": {"type": "simple", "config": {"mode": "tilt_up"}},
            "horizontal": {"type": "simple", "config": {"mode": "horizontal"}},
            "vertical": {"type": "simple", "config": {"mode": "vertical"}},
        }

        if camera and camera in camera_map:
            # 文生视频才用 camera_control，图生视频用 prompt 描述动态
            if not reference_image:
                task_id = kling_client.text_to_video(
                    prompt=params.prompt,
                    duration=params.duration,
                    model=params.model,
                    mode=params.mode,
                    aspect_ratio=params.aspect_ratio,
                    negative_prompt=params.negative_prompt,
                    cfg_scale=params.cfg_scale,
                    camera_control=camera_map[camera],
                )
            else:
                task_id = kling_client.image_to_video(
                    image=reference_image,
                    prompt=params.prompt,
                    duration=params.duration,
                    model=params.model,
                    mode=params.mode,
                )
        else:
            task_id = kling_client.text_to_video(
                prompt=params.prompt,
                duration=params.duration,
                model=params.model,
                mode=params.mode,
                aspect_ratio=params.aspect_ratio,
            ) if not reference_image else kling_client.image_to_video(
                image=reference_image,
                prompt=params.prompt,
                duration=params.duration,
                model=params.model,
                mode=params.mode,
            )

        video_url, elapsed = kling_client.wait_for_completion(task_id)
        kling_client.download_video(video_url, video_path)
        scene_videos.append(video_path)
        logger.info(f"  ✅ 场景 {scene_id} 完成 ({elapsed:.0f}s)")

    # ---- Step 2: TTS 配音 ----
    full_narration = " ".join(s["narration"] for s in storyboard)
    audio_path = os.path.join(output_dir, "narration.mp3")

    tts(
        text=full_narration,
        voice_name=voice_name,
        voice_rate=1.0,
        voice_file=audio_path,
        voice_volume=1.0,
    )
    logger.info(f"🔊 配音完成: {audio_path}")

    # ---- Step 3: ffmpeg 拼接 ----
    concat_file = os.path.join(output_dir, "concat_list.txt")
    with open(concat_file, "w") as f:
        for v in scene_videos:
            f.write(f"file '{os.path.abspath(v)}'\n")

    temp_video = os.path.join(output_dir, "temp_combined.mp4")
    subprocess.run(
        [ffmpeg_bin, "-y", "-f", "concat", "-safe", "0", "-i", concat_file,
         "-c", "copy", temp_video],
        check=True, capture_output=True,
    )

    # ---- Step 4: 合成音频 ----
    final_video = os.path.join(output_dir, "final_storyboard.mp4")
    subprocess.run(
        [ffmpeg_bin, "-y", "-i", temp_video, "-i", audio_path,
         "-c:v", "copy", "-c:a", "aac", "-shortest",
         "-map", "0:v:0", "-map", "1:a:0", final_video],
        check=True, capture_output=True,
    )

    # 清理
    os.remove(concat_file)
    os.remove(temp_video)

    logger.info(f"🎉 最终视频: {final_video}")
    return final_video


# ============================================================
# 一键生成入口
# ============================================================

def generate(
    video_subject: str,
    scene_count: int = 5,
    output_dir: str = None,
    mode: QualityMode = "std",
    model: ModelName = "kling-v1-6",
    aspect_ratio: AspectRatio = "16:9",
    reference_image: Optional[str] = None,
    voice_name: str = "zh-CN-XiaoxiaoNeural",
    access_key: str = None,
    secret_key: str = None,
) -> str:
    """
    一键生成分镜叙事视频
    
    Args:
        video_subject: 视频主题
        scene_count: 分镜数
        output_dir: 输出目录
        mode: std(标准) / pro(高画质)
        model: 模型版本
        aspect_ratio: 画面比例
        reference_image: 参考图片(图生视频)
        voice_name: TTS 音色
    
    Returns:
        最终视频路径
    """
    if output_dir is None:
        output_dir = f"/tmp/kling_video_{int(time.time())}"

    # 1. 分镜
    logger.info(f"🎬 开始: {video_subject} ({mode}/{aspect_ratio}/{model})")
    storyboard = generate_storyboard(
        video_subject=video_subject,
        scene_count=scene_count,
        has_reference_image=bool(reference_image),
    )

    storyboard_path = os.path.join(output_dir, "storyboard.json")
    with open(storyboard_path, "w", encoding="utf-8") as f:
        json.dump(storyboard, f, ensure_ascii=False, indent=2)

    # 2. Kling
    client = KlingClient(
        access_key=access_key or KLING_ACCESS_KEY,
        secret_key=secret_key or KLING_SECRET_KEY,
    )

    # 3. 合成
    final = compose_storyboard_video(
        storyboard=storyboard,
        kling_client=client,
        output_dir=output_dir,
        mode=mode,
        model=model,
        aspect_ratio=aspect_ratio,
        reference_image=reference_image,
        voice_name=voice_name,
    )

    logger.success(f"✅ 完成! {final}")
    return final


if __name__ == "__main__":
    import sys
    subject = sys.argv[1] if len(sys.argv) > 1 else "深海磷虾油广告"
    scenes = int(sys.argv[2]) if len(sys.argv) > 2 else 5
    output = sys.argv[3] if len(sys.argv) > 3 else None
    generate(video_subject=subject, scene_count=scenes, output_dir=output)
