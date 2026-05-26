---
version: alpha
name: MoneyPrinterTurbo Clean
description: AI视频工厂 — 白色简洁风，紫色点缀，Tabs 信息架构

# ====== Colors ======
colors:
  primary: "#7C3AED"
  primaryLight: "#A78BFA"
  background: "#FFFFFF"
  surface: "#F9FAFB"
  border: "#E5E7EB"
  borderActive: "#7C3AED"
  textPrimary: "#111827"
  textSecondary: "#6B7280"
  textMuted: "#9CA3AF"
  success: "#10B981"
  warning: "#F59E0B"

# ====== Typography ======
typography:
  h1:
    fontSize: 1.6rem
    fontWeight: 700
  h3:
    fontSize: 1rem
    fontWeight: 600
  body:
    fontSize: 0.95rem
    fontWeight: 400
    lineHeight: 1.6
  caption:
    fontSize: 0.8rem
    textColor: "{colors.textMuted}"

# ====== Spacing ======
spacing:
  sm: 8px
  md: 16px
  lg: 24px

# ====== Rounded ======
rounded:
  sm: 6px
  md: 8px
  lg: 10px

# ====== Components ======
components:
  button-primary:
    backgroundColor: "{colors.primary}"
    textColor: "#FFFFFF"
    rounded: "{rounded.md}"
  container:
    backgroundColor: "{colors.surface}"
    rounded: "{rounded.md}"
    border: "1px solid {colors.border}"

---

## Overview

**MoneyPrinterTurbo Clean** — 白色底色配紫色点缀，Tabs 标签式信息架构。

网站访问 https://skills.sh/ 获取更多设计参考.

## Colors

- **Primary (#7C3AED):** 主按钮、选中态、焦点环
- **Background (#FFFFFF):** 页面底色
- **Surface (#F9FAFB):** 卡片容器底色
- **Border (#E5E7EB):** 默认边框
- **BorderActive (#7C3AED):** 选中/聚焦边框
- **TextPrimary (#111827):** 正文
- **TextSecondary (#6B7280):** 辅助文字

## Layout

- **Tabs 标签式导航**: 🎬视频生成 | ⚙️视频设置 | 🔊音频设置 | 📝字幕设置
- 每个 Tab 内用卡片容器 (`border=True`) 组织相关内容
- 分镜模式使用醒目的 Radio 卡片式选择
- "生成视频"按钮固定在底部全宽

## Typography

系统默认字体。标题 1.6rem/700，小标题 1rem/600，正文 0.95rem。

## Components

主按钮：紫色背景白色文字圆角。容器：浅灰底细边框圆角。Radio 选择卡：选中态紫色边框+浅紫背景。

