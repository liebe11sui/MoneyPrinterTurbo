"""
Inference.sh 多模型视频引擎 — 集成到 MoneyPrinterTurbo
======================================================

提供 40+ AI 视频模型作为 Kling 之外的备选引擎。
通过 belt CLI 调用 inference.sh 云平台。

支持模型:
  - google/veo-3-1-fast    — 谷歌 Veo，快速文生视频
  - bytedance/seedance-2-0  — 字节 Seedance (抖音同门！)
  - alibaba/happyhorse-1-0  — 阿里 HappyHorse
  - falai/wan-2-5          — Wan 图生视频
  - pruna/p-video          — 经济实惠方案

用法:
    from app.services.inference_video import InferenceVideoEngine
    engine = InferenceVideoEngine()
    result = engine.text_to_video("a cat walking", model="google/veo-3-1-fast")

依赖:
    belt CLI: curl -fsSL cli.inference.sh | sh
    登录: belt login
"""

import json
import os
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Optional, Dict, List
from dataclasses import dataclass
from loguru import logger

# ============================================================
# 模型注册表
# ============================================================

@dataclass
class VideoModel:
    """视频模型定义"""
    id: str
    name: str
    provider: str
    mode: str           # "t2v" | "i2v" | "both"
    description: str
    tags: Optional[List[str]] = None

# 常用模型（来自 skills.sh 排行榜 + 电商场景精选）
MODELS: Dict[str, VideoModel] = {
    # --- 文生视频 ---
    "google/veo-3-1-fast": VideoModel(
        id="google/veo-3-1-fast", name="Veo 3.1 Fast", provider="Google",
        mode="t2v", description="最快文生视频，可带音频", tags=["fast", "audio"]),
    "google/veo-3-1": VideoModel(
        id="google/veo-3-1", name="Veo 3.1", provider="Google",
        mode="t2v", description="最佳画质文生视频", tags=["quality"]),
    "bytedance/seedance-2-0": VideoModel(
        id="bytedance/seedance-2-0", name="Seedance 2.0", provider="ByteDance",
        mode="both", description="字节跳动视频模型，支持文/图生视频+同步音频，1080p",
        tags=["douyin", "both", "audio", "1080p"]),
    "bytedance/seedance-2-0-fast": VideoModel(
        id="bytedance/seedance-2-0-fast", name="Seedance 2.0 Fast", provider="ByteDance",
        mode="both", description="Seedance 快速版", tags=["douyin", "fast"]),
    "alibaba/happyhorse-1-0-t2v": VideoModel(
        id="alibaba/happyhorse-1-0-t2v", name="HappyHorse T2V", provider="Alibaba",
        mode="t2v", description="阿里物理级真实视频，最长15秒", tags=["realistic", "15s"]),
    "alibaba/happyhorse-1-0-i2v": VideoModel(
        id="alibaba/happyhorse-1-0-i2v", name="HappyHorse I2V", provider="Alibaba",
        mode="i2v", description="图生视频，1080P/15秒", tags=["i2v", "1080p"]),
    "xai/grok-imagine-video": VideoModel(
        id="xai/grok-imagine-video", name="Grok Video", provider="xAI",
        mode="t2v", description="马斯克 xAI 视频模型", tags=["configurable"]),
    # --- 图生视频 ---
    "falai/wan-2-5": VideoModel(
        id="falai/wan-2-5", name="Wan 2.5", provider="FAL",
        mode="i2v", description="高质量图生视频", tags=["i2v", "quality"]),
    "falai/wan-2-5-i2v": VideoModel(
        id="falai/wan-2-5-i2v", name="Wan 2.5 I2V", provider="FAL",
        mode="i2v", description="专用图生视频模型", tags=["i2v"]),
    # --- 经济实惠 ---
    "pruna/p-video": VideoModel(
        id="pruna/p-video", name="P-Video", provider="Pruna",
        mode="both", description="快速经济方案，支持音频", tags=["cheap", "fast", "both"]),
    "pruna/wan-t2v": VideoModel(
        id="pruna/wan-t2v", name="WAN T2V", provider="Pruna",
        mode="t2v", description="经济 480p/720p 文生视频", tags=["cheap"]),
    # --- 数字人/唇形同步 ---
    "bytedance/omnihuman-1-5": VideoModel(
        id="bytedance/omnihuman-1-5", name="OmniHuman 1.5", provider="ByteDance",
        mode="i2v", description="多人物数字人，图片+音频→说话视频", tags=["avatar", "lipsync"]),
    "falai/fabric-1-0": VideoModel(
        id="falai/fabric-1-0", name="Fabric 1.0", provider="FAL",
        mode="i2v", description="图片说话，唇形同步", tags=["avatar", "lipsync"]),
    # --- 视频编辑 ---
    "alibaba/happyhorse-1-0-video-edit": VideoModel(
        id="alibaba/happyhorse-1-0-video-edit", name="HappyHorse Edit", provider="Alibaba",
        mode="i2v", description="自然语言视频编辑", tags=["edit"]),
    # --- 工具 ---
    "falai/topaz-video-upscaler": VideoModel(
        id="falai/topaz-video-upscaler", name="Topaz Upscaler", provider="FAL",
        mode="util", description="视频超分辨率", tags=["upscale"]),
    "infsh/hunyuanvideo-foley": VideoModel(
        id="infsh/hunyuanvideo-foley", name="Hunyuan Foley", provider="Tencent",
        mode="util", description="给视频加音效", tags=["audio", "foley"]),
}

# 推荐用于抖音电商场景的模型
DOUYIN_RECOMMENDED = [
    "bytedance/seedance-2-0",        # 字节自家，1080p，文+图生视频
    "bytedance/seedance-2-0-fast",   # 快速版
    "alibaba/happyhorse-1-0-t2v",    # 阿里，物理级真实
    "alibaba/happyhorse-1-0-i2v",    # 图生视频，商品展示
    "falai/wan-2-5",                 # 高质量图生视频
    "pruna/p-video",                 # 经济实惠
]

# ============================================================
# 引擎
# ============================================================

class InferenceVideoEngine:
    """Inference.sh 视频引擎 — belt CLI 包装器"""

    def __init__(self, belt_bin: str = None):
        self.belt_bin = belt_bin or self._find_belt()

    @staticmethod
    def _find_belt() -> str:
        for path in ["belt", "infsh", "inferencesh",
                     os.path.expanduser("~/.local/bin/belt")]:
            if subprocess.run(["which", path], capture_output=True).returncode == 0:
                return path
        return "belt"  # fallback

    def _run(self, args: List[str], timeout: int = 600) -> dict:
        """执行 belt 命令，返回 JSON"""
        cmd = [self.belt_bin] + args + ["--json"]
        logger.debug(f"belt: {' '.join(cmd)}")

        result = subprocess.run(
            cmd,
            capture_output=True, text=True, timeout=timeout,
            env={**os.environ, "http_proxy": os.environ.get("http_proxy", ""),
                 "https_proxy": os.environ.get("https_proxy", "")},
        )

        if result.returncode != 0:
            stderr = result.stderr.strip()
            if "not logged in" in stderr:
                raise RuntimeError("belt 未登录！运行: belt login")
            raise RuntimeError(f"belt error: {stderr}")

        try:
            return json.loads(result.stdout) if result.stdout.strip() else {}
        except json.JSONDecodeError:
            logger.warning(f"belt 非 JSON 输出: {result.stdout[:200]}")
            return {"raw": result.stdout}

    def is_logged_in(self) -> bool:
        """检查登录状态"""
        try:
            result = subprocess.run(
                [self.belt_bin, "me", "--json"],
                capture_output=True, text=True, timeout=10,
            )
            return result.returncode == 0
        except Exception:
            return False

    def text_to_video(
        self,
        prompt: str,
        model: str = "bytedance/seedance-2-0",
        duration: int = 5,
        output_path: str = None,
        negative_prompt: str = "",
        **kwargs,
    ) -> str:
        """
        文生视频
        
        Args:
            prompt: 画面描述（英文）
            model: 模型 ID
            duration: 时长(秒)
            output_path: 输出路径，不指定则自动生成
            negative_prompt: 负面提示
        
        Returns:
            输出视频路径
        """
        input_data = {"prompt": prompt}
        if duration:
            input_data["duration"] = duration
        if negative_prompt:
            input_data["negative_prompt"] = negative_prompt
        input_data.update(kwargs)

        logger.info(f"🎬 inference.sh t2v: {model} | {prompt[:60]}...")

        result = self._run([
            "app", "run", model,
            "--input", json.dumps(input_data),
        ], timeout=600)

        return self._extract_video(result, output_path)

    def image_to_video(
        self,
        image_path: str,
        prompt: str = "",
        model: str = "falai/wan-2-5",
        duration: int = 5,
        output_path: str = None,
        **kwargs,
    ) -> str:
        """
        图生视频
        
        Args:
            image_path: 图片路径或 URL
            prompt: 动态描述
            model: 模型 ID
            duration: 时长
            output_path: 输出路径
        
        Returns:
            输出视频路径
        """
        input_data = {}
        # 判断是本地文件还是 URL
        if image_path.startswith(("http://", "https://")):
            input_data["image_url"] = image_path
        else:
            input_data["image_url"] = image_path  # belt 也接受本地路径
        
        if prompt:
            input_data["prompt"] = prompt
        if duration:
            input_data["duration"] = duration
        input_data.update(kwargs)

        logger.info(f"🖼️ inference.sh i2v: {model} | {image_path[:60]}...")

        result = self._run([
            "app", "run", model,
            "--input", json.dumps(input_data),
        ], timeout=600)

        return self._extract_video(result, output_path)

    def _extract_video(self, result: dict, output_path: str = None) -> str:
        """从 belt 结果中提取/下载视频"""
        # belt 返回格式通常是 {"output": {"video_url": "..."}} 或类似
        video_url = None

        # 尝试多种可能的字段
        if isinstance(result, dict):
            for key in ("video_url", "url", "output_url", "result_url"):
                if key in result:
                    video_url = result[key]
                    break
            # 嵌套查找
            for key in ("output", "result", "data"):
                if key in result and isinstance(result[key], dict):
                    for sub in ("video_url", "url"):
                        if sub in result[key]:
                            video_url = result[key][sub]
                            break

        if not video_url:
            # belt 可能把结果保存为文件
            if "result_file" in result:
                video_url = result["result_file"]
            else:
                logger.warning(f"无法从结果提取视频 URL: {json.dumps(result, indent=2)[:500]}")
                raise RuntimeError("belt 返回结果中未找到视频 URL")

        # 下载
        if output_path is None:
            output_path = os.path.join(
                tempfile.gettempdir(),
                f"infsh_video_{int(time.time())}.mp4"
            )

        if video_url.startswith(("http://", "https://")):
            import requests
            resp = requests.get(video_url, timeout=120)
            os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
            with open(output_path, "wb") as f:
                f.write(resp.content)
            logger.info(f"💾 已保存: {output_path} ({len(resp.content)/1024/1024:.1f}MB)")
        else:
            # 本地路径，直接复制
            import shutil
            shutil.copy(video_url, output_path)

        return output_path

    def upscale_video(self, video_path: str, output_path: str = None) -> str:
        """视频超分辨率"""
        logger.info(f"🔍 upscaling: {video_path}")
        result = self._run([
            "app", "run", "falai/topaz-video-upscaler",
            "--input", json.dumps({"video_url": video_path}),
        ])
        return self._extract_video(result, output_path)

    def add_sound_effects(self, video_path: str, sound_prompt: str, output_path: str = None) -> str:
        """给视频加音效"""
        result = self._run([
            "app", "run", "infsh/hunyuanvideo-foley",
            "--input", json.dumps({
                "video_url": video_path,
                "prompt": sound_prompt,
            }),
        ])
        return self._extract_video(result, output_path)


# ============================================================
# 快捷函数
# ============================================================

def get_models_for_mode(mode: str = "all") -> List[VideoModel]:
    """获取指定模式的模型列表"""
    if mode == "all":
        return list(MODELS.values())
    if mode == "douyin":
        return [MODELS[m] for m in DOUYIN_RECOMMENDED if m in MODELS]
    return [m for m in MODELS.values() if m.mode == mode or m.mode == "both"]


def get_model_choices(engine: str = "inference") -> List[tuple]:
    """
    获取 UI 可用的模型选择列表
    返回: [(显示名, 模型ID), ...]
    """
    if engine == "inference":
        models = get_models_for_mode("douyin")  # 抖音推荐优先
        return [(f"{m.name} ({m.provider}) - {m.description[:30]}", m.id) for m in models]
    elif engine == "kling":
        return [
            ("Kling v1-6 (推荐)", "kling-v1-6"),
            ("Kling v1-5", "kling-v1-5"),
            ("Kling v2 (最新)", "kling-v2"),
            ("Kling v2 Master", "kling-v2-master"),
        ]
    return []


if __name__ == "__main__":
    # 测试
    engine = InferenceVideoEngine()
    print(f"belt binary: {engine.belt_bin}")
    print(f"logged in: {engine.is_logged_in()}")
    print(f"\n抖音推荐模型:")
    for m in get_models_for_mode("douyin"):
        print(f"  {m.id:40s} {m.provider:10s} {m.description}")
