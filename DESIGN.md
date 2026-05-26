---
version: alpha
name: MoneyPrinterTurbo Dark
description: AI视频工厂 — 暗黑科技风，紫色渐变主色调，清晰的功能分区

# ====== Colors ======
colors:
  # 主色调 — 科技紫
  primary: "#7C3AED"
  primaryLight: "#A78BFA"
  primaryDark: "#5B21B6"

  # 强调色 — 青色，用于成功/激活
  accent: "#06B6D4"
  accentLight: "#22D3EE"

  # 警告/高亮 — 琥珀
  warning: "#F59E0B"
  error: "#EF4444"
  success: "#10B981"

  # 表面色
  surfacePrimary: "#0F0F1A"      # 最深背景
  surfaceSecondary: "#1A1A2E"    # 卡片/容器
  surfaceTertiary: "#252540"     # hover/选中

  # 文字色
  textPrimary: "#F8FAFC"
  textSecondary: "#94A3B8"
  textMuted: "#64748B"

  # 边框
  border: "#2D2D50"
  borderLight: "#3D3D60"

# ====== Typography ======
typography:
  h1:
    fontFamily: "Inter, Segoe UI, sans-serif"
    fontSize: 2rem
    fontWeight: 700
    letterSpacing: "-0.02em"
  h2:
    fontFamily: "Inter, Segoe UI, sans-serif"
    fontSize: 1.5rem
    fontWeight: 600
  h3:
    fontFamily: "Inter, Segoe UI, sans-serif"
    fontSize: 1.25rem
    fontWeight: 600
  body:
    fontFamily: "Inter, Segoe UI, sans-serif"
    fontSize: 0.95rem
    fontWeight: 400
    lineHeight: 1.6
  caption:
    fontFamily: "Inter, Segoe UI, sans-serif"
    fontSize: 0.8rem
    fontWeight: 400
    textColor: "{colors.textMuted}"

# ====== Spacing ======
spacing:
  xs: 4px
  sm: 8px
  md: 16px
  lg: 24px
  xl: 32px

# ====== Rounded ======
rounded:
  sm: 6px
  md: 10px
  lg: 16px
  full: 9999px

# ====== Components ======
components:
  button-primary:
    backgroundColor: "{colors.primary}"
    textColor: "#FFFFFF"
    rounded: "{rounded.sm}"
    padding: "10px 24px"
  button-primary-hover:
    backgroundColor: "{colors.primaryLight}"
  button-secondary:
    backgroundColor: "{colors.surfaceTertiary}"
    textColor: "{colors.textPrimary}"
    rounded: "{rounded.sm}"
  card:
    backgroundColor: "{colors.surfaceSecondary}"
    rounded: "{rounded.md}"
  input:
    backgroundColor: "{colors.surfacePrimary}"
    textColor: "{colors.textPrimary}"
    rounded: "{rounded.sm}"
    padding: "8px 12px"

---

## Overview

**MoneyPrinterTurbo Dark** — 为 AI 视频生成工具定制的暗黑科技风主题。

核心理念：深色背景减少视觉疲劳（长时间等视频生成），紫色渐变主色调传达 AI/科技感，清晰的分区让复杂的参数配置一目了然。

## Colors

- **Primary (#7C3AED):** 品牌紫 — Logo、主按钮、选中态、链接
- **PrimaryDark (#5B21B6):** 按钮渐变终点、深色强调
- **Accent (#06B6D4):** 青色 — 用于分镜模式激活、生成成功、视频引擎标签
- **SurfacePrimary (#0F0F1A):** 最深背景 — 页面底色
- **SurfaceSecondary (#1A1A2E):** 卡片底色 — 容器、面板、输入框背景
- **TextPrimary (#F8FAFC):** 正文白
- **TextSecondary (#94A3B8):** 辅助文字灰
- **Border (#2D2D50):** 默认边框

## Typography

全站使用 Inter 字体（系统无则 fallback 到 Segoe UI）。标题加粗，正文常规，标注小号灰字。

## Layout

三栏布局（文案 | 视频设置 | 字幕设置），每个面板用 `border=True` 的 container 包裹，面板间留有间距。

## Components

- 主按钮：紫色渐变 + 白色文字 + hover 变亮
- 次按钮：暗灰底 + 边框
- 卡片：表面色底 + 紫边微光 + 圆角
- 输入框：深色底 + 灰边框 + focus 紫光
- 下拉框/Radio：统一深色主题

## Do's and Don'ts

✅ 使用紫色系表达 AI/科技品牌感
✅ 分镜模式用明显的颜色/图标区分
✅ 引擎切换有清晰的视觉反馈
✅ 等生成时用 spinner + 进度提示
❌ 不要用纯白背景（太刺眼）
❌ 不要让关键操作按钮颜色不突出
❌ 不要把不同功能的控件混在一起不加分隔
