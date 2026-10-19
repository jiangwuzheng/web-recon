---
name: web-recon
description: "网页/平台全方位侦察技能：扫描任意已打开的网页（拼多多/抖音/小红书/淘宝等商家后台或任何在线页面），一键生成「页面侦察地图」——识别框架（React/Vue/jQuery）、列出全部可交互元素（按钮/输入框/下拉/链接/开关/文件上传口）的位置坐标、文本、type、role、class，穿透 Shadow DOM（找小红书保存按钮那种隐藏元素），检测 navigator.webdriver 防自动化信号，输出可视化的 HTML 地图 + JSON 数据 + 页面截图。适用于：操作任何网页后台前先摸底、按钮点不到时排查元素是否藏在 Shadow DOM、需要精确 CSS 坐标做自动化点击、判断页面框架和 DPR 做坐标换算。触发词：扫描页面、扫一下这个页面、看下这个页面、识别这个网页、识别这个软件页面、了解下这个网页、了解下这个网站、去看下某某网站、页面地图、侦察、按钮找不到、元素定位、这个页面怎么操作、读懂页面、全方位了解平台。注意：只有用户想让AI了解/操作某个网页页面的内部结构时才用；如果只是普通搜索问答（问网站是什么、有没有这个产品）不用本技能。"
platform: 任意带 CDP 调试端口的浏览器（默认 Edge/Chrome 9223）
version: 1.1.0
updated: 2026-10-19
---

# 网页侦察器 web-recon（读懂页面 / 全方位扫描平台）

## 什么时候用
- 第一次操作某个平台/页面，先扫描摸底，避免瞎点。
- 按钮点不到、找不到元素（可能是 Shadow DOM 或防自动化）。
- 需要精确 CSS 坐标做自动化点击（截图 OCR 坐标 ÷DPR = CSS 坐标）。
- 想知道页面用的什么框架（React 受控组件 = 必须真实键盘输入，不能直接改 value）。
- 找文件上传口（SKU 图/详情图注入点 input[type=file]）。

## 环境前提
- 浏览器带调试端口启动（拼多多场景：Edge `--remote-debugging-port=9223`，user-data-dir `C:\temp\pdd-edge`）。
- 需要 python + websocket-client 库。
- 目标页面已在该浏览器打开（或可先导航过去）。

## 用法
```bash
python scan_page.py                       # 默认 9223，自动挑电商后台/编辑页
python scan_page.py --match goods_list    # 按 URL 片段匹配 tab
python scan_page.py --list                # 先看有哪些页面可扫
python scan_page.py --out D:\out          # 指定输出目录
python scan_page.py --scroll 15 --aggressive   # v1.1.0: 滚动全页扫描(懒加载不遗漏)+按钮深度识别
```
v1.1.0 新增：`--scroll N` 自动滚动 N 屏合并扫描（页面不滚时会自动找最大滚动容器，如抖音 _bpJj4nI）；`--aggressive` 深度按钮识别（button/role=button/onclick/带操作词的 cursor:pointer div/span/图标按钮 class，链接不算按钮）；同域 iframe 自动穿透；坐标是文档坐标（已含滚动偏移）。

## 产物（3个）
1. **`<页面>_侦察地图.html`** —— 可视化地图：
   - 首屏 SVG 布局图：所有可交互元素按真实位置画框（按钮蓝/输入框绿/链接黄/上传口紫/控件橙），**虚线框 = 藏在 Shadow DOM 里**（普通方式点不到）。
   - 全部元素表格（可搜索），点行看详情（文本/placeholder/type/role/class/坐标/可用性/影子路径）。
   - 顶部统计条：元素总数、按钮数、输入框数、上传口数、影子DOM数、框架、视口、DPR、webdriver 检测。
2. **`<页面>_recon.json`** —— 结构化数据，直接给自动化脚本用。
3. **`<页面>_recon.png`** —— 页面截图留档。

## 侦察报告怎么用（关键）
- **DPR 坐标换算**：侦察地图里所有坐标是 CSS 像素。截图/OCR 得到的像素坐标要 ÷DPR 才是 CDP real_click 用的坐标（例：截图 3828px / DPR 1.5 = CSS 2552px）。
- **Shadow DOM**：标记 `→ xxx[shadow]` 的元素，`document.querySelector` 找不到，需用 `element.shadowRoot.querySelector` 穿透（或脚本里已递归遍历）。
- **框架**：
  - React → 输入框必须 focus + 真实鼠标点击 + `Input.insertText`（直接设 value 无效）。
  - 原生/jQuery → 可直接设 value + 派发 change。
- **webdriver=true** → 页面可能识别自动化（拼多多提交按钮装死等），先 `inject_stealth` 再操作。
- **上传口 input[type=file]** → 用 `DOM.setFileInputFiles` 注入本地文件（SKU 图上传）。

## 与其他技能配合
- 拼多多批量操作：先 `scan_page.py --match goods_add` 拿到当前编辑页地图（按钮/输入框坐标），再按 pdd-backend-sku-sync 的流程操作。
- 小红书：地图能直接标出 Shadow DOM 里的保存按钮（`xhs-publish-btn`），配合 shadowPoint 定位。

## 已知边界
- 只扫描**当前页面已渲染**的内容（懒加载内容需先滚动再扫；或扫完再滚再扫合并）。
- iframe/OOPIF 里的元素不在此页 DOM 中（拼多多装修器的手机预览就是跨域 iframe，扫不到，但主画布能扫到）。
- 元素坐标是**当前滚动位置**的视口坐标，滚动后需重扫。
