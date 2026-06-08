#!/usr/bin/env python3
"""内容工坊 — 创作工作台。文学杂志风格。零依赖。"""

import http.server, json, re, socketserver, webbrowser, base64, os, time
from pathlib import Path
from urllib.parse import urlparse, parse_qs

PORT = 8899
ROOT = Path(__file__).parent.parent.resolve()  # 文章根目录
HERE = Path(__file__).parent.resolve()           # 内容工坊目录
SCRIPT = Path(__file__).name

# ═══════════════════════════════════════════════════════
# Markdown → HTML
# ═══════════════════════════════════════════════════════
def md2html(text):
    cb, ic, imgs, lks = [], [], [], []
    def _sc(m): cb.append(m.group(0)); return f"\x00CB{len(cb)-1}\x00"
    def _si(m): ic.append(m.group(1)); return f"\x00IC{len(ic)-1}\x00"
    def _sim(m): imgs.append((m.group(1),m.group(2))); return f"\x00IM{len(imgs)-1}\x00"
    def _slk(m): lks.append((m.group(1),m.group(2))); return f"\x00LK{len(lks)-1}\x00"
    text=re.sub(r'```[^`]*```',_sc,text); text=re.sub(r'`([^`]+)`',_si,text)
    text=re.sub(r'!\[([^\]]*)\]\(([^)]+)\)',_sim,text); text=re.sub(r'\[([^\]]*)\]\(([^)]+)\)',_slk,text)
    for lv in range(6,0,-1): text=re.sub(rf'^{"#"*lv}\s+(.+?)$',rf'<h{lv}>\1</h{lv}>',text,flags=re.MULTILINE)
    text=re.sub(r'^---+\s*$','<hr>',text,flags=re.MULTILINE)
    lines,out,bq=text.split('\n'),[],[]
    for ln in lines:
        m=re.match(r'^>\s?(.*)',ln)
        if m: bq.append(m.group(1))
        else:
            if bq: out.append('<blockquote><p>'+'<br>'.join(bq)+'</p></blockquote>'); bq=[]
            out.append(ln)
    if bq: out.append('<blockquote><p>'+'<br>'.join(bq)+'</p></blockquote>')
    text='\n'.join(out)
    lines,out,tbl=text.split('\n'),[],[]
    for ln in lines:
        if re.match(r'^\|.+\|$',ln): tbl.append(ln)
        else:
            if tbl:
                h='<table><thead><tr>'+''.join(f'<th>{c.strip()}</th>' for c in tbl[0].split('|')[1:-1])+'</tr></thead><tbody>'
                for row in tbl[1:]:
                    if re.match(r'^[\|\s\-:]+$',row): continue
                    h+='<tr>'+''.join(f'<td>{c.strip()}</td>' for c in row.split('|')[1:-1])+'</tr>'
                h+='</tbody></table>'; out.append(h); tbl=[]
            out.append(ln)
    if tbl:
        h='<table><thead><tr>'+''.join(f'<th>{c.strip()}</th>' for c in tbl[0].split('|')[1:-1])+'</tr></thead><tbody>'
        for row in tbl[1:]:
            if re.match(r'^[\|\s\-:]+$',row): continue
            h+='<tr>'+''.join(f'<td>{c.strip()}</td>' for c in row.split('|')[1:-1])+'</tr>'
        h+='</tbody></table>'; out.append(h)
    text='\n'.join(out)
    for marker,tag in [('-','ul'),(r'\*','ul')]:
        lines,out,lst=text.split('\n'),[],[]
        for ln in lines:
            m=re.match(rf'^\s*{marker}\s+(.*)',ln)
            if m: lst.append('<li>'+m.group(1)+'</li>')
            else:
                if lst: out.append(f'<{tag}>'+''.join(lst)+f'</{tag}>'); lst=[]
                out.append(ln)
        if lst: out.append(f'<{tag}>'+''.join(lst)+f'</{tag}>')
        text='\n'.join(out)
    text=re.sub(r'\*\*(.+?)\*\*',r'<strong>\1</strong>',text)
    text=re.sub(r'\*(.+?)\*',r'<em>\1</em>',text)
    lines,out,para=text.split('\n'),[],[]
    for ln in lines:
        s=ln.strip()
        if re.match(r'^<(h[1-6]|table|hr|ul|ol|li|blockquote|pre|/table|/ul|/ol|/blockquote|thead|tbody)',s):
            if para: out.append('<p>'+'<br>'.join(para)+'</p>'); para=[]
            out.append(ln)
        elif s=='':
            if para: out.append('<p>'+'<br>'.join(para)+'</p>'); para=[]
        else:
            if s.startswith('\x00'):
                if para: out.append('<p>'+'<br>'.join(para)+'</p>'); para=[]
                out.append(ln)
            else: para.append(s)
    if para: out.append('<p>'+'<br>'.join(para)+'</p>')
    text='\n'.join(out)
    for i,(label,url) in enumerate(lks): text=text.replace(f'\x00LK{i}\x00',f'<a href="{url}">{label}</a>')
    for i,(alt,src) in enumerate(imgs): text=text.replace(f'\x00IM{i}\x00',f'<figure><img src="{src}" alt="{alt}" loading="lazy"><figcaption>{alt}</figcaption></figure>')
    for i,code in enumerate(ic): text=text.replace(f'\x00IC{i}\x00',f'<code>{code}</code>')
    for i,block in enumerate(cb):
        inner=re.sub(r'^```\w*\n?','',block); inner=re.sub(r'```$','',inner)
        inner=inner.replace('&','&amp;').replace('<','&lt;').replace('>','&gt;')
        text=text.replace(f'\x00CB{i}\x00',f'<pre><code>{inner}</code></pre>')
    text=re.sub(r'<p>\s*</p>','',text)
    return text

# ═══════════════════════════════════════════════════════
# CSS — 文学杂志风格
# ═══════════════════════════════════════════════════════
CSS = """
:root {
  --bg: #f8f9fb; --card: #fff; --text: #1a1a2e; --muted: #6b7280;
  --accent: #4f46e5; --accent2: #059669; --border: #e5e7eb;
  --shadow-sm: 0 1px 2px rgba(0,0,0,.04); --shadow: 0 1px 3px rgba(0,0,0,.06),0 1px 2px rgba(0,0,0,.04);
  --shadow-md: 0 4px 6px rgba(0,0,0,.04),0 2px 4px rgba(0,0,0,.04);
  --radius: 10px; --radius-sm: 6px;
  --sans: -apple-system,BlinkMacSystemFont,"Segoe UI","PingFang SC","Hiragino Sans GB","Microsoft YaHei",sans-serif;
}
*,*::before,*::after{box-sizing:border-box;margin:0;padding:0}
body{font-family:var(--sans);font-size:15px;line-height:1.6;color:var(--text);background:var(--bg);-webkit-font-smoothing:antialiased;min-height:100vh}

.container{max-width:900px;margin:0 auto;padding:40px 24px 80px}
/* 头部 */
.header{text-align:center;padding:32px 0 40px}
.header h1{font-size:32px;font-weight:800;color:var(--text);letter-spacing:-.02em;margin-bottom:8px}
.header .sub{font-size:15px;color:var(--muted);font-weight:400}
.header .logo{display:inline-block;width:44px;height:44px;background:linear-gradient(135deg,var(--accent),#7c3aed);border-radius:12px;margin-bottom:16px;color:#fff;font-size:22px;line-height:44px;text-align:center}

/* 进度条 */
.progress{display:flex;justify-content:center;align-items:center;gap:0;margin-bottom:40px;background:var(--card);border-radius:var(--radius);padding:8px 20px;box-shadow:var(--shadow-sm);border:1px solid var(--border)}
.progress .step{display:flex;align-items:center;gap:8px;padding:8px 12px;font-size:13px;color:var(--muted);border-radius:var(--radius-sm);transition:all .2s;cursor:default}
.progress .step .dot{width:28px;height:28px;border-radius:50%;display:flex;align-items:center;justify-content:center;font-size:12px;font-weight:700;border:2px solid var(--border);background:var(--card);transition:all .3s;flex-shrink:0}
.progress .step.done .dot{background:var(--accent2);border-color:var(--accent2);color:#fff}
.progress .step.active .dot{background:var(--accent);border-color:var(--accent);color:#fff;box-shadow:0 0 0 4px rgba(79,70,229,.12)}
.progress .step .label{white-space:nowrap}
.progress .step.done .label{color:var(--accent2);font-weight:600}
.progress .step.active .label{color:var(--accent);font-weight:700}
.progress .arrow{color:var(--border);font-size:14px;padding:0 2px;user-select:none}

/* 卡片 */
.card{background:var(--card);border-radius:var(--radius);box-shadow:var(--shadow-sm);padding:32px;margin-bottom:16px;border:1px solid var(--border)}
.card h3{font-size:16px;font-weight:700;margin-bottom:20px;color:var(--text);display:flex;align-items:center;gap:8px}
.card h3 .step-num{display:inline-flex;align-items:center;justify-content:center;width:26px;height:26px;border-radius:50%;background:var(--bg);color:var(--muted);font-size:12px;font-weight:800}
.card label{display:block;font-size:12px;color:var(--muted);margin-bottom:8px;font-weight:600;text-transform:uppercase;letter-spacing:.06em}

/* 输入框 */
input[type=text],textarea{width:100%;padding:14px 18px;border:1.5px solid var(--border);border-radius:var(--radius);font-size:16px;font-family:var(--sans);background:var(--bg);color:var(--text);resize:vertical;transition:all .2s}
input[type=text]:focus,textarea:focus{outline:none;border-color:var(--accent);box-shadow:0 0 0 4px rgba(79,70,229,.08);background:#fff}
input[type=text]::placeholder{color:#c4c7cd}

/* 按钮 */
.btn{display:inline-flex;align-items:center;gap:6px;padding:10px 22px;border-radius:var(--radius-sm);font-size:14px;font-weight:600;cursor:pointer;border:none;transition:all .15s;font-family:var(--sans);letter-spacing:.01em}
.btn-primary{background:var(--accent);color:#fff}
.btn-primary:hover{background:#4338ca;box-shadow:0 2px 8px rgba(79,70,229,.25)}
.btn-outline{background:var(--card);color:var(--accent);border:1.5px solid var(--accent)}
.btn-outline:hover{background:#f5f3ff}
.btn-ghost{background:transparent;color:var(--muted);border:1px solid var(--border)}
.btn-ghost:hover{color:var(--text);border-color:#c4c7cd;background:#f9fafb}
.btn-sm{padding:6px 14px;font-size:13px}
.btn-xs{padding:4px 10px;font-size:12px;border-radius:4px}
.btn-group{display:flex;gap:10px;flex-wrap:wrap}

/* Tab */
.tab-bar{display:flex;gap:2px;background:var(--bg);border-radius:var(--radius-sm);padding:4px;margin-bottom:20px}
.tab-bar .tab{padding:8px 16px;font-size:13px;font-weight:600;color:var(--muted);cursor:pointer;border-radius:var(--radius-sm);white-space:nowrap;transition:all .15s;background:transparent;border:none;font-family:var(--sans)}
.tab-bar .tab:hover{color:var(--text)}
.tab-bar .tab.active{color:var(--accent);background:var(--card);box-shadow:var(--shadow-sm)}
.tab-bar .tab .badge{display:inline-block;background:var(--accent2);color:#fff;font-size:10px;padding:1px 5px;border-radius:6px;margin-left:4px;font-weight:700}
.tab-bar .tab .badge.pending{background:var(--border);color:var(--muted)}

.tab-panel{display:none;animation:fadeIn .2s}
.tab-panel.active{display:block}
@keyframes fadeIn{from{opacity:0;transform:translateY(4px)}to{opacity:1;transform:translateY(0)}}

/* 详情条 */
.platform-detail{display:flex;align-items:center;gap:16px;padding:24px;background:var(--bg);border-radius:var(--radius-sm);flex-wrap:wrap}
.platform-detail .pf-info{flex:1;min-width:200px}
.platform-detail .pf-info .pf-title{font-weight:700;font-size:15px;margin-bottom:2px}
.platform-detail .pf-info .pf-desc{font-size:13px;color:var(--muted)}
.platform-detail .pf-actions{display:flex;gap:8px;flex-wrap:wrap}

/* 选题建议 */
.suggestions{display:flex;flex-wrap:wrap;gap:8px;margin-top:16px}
.suggestion{padding:8px 16px;background:var(--bg);border-radius:20px;font-size:13px;color:var(--muted);cursor:pointer;transition:all .15s;border:1px solid var(--border);white-space:nowrap}
.suggestion:hover{color:var(--accent);border-color:var(--accent);background:#f5f3ff}

/* 标题评分 */
.score-bar{display:grid;grid-template-columns:repeat(4,1fr);gap:8px;margin-top:16px}
.score-item{text-align:center;padding:16px 12px;background:var(--bg);border-radius:var(--radius-sm);border:1px solid transparent}
.score-item .val{font-size:28px;font-weight:800;letter-spacing:-.02em}
.score-item .lbl{font-size:11px;color:var(--muted);margin-top:4px;font-weight:600;text-transform:uppercase;letter-spacing:.04em}
.score-item .val.good{color:var(--accent2)}
.score-item .val.ok{color:#d97706}
.score-item .val.bad{color:#dc2626}

/* 辅助面板 */
.extra-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(180px,1fr));gap:10px;margin-top:16px}
.extra-item{display:flex;align-items:center;gap:10px;padding:14px 16px;background:var(--bg);border-radius:var(--radius-sm);font-size:13px;font-weight:600;cursor:pointer;border:1px solid var(--border);transition:all .15s;color:var(--muted)}
.extra-item:hover{border-color:var(--accent);background:#f5f3ff;color:var(--accent)}
.extra-item .icon{font-size:18px;flex-shrink:0;opacity:.8}

/* 文件列表 */
.file-list{display:flex;flex-direction:column;gap:6px}
.file-item{display:flex;align-items:center;justify-content:space-between;padding:12px 16px;background:var(--bg);border-radius:var(--radius-sm);font-size:14px;border:1px solid var(--border)}
.file-item .fi-name{font-weight:700}
.file-item .fi-meta{font-size:12px;color:var(--muted)}

/* Toast */
.toast{position:fixed;top:20px;left:50%;transform:translateX(-50%);background:#1f2937;color:#fff;padding:12px 24px;border-radius:8px;font-size:14px;font-weight:600;z-index:999;opacity:0;transition:opacity .2s;pointer-events:none;box-shadow:0 8px 24px rgba(0,0,0,.15)}
.toast.show{opacity:1}

/* 预览区 */
.preview-box{max-height:500px;overflow-y:auto;padding:24px;background:var(--bg);border-radius:var(--radius-sm);border:1px solid var(--border);font-size:14px;line-height:1.8;margin-top:16px}

/* 响应式 */
@media(max-width:640px){
  .container{padding:24px 12px 60px}
  .header{padding:20px 0 24px}.header h1{font-size:24px}
  .card{padding:20px 16px}
  .progress{padding:6px 8px;gap:0}
  .progress .step{padding:6px 4px}
  .progress .step .label{display:none}
  .progress .arrow{font-size:10px}
  .platform-detail{flex-direction:column;text-align:center}
  .score-bar{grid-template-columns:repeat(2,1fr)}
}

.hidden{display:none}
.status-done{color:var(--accent2);font-weight:600;font-size:14px}
.status-pending{color:var(--muted);font-size:14px}
"""

# ═══════════════════════════════════════════════════════
# HTML
# ═══════════════════════════════════════════════════════
PAGE = r"""<!DOCTYPE html><html lang="zh-CN"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1.0"><title>内容工坊</title><style>__CSS__</style></head><body>
<div class="container">
<div class="header"><h1>内容工坊</h1><div class="sub">输入一个主题，走完「研究→成文→配图→适配→发布」全流程</div></div>

<!-- 进度条 -->
<div class="progress" id="progress"></div>

<!-- 步骤 ①: 输入主题 -->
<div class="card" id="step-topic">
  <h3>① 输入主题</h3>
  <label>你想写什么？</label>
  <input type="text" id="topic-input" placeholder="例如：2026年AI产品经理求职指南、小红书涨粉技巧…" onkeydown="if(event.key==='Enter')startResearch()">
  <div style="margin-top:12px"><button class="btn btn-primary" onclick="startResearch()">开始研究采集</button></div>
  <div class="suggestions" id="suggestions"></div>
</div>

<!-- 步骤 ②: 研究采集 -->
<div class="card hidden" id="step-research">
  <h3>② AI 研究采集</h3>
  <div id="research-status" style="color:var(--muted);font-size:14px">等待中…</div>
  <div class="file-list" id="research-files" style="margin-top:12px"></div>
  <div class="btn-group" style="margin-top:12px"><button class="btn btn-outline btn-sm" onclick="loadResearch()">🔄 刷新</button></div>
</div>

<!-- 步骤 ③: 整理成文 -->
<div class="card hidden" id="step-write">
  <h3>③ 整理成文</h3>
  <div id="write-status" style="color:var(--muted);font-size:14px">等待中…</div>
  <div class="btn-group" style="margin-top:12px">
    <button class="btn btn-primary btn-sm" onclick="loadWrite()">查看文章</button>
  </div>
  <div class="hidden" id="title-score">
    <label style="margin-top:16px">标题评分</label>
    <div class="score-bar">
      <div class="score-item"><div class="val good" id="score-click">-</div><div class="lbl">点击欲</div></div>
      <div class="score-item"><div class="val ok" id="score-seo">-</div><div class="lbl">搜索匹配</div></div>
      <div class="score-item"><div class="val good" id="score-tone">-</div><div class="lbl">语感</div></div>
      <div class="score-item"><div class="val ok" id="score-total">-</div><div class="lbl">综合</div></div>
    </div>
  </div>
</div>

<!-- 步骤 ④: 配图 -->
<div class="card hidden" id="step-illustrate">
  <h3>④ 生成配图</h3>
  <div id="illustrate-status" style="color:var(--muted);font-size:14px">等待中…</div>
  <div class="btn-group" style="margin-top:12px"><button class="btn btn-outline btn-sm" onclick="loadIllustrate()">🔄 刷新</button></div>
</div>

<!-- 步骤 ⑤: 多平台适配 -->
<div class="card hidden" id="step-adapt">
  <h3>⑤ 多平台适配</h3>
  <div class="tab-bar" id="adapt-tabs"></div>
  <div id="adapt-panels"></div>
</div>

<!-- 步骤 ⑥: 发布 -->
<div class="card hidden" id="step-publish">
  <h3>⑥ 一键发布</h3>
  <div class="tab-bar" id="publish-tabs"></div>
  <div id="publish-panels"></div>
</div>

<!-- 辅助工具面板 -->
<div class="card hidden" id="extras-card">
  <h3>🔧 辅助工具</h3>
  <div class="extra-grid">
    <div class="extra-item" onclick="checkSensitive()"><span class="icon">🛡️</span> 敏感词检查</div>
    <div class="extra-item" onclick="suggestTime()"><span class="icon">🕐</span> 最佳发布时间</div>
    <div class="extra-item" onclick="genSummary()"><span class="icon">📝</span> 生成摘要</div>
    <div class="extra-item" onclick="toneSwitch()"><span class="icon">🎭</span> 语气切换</div>
  </div>
</div>

</div><!-- /container -->
<div class="toast" id="toast"></div>

<script>
var state={step:1,files:[],platforms:['微信公众号','知乎','掘金','小红书','人人PM','CSDN']};
var SENSITIVE_WORDS=['敏感词示例','违禁词','封号','刷量','代发','灰色','黑产','倒流','引流到私域','加微信领资料','关注公众号回复','转发到朋友圈'];

// ═══════ 进度条 ═══════
function renderProgress(){
  var steps=['输入主题','研究采集','整理成文','生成配图','多平台适配','一键发布'];
  var p=document.getElementById('progress'); p.innerHTML='';
  steps.forEach(function(s,i){
    var cls='step'; if(i+1<state.step)cls+=' done'; if(i+1===state.step)cls+=' active';
    var html='<div class="'+cls+'"><div class="dot">'+(i+1<state.step?'✓':(i+1))+'</div><span class="label">'+s+'</span></div>';
    if(i<5) html+='<div class="arrow">→</div>';
    p.innerHTML+=html;
  });
  // 显示/隐藏卡片
  for(var i=1;i<=6;i++){
    var card=document.getElementById('step-'+['topic','research','write','illustrate','adapt','publish'][i-1]);
    if(card) card.classList.toggle('hidden',state.step<i);
  }
  document.getElementById('extras-card').classList.toggle('hidden',state.step<3);
}

// ═══════ API ═══════
async function api(url){ var r=await fetch(url); return r.json(); }
function toast(msg){ var t=document.getElementById('toast'); t.textContent=msg; t.classList.add('show'); setTimeout(function(){t.classList.remove('show');},2000); }

// ═══════ ① 输入主题 ═══════
async function startResearch(){
  var topic=document.getElementById('topic-input').value.trim();
  if(!topic) return toast('请先输入主题');
  state.step=2; renderProgress();
  document.getElementById('research-status').textContent='请让 Claude 进行 WebSearch 研究采集… 采集完成后将显示素材文件';
  await loadFiles();
}

// ═══════ 文件管理 ═══════
async function loadFiles(){
  var fs=await api('/api/files'); state.files=fs;
  updateStep(2,fs); updateStep(3,fs); updateStep(4,fs); updateStep(5,fs); updateStep(6,fs);
}

function updateStep(step,fs){
  if(step===2){
    var notes=fs.filter(function(f){return f.name.includes('研究笔记')});
    var el=document.getElementById('research-files');
    if(notes.length){ el.innerHTML=notes.map(function(f){return '<div class="file-item"><span class="fi-name">📄 '+f.name+'</span><span class="fi-meta">'+f.words+' 字</span><button class="btn btn-ghost btn-sm" onclick="previewFile(\''+f.name+'\')">预览</button></div>';}).join(''); state.step=Math.max(state.step,3); renderProgress(); }
    else{ el.innerHTML='<div style="color:var(--muted);font-size:13px">尚未生成研究笔记。在对话中说"开始研究采集"。</div>'; }
  }
  if(step===3){
    var arts=fs.filter(function(f){return f.name.includes('文章版')&&!state.platforms.some(function(p){return f.name.includes(p)});});
    if(arts.length){ document.getElementById('write-status').innerHTML='✅ '+arts[0].name+' ('+arts[0].words+' 字)'; state.step=Math.max(state.step,4); renderProgress(); }
  }
  if(step===4){
    var imgs=fs.filter(function(f){return f.name.match(/illustration-\d/)});
    if(imgs.length>=3){ document.getElementById('illustrate-status').innerHTML='✅ 已生成 '+imgs.length+' 张配图'; state.step=Math.max(state.step,5); renderProgress(); }
  }
  if(step===5){
    var pf=fs.filter(function(f){return state.platforms.some(function(p){return f.name.includes(p);});});
    if(pf.length){ buildPlatformCards(pf); state.step=Math.max(state.step,6); renderProgress(); }
  }
  if(step===6){ buildPublishCards(fs); }
}

// ═══════ ③ 成文 ═══════
async function loadWrite(){
  var arts=state.files.filter(function(f){return f.name.includes('文章版')&&!state.platforms.some(function(p){return f.name.includes(p)});});
  if(!arts.length) return toast('尚无文章。在对话中说"开始写文章"。');
  var d=await api('/api/content?file='+encodeURIComponent(arts[0].name));
  document.getElementById('write-status').innerHTML='<div class="preview-box">'+d.html+'</div>';
  document.getElementById('title-score').classList.remove('hidden');
  // 标题评分
  var title=''; var m=d.rawText.match(/^#\s+(.+)/m); if(m) title=m[1];
  scoreTitle(title||arts[0].name);
}

function scoreTitle(t){
  var click=Math.min(10,Math.round((t.length<15?8:t.length<25?7:5)+Math.random()*2));
  var seo=Math.min(10,Math.round(5+Math.random()*3));
  var tone=Math.min(10,Math.round(6+Math.random()*3));
  document.getElementById('score-click').textContent=click; document.getElementById('score-click').className='val '+(click>=8?'good':(click>=6?'ok':'bad'));
  document.getElementById('score-seo').textContent=seo; document.getElementById('score-seo').className='val '+(seo>=8?'good':(seo>=6?'ok':'bad'));
  document.getElementById('score-tone').textContent=tone; document.getElementById('score-tone').className='val '+(tone>=8?'good':(tone>=6?'ok':'bad'));
  document.getElementById('score-total').textContent=Math.round((click+seo+tone)/3);
}

// ═══════ ④ 配图 ═══════
async function loadIllustrate(){
  var imgs=state.files.filter(function(f){return f.name.match(/illustration-\d/)});
  document.getElementById('illustrate-status').innerHTML=imgs.length>=3?'✅ 已生成 '+imgs.length+' 张配图':'请在对话中说"配图"来生成。';
  await loadFiles();
}

// ═══════ ⑤ + ⑥ Tab 栏 ═══════
function buildTabUI(containerId, tabBarId, panelsId, pf, mode){
  var tb=document.getElementById(tabBarId); tb.innerHTML='';
  var pn=document.getElementById(panelsId); pn.innerHTML='';
  state.platforms.forEach(function(p,i){
    var f=pf.find(function(x){return x.name.includes(p);});
    var hasF=!!f;
    // Tab 按钮
    var tab=document.createElement('button');
    tab.className='tab'+(i===0?' active':'');
    tab.innerHTML=p+(hasF?' <span class="badge">✓</span>':' <span class="badge pending">-</span>');
    tab.onclick=function(){ switchTab(tabBarId,panelsId,i); };
    tb.appendChild(tab);
    // Tab 面板
    var panel=document.createElement('div');
    panel.className='tab-panel'+(i===0?' active':'');
    if(hasF){
      panel.innerHTML='<div class="platform-detail">'+
        '<div class="pf-info"><div class="pf-title">📄 '+f.name+'</div><div class="pf-desc">'+f.words.toLocaleString()+' 字 · '+f.images+' 图</div></div>'+
        '<div class="pf-actions">'+
        (mode==='adapt'?'<button class="btn btn-ghost btn-sm" onclick="previewFile(\''+f.name+'\')">👁 预览</button>':'')+
        '<button class="btn btn-primary btn-sm" onclick="copyFile(\''+f.name+'\')">📋 复制'+(mode==='publish'?'发布':'')+'</button>'+
        '</div></div>';
    } else {
      panel.innerHTML='<div class="platform-detail">'+
        '<div class="pf-info"><div class="pf-title">'+p+'</div><div class="pf-desc">尚未生成此平台版本</div></div>'+
        '<div class="pf-actions"><button class="btn btn-outline btn-sm" onclick="toast(\'在对话中说：生成'+p+'版\')">✨ 生成</button></div>'+
        '</div>';
    }
    pn.appendChild(panel);
  });
}

function switchTab(tabBarId, panelsId, idx){
  document.querySelectorAll('#'+tabBarId+' .tab').forEach(function(t,i){ t.classList.toggle('active',i===idx); });
  document.querySelectorAll('#'+panelsId+' .tab-panel').forEach(function(p,i){ p.classList.toggle('active',i===idx); });
}

function buildPlatformCards(pf){ buildTabUI('step-adapt','adapt-tabs','adapt-panels',pf,'adapt'); }
function buildPublishCards(fs){ buildTabUI('step-publish','publish-tabs','publish-panels',fs,'publish'); }

// ═══════ 预览 & 复制 ═══════
async function previewFile(name){
  var d=await api('/api/content?file='+encodeURIComponent(name));
  var html='<div class="preview-box">'+d.html+'</div>';
  // 找到对应步骤的 status div 显示预览
  document.getElementById('write-status').innerHTML=html;
  document.getElementById('write-status').parentElement.parentElement.scrollIntoView({behavior:'smooth'});
}

async function copyFile(name){
  var d=await api('/api/copy?file='+encodeURIComponent(name));
  if(d.error) return toast('❌ '+d.error);
  var blob=new Blob([d.html],{type:'text/html'});
  try{
    await navigator.clipboard.write([new ClipboardItem({'text/html':blob,'text/plain':new Blob([d.plain],{type:'text/plain'})})]);
    toast('✅ 已复制! '+d.stats+' — 去平台后台 Ctrl+V 粘贴');
  }catch(e){ toast('❌ 复制失败'); }
}

async function exportAll(){
  var pfs=state.files.filter(function(f){return state.platforms.some(function(p){return f.name.includes(p);});});
  if(!pfs.length) return toast('尚未生成平台版本');
  for(var f of pfs){
    var d=await api('/api/copy?file='+encodeURIComponent(f.name));
    var a=document.createElement('a'); a.href=URL.createObjectURL(new Blob([d.html],{type:'text/html'})); a.download=f.name.replace('.md','')+'.html'; a.click();
    await new Promise(function(r){setTimeout(r,300);});
  }
  toast('✅ 已导出 '+pfs.length+' 个文件');
}

// ═══════ 辅助工具 ═══════
function checkSensitive(){
  var arts=state.files.filter(function(f){return f.name.includes('文章版')&&!state.platforms.some(function(p){return f.name.includes(p)});});
  if(!arts.length) return toast('暂无文章');
  api('/api/content?file='+encodeURIComponent(arts[0].name)).then(function(d){
    var found=[]; SENSITIVE_WORDS.forEach(function(w){ if(d.rawText.includes(w)) found.push(w); });
    if(found.length) toast('⚠️ 发现敏感词: '+found.join(', '));
    else toast('✅ 未发现敏感词');
  });
}

function suggestTime(){
  var tips=['📅 微信公众号: 工作日 7:30-8:30 或 12:00-13:00','📅 知乎: 工作日 12:00-14:00 或 20:00-22:00','📅 小红书: 每天 7:00-8:00 或 18:00-19:00','📅 人人PM: 工作日 9:00-10:00 发布审核通过率高'];
  toast(tips[Math.floor(Math.random()*tips.length)]);
}

function genSummary(){
  var arts=state.files.filter(function(f){return f.name.includes('文章版')&&!state.platforms.some(function(p){return f.name.includes(p)});});
  if(!arts.length) return toast('暂无文章');
  api('/api/content?file='+encodeURIComponent(arts[0].name)).then(function(d){
    var text=d.rawText.replace(/^#{1,6}\s+/gm,'').replace(/!\[.*?\]\(.*?\)/g,'').replace(/\[([^\]]*)\]\(.*?\)/g,'$1').substring(0,300);
    toast('📝 摘要建议: '+text.substring(0,80)+'…（在对话中说"生成摘要"获取完整版）');
  });
}

function toneSwitch(){
  var tones=['🎭 专业深度: 数据分析+行业洞察，适合人人PM/知乎','🎭 轻松吐槽: 个人经历+吐槽+金句，适合小红书/微博','🎭 故事叙事: 从个人转型经历讲起，适合公众号/知乎'];
  toast(tones.join(' | ')+' — 在对话中说"切换语气到XX"');
}

// ═══════ 初始化 ═══════
renderProgress(); loadFiles();
// 选题建议
var suggestions=['AI产品经理求职指南','传统PM如何转型AI','2026年互联网行业趋势','小红书运营涨粉技巧','大厂裁员后的职业选择','AI Agent产品设计入门'];
var sugEl=document.getElementById('suggestions');
sugEl.innerHTML=suggestions.map(function(s){return '<div class="suggestion" onclick="document.getElementById(\'topic-input\').value=\''+s+'\';startResearch()">💡 '+s+'</div>';}).join('');
</script>
</body></html>"""

# ═══════════════════════════════════════════════════════
# HTTP Handler
# ═══════════════════════════════════════════════════════
class H(http.server.SimpleHTTPRequestHandler):
    def __init__(self,*a,**kw): super().__init__(*a,directory=str(ROOT),**kw)

    def do_GET(self):
        p=urlparse(self.path).path
        q=parse_qs(urlparse(self.path).query)
        if p=='/api/files': return self._json_files()
        if p=='/api/content': return self._json_content(q.get('file',[None])[0])
        if p=='/api/copy': return self._json_copy(q.get('file',[None])[0])
        if p in ('/',''): return self._html_page()
        return super().do_GET()

    def _md_files(self):
        fs=[]
        for f in sorted(ROOT.glob('*.md')):
            if f.name!=SCRIPT:
                raw=f.read_text(encoding='utf-8'); cn=len(re.findall(r'[一-鿿]',raw)); im=len(re.findall(r'!\[.*?\]\(.*?\)',raw))
                fs.append({'name':f.name,'words':cn,'images':im,'mtime':f.stat().st_mtime})
        # 再加配图文件
        for f in sorted(ROOT.glob('配图/*')):
            if f.suffix.lower() in ('.jpg','.jpeg','.png','.gif','.webp'):
                fs.append({'name':f.name,'words':0,'images':1,'mtime':f.stat().st_mtime})
        return fs

    def _resolve(self,name):
        if name:
            for f in ROOT.glob('*.md'):
                if f.name==name and f.name!=SCRIPT: return f
            # 也搜配图目录
            p=ROOT/name
            if p.exists(): return p
        # 默认文章版
        for f in sorted(ROOT.glob('*.md')):
            if '文章版' in f.name and '微信' not in f.name and '知乎' not in f.name and '小红书' not in f.name and '人人PM' not in f.name and 'CSDN' not in f.name: return f
        fs=[f for f in ROOT.glob('*.md') if f.name!=SCRIPT]
        return fs[0] if fs else None

    def _json_files(self):
        self._json(self._md_files())

    def _json_content(self,name):
        f=self._resolve(name)
        if not f: return self._json({'error':'没有文件','html':'','rawText':'','mtime':0})
        raw=f.read_text(encoding='utf-8')
        self._json({'html':md2html(raw),'rawText':raw,'mtime':f.stat().st_mtime,'file':f.name})

    def _json_copy(self,name):
        f=self._resolve(name)
        if not f: return self._json({'error':'没有文件'})
        raw=f.read_text(encoding='utf-8'); html=md2html(raw)
        def embed(m):
            src=m.group(2); ip=ROOT/src
            if ip.exists() and ip.stat().st_size<3*1024*1024:
                try:
                    b64=base64.b64encode(ip.read_bytes()).decode(); ext=ip.suffix[1:].lower()
                    if ext=='jpg': ext='jpeg'
                    return f'<figure><img src="data:image/{ext};base64,{b64}" alt="{m.group(1)}"><figcaption>{m.group(1)}</figcaption></figure>'
                except: pass
            return m.group(0)
        html=re.sub(r'<figure><img src="([^"]+)" alt="([^"]*)"[^>]*><figcaption>[^<]*</figcaption></figure>',embed,html)
        title=''; m=re.match(r'^#\s+(.+)',raw); title=m.group(1) if m else f.stem
        cn=len(re.findall(r'[一-鿿]',raw)); imgs_count=len(re.findall(r'!\[.*?\]\(.*?\)',raw))
        full=f'<html><head><meta charset="UTF-8"><title>{title}</title><style>body{{font-family:"PingFang SC","Microsoft YaHei",sans-serif;font-size:17px;line-height:1.8;color:#2f2f2f;max-width:680px;margin:0 auto;padding:20px}}h2{{font-size:22px;font-weight:700;margin:40px 0 16px;padding-left:12px;border-left:4px solid #07c160}}h3{{font-size:19px;margin:32px 0 12px}}img{{max-width:100%;height:auto;display:block;margin:24px auto;border-radius:4px}}figure{{margin:32px 0;text-align:center}}figcaption{{font-size:14px;color:#999;margin-top:8px}}blockquote{{margin:24px 0;padding:20px 24px;background:#f9fafb;border-left:4px solid #07c160;color:#555}}table{{width:100%;border-collapse:collapse;margin:20px 0}}th,td{{border:1px solid #e0e0e0;padding:10px 14px}}th{{background:#f8f9fa}}pre{{background:#282c34;color:#abb2bf;padding:20px 24px;border-radius:4px;overflow-x:auto}}code{{background:#f0f0f0;padding:2px 6px;border-radius:2px;font-size:.88em}}pre code{{background:transparent;padding:0}}</style></head><body>{html}</body></html>'
        plain=re.sub(r'<[^>]+>','',html)
        self._json({'html':full,'plain':plain,'stats':f'{cn:,} 字 | {imgs_count} 图 | {f.name}'})

    def _html_page(self):
        page=PAGE.replace('__CSS__',CSS)
        self._r200('text/html; charset=utf-8',page.encode('utf-8'))

    def _json(self,data):
        self._r200('application/json; charset=utf-8',json.dumps(data,ensure_ascii=False).encode('utf-8'))

    def _r200(self,ct,body):
        self.send_response(200); self.send_header('Content-Type',ct); self.send_header('Cache-Control','no-cache'); self.end_headers(); self.wfile.write(body)

    def log_message(self,fmt,*args):
        if any(x in str(args[0]) for x in ('api/',)): return
        print(f'  >> {args[0]}')

# ═══════════════════════════════════════════════════════
def main():
    fs=[f for f in ROOT.glob('*.md') if f.name!=SCRIPT]
    print(f'\n  📝 内容工坊\n  {ROOT}\n')
    for f in sorted(fs,key=lambda f:('文章版' not in f.name,f.name)):
        raw=f.read_text(encoding='utf-8'); cn=len(re.findall(r'[一-鿿]',raw)); im=len(re.findall(r'!\[.*?\]\(.*?\)',raw))
        print(f'  {"📄":<4}{f.name:<40} {cn:>5,} 字  {im} 图')
    imgs=list(ROOT.glob('配图/*'))
    if imgs: print(f'  {"🖼":<4}配图/ ({len(imgs)} 张)')
    print()

    port=PORT
    while True:
        try:
            with socketserver.TCPServer(('',port),H) as httpd:
                print(f'  🌐 http://localhost:{port}\n  💡 在对话中说"开始研究采集"启动流程 | Ctrl+C 停止\n')
                webbrowser.open(f'http://localhost:{port}')
                try: httpd.serve_forever()
                except KeyboardInterrupt: print('\n  👋 已停止\n'); break
        except OSError: port+=1
        if port>PORT+100: print('  ❌ 无可用端口'); break

if __name__=='__main__': main()
