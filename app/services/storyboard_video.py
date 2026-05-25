"""
分镜式视频组装器 — 每个分镜独立素材，顺序拼接

集成到 MoneyPrinterTurbo，支持两种模式：
  1. Pexels 搜素材模式（和 Turbo 原始逻辑一致，但按分镜拆分）
  2. Kling API 文生视频模式（每个分镜 AI 生成专属画面）
"""

import os
import random
import shutil
import json
from typing import List, Dict, Optional

from loguru import logger
from moviepy import (
    AudioFileClip,
    ColorClip,
    CompositeAudioClip,
    CompositeVideoClip,
    ImageClip,
    TextClip,
    VideoFileClip,
    afx,
)
from moviepy.video.tools.subtitles import SubtitlesClip
from PIL import Image, ImageFont

from app.models.schema import (
    MaterialInfo,
    VideoAspect,
    VideoConcatMode,
    VideoParams,
    VideoTransitionMode,
)
from app.services import material as material_service
from app.services.utils import video_effects
from app.services.video import (
    _open_video_clip_quietly,
    _open_image_clip_with_fallback,
    close_clip,
    preprocess_video,
    get_ffmpeg_binary,
)

fps = 30
video_codec = "libx264"
audio_codec = "aac"


def compose_storyboard_video(
    storyboard: List[Dict],
    video_params: VideoParams,
    output_dir: str,
    use_kling: bool = False,
    kling_client=None,
    background_music: Optional[str] = None,
) -> str:
    """
    分镜式视频组装

    Args:
        storyboard: LLM 生成的分镜列表
        video_params: 视频参数
        output_dir: 输出目录
        use_kling: 是否使用 Kling API 生成画面
        kling_client: KlingClient 实例
        background_music: 背景音乐路径

    Returns:
        最终视频路径
    """
    video_width, video_height = video_params.video_aspect.to_resolution()

    # ============================================================
    # Step 1: 为每个分镜获取素材
    # ============================================================
    scene_clips = []

    for i, scene in enumerate(storyboard):
        scene_id = scene.get("scene_id", i + 1)
        visual_prompt = scene.get("visual_prompt", "")
        duration = scene.get("duration", 5)
        narration = scene.get("narration", "")

        logger.info(f"分镜 {scene_id}/{len(storyboard)}: {visual_prompt[:60]}")

        scene_video_path = None

        if use_kling and kling_client:
            # Kling API 生成视频
            scene_video_path = os.path.join(
                output_dir, f"scene_{scene_id:02d}_kling.mp4"
            )
            if not os.path.exists(scene_video_path):
                try:
                    kling_client.generate_video(
                        prompt=visual_prompt,
                        output_path=scene_video_path,
                        duration=min(duration, 5),
                    )
                    logger.info(f"  分镜 {scene_id} Kling 完成")
                except Exception as e:
                    logger.error(f"  分镜 {scene_id} Kling 失败: {e}, 回退到 Pexels")
                    scene_video_path = None

        if not scene_video_path:
            # Pexels 搜素材
            search_terms = [visual_prompt]
            # 把英文 visual_prompt 拆成 1-3 个搜索词
            words = visual_prompt.split()
            if len(words) > 4:
                search_terms = [
                    " ".join(words[:3]),
                    " ".join(words[2:5]),
                    " ".join(words[-3:]),
                ]

            materials = []
            for term in search_terms[:2]:
                try:
                    results = material_service.search_videos_pexels(
                        search_term=term,
                        minimum_duration=duration,
                        video_aspect=video_params.video_aspect,
                    )
                    materials.extend(results[:3])
                except Exception as e:
                    logger.warning(f"  Pexels 搜索失败 '{term}': {e}")

            if not materials:
                logger.warning(f"  分镜 {scene_id}: 无素材，跳过")
                continue

            # 预处理素材
            scene_output_dir = os.path.join(output_dir, f"scene_{scene_id:02d}")
            os.makedirs(scene_output_dir, exist_ok=True)
            processed = preprocess_video(
                materials=materials, clip_duration=duration + 1
            )
            if processed:
                scene_video_path = processed[0]
            else:
                continue

        scene_clips.append(
            {
                "path": scene_video_path,
                "narration": narration,
                "duration": duration,
                "scene_id": scene_id,
            }
        )

    if not scene_clips:
        raise RuntimeError("没有生成任何场景素材")

    # ============================================================
    # Step 2: 生成完整配音  
    # ============================================================
    full_narration = " ".join(s["narration"] for s in scene_clips)
    audio_path = os.path.join(output_dir, "narration.mp3")

    from app.services import voice

    voice.tts(
        text=full_narration,
        voice_name=video_params.voice_name,
        voice_rate=video_params.voice_rate,
        voice_file=audio_path,
        voice_volume=video_params.voice_volume,
    )
    logger.info(f"配音完成: {audio_path}")

    # ============================================================
    # Step 3: 顺序拼接 + 字幕 + BGM
    # ============================================================
    return _assemble_scenes(
        scene_clips=scene_clips,
        audio_path=audio_path,
        video_params=video_params,
        output_dir=output_dir,
        background_music=background_music,
    )


def _assemble_scenes(
    scene_clips: List[Dict],
    audio_path: str,
    video_params: VideoParams,
    output_dir: str,
    background_music: Optional[str] = None,
) -> str:
    """
    将分镜素材按顺序拼接，加配音 + 字幕 + BGM
    """
    video_width, video_height = video_params.video_aspect.to_resolution()

    # --- 字幕生成 ---
    subtitle_path = None
    if video_params.subtitle_enabled:
        subtitle_path = os.path.join(output_dir, "subtitle.srt")
        from app.services import voice as voice_service
        # 用 edge_tts 生成字幕（复用已有逻辑）
        try:
            from app.services.voice import _azure_tts_v1
            _azure_tts_v1(
                text=" ".join(s["narration"] for s in scene_clips),
                voice_name=video_params.voice_name,
                voice_rate=video_params.voice_rate,
                voice_file=audio_path,
                voice_volume=video_params.voice_volume,
                subtitle_file=subtitle_path,
            )
        except Exception as e:
            logger.warning(f"字幕生成失败: {e}")
            subtitle_path = None

    # --- 组装视频片段 ---
    assembled_clips = []

    for scene in scene_clips:
        clip_path = scene["path"]
        duration = scene.get("duration", 5)

        try:
            clip = VideoFileClip(clip_path).without_audio()
        except Exception:
            clip = ImageClip(clip_path).with_duration(duration)

        # 调整尺寸
        if clip.w != video_width or clip.h != video_height:
            clip = clip.resized(new_size=(video_width, video_height))

        if clip.duration > duration:
            clip = clip.subclipped(0, duration)

        assembled_clips.append(clip)

    # 拼接
    if len(assembled_clips) == 1:
        video_clip = assembled_clips[0]
    else:
        video_clip = CompositeVideoClip([
            assembled_clips[0],
            *[c.with_start(sum(s.duration for s in assembled_clips[:i]))
              for i, c in enumerate(assembled_clips[1:], 1)]
        ])

    # --- 字幕叠加 ---
    if subtitle_path and os.path.exists(subtitle_path):
        from app.services.video import create_text_clip as _make_clip_func
        # 简化版字幕
        try:
            sub = SubtitlesClip(
                subtitles=subtitle_path,
                encoding="utf-8",
                make_textclip=lambda txt: TextClip(
                    text=txt,
                    font=video_params.font_name or "MicrosoftYaHei",
                    font_size=video_params.font_size,
                    color=video_params.text_fore_color or "#FFFFFF",
                    stroke_color=video_params.stroke_color or "#000000",
                    stroke_width=video_params.stroke_width or 1.5,
                ),
            )
            video_clip = CompositeVideoClip([video_clip, sub.with_position("center")])
        except Exception as e:
            logger.warning(f"字幕叠加失败: {e}")

    # --- 音频 ---
    audio_clip = AudioFileClip(audio_path)
    if video_clip.duration > audio_clip.duration:
        audio_clip = audio_clip.with_effects([afx.AudioLoop(duration=video_clip.duration)])

    # --- BGM ---
    if background_music and os.path.exists(background_music):
        bgm = AudioFileClip(background_music).with_effects([
            afx.MultiplyVolume(0.2),
            afx.AudioLoop(duration=video_clip.duration),
        ])
        audio_clip = CompositeAudioClip([audio_clip, bgm])

    video_clip = video_clip.with_audio(audio_clip)

    # --- 输出 ---
    final_path = os.path.join(output_dir, "final_storyboard.mp4")
    video_clip.write_videofile(
        final_path,
        fps=fps,
        codec=video_codec,
        audio_codec=audio_codec,
        threads=2,
        logger=None,
    )

    # 清理
    video_clip.close()
    for c in assembled_clips:
        try:
            c.close()
        except Exception:
            pass

    logger.success(f"最终视频: {final_path}")
    return final_path
