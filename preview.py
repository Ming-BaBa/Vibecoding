#!/usr/bin/env python3
"""内容工坊 - 预览底座 v4.0  零依赖，纯 Python 标准库。不做平台适配。"""

import http.server, json, re, socketserver, webbrowser, base64
from pathlib import Path
from urllib.parse import urlparse, parse_qs

PORT = 8899
ROOT = Path(__file__).parent.resolve()
SCRIPT = Path(__file__).name

# ═══════════════════════════════════════════════════════════════
# Markdown → HTML（简易解析器）
# ═══════════════════════════════════════════════════════════════
def md2html(text):
    cb, ic, imgs, lks = [], [], [], []

    def _sc(m): cb.append(m.group(0)); return f"\x00CB{len(cb)-1}\x00"
    def _si(m): ic.append(m.group(1)); return f"\x00IC{len(ic)-1}\x00"
    def _sim(m): imgs.append((m.group(1),m.group(2))); return f"\x00IM{len(imgs)-1}\x00"
    def _slk(m): lks.append((m.group(1),m.group(2))); return f"\x00LK{len(lks)-1}\x00"

    text = re.sub(r'```[^`]*```', _sc, text)
    text = re.sub(r'`([^`]+)`', _si, text)
    text = re.sub(r'!\[([^\]]*)\]\(([^)]+)\)', _sim, text)
    text = re.sub(r'\[([^\]]*)\]\(([^)]+)\)', _slk, text)

    for lv in range(6,0,-1):
        text = re.sub(rf'^{"#"*lv}\s+(.+?)$', rf'<h{lv}>\1</h{lv}>', text, flags=re.MULTILINE)
    text = re.sub(r'^---+\s*$', '<hr>', text, flags=re.MULTILINE)

    # 引用块
    lines,out,bq = text.split('\n'),[],[]
    for ln in lines:
        m=re.match(r'^>\s?(.*)',ln)
        if m: bq.append(m.group(1))
        else:
            if bq: out.append('<blockquote><p>'+'<br>'.join(bq)+'</p></blockquote>'); bq=[]
            out.append(ln)
    if bq: out.append('<blockquote><p>'+'<br>'.join(bq)+'</p></blockquote>')
    text='\n'.join(out)

    # 表格
    lines,out,tbl=text.split('\n'),[],[]
    for ln in lines:
        if re.match(r'^\|.+\|$',ln): tbl.append(ln)
        else:
            if tbl:
                h='<table>'
                hc=[c.strip() for c in tbl[0].split('|')[1:-1]]
                h+='<thead><tr>'+''.join(f'<th>{c}</th>' for c in hc)+'</tr></thead><tbody>'
                for row in tbl[1:]:
                    if re.match(r'^[\|\s\-:]+$',row): continue
                    cells=[c.strip() for c in row.split('|')[1:-1]]
                    h+='<tr>'+''.join(f'<td>{c}</td>' for c in cells)+'</tr>'
                h+='</tbody></table>'; out.append(h); tbl=[]
            out.append(ln)
    if tbl:
        h='<table><thead><tr>'+''.join(f'<th>{c.strip()}</th>' for c in tbl[0].split('|')[1:-1])+'</tr></thead><tbody>'
        for row in tbl[1:]:
            if re.match(r'^[\|\s\-:]+$',row): continue
            cells=[c.strip() for c in row.split('|')[1:-1]]
            h+='<tr>'+''.join(f'<td>{c}</td>' for c in cells)+'</tr>'
        h+='</tbody></table>'; out.append(h)
    text='\n'.join(out)

    # 列表
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

    # 粗/斜
    text=re.sub(r'\*\*(.+?)\*\*',r'<strong>\1</strong>',text)
    text=re.sub(r'__(.+?)__',r'<strong>\1</strong>',text)
    text=re.sub(r'\*(.+?)\*',r'<em>\1</em>',text)

    # 段落
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

    # 恢复
    for i,(label,url) in enumerate(lks): text=text.replace(f'\x00LK{i}\x00',f'<a href="{url}">{label}</a>')
    for i,(alt,src) in enumerate(imgs): text=text.replace(f'\x00IM{i}\x00',f'<figure><img src="{src}" alt="{alt}" loading="lazy"><figcaption>{alt}</figcaption></figure>')
    for i,code in enumerate(ic): text=text.replace(f'\x00IC{i}\x00',f'<code>{code}</code>')
    for i,block in enumerate(cb):
        inner=re.sub(r'^```\w*\n?','',block); inner=re.sub(r'```$','',inner)
        inner=inner.replace('&','&amp;').replace('<','&lt;').replace('>','&gt;')
        text=text.replace(f'\x00CB{i}\x00',f'<pre><code>{inner}</code></pre>')

    text=re.sub(r'<p>\s*</p>','',text)
    return text

# ═══════════════════════════════════════════════════════════════
# CSS + HTML
# ═══════════════════════════════════════════════════════════════
CSS = """
*,*::before,*::after{box-sizing:border-box;margin:0;padding:0}
body{font-family:"PingFang SC","Hiragino Sans GB","Microsoft YaHei","Helvetica Neue",sans-serif;font-size:17px;line-height:1.8;color:#2f2f2f;background:#f5f5f5;-webkit-font-smoothing:antialiased}
.wrapper{max-width:680px;margin:0 auto;padding:0 16px 40px}
.article{background:#fff;margin-top:20px;border-radius:0;padding:60px 48px 48px;box-shadow:0 1px 3px rgba(0,0,0,.04)}
.toolbar{position:fixed;top:0;left:0;right:0;z-index:100;background:rgba(255,255,255,.95);backdrop-filter:blur(10px);border-bottom:1px solid #eee;padding:8px 16px;display:flex;align-items:center;gap:10px;font-size:13px}
.toolbar-spacer{height:48px}
.toolbar select{padding:4px 8px;border:1px solid #d9d9d9;border-radius:3px;font-size:13px;background:#fff;cursor:pointer;max-width:260px}
.toolbar .btn{padding:5px 14px;border:1px solid #d9d9d9;border-radius:3px;background:#fff;font-size:12px;cursor:pointer;color:#333;white-space:nowrap}
.toolbar .btn:hover{border-color:#07c160;color:#07c160}
.toolbar .btn.primary{background:#07c160;color:#fff;border-color:#07c160;font-weight:600}
.toolbar .btn.primary:hover{background:#06ad56}
.toolbar .dot{width:6px;height:6px;border-radius:50%;background:#52c41a;margin-left:auto;opacity:.6}
.toast{position:fixed;top:60px;left:50%;transform:translateX(-50%);background:#333;color:#fff;padding:10px 24px;border-radius:6px;font-size:14px;z-index:999;opacity:0;transition:opacity .2s}
.toast.show{opacity:1}
.content h1{font-size:28px;font-weight:700;line-height:1.4;color:#111;margin-bottom:16px}
.content h2{font-size:22px;font-weight:700;color:#111;margin:40px 0 16px;padding-left:12px;border-left:4px solid #07c160}
.content h3{font-size:19px;font-weight:700;color:#1a1a1a;margin:32px 0 12px}
.content h4{font-size:17px;font-weight:700;color:#333;margin:24px 0 8px}
.content p{margin:0 0 1.2em;text-align:justify}
.content strong{font-weight:700;color:#111}
.content a{color:#576b95;text-decoration:none}
.content blockquote{margin:24px 0;padding:20px 24px;background:#f9fafb;border-left:4px solid #07c160;color:#555;font-size:16px}
.content blockquote p{margin:0}
.content ul,.content ol{margin:12px 0 20px;padding-left:1.8em}
.content li{margin:6px 0}
.content hr{border:none;height:1px;background:#eee;margin:40px 0}
.content code{background:#f0f0f0;padding:2px 6px;border-radius:2px;font-size:.88em;font-family:SFMono-Regular,Consolas,monospace;color:#c7254e}
.content pre{background:#282c34;color:#abb2bf;padding:20px 24px;border-radius:4px;overflow-x:auto;margin:20px 0;line-height:1.6;font-size:14px}
.content pre code{background:transparent;padding:0;color:inherit}
.content table{width:100%;border-collapse:collapse;margin:20px 0;font-size:15px}
.content th,.content td{border:1px solid #e0e0e0;padding:10px 14px;text-align:left}
.content th{background:#f8f9fa;font-weight:700}
.content tr:nth-child(even) td{background:#fafbfc}
.content figure{margin:32px 0;text-align:center}
.content figure img{max-width:100%;height:auto;border-radius:4px;box-shadow:0 2px 12px rgba(0,0,0,.06);cursor:zoom-in}
.content figcaption{margin-top:10px;font-size:14px;color:#999}
.footer-bar{margin-top:40px;padding-top:20px;border-top:1px solid #f0f0f0;display:flex;gap:20px;font-size:13px;color:#bbb}
.lb{display:none;position:fixed;z-index:999;left:0;top:0;width:100%;height:100%;background:rgba(0,0,0,.92);justify-content:center;align-items:center;cursor:zoom-out}
.lb.show{display:flex}
.lb img{max-width:92vw;max-height:92vh;border-radius:4px}
.lb .close{position:fixed;top:20px;right:30px;color:#fff;font-size:36px;cursor:pointer;opacity:.7}
.lb .close:hover{opacity:1}
@media(max-width:768px){.article{padding:32px 20px 24px}body{font-size:16px}.content h2{font-size:20px}}
"""

PAGE = r"""<!DOCTYPE html><html lang="zh-CN"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1.0"><title>__TITLE__</title><style>__CSS__</style></head><body>
<div class="toolbar">
  <span style="color:#999">文件:</span>
  <select id="fs" onchange="switchFile()"></select>
  <button class="btn primary" onclick="copyHTML()">&#128203; 复制 HTML</button>
  <button class="btn" onclick="exportHTML()">&#128229; 导出</button>
  <span class="dot" title="热重载中"></span>
</div>
<div class="toast" id="toast"></div><div class="toolbar-spacer"></div>
<div class="wrapper"><div class="article">
<div class="content" id="content"><div style="text-align:center;padding:80px 20px;color:#bbb"><div style="font-size:48px;margin-bottom:16px">&#9203;</div><p>加载中…</p></div></div>
<div class="footer-bar"><span>&#9998; <span id="wc">-</span></span><span>&#128444; <span id="ic">-</span></span><span>&#9201; <span id="rt">-</span> min</span><span>&#8635; <span id="lr">-</span></span></div>
</div></div>
<div class="lb" id="lb"><span class="close">&times;</span><img id="lb-img" src="" alt=""></div>
<script>
var _mtime=null,_files=[];
fetch('/__files__').then(function(r){return r.json()}).then(function(fs){
  _files=fs; var sel=document.getElementById('fs');
  fs.forEach(function(f,i){ var o=document.createElement('option'); o.value=f.name; o.textContent=f.name+(f.current?' (当前)':''); if(f.current)o.selected=true; sel.appendChild(o); });
  load();
});
function switchFile(){ load(); }
function load(){
  var f=document.getElementById('fs').value;
  fetch('/__content__?file='+encodeURIComponent(f)+'&t='+Date.now()).then(function(r){return r.json()}).then(function(d){
    if(d.error){ document.getElementById('content').innerHTML='<div style="text-align:center;padding:80px 20px;color:#bbb"><p>'+d.error+'</p></div>'; return; }
    if(_mtime&&d.mtime===_mtime) return; _mtime=d.mtime;
    var title='';
    var m=d.rawText.match(/^#\s+(.+)/m); if(m) title=m[1];
    document.getElementById('content').innerHTML=(title?'<h1>'+title+'</h1>':'')+d.html;
    document.title=title||f; document.getElementById('lr').textContent=new Date().toLocaleTimeString('zh-CN');
    stats(d.rawText); bindImgs();
  }).catch(function(e){ document.getElementById('content').innerHTML='<div style="text-align:center;padding:80px 20px;color:#bbb"><p>加载失败: '+e.message+'</p></div>'; });
}
function stats(md){ var t=md.replace(/^#{1,6}\s+/gm,'').replace(/!\[.*?\]\(.*?\)/g,'').replace(/\[([^\]]*)\]\(.*?\)/g,'$1').replace(/```[\s\S]*?```/g,'').replace(/`[^`]*`/g,'').replace(/\|.*\|/g,'').replace(/[-*_#>]/g,''); var cn=(t.match(/[一-鿿]/g)||[]).length; var en=t.trim().split(/\s+/).filter(Boolean).length; var total=cn+en; var imgs=(md.match(/!\[.*?\]\(.*?\)/g)||[]).length; document.getElementById('wc').textContent=total.toLocaleString()+' 字'; document.getElementById('ic').textContent=imgs+' 图'; document.getElementById('rt').textContent=Math.max(1,Math.round(total/600)); }
function bindImgs(){ document.querySelectorAll('.content img').forEach(function(img){ img.addEventListener('click',function(){ document.getElementById('lb-img').src=img.src; document.getElementById('lb').classList.add('show'); }); }); }
function copyHTML(){
  var f=document.getElementById('fs').value;
  fetch('/__copy__?file='+encodeURIComponent(f)).then(function(r){return r.json()}).then(function(d){
    if(d.error){ toast('&#10060; '+d.error); return; }
    var blob=new Blob([d.html],{type:'text/html'});
    navigator.clipboard.write([new ClipboardItem({'text/html':blob,'text/plain':new Blob([d.plain],{type:'text/plain'})})]).then(function(){ toast('&#9989; 已复制! '+d.stats); }).catch(function(){ toast('&#10060; 复制失败，请重试'); });
  });
}
function exportHTML(){
  var f=document.getElementById('fs').value;
  fetch('/__copy__?file='+encodeURIComponent(f)).then(function(r){return r.json()}).then(function(d){
    if(d.error){ toast('&#10060; '+d.error); return; }
    var a=document.createElement('a'); a.href=URL.createObjectURL(new Blob([d.html],{type:'text/html'})); a.download=f.replace('.md','')+'.html'; a.click();
    toast('&#9989; 已导出 '+a.download);
  });
}
function toast(msg){ var t=document.getElementById('toast'); t.innerHTML=msg; t.classList.add('show'); setTimeout(function(){t.classList.remove('show');},2000); }
document.getElementById('lb').addEventListener('click',function(e){ if(e.target===this||e.target.classList.contains('close'))this.classList.remove('show'); });
document.addEventListener('keydown',function(e){ if(e.key==='Escape')document.getElementById('lb').classList.remove('show'); });
load(); setInterval(load,2000);
</script></body></html>"""

# ═══════════════════════════════════════════════════════════════
# HTTP Handler
# ═══════════════════════════════════════════════════════════════
class H(http.server.SimpleHTTPRequestHandler):
    def __init__(self,*a,**kw): super().__init__(*a,directory=str(ROOT),**kw)

    def do_GET(self):
        p=urlparse(self.path).path
        q=parse_qs(urlparse(self.path).query)
        if p=='/__files__': return self._json_files()
        if p=='/__content__': return self._json_content(q.get('file',[None])[0])
        if p=='/__copy__': return self._json_copy(q.get('file',[None])[0])
        if p in ('/',''): return self._html_page()
        return super().do_GET()

    def _md_files(self):
        return sorted([f for f in ROOT.glob('*.md') if f.name!=SCRIPT],
                      key=lambda f: ('文章版' not in f.name, f.name))

    def _resolve(self, name):
        if name:
            for f in self._md_files():
                if f.name==name: return f
        # 默认：优先文章版
        for f in self._md_files():
            if '文章版' in f.name: return f
        fs=self._md_files()
        return fs[0] if fs else None

    def _json_files(self):
        fs=self._md_files()
        cur=self._resolve(None)
        self._json([{'name':f.name,'current':f==cur} for f in fs])

    def _json_content(self, name):
        f=self._resolve(name)
        if not f: return self._json({'error':'没有 .md 文件','html':'','rawText':'','title':'','mtime':0})
        raw=f.read_text(encoding='utf-8')
        self._json({'html':md2html(raw),'rawText':raw,'mtime':f.stat().st_mtime,'file':f.name})

    def _json_copy(self, name):
        f=self._resolve(name)
        if not f: return self._json({'error':'没有 .md 文件'})
        raw=f.read_text(encoding='utf-8')
        html=md2html(raw)

        # 图片 base64 内联
        def embed_img(m):
            src=m.group(2)
            img_path=ROOT/src
            if img_path.exists() and img_path.stat().st_size<3*1024*1024:
                try:
                    b64=base64.b64encode(img_path.read_bytes()).decode()
                    ext=img_path.suffix[1:].lower()
                    if ext=='jpg': ext='jpeg'
                    return f'<figure><img src="data:image/{ext};base64,{b64}" alt="{m.group(1)}"><figcaption>{m.group(1)}</figcaption></figure>'
                except: pass
            return m.group(0)
        html=re.sub(r'<figure><img src="([^"]+)" alt="([^"]*)"[^>]*><figcaption>[^<]*</figcaption></figure>', embed_img, html)

        title='' ; m=re.match(r'^#\s+(.+)',raw); title=m.group(1) if m else f.stem
        cn=len(re.findall(r'[一-鿿]',raw)); imgs_count=len(re.findall(r'!\[.*?\]\(.*?\)',raw))
        full=f'<html><head><meta charset="UTF-8"><title>{title}</title>'
        full+=f'<style>body{{font-family:"PingFang SC","Microsoft YaHei",sans-serif;font-size:17px;line-height:1.8;color:#2f2f2f;max-width:680px;margin:0 auto;padding:20px}}'
        full+=f'h2{{font-size:22px;font-weight:700;margin:40px 0 16px;padding-left:12px;border-left:4px solid #07c160}}'
        full+=f'h3{{font-size:19px;font-weight:700;margin:32px 0 12px}}'
        full+=f'img{{max-width:100%;height:auto;display:block;margin:24px auto;border-radius:4px}}'
        full+=f'figure{{margin:32px 0;text-align:center}} figcaption{{font-size:14px;color:#999;margin-top:8px}}'
        full+=f'blockquote{{margin:24px 0;padding:20px 24px;background:#f9fafb;border-left:4px solid #07c160;color:#555}}'
        full+=f'table{{width:100%;border-collapse:collapse;margin:20px 0}} th,td{{border:1px solid #e0e0e0;padding:10px 14px}} th{{background:#f8f9fa}}'
        full+=f'pre{{background:#282c34;color:#abb2bf;padding:20px 24px;border-radius:4px;overflow-x:auto}}'
        full+=f'code{{background:#f0f0f0;padding:2px 6px;border-radius:2px;font-size:.88em}} pre code{{background:transparent;padding:0}}'
        full+=f'</style></head><body>{html}</body></html>'

        plain=re.sub(r'<[^>]+>','',html)

        self._json({'html':full,'plain':plain,'stats':f'{cn:,} 字 | {imgs_count} 图 | {f.name}'})

    def _html_page(self):
        f=self._resolve(None)
        title=f.stem if f else '内容工坊'
        page=PAGE.replace('__TITLE__',title).replace('__CSS__',CSS)
        self._r200('text/html; charset=utf-8',page.encode('utf-8'))

    def _json(self,data):
        self._r200('application/json; charset=utf-8',json.dumps(data,ensure_ascii=False).encode('utf-8'))

    def _r200(self,ct,body):
        self.send_response(200); self.send_header('Content-Type',ct); self.send_header('Cache-Control','no-cache'); self.end_headers(); self.wfile.write(body)

    def log_message(self,fmt,*args):
        if any(x in str(args[0]) for x in ('__content__','__files__','__copy__')): return
        print(f'  >> {args[0]}')

# ═══════════════════════════════════════════════════════════════
def main():
    fs=[f for f in ROOT.glob('*.md') if f.name!=SCRIPT]
    print(f'\n  内容工坊 v4.0\n  {ROOT}\n')
    for f in sorted(fs,key=lambda f:('文章版' not in f.name,f.name)):
        raw=f.read_text(encoding='utf-8'); cn=len(re.findall(r'[一-鿿]',raw)); im=len(re.findall(r'!\[.*?\]\(.*?\)',raw))
        tag=' ← 默认' if '文章版' in f.name else ''
        print(f'  {'📄':<4}{f.name:<40} {cn:>5,} 字  {im} 图{tag}')
    print()

    port=PORT
    while True:
        try:
            with socketserver.TCPServer(('',port),H) as httpd:
                print(f'  🌐 http://localhost:{port}\n  💡 下拉切换文件 | 复制HTML | Ctrl+C 停止\n')
                webbrowser.open(f'http://localhost:{port}')
                try: httpd.serve_forever()
                except KeyboardInterrupt: print('\n  👋 已停止\n'); break
        except OSError: port+=1
        if port>PORT+100: print('  ❌ 无可用端口'); break

if __name__=='__main__': main()
