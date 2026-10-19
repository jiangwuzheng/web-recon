# -*- coding: utf-8 -*-
"""
web-recon 网页侦察器 v1.1.0（网页/平台全方位扫描）
新增 v1.1.0：
  --scroll      自动滚动全页扫描（懒加载内容不遗漏），默认最多 30 屏
  --aggressive  深度按钮识别：div/span 带 onclick / cursor:pointer / class含btn 也算按钮
  同域 iframe 自动穿透（contentDocument 可访问时递归）
  元素记录"文档坐标"（已加滚动偏移），全页不漏

用法:
  python scan_page.py --match goods_list --scroll --aggressive --out D:\out
  python scan_page.py --list
产物(输出到 --out, 默认当前目录):
  1. <页面>_侦察地图.html —— SVG 全页布局图 + 可搜索元素清单
  2. <页面>_recon.json   —— 结构化数据(文档坐标, 给自动化脚本用)
  3. <页面>_recon.png    —— 页面截图
"""
import argparse, base64, json, os, re, sys, time, urllib.parse, urllib.request, itertools

try:
    import websocket
except ImportError:
    print("缺少 websocket-client 库, 请先: pip install websocket-client")
    sys.exit(1)

HERE = os.path.dirname(os.path.abspath(__file__))


class CDP:
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
  if(!window.__reconState){window.__reconState={all:new Map(),sc:null,scType:'win'};}
  const st=window.__reconState;
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
  function scrollOffset(){
    if(st.scType==='win')return window.scrollY||0;
    if(st.sc)return st.sc.scrollTop||0;
    return 0;
  }
  function add(el,sp,type,is_btn){
    if(seen.has(el))return; seen.add(el);
    let r=null; try{r=el.getBoundingClientRect();}catch(e){return;}
    if(!r||r.width<=0||r.height<=0)return;
    if(r.y>60000||r.x>30000)return;
    let s=null; try{s=getComputedStyle(el);}catch(e){}
    if(s&&(s.display==='none'||s.visibility==='hidden'))return;
    const tag=el.tagName.toLowerCase();
    const dy=Math.round(r.y+scrollOffset());
    const o={tag:tag,text:(el.textContent||'').trim().replace(/\s+/g,' ').slice(0,80),
      ph:el.getAttribute('placeholder')||'',type:type||(el.getAttribute('type')||'').toLowerCase(),
      role:el.getAttribute('role')||'',cls:(typeof el.className==='string'?el.className:'').slice(0,120),
      x:Math.round(r.x),y:dy,w:Math.round(r.width),h:Math.round(r.height),
      dis:!!el.disabled,shadow:sp||''};
    if(is_btn){o.kind='button';}
    else if(tag==='input'&&o.type==='file'){o.kind='file';out.files.push(o);}
    else if(tag==='input'||tag==='textarea'||tag==='select')o.kind='input';
    else if(tag==='a')o.kind='link';
    else o.kind='widget';
    const k=[o.kind,o.tag,o.text,o.ph,o.cls].join('|');
    st.all.set(k,o);  // 同特征元素: 保留最新坐标
  }
  const OPER_WORDS=['关注','点赞','收藏','评论','分享','转发','直播','发布','删除','编辑','保存','提交','登录','注册','搜索','确定','取消','上传','添加','设置','立即','更换','刷新','更多','展开','同意','复制','下载','播放','暂停','追更','投币','弹幕','下载APP','打开App','知道了','换一批','签到','抽奖','反馈','举报','关注中','已关注'];
  function isBtn(el,tag,type,role,s){
    if(tag==='a')return false;  // 链接归链接, 不标按钮
    if(tag==='button'||(tag==='input'&&['button','submit','reset'].indexOf(type)>=0))return true;
    if(role==='button')return true;
    if(__AGGR__){
      if((tag==='div'||tag==='span')){
        if(el.getAttribute('onclick')!==null||el.getAttribute('onmousedown')!==null)return true;
        if(role==='link'||role==='tab'||role==='menuitem'||role==='switch'||role==='checkbox'||role==='radio')return true;
        if(s&&s.cursor==='pointer'){
          const txt=(el.textContent||'').trim().replace(/\s+/g,' ');
          const aria=(el.getAttribute('aria-label')||'')+ (el.getAttribute('title')||'');
          const cn=typeof el.className==='string'?el.className:'';
          if(txt.length<=8&&OPER_WORDS.some(w=>txt.includes(w)))return true;   // 短文本+操作词 → 真按钮
          if(OPER_WORDS.some(w=>aria.includes(w)))return true;                 // aria/title 含操作词 → 真按钮
          if(/icon-button|btn-icon|oper|button/i.test(cn)&&cn.length<60)return true; // 图标按钮class
        }
      }
    }
    return false;
  }
  function walk(root,sp){
    let all=[]; try{all=root.querySelectorAll('*');}catch(e){}
    for(let i=0;i<all.length;i++){
      const el=all[i]; if(!el)continue;
      const tag=el.tagName.toLowerCase();
      const type=(el.getAttribute('type')||'').toLowerCase();
      const role=el.getAttribute('role')||'';
      let s=null; try{s=getComputedStyle(el);}catch(e){}
      if(isBtn(el,tag,type,role,s)){add(el,sp,type,true);continue;}
      const isInput=tag==='input'||tag==='textarea'||tag==='select';
      const isRole=!!role;
      const isEdit=el.getAttribute('contenteditable')==='true';
      if(isInput||isRole||isEdit)add(el,sp,type,false);
      if(el.shadowRoot)walk(el.shadowRoot,sp+' → '+tag+'[shadow]');
    }
  }
  walk(document,'');
  try{
    document.querySelectorAll('iframe').forEach(f=>{
      try{const d=f.contentDocument; if(d)walk(d,' → iframe');}catch(e){}
    });
  }catch(e){}
  out.elements=[...st.all.values()];
  return out;
})()
"""

SCROLL_JS = r"""
(()=>{
  if(!window.__reconState){window.__reconState={all:new Map(),sc:null,scType:'win'};}
  const st=window.__reconState;
  const se=document.scrollingElement||document.documentElement;
  if(!st.sc){
    // 优先整页(se)能滚就用整页; 否则找最大的可滚动容器
    if((document.documentElement.scrollHeight||0)>window.innerHeight+80){
      st.sc=se; st.scType='win';
    }else{
      let best=null, bestH=0;
      try{
        const all=document.querySelectorAll('*');
        for(const e of all){
          if(e.scrollHeight>e.clientHeight+80){
            const s=getComputedStyle(e);
            if(s&&/auto|scroll/.test(s.overflowY)&&e.scrollHeight>bestH){best=e;bestH=e.scrollHeight;}
          }
        }
      }catch(e){}
      st.sc=best||se; st.scType=best?'el':'win';
    }
  }
  const sc=st.sc;
  let cur,max;
  if(st.scType==='win'){cur=window.scrollY||0; max=(document.documentElement.scrollHeight||0)-window.innerHeight;}
  else{cur=sc.scrollTop||0; max=sc.scrollHeight-sc.clientHeight;}
  if(max<5)return {end:true,cur:0,max:0};
  if(cur>=max-5)return {end:true,cur:cur,max:max};
  if(st.scType==='win')window.scrollBy(0,600); else sc.scrollTop=cur+600;
  return {end:false,cur:(st.scType==='win'?(window.scrollY||0):(sc.scrollTop||0)),max:max};
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
    maxy = max([e["y"] + e["h"] for e in els] or [vp["h"]])
    svg_els = els
    svg_w = max(vp["w"], 800)
    svg_h = min(max(maxy, vp["h"]), 4000)
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
    ap = argparse.ArgumentParser(description="网页侦察器 v1.1.0: 扫描页面生成可视化地图(支持滚动全扫/按钮深度识别)")
    ap.add_argument("--port", type=int, default=9223, help="CDP 端口(默认9223)")
    ap.add_argument("--match", default="", help="按 URL 片段匹配 tab(默认自动优先电商后台)")
    ap.add_argument("--out", default=".", help="输出目录(默认当前目录)")
    ap.add_argument("--list", action="store_true", help="只列出可连接的页面")
    ap.add_argument("--full", action="store_true", help="截图用整页模式")
    ap.add_argument("--scroll", type=int, nargs="?", const=30, default=0,
                    help="自动滚动全页扫描(懒加载不遗漏), 默认最多30屏; 传数字自定义屏数, 如 --scroll 10")
    ap.add_argument("--aggressive", action="store_true", help="按钮深度识别(div/span带onclick/cursor:pointer/class含btn)")
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
        # 初始化: 清掉残留状态
        c.eval("window.__reconState=null;true")
        recon_js = RECON_JS.replace("__AGGR__", "true" if a.aggressive else "false")
        if a.scroll:
            recon = None
            for step in range(a.scroll):
                recon = c.eval(recon_js)   # 先收集当前屏(返回累积全量)
                st = c.eval(SCROLL_JS)
                if not isinstance(st, dict):
                    break
                if st.get("end"):
                    break
                time.sleep(0.6)
            recon = c.eval(recon_js)       # 最后再收一次
        else:
            recon = c.eval(recon_js)
        if not isinstance(recon, dict) or "elements" not in recon:
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
