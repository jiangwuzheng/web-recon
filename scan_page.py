# -*- coding: utf-8 -*-
"""
web-recon 网页侦察器（网页/平台全方位扫描）

用法:
  python scan_page.py                      # 默认连 9223, 自动挑电商后台页面
  python scan_page.py --port 9223 --match mms.pinduoduo.com
  python scan_page.py --match goods_list   # 按 URL 片段匹配 tab
  python scan_page.py --list               # 只列出当前所有可连的页面

产物(输出到 --out 目录, 默认当前目录):
  1. <页面名>_侦察地图.html  —— 可视化地图: SVG 布局图(所有按钮/输入框/上传口位置) + 可搜索元素清单 + 点击元素看详情
  2. <页面名>_recon.json    —— 结构化侦察数据(给后续自动化脚本直接用)
  3. <页面名>_recon.png     —— 页面截图(留档)

侦察内容:
  - 框架指纹 (React/Vue/jQuery/Angular)
  - 视口 / DPR (截图坐标换算依据: 截图像素 = CSS坐标 x DPR)
  - navigator.webdriver 标志 (防自动化检测信号)
  - 全部可交互元素: 按钮/输入框/下拉/链接/开关/文件上传, 含文本、placeholder、type、role、class、CSS坐标、是否disabled
  - Shadow DOM 递归穿透 (小红书保存按钮那种藏在影子DOM里的元素, 会标注"→ xxx[shadow]")
  - 文件上传入口 input[type=file] (SKU图/详情图注入点)
"""
import argparse, base64, json, os, re, sys, time, urllib.parse, urllib.request, itertools

try:
    import websocket
except ImportError:
    print("缺少 websocket-client 库, 请先: pip install websocket-client")
    sys.exit(1)

HERE = os.path.dirname(os.path.abspath(__file__))


class CDP:
    """极简 CDP 客户端(自包含, 不依赖外部工作目录)。"""
    def __init__(self, ws_url):
        self.ws = websocket.create_connection(ws_url, max_receive_message_size=64*1024*1024,
                                              timeout=60, suppress_origin=True)
        self._ids = itertools.count(1)

    def send(self, method, params=None, timeout=60):
        mid = next(self._ids)
        self.ws.send(json.dumps({"id": mid, "method": method, "params": params or {}}))
        end = time.time() + timeout
        while time.time() < end:
            self.ws.settimeout(max(0.5, end - time.time()))
            msg = json.loads(self.ws.recv())
            if msg.get("id") == mid:
                if "error" in msg:
                    raise RuntimeError(f"CDP {method} error: {msg['error']}")
                return msg.get("result", {})
        raise TimeoutError(method)

    def eval(self, expression, timeout=60):
        r = self.send("Runtime.evaluate", {"expression": expression, "returnByValue": True,
                                           "awaitPromise": True}, timeout=timeout)
        if "exceptionDetails" in r:
            exc = r["exceptionDetails"].get("exception", {})
            raise RuntimeError("JS异常: " + str(exc.get("description", r["exceptionDetails"]))[:300])
        return r.get("result", {}).get("value")

    def screenshot(self, full_page=False):
        cap = self.send("Page.captureScreenshot", {"format": "png", "captureBeyondViewport": full_page})
        return base64.b64decode(cap["data"])

    def close(self):
        try: self.ws.close()
        except Exception: pass


RECON_JS = r"""
(()=>{
  const out={url:location.href,title:document.title,
    viewport:{w:window.innerWidth,h:window.innerHeight,dpr:window.devicePixelRatio||1},
    webdriver:!!navigator.webdriver,framework:[],elements:[],files:[]};
  try{
    if(window.React||document.querySelector('#root')||document.querySelector('#__next')||document.querySelector('#app'))out.framework.push('React');
    if(window.__NUXT__||window.__VUE__||document.querySelector('[data-v-]'))out.framework.push('Vue');
    if(window.jQuery)out.framework.push('jQuery');
    if(window.angular)out.framework.push('Angular');
  }catch(e){}
  const seen=new Set();
  function add(el,sp,type){
    if(seen.has(el))return; seen.add(el);
    let r=null; try{r=el.getBoundingClientRect();}catch(e){return;}
    if(!r||r.width<=0||r.height<=0)return;
    if(r.y>60000||r.x>30000)return;
    let s=null; try{s=getComputedStyle(el);}catch(e){}
    if(s&&(s.display==='none'||s.visibility==='hidden'))return;
    const tag=el.tagName.toLowerCase();
    const o={tag:tag,text:(el.textContent||'').trim().replace(/\s+/g,' ').slice(0,80),
      ph:el.getAttribute('placeholder')||'',type:type||(el.getAttribute('type')||'').toLowerCase(),
      role:el.getAttribute('role')||'',cls:(typeof el.className==='string'?el.className:'').slice(0,120),
      x:Math.round(r.x),y:Math.round(r.y),w:Math.round(r.width),h:Math.round(r.height),
      dis:!!el.disabled,shadow:sp||''};
    if(tag==='input'&&o.type==='file'){o.kind='file';out.files.push(o);}
    else if(tag==='button'||(tag==='input'&&['button','submit','reset'].indexOf(o.type)>=0))o.kind='button';
    else if(tag==='input'||tag==='textarea'||tag==='select')o.kind='input';
    else if(tag==='a')o.kind='link';
    else o.kind='widget';
    out.elements.push(o);
  }
  function walk(root,sp){
    let all=[]; try{all=root.querySelectorAll('*');}catch(e){}
    const roles=['button','switch','checkbox','radio','tab','menuitem','link','searchbox','textbox','combobox','dialog'];
    for(let i=0;i<all.length;i++){
      const el=all[i]; if(!el)continue;
      const tag=el.tagName.toLowerCase();
      const type=(el.getAttribute('type')||'').toLowerCase();
      const role=el.getAttribute('role')||'';
      const isBtn=tag==='button'||(tag==='input'&&['button','submit','reset'].indexOf(type)>=0);
      const isInput=tag==='input'||tag==='textarea'||tag==='select';
      const isLink=tag==='a'&&el.getAttribute('href')!==null;
      const isRole=roles.indexOf(role)>=0;
      const isEdit=el.getAttribute('contenteditable')==='true';
      if(isBtn||isInput||isLink||isRole||isEdit)add(el,sp,type);
      if(el.shadowRoot)walk(el.shadowRoot,sp+' → '+tag+'[shadow]');
    }
  }
  walk(document,'');
  return out;
})()
"""


def get_pages(port):
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/json", timeout=8) as r:
            return json.loads(r.read().decode("utf-8"))
    except Exception as e:
        print(f"连接失败: 127.0.0.1:{port} 无响应({e})。请确认浏览器已带 --remote-debugging-port={port} 启动。")
        sys.exit(1)


def pick_page(pages, match):
    targets = [t for t in pages if t.get("type") == "page"]
    if not targets:
        print("没有可连接的页面 tab"); sys.exit(1)
    if match:
        hits = [t for t in targets if match.lower() in t.get("url", "").lower()]
        if not hits:
            print(f"没有 URL 包含 '{match}' 的页面。现有页面:")
            for t in targets[:20]:
                print("  -", t.get("url", "")[:120])
            sys.exit(1)
        return hits[0]
    for pref in ("goods_add", "mms.pinduoduo.com", "creator.douyin", "xhslink", "shop."):
        for t in targets:
            if pref in t.get("url", ""):
                return t
    return targets[0]


def esc(s):
    return (s or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")


def build_html(recon, name):
    template = open(os.path.join(HERE, "recon_template.html"), encoding="utf-8").read()
    els = recon["elements"]
    vp = recon["viewport"]
    kinds = {"button": ("#4d9fff", "按钮"), "input": ("#37c46f", "输入框"), "link": ("#ffd479", "链接"),
             "file": ("#c86bff", "上传口"), "widget": ("#ff8f6b", "控件")}
    svg_els = [e for e in els if e["y"] < vp["h"] and e["y"] + e["h"] > 0]
    svg_w = max(vp["w"], 800)
    svg_h = min(vp["h"], 1600)
    rects = []
    for i, e in enumerate(svg_els):
        col = kinds.get(e["kind"], ("#999", "?"))[0]
        dash = ' stroke-dasharray="5,4"' if e["shadow"] else ""
        lab = esc((e["text"] or e["ph"] or e["type"] or e["tag"])[:14])
        rects.append(
            '<rect data-i="%d" x="%d" y="%d" width="%d" height="%d" fill="%s" fill-opacity="0.16" '
            'stroke="%s" stroke-width="1.5"%s style="cursor:pointer"/>'
            '<text x="%d" y="%d" font-size="11" fill="%s" style="cursor:pointer;pointer-events:none">%s</text>'
            % (i, e["x"], e["y"], max(e["w"], 2), max(e["h"], 2), col, col, dash, e["x"] + 3, e["y"] + 12, col, lab))
    rows = []
    for i, e in enumerate(els):
        col = kinds.get(e["kind"], ("#666", "?"))[0]
        chip = '<span class="chip" style="background:%s22;color:%s;border:1px solid %s55">%s</span>' % (
            col, col, col, kinds.get(e["kind"], ("#666", "?"))[1])
        rows.append(
            '<tr data-i="%d" style="cursor:pointer"><td>%s</td><td>%s</td><td>%s</td><td>%s</td><td>%s</td>'
            '<td>%s</td><td>%d,%d</td><td>%d×%d</td><td>%s</td><td>%s</td><td style="color:#7c87a0;font-size:11px">%s</td></tr>'
            % (i, chip, esc(e["tag"]), esc(e["text"] or "-"), esc(e["ph"] or "-"), esc(e["type"] or "-"),
               esc(e["role"] or "-"), e["x"], e["y"], e["w"], e["h"],
               '<span style="color:#ff6b6b">禁</span>' if e["dis"] else "✓",
               esc(e["shadow"]) if e["shadow"] else "-", esc(e["cls"][:40])))
    n_btn = sum(1 for e in els if e["kind"] == "button")
    n_in = sum(1 for e in els if e["kind"] == "input")
    n_file = len(recon["files"])
    n_sh = sum(1 for e in els if e["shadow"])
    fw = "、".join(recon["framework"]) if recon["framework"] else "未知/原生"
    wd = "⚠ 检测到" if recon["webdriver"] else "未暴露"
    wdc = "#ff6b6b" if recon["webdriver"] else "#37c46f"
    stats = (
        '<div class="stat"><b>%d</b>可交互元素</div>'
        '<div class="stat"><b>%d</b>按钮</div>'
        '<div class="stat"><b>%d</b>输入框</div>'
        '<div class="stat"><b>%d</b>上传口</div>'
        '<div class="stat"><b>%d</b>影子DOM内</div>'
        '<div class="stat"><b>%s</b>框架</div>'
        '<div class="stat"><b>%d×%d</b>视口</div>'
        '<div class="stat"><b>%s</b>DPR</div>'
        '<div class="stat" style="border-color:%s"><b>%s</b>webdriver</div>'
        % (len(els), n_btn, n_in, n_file, n_sh, esc(fw), vp["w"], vp["h"], vp["dpr"], wdc, wd))
    data = json.dumps([{"tag": e["tag"], "text": e["text"], "ph": e["ph"], "type": e["type"], "role": e["role"],
                        "cls": e["cls"], "x": e["x"], "y": e["y"], "w": e["w"], "h": e["h"],
                        "dis": e["dis"], "shadow": e["shadow"], "kind": e["kind"]} for e in els],
                      ensure_ascii=False)
    out = template.replace("__TITLE__", esc(name))
    out = out.replace("__URL__", esc(recon["url"]))
    out = out.replace("__STATS__", stats)
    out = out.replace("__SVG_W__", str(svg_w))
    out = out.replace("__SVG_H__", str(svg_h))
    out = out.replace("__SVG__", "".join(rects))
    out = out.replace("__ROWS__", "".join(rows))
    out = out.replace("__DATA__", data)
    out = out.replace("__DPR__", str(vp["dpr"]))
    return out


def main():
    ap = argparse.ArgumentParser(description="网页侦察器: 扫描一个页面生成可视化地图")
    ap.add_argument("--port", type=int, default=9223, help="CDP 端口(默认9223)")
    ap.add_argument("--match", default="", help="按 URL 片段匹配 tab(默认自动优先电商后台)")
    ap.add_argument("--out", default=".", help="输出目录(默认当前目录)")
    ap.add_argument("--list", action="store_true", help="只列出可连接的页面")
    ap.add_argument("--full", action="store_true", help="截图用整页模式")
    a = ap.parse_args()

    pages = get_pages(a.port)
    if a.list:
        for t in pages:
            if t.get("type") == "page":
                print("- [%s] %s" % (t.get("id", "")[:8], t.get("url", "")[:130]))
        return

    t = pick_page(pages, a.match)
    print("目标页面:", t.get("url", "")[:130])
    c = CDP(t["webSocketDebuggerUrl"])
    try:
        recon = c.eval(RECON_JS)
        if not isinstance(recon, dict):
            print("侦察返回异常:", str(recon)[:200]); return
        base = re.sub(r'[\\/:*?"<>|]', "_", (recon.get("title") or "page"))[:40] or "page"
        os.makedirs(a.out, exist_ok=True)
        with open(os.path.join(a.out, base + "_recon.json"), "w", encoding="utf-8") as f:
            json.dump(recon, f, ensure_ascii=False, indent=1)
        html = build_html(recon, base)
        html_path = os.path.join(a.out, base + "_侦察地图.html")
        with open(html_path, "w", encoding="utf-8") as f:
            f.write(html)
        with open(os.path.join(a.out, base + "_recon.png"), "wb") as f:
            f.write(c.screenshot(full_page=a.full))
        n_btn = sum(1 for e in recon["elements"] if e["kind"] == "button")
        n_in = sum(1 for e in recon["elements"] if e["kind"] == "input")
        n_sh = sum(1 for e in recon["elements"] if e["shadow"])
        print("完成: 元素%d个 | 按钮%d | 输入框%d | 上传口%d | 影子DOM内%d | 框架%s" % (
            len(recon["elements"]), n_btn, n_in, len(recon["files"]), n_sh,
            "、".join(recon["framework"]) or "未知"))
        print("地图:", os.path.abspath(html_path))
        print("数据:", os.path.abspath(os.path.join(a.out, base + "_recon.json")))
    finally:
        c.close()


if __name__ == "__main__":
    main()
