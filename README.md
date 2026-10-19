# web-recon 网页侦察器

一键扫描任意已打开的网页（电商商家后台、社交平台、任何在线页面），生成「页面侦察地图」——识别框架、列出全部可交互元素（按钮/输入框/下拉/链接/开关/文件上传口）的位置坐标、文本、type、role、class，穿透 Shadow DOM，检测 navigator.webdriver 防自动化信号，输出可视化 HTML 地图 + JSON 数据 + 页面截图。

## 适用场景

- 第一次操作某个平台/页面，先扫描摸底，避免瞎点。
- 按钮点不到、找不到元素（排查是否藏在 Shadow DOM 或页面做了防自动化）。
- 需要精确 CSS 坐标做自动化点击（截图 OCR 坐标 ÷ DPR = CSS 坐标）。
- 判断页面框架（React 受控组件必须真实键盘输入，不能直接改 value）。
- 找文件上传口（input[type=file] 注入点）。

## 环境前提

- 目标浏览器以调试端口启动（如 `--remote-debugging-port=9223`）。
- Python 3 + `websocket-client` 库：`pip install websocket-client`
- 目标页面已在该浏览器打开。

## 用法

```bash
python scan_page.py                       # 默认 9223，自动挑电商后台/编辑页
python scan_page.py --port 9223 --match mms.pinduoduo.com
python scan_page.py --match goods_list    # 按 URL 片段匹配 tab
python scan_page.py --list                # 先看有哪些页面可扫
python scan_page.py --out D:\out          # 指定输出目录
python scan_page.py --full                # 整页截图模式
```

Windows 下也可直接双击 `启动扫描.bat`。

## 产物（3个）

1. **`<页面>_侦察地图.html`** —— 可视化地图：
   - 首屏 SVG 布局图：所有可交互元素按真实位置画框（按钮蓝/输入框绿/链接黄/上传口紫/控件橙），**虚线框 = 藏在 Shadow DOM 里**（普通方式点不到）。
   - 全部元素表格（可搜索），点行看详情。
   - 顶部统计条：元素总数、按钮数、输入框数、上传口数、影子DOM数、框架、视口、DPR、webdriver 检测。
2. **`<页面>_recon.json`** —— 结构化数据，直接给自动化脚本用。
3. **`<页面>_recon.png`** —— 页面截图留档。

## 侦察报告怎么用（关键）

- **DPR 坐标换算**：地图里所有坐标是 CSS 像素。截图/OCR 得到的像素坐标要 ÷DPR 才是 CDP real_click 用的坐标。
- **Shadow DOM**：标记 `→ xxx[shadow]` 的元素，`document.querySelector` 找不到，需用 `element.shadowRoot.querySelector` 穿透。
- **框架**：React → 输入框必须 focus + 真实鼠标点击 + `Input.insertText`（直接设 value 无效）；原生/jQuery → 可直接设 value + 派发 change。
- **webdriver=true** → 页面可能识别自动化，操作前先处理。
- **上传口 input[type=file]** → 用 `DOM.setFileInputFiles` 注入本地文件。

## 已知边界

- 只扫描当前页面已渲染的内容（懒加载内容需先滚动再扫）。
- iframe/OOPIF 里的元素不在此页 DOM 中。
- 元素坐标是当前滚动位置的视口坐标，滚动后需重扫。
