"""
Kling 可灵 + 分镜叙事视频生成模块
集成到 MoneyPrinterTurbo

用法:
    python -m app.services.kling_storyboard "深海磷虾油广告，5个场景"

工作流:
    主题 → LLM生成分镜JSON → 每个分镜调Kling API → 下载视频 → 拼接
"""

import json
import time
import os
import requests
from typing import List, Dict
from loguru import logger

# ============================================================
# Kling API 配置
# ============================================================
KLING_API_BASE = "https://api.klingai.com/v1"

# Access Key ID + Secret Key (从可灵开放平台获取)
KLING_ACCESS_KEY = os.environ.get("KLING_ACCESS_KEY", "你的AK")
KLING_SECRET_KEY = os.environ.get("KLING_SECRET_KEY", "你的SK")


# ============================================================
# Kling API 客户端
# ============================================================

class KlingClient:
    """可灵 API 客户端"""

    def __init__(self, access_key: str = None, secret_key: str = None):
        self.access_key = access_key or KLING_ACCESS_KEY
        self.secret_key = secret_key or KLING_SECRET_KEY
        self._token = None
        self._token_expires = 0

    def _get_token(self) -> str:
        """获取 JWT token"""
        if self._token and time.time() < self._token_expires:
            return self._token

        # 用 AK/SK 生成 JWT
        try:
            import jwt as pyjwt
        except ImportError:
            logger.error("请安装: pip install PyJWT")
            raise

        payload = {
            "iss": self.access_key,
            "exp": int(time.time()) + 1800,
            "nbf": int(time.time()) - 5,
        }
        headers = {"alg": "HS256", "typ": "JWT"}
        self._token = pyjwt.encode(payload, self.secret_key, headers=headers)
        self._token_expires = time.time() + 1700
        return self._token

    def _headers(self) -> Dict:
        return {
            "Authorization": f"Bearer {self._get_token()}",
            "Content-Type": "application/json",
        }

    def text_to_video(
        self,
        prompt: str,
        duration: int = 5,
        model: str = "kling-v1",
        negative_prompt: str = "",
        cfg_scale: float = 0.5,
    ) -> str:
        """
        文生视频 - 提交任务，返回 task_id
        """
        url = f"{KLING_API_BASE}/videos/text2video"
        payload = {
            "model_name": model,
            "prompt": prompt,
            "negative_prompt": negative_prompt,
            "cfg_scale": cfg_scale,
            "duration": duration,
        }
        resp = requests.post(url, json=payload, headers=self._headers(), timeout=30)
        data = resp.json()
        if data.get("code") != 0:
            raise RuntimeError(f"Kling API error: {data}")
        task_id = data["data"]["task_id"]
        logger.info(f"Kling 任务已创建: {task_id} (prompt: {prompt[:50]})")
        return task_id

    def query_task(self, task_id: str) -> Dict:
        """查询任务状态"""
        url = f"{KLING_API_BASE}/videos/text2video/{task_id}"
        resp = requests.get(url, headers=self._headers(), timeout=15)
        return resp.json()

    def wait_for_completion(
        self, task_id: str, timeout: int = 600, poll_interval: int = 5
    ) -> str:
        """
        等待任务完成，返回视频下载 URL
        """
        start = time.time()
        while time.time() - start < timeout:
            result = self.query_task(task_id)
            status = result.get("data", {}).get("task_status", "")

            if status == "succeed":
                video_url = result["data"]["task_result"]["videos"][0]["url"]
                logger.info(f"Kling 任务完成: {task_id}")
                return video_url
            elif status in ("failed", "error"):
                raise RuntimeError(f"Kling 任务失败: {result}")

            logger.debug(f"等待 Kling {task_id}... {status}")
            time.sleep(poll_interval)

        raise TimeoutError(f"Kling 任务超时: {task_id}")

    def generate_video(
        self, prompt: str, output_path: str, duration: int = 5, model: str = "kling-v1"
    ) -> str:
        """完整流程：提交 → 等待 → 下载 → 返回本地路径"""
        task_id = self.text_to_video(prompt, duration=duration, model=model)
        video_url = self.wait_for_completion(task_id)

        # 下载视频
        resp = requests.get(video_url, timeout=120)
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        with open(output_path, "wb") as f:
            f.write(resp.content)

        logger.info(f"视频已保存: {output_path}")
        return output_path


# ============================================================
# 分镜生成器 (使用现有 Turbo LLM)
# ============================================================

STORYBOARD_PROMPT = """你是一个专业的短视频导演。根据用户的视频主题，生成一个分镜脚本。

要求：
1. 生成 {scene_count} 个分镜场景
2. 每个场景包含：
   - scene_id: 序号
   - narration: 该场景的旁白/配音文案 (20-40字)
   - visual_prompt: 画面描述，必须是英文，用于AI视频生成 (10-20个单词，描述具体画面，如 "Antarctic iceberg under blue sky, cinematic wide shot")
   - duration: 该场景时长，单位秒 (建议 4-6 秒)
3. 所有场景的 narration 连起来是一个完整的叙事
4. 所有场景的 visual_prompt 必须各不相同，覆盖不同的画面
5. 返回纯 JSON 数组，不要 markdown 标记

视频主题: {video_subject}

输出格式:
[
  {{
    "scene_id": 1,
    "narration": "第一段旁白文案",
    "visual_prompt": "English visual description for AI video generation",
    "duration": 5
  }},
  ...
]

只返回 JSON 数组，不要任何其他文字。"""


def generate_storyboard(
    video_subject: str, scene_count: int = 5
) -> List[Dict]:
    """
    使用 Turbo 的 LLM 生成分镜脚本
    """
    from app.services.llm import _generate_response

    prompt = STORYBOARD_PROMPT.format(
        scene_count=scene_count,
        video_subject=video_subject,
    )

    logger.info(f"生成分镜脚本: {video_subject}")

    for attempt in range(3):
        try:
            response = _generate_response(prompt=prompt)
            # 清理可能出现的 markdown
            response = response.strip()
            if response.startswith("```"):
                response = response.split("\n", 1)[1]
                if response.endswith("```"):
                    response = response[:-3]

            storyboard = json.loads(response)
            logger.info(f"分镜生成成功: {len(storyboard)} 个场景")
            return storyboard
        except json.JSONDecodeError as e:
            logger.warning(f"JSON 解析失败 (attempt {attempt+1}): {e}")
            if attempt == 2:
                raise
        except Exception as e:
            logger.error(f"分镜生成失败: {e}")
            raise

    return []


# ============================================================
# 完整的视频生成流水线
# ============================================================

def compose_storyboard_video(
    storyboard: List[Dict],
    kling_client: KlingClient,
    output_dir: str,
    voice_name: str = "zh-CN-XiaoxiaoNeural",
) -> str:
    """
    完整流程：分镜 → Kling生成视频 → TTS配音 → 拼接

    返回最终视频路径
    """
    import subprocess
    from app.services.voice import tts

    scene_videos = []
    scene_audios = []
    ffmpeg_bin = "ffmpeg"
    
    # 尝试用 imageio-ffmpeg 的 ffmpeg
    try:
        import imageio_ffmpeg
        ffmpeg_bin = imageio_ffmpeg.get_ffmpeg_exe()
    except:
        pass

    os.makedirs(output_dir, exist_ok=True)

    # Step 1: 每个场景生成 AI 视频
    for scene in storyboard:
        scene_id = scene["scene_id"]
        visual_prompt = scene["visual_prompt"]
        duration = scene.get("duration", 5)

        video_path = os.path.join(output_dir, f"scene_{scene_id:02d}.mp4")
        logger.info(f"场景 {scene_id}: {visual_prompt[:60]}")

        if not os.path.exists(video_path):
            kling_client.generate_video(
                prompt=visual_prompt,
                output_path=video_path,
                duration=duration,
            )
        scene_videos.append(video_path)

    # Step 2: 生成完整旁白配音
    full_narration = " ".join(s["narration"] for s in storyboard)
    audio_path = os.path.join(output_dir, "narration.mp3")

    sub_maker = tts(
        text=full_narration,
        voice_name=voice_name,
        voice_rate=1.0,
        voice_file=audio_path,
        voice_volume=1.0,
    )
    logger.info(f"配音完成: {audio_path}")

    # Step 3: 用 ffmpeg concat 拼接所有场景视频
    concat_file = os.path.join(output_dir, "concat_list.txt")
    with open(concat_file, "w") as f:
        for v in scene_videos:
            f.write(f"file '{os.path.abspath(v)}'\n")

    temp_video = os.path.join(output_dir, "temp_combined.mp4")
    subprocess.run(
        [ffmpeg_bin, "-y", "-f", "concat", "-safe", "0", "-i", concat_file,
         "-c", "copy", temp_video],
        check=True,
        capture_output=True,
    )

    # Step 4: 合成音频到视频
    final_video = os.path.join(output_dir, "final_storyboard.mp4")
    subprocess.run(
        [ffmpeg_bin, "-y", "-i", temp_video, "-i", audio_path,
         "-c:v", "copy", "-c:a", "aac", "-shortest",
         "-map", "0:v:0", "-map", "1:a:0",
         final_video],
        check=True,
        capture_output=True,
    )

    # 清理临时文件
    os.remove(concat_file)
    os.remove(temp_video)

    logger.info(f"最终视频: {final_video}")
    return final_video


# ============================================================
# 一键生成入口
# ============================================================

def generate(
    video_subject: str,
    scene_count: int = 5,
    output_dir: str = None,
    voice_name: str = "zh-CN-XiaoxiaoNeural",
    access_key: str = None,
    secret_key: str = None,
) -> str:
    """
    一键生成分镜叙事视频

    Args:
        video_subject: 视频主题，如 "深海磷虾油广告，南极捕捞到成品"
        scene_count: 分镜数
        output_dir: 输出目录
        voice_name: 配音音色
        access_key: 可灵 AK
        secret_key: 可灵 SK

    Returns:
        最终视频路径
    """
    if output_dir is None:
        output_dir = f"/tmp/kling_video_{int(time.time())}"

    # 1. 生成分镜
    logger.info(f"🎬 开始生成: {video_subject}")
    storyboard = generate_storyboard(video_subject, scene_count)

    # 保存分镜
    storyboard_path = os.path.join(output_dir, "storyboard.json")
    with open(storyboard_path, "w", encoding="utf-8") as f:
        json.dump(storyboard, f, ensure_ascii=False, indent=2)
    logger.info(f"分镜已保存: {storyboard_path}")

    # 2. Kling 客户端
    client = KlingClient(
        access_key=access_key or KLING_ACCESS_KEY,
        secret_key=secret_key or KLING_SECRET_KEY,
    )

    # 3. 生成 + 合成
    final = compose_storyboard_video(
        storyboard=storyboard,
        kling_client=client,
        output_dir=output_dir,
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
