"""Generate a self-contained static HTML dashboard for CTA signals."""
from datetime import datetime
from pathlib import Path

from config import OUTPUT_DIR


# ── Helper renderers ───────────────────────────────────

def _sparkline(prices: list[float], w: int = 100, h: int = 28) -> str:
    valid = [p for p in prices if p and p > 0]
    if len(valid) < 2:
        return ""
    lo, hi = min(valid), max(valid)
    rng = hi - lo or 1
    n = len(valid)
    pts = []
    for i, p in enumerate(valid):
        x = round(i / (n - 1) * w, 1)
        y = round(h - 2 - (p - lo) / rng * (h - 4), 1)
        pts.append(f"{x},{y}")
    color = "#3fb950" if valid[-1] >= valid[0] else "#f85149"
    lx, ly = pts[-1].split(",")
    return (
        f'<svg width="{w}" height="{h}">'
        f'<polyline points="{" ".join(pts)}" fill="none" stroke="{color}" '
        f'stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/>'
        f'<circle cx="{lx}" cy="{ly}" r="2" fill="{color}"/>'
        f"</svg>"
    )


def _rsi_bar(val: float) -> str:
    pct = max(0, min(val / 100, 1))
    if val < 30:
        c = "#f85149"
    elif val < 50:
        c = "#d29922"
    elif val < 70:
        c = "#58a6ff"
    else:
        c = "#3fb950"
    return (
        f'<div class="rsi-bar">'
        f'<div class="rsi-fill" style="width:{pct*100:.0f}%;background:{c}"></div>'
        f'<span class="rsi-val">{val:.1f}</span>'
        f"</div>"
    )


def _badges(descs: list[str]) -> str:
    parts = []
    for d in descs:
        if "反彈" in d or "金叉" in d:
            cls = "bg"
        elif "收斂" in d or "低檔" in d:
            cls = "by"
        elif "超賣" in d:
            cls = "br"
        else:
            cls = "bw"
        parts.append(f'<span class="bd {cls}">{d}</span>')
    return " ".join(parts)


def _stars(n: int, level: str) -> str:
    c = {"strong": "#3fb950", "medium": "#d29922", "watch": "#8b949e"}[level]
    return f'<span style="color:{c};letter-spacing:2px">{"★" * n}{"☆" * (5 - n)}</span>'


def _fmt_macd(v: float) -> str:
    a = abs(v)
    if a >= 1:
        return f"{v:.2f}"
    if a >= 0.01:
        return f"{v:.3f}"
    return f"{v:.4f}"


# ── Main generator ─────────────────────────────────────

def generate_report(results: list[dict], total_scanned: int, date_str: str) -> Path:
    strong = sum(1 for r in results if r["level"] == "strong")
    medium = sum(1 for r in results if r["level"] == "medium")
    watch  = sum(1 for r in results if r["level"] == "watch")

    # build table rows
    rows = []
    for i, r in enumerate(results, 1):
        chg = r["pct_change"]
        chg_cls = "gr" if chg >= 0 else "rd"
        chg_sign = "+" if chg >= 0 else ""
        rows.append(
            f'<tr data-level="{r["level"]}">'
            f'<td class="c" data-v="{i}">{i}</td>'
            f'<td class="code"><a href="https://www.google.com/finance/quote/{r["code"]}:TPE" target="_blank">{r["code"]}</a></td>'
            f'<td>{r["name"]}</td>'
            f'<td class="mkt">{r["market"]}</td>'
            f'<td class="n" data-v="{r["close"]}">{r["close"]:.2f}</td>'
            f'<td class="n {chg_cls}" data-v="{chg}">{chg_sign}{chg:.2f}%</td>'
            f'<td data-v="{r["rsi"]}">{_rsi_bar(r["rsi"])}</td>'
            f'<td class="n mono" data-v="{r["macd"]}">{_fmt_macd(r["macd"])}</td>'
            f'<td class="sigs">{_badges(r["descriptions"])}</td>'
            f'<td class="c" data-v="{r["stars"]}">{_stars(r["stars"], r["level"])}</td>'
            f'<td class="spark">{_sparkline(r.get("recent_prices", []))}</td>'
            f"</tr>"
        )
    tbody = "\n".join(rows)

    no_signal_row = (
        '<tr><td colspan="11" style="text-align:center;padding:40px;color:var(--t2)">'
        "今日未偵測到反轉訊號</td></tr>"
        if not results
        else ""
    )

    html = _TEMPLATE.format(
        date=date_str,
        now=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        strong=strong,
        medium=medium,
        watch=watch,
        total=total_scanned,
        tbody=tbody or no_signal_row,
    )

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    out = OUTPUT_DIR / f"cta_report_{date_str}.html"
    out.write_text(html, encoding="utf-8")
    return out


# ── HTML template (self-contained) ─────────────────────

_TEMPLATE = r"""<!DOCTYPE html>
<html lang="zh-TW">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>CTA Dashboard — {date}</title>
<style>
:root{{
  --bg:#0d1117;--sf:#161b22;--sf2:#21262d;--bd:#30363d;
  --t1:#e6edf3;--t2:#8b949e;
  --gr:#3fb950;--rd:#f85149;--yw:#d29922;--bl:#58a6ff;
}}
*{{margin:0;padding:0;box-sizing:border-box}}
body{{background:var(--bg);color:var(--t1);
  font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Helvetica,Arial,sans-serif;
  font-size:14px;line-height:1.5}}
.wrap{{max-width:1480px;margin:0 auto;padding:24px}}

/* header */
header{{text-align:center;margin-bottom:32px;padding-bottom:24px;border-bottom:1px solid var(--bd)}}
header h1{{font-size:28px;font-weight:700;
  background:linear-gradient(135deg,var(--gr),var(--bl));
  -webkit-background-clip:text;-webkit-text-fill-color:transparent}}
.sub{{color:var(--t2);font-size:15px;margin-top:6px}}

/* summary cards */
.cards{{display:grid;grid-template-columns:repeat(4,1fr);gap:16px;margin-bottom:24px}}
.cd{{background:var(--sf);border:1px solid var(--bd);border-radius:12px;padding:20px;text-align:center}}
.cd-n{{font-size:36px;font-weight:700;font-variant-numeric:tabular-nums}}
.cd-l{{color:var(--t2);font-size:13px;margin-top:4px}}
.cd-s{{border-left:4px solid var(--gr)}} .cd-s .cd-n{{color:var(--gr)}}
.cd-m{{border-left:4px solid var(--yw)}} .cd-m .cd-n{{color:var(--yw)}}
.cd-w{{border-left:4px solid var(--t2)}} .cd-w .cd-n{{color:var(--t2)}}
.cd-t{{border-left:4px solid var(--bl)}} .cd-t .cd-n{{color:var(--bl)}}

/* controls */
.ctl{{display:flex;gap:12px;margin-bottom:16px}}
.ctl input,.ctl select{{
  background:var(--sf);border:1px solid var(--bd);border-radius:8px;
  color:var(--t1);padding:8px 14px;font-size:14px;outline:none}}
.ctl input{{flex:1;max-width:320px}}
.ctl input:focus,.ctl select:focus{{border-color:var(--bl)}}

/* table */
.tw{{overflow-x:auto;border:1px solid var(--bd);border-radius:12px}}
table{{width:100%;border-collapse:collapse;white-space:nowrap}}
thead th{{
  background:var(--sf2);color:var(--t2);font-weight:600;font-size:12px;
  text-transform:uppercase;letter-spacing:.5px;padding:12px 14px;text-align:left;
  border-bottom:1px solid var(--bd);cursor:pointer;user-select:none;position:sticky;top:0}}
thead th:hover{{color:var(--t1);background:var(--sf)}}
thead th.sa::after{{content:" ▲";font-size:10px}}
thead th.sd::after{{content:" ▼";font-size:10px}}
tbody tr{{border-bottom:1px solid var(--bd);transition:background .15s}}
tbody tr:hover{{background:var(--sf2)}}
tbody td{{padding:10px 14px}}
.c{{text-align:center}}.n{{text-align:right;font-variant-numeric:tabular-nums}}
.mono{{font-family:"SF Mono",Monaco,Consolas,monospace;font-size:12px}}
.code{{font-weight:600}} .code a{{color:var(--bl);text-decoration:none}} .code a:hover{{text-decoration:underline}}
.mkt{{color:var(--t2);font-size:12px}}
.gr{{color:var(--gr)}}.rd{{color:var(--rd)}}

/* rsi bar */
.rsi-bar{{position:relative;width:80px;height:20px;background:var(--sf2);border-radius:4px;overflow:hidden;display:inline-block}}
.rsi-fill{{height:100%;border-radius:4px}}
.rsi-val{{position:absolute;inset:0;display:flex;align-items:center;justify-content:center;
  font-size:11px;font-weight:600;color:#fff;text-shadow:0 0 3px rgba(0,0,0,.8)}}

/* badges */
.sigs{{max-width:280px;white-space:normal}}
.bd{{display:inline-block;padding:2px 8px;border-radius:12px;font-size:11px;font-weight:500;margin:2px 4px 2px 0}}
.bg{{background:rgba(63,185,80,.15);color:var(--gr)}}
.br{{background:rgba(248,81,73,.15);color:var(--rd)}}
.by{{background:rgba(210,153,34,.15);color:var(--yw)}}
.bw{{background:rgba(139,148,158,.15);color:var(--t2)}}

.spark{{padding:4px 8px}}

footer{{text-align:center;color:var(--t2);font-size:12px;margin-top:24px;
  padding-top:16px;border-top:1px solid var(--bd)}}

@media(max-width:768px){{
  .cards{{grid-template-columns:repeat(2,1fr)}}
  .ctl{{flex-direction:column}}.ctl input{{max-width:100%}}
}}
</style>
</head>
<body>
<div class="wrap">

<header>
  <h1>CTA Dashboard</h1>
  <p class="sub">台股前 1000 大 &middot; RSI / MACD 抄底反轉訊號 &middot; {date}</p>
</header>

<div class="cards">
  <div class="cd cd-s"><div class="cd-n">{strong}</div><div class="cd-l">Strong Call</div></div>
  <div class="cd cd-m"><div class="cd-n">{medium}</div><div class="cd-l">Call</div></div>
  <div class="cd cd-w"><div class="cd-n">{watch}</div><div class="cd-l">Watch</div></div>
  <div class="cd cd-t"><div class="cd-n">{total}</div><div class="cd-l">Scanned</div></div>
</div>

<div class="ctl">
  <input id="q" placeholder="Search code / name ..." />
  <select id="lf">
    <option value="all">All Signals</option>
    <option value="strong">Strong Call</option>
    <option value="medium">Call</option>
    <option value="watch">Watch</option>
  </select>
</div>

<div class="tw">
<table id="tbl">
<thead><tr>
  <th data-s="n" class="c">#</th>
  <th data-s="s">Code</th>
  <th data-s="s">Name</th>
  <th data-s="s">Mkt</th>
  <th data-s="n">Close</th>
  <th data-s="n">Chg%</th>
  <th data-s="n">RSI(14)</th>
  <th data-s="n">MACD</th>
  <th>Signals</th>
  <th data-s="n" class="c">Strength</th>
  <th>Trend</th>
</tr></thead>
<tbody>
{tbody}
</tbody>
</table>
</div>

<footer>Generated {now} &middot; CTA Dashboard v1.0</footer>

</div>
<script>
(function(){{
  var tb=document.querySelector("#tbl tbody"),
      ths=document.querySelectorAll("#tbl thead th"),
      qI=document.getElementById("q"),
      lf=document.getElementById("lf"),
      sc=-1,asc=true;

  function filt(){{
    var q=qI.value.toLowerCase(),lv=lf.value;
    [].forEach.call(tb.rows,function(r){{
      var ok=(!q||r.textContent.toLowerCase().indexOf(q)>=0)&&
             (lv==="all"||r.dataset.level===lv);
      r.style.display=ok?"":"none";
    }});
  }}
  qI.addEventListener("input",filt);
  lf.addEventListener("change",filt);

  [].forEach.call(ths,function(th,idx){{
    if(!th.dataset.s)return;
    th.addEventListener("click",function(){{
      if(sc===idx)asc=!asc;else{{sc=idx;asc=true}}
      [].forEach.call(ths,function(h){{h.classList.remove("sa","sd")}});
      th.classList.add(asc?"sa":"sd");
      var rows=[].slice.call(tb.rows),isN=th.dataset.s==="n";
      rows.sort(function(a,b){{
        var va=a.cells[idx].dataset.v!==undefined?a.cells[idx].dataset.v:a.cells[idx].textContent.trim(),
            vb=b.cells[idx].dataset.v!==undefined?b.cells[idx].dataset.v:b.cells[idx].textContent.trim();
        if(isN){{va=parseFloat(va)||0;vb=parseFloat(vb)||0}}
        if(va<vb)return asc?-1:1;if(va>vb)return asc?1:-1;return 0;
      }});
      rows.forEach(function(r){{tb.appendChild(r)}});
    }});
  }});
}})();
</script>
</body>
</html>"""
