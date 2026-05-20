#!/usr/bin/env python3
"""N字形态策略选股报告生成器

数据来源：
- K线/行情：TickFlow API
- 股票名称：TickFlow instruments
- 行业/概念：东方财富 Web API（push2 slist spt=7/13）
- K线图：matplotlib 手绘（整数索引x轴，无非交易日空白）
- PDF：weasyprint HTML转PDF
"""

import json, os, sys, time, urllib.error, urllib.request
from datetime import date, datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

plt.rcParams['font.sans-serif'] = ['WenQuanYi Micro Hei', 'DejaVu Sans']
plt.rcParams['axes.unicode_minus'] = False

from dotenv import load_dotenv
load_dotenv()

from sequoia_x.core.config import get_settings
from sequoia_x.data.engine import DataEngine, _to_tickflow_symbol
from sequoia_x.strategy.n_shape import NShapeStrategy
from sequoia_x.core.logger import get_logger

logger = get_logger(__name__)

OUTPUT_DIR = Path("reports")
OUTPUT_DIR.mkdir(exist_ok=True)

_em_cache: dict[str, dict] = {}
_em_cache_file = OUTPUT_DIR / "em_stock_info_cache.json"

def _load_em_cache():
    global _em_cache
    if _em_cache_file.exists():
        try:
            with open(_em_cache_file, 'r', encoding='utf-8') as f:
                _em_cache = json.load(f)
        except Exception:
            _em_cache = {}

def _save_em_cache():
    try:
        with open(_em_cache_file, 'w', encoding='utf-8') as f:
            json.dump(_em_cache, f, ensure_ascii=False)
    except Exception:
        pass

def _em_request(url: str, max_retries: int = 3) -> dict | None:
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
        'Referer': 'https://quote.eastmoney.com/',
    }
    for attempt in range(max_retries):
        try:
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=10) as resp:
                return json.loads(resp.read().decode('utf-8'))
        except Exception as e:
            if attempt < max_retries - 1:
                time.sleep(1)
            else:
                logger.warning(f"东方财富请求失败: {e}")
    return None

def get_stock_info_tickflow_batch(symbols: list[str]) -> dict[str, dict]:
    try:
        from tickflow import TickFlow
        tf = TickFlow(api_key=get_settings().tickflow_api_key)
        tf_syms = [_to_tickflow_symbol(s) for s in symbols]
        insts = tf.instruments.batch(tf_syms)
        result = {}
        for inst in insts:
            code = inst['symbol'].split('.')[0]
            result[code] = {"name": inst.get('name', '-'), "industry": "-", "concepts": "-"}
        return result
    except Exception as e:
        logger.error(f"TickFlow 批量获取名称失败: {e}")
        return {}

def get_stock_info_em(symbol: str) -> dict:
    global _em_cache
    if symbol in _em_cache:
        return _em_cache[symbol]
    secid = f"0.{symbol}" if symbol.startswith(('0', '3')) else f"1.{symbol}"
    result = {"name": "-", "industry": "-", "concepts": "-"}
    industry_url = (
        f"https://push2.eastmoney.com/api/qt/slist/get?"
        f"spt=7&fltt=2&invt=2&secid={secid}&fields=f12,f14&pn=1&pz=10&po=1&np=1"
        f"&ut=bd1d9ddb04089700cf9c27f6f7426281"
    )
    industry_data = _em_request(industry_url)
    if industry_data and industry_data.get('data') and industry_data['data'].get('diff'):
        boards = industry_data['data']['diff']
        names = [b.get('f14', '') for b in boards if b.get('f14')]
        result['industry'] = '、'.join(names[:3]) if names else '-'
    concept_url = (
        f"https://push2.eastmoney.com/api/qt/slist/get?"
        f"spt=13&fltt=2&invt=2&secid={secid}&fields=f12,f14&pn=1&pz=50&po=1&np=1"
        f"&ut=bd1d9ddb04089700cf9c27f6f7426281"
    )
    concept_data = _em_request(concept_url)
    if concept_data and concept_data.get('data') and concept_data['data'].get('diff'):
        boards = concept_data['data']['diff']
        names = [b.get('f14', '') for b in boards if b.get('f14')]
        result['concepts'] = '、'.join(names[:5]) if names else '-'
    _em_cache[symbol] = result
    return result

def analyze_nshape_details(df: pd.DataFrame) -> dict:
    if len(df) < 15:
        return {}
    df_recent = df.tail(15).copy().reset_index(drop=True)
    df_recent['prev_close'] = df_recent['close'].shift(1)
    df_recent['change_pct'] = (df_recent['close'] - df_recent['prev_close']) / df_recent['prev_close'] * 100
    df_recent['vol_ma5'] = df_recent['volume'].rolling(5).mean()
    surge_idx = surge_low = surge_date = surge_change = None
    for i in range(1, 8):
        if i >= len(df_recent):
            break
        row = df_recent.iloc[-i]
        if row['change_pct'] >= 7.0:
            surge_idx = len(df_recent) - i
            surge_low = row['low']
            surge_date = row['date']
            surge_change = f"{row['change_pct']:.1f}%"
            break
    if surge_idx is None:
        return {}
    after_surge = df_recent.iloc[surge_idx + 1:]
    if len(after_surge) < 3:
        return {}
    min_low_after = after_surge['low'].min()
    last_3 = df_recent.tail(3)
    pattern_type = pattern_desc = ""
    for idx in range(len(last_3)):
        row = last_3.iloc[idx]
        if 3.0 <= row['change_pct'] <= 7.0 and row['volume'] > row['vol_ma5'] * 1.5:
            pattern_type = "放量中阳"
            pattern_desc = f"涨幅{row['change_pct']:.1f}%，量比{row['volume']/row['vol_ma5']:.1f}倍"
            break
    if not pattern_type and len(last_3) >= 2:
        d1, d2 = last_3.iloc[-2], last_3.iloc[-1]
        if 1.0 <= d1['change_pct'] <= 3.0 and 1.0 <= d2['change_pct'] <= 3.0 and d2['close'] > d1['close']:
            pattern_type = "连续小阳"
            pattern_desc = f"两日涨幅{d1['change_pct']:.1f}%+{d2['change_pct']:.1f}%"
    if not pattern_type:
        today = df_recent.iloc[-1]
        body = abs(today['close'] - today['open'])
        lower_shadow = min(today['open'], today['close']) - today['low']
        total_range = today['high'] - today['low']
        if total_range > 0 and lower_shadow / total_range > 0.5 and body / total_range < 0.3:
            pattern_type = "锤头线/十字星"
            pattern_desc = "下影线长、实体小，企稳信号"
    if not pattern_type:
        pattern_type = "N字形态"
        pattern_desc = "涨停后洗盘不破支撑"
    support_desc = "不破支撑位" if min_low_after >= surge_low * 0.98 else "接近支撑位"
    current_close = df_recent.iloc[-1]['close']
    gain_from_support = (current_close - surge_low) / surge_low * 100
    return {
        "surge_date": surge_date, "surge_low": surge_low, "surge_change": surge_change,
        "min_low_after": min_low_after, "pattern_type": pattern_type, "pattern_desc": pattern_desc,
        "support_desc": support_desc, "days_after_surge": len(after_surge),
        "support_level": f"{surge_low:.2f}", "current_price": f"{current_close:.2f}",
        "current_change": f"{df_recent.iloc[-1]['change_pct']:.2f}%",
        "gain_from_support": f"{gain_from_support:.1f}%",
    }

def generate_kline_chart(symbol: str, df: pd.DataFrame, details: dict, output_path: Path):
    try:
        df_chart = df.tail(20).copy().reset_index(drop=True)
        dates = pd.to_datetime(df_chart['date'])
        opens, highs, lows, closes, volumes = df_chart['open'].values, df_chart['high'].values, df_chart['low'].values, df_chart['close'].values, df_chart['volume'].values
        n = len(dates)
        fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(10, 7), gridspec_kw={'height_ratios': [3, 1]}, sharex=True)
        fig.subplots_adjust(hspace=0.05)
        x = list(range(n))
        for i in range(n):
            o, h, l, c = opens[i], highs[i], lows[i], closes[i]
            color = '#d32f2f' if c >= o else '#388e3c'
            ax1.plot([x[i], x[i]], [l, h], color=color, linewidth=0.8)
            body_bottom = min(o, c)
            body_height = max(abs(c - o), 0.001)
            ax1.add_patch(plt.Rectangle((x[i] - 0.3, body_bottom), 0.6, body_height, facecolor=color, edgecolor=color))
        if details.get('surge_low'):
            ax1.axhline(y=details['surge_low'], color='#1565c0', linestyle='--', linewidth=1.2, label=f"主力底线: {details['surge_low']:.2f}")
            ax1.legend(loc='upper left', fontsize=9)
        ax1.set_title(f"{symbol} N字形态 K线图", fontsize=14, fontweight='bold')
        ax1.set_ylabel("价格"); ax1.grid(True, alpha=0.3); ax1.tick_params(axis='x', labelbottom=False)
        colors = ['#d32f2f' if closes[i] >= opens[i] else '#388e3c' for i in range(n)]
        ax2.bar(x, volumes, color=colors, width=0.6, alpha=0.7)
        ax2.set_ylabel("成交量"); ax2.grid(True, alpha=0.3)
        ax2.set_xticks(x)
        date_labels = [d.strftime('%m-%d') for d in dates]
        if n > 15: date_labels = [dl if i % 2 == 0 else '' for i, dl in enumerate(date_labels)]
        ax2.set_xticklabels(date_labels, rotation=45, fontsize=8)
        plt.savefig(output_path, dpi=150, bbox_inches='tight')
        plt.close()
        return True
    except Exception as e:
        logger.error(f"生成 {symbol} K线图失败: {e}")
        return False

def generate_html_report(stocks_data: list, output_path: Path):
    today_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    html = f"""<!DOCTYPE html><html lang="zh-CN"><head><meta charset="UTF-8">
<title>N字形态选股报告 - {date.today()}</title>
<style>
body{{font-family:"Microsoft YaHei","PingFang SC",sans-serif;margin:20px;background:#f0f2f5}}
.header{{background:linear-gradient(135deg,#1a237e,#4a148c);color:#fff;padding:24px;border-radius:12px;margin-bottom:20px}}
.header h1{{margin:0;font-size:26px}}.header .meta{{margin-top:8px;opacity:.85;font-size:14px}}
.strategy-box{{background:#fff8e1;border-left:4px solid #ff8f00;padding:14px 18px;border-radius:8px;margin-bottom:20px;font-size:14px;line-height:1.7}}
.summary{{background:#fff;padding:16px 20px;border-radius:10px;margin-bottom:20px;box-shadow:0 1px 4px rgba(0,0,0,.08);font-size:15px}}
.card{{background:#fff;border-radius:10px;padding:20px;margin-bottom:20px;box-shadow:0 2px 8px rgba(0,0,0,.08);page-break-inside:avoid}}
.card-head{{display:flex;justify-content:space-between;align-items:center;border-bottom:2px solid #e0e0e0;padding-bottom:12px;margin-bottom:14px}}
.code{{font-size:22px;font-weight:700;color:#1a237e}}.name{{font-size:16px;color:#555;margin-left:8px}}
.tag{{display:inline-block;padding:3px 10px;border-radius:12px;font-size:12px;margin-right:6px}}
.tag-industry{{background:#e3f2fd;color:#1565c0}}.tag-concept{{background:#f3e5f5;color:#7b1fa2}}.tag-pattern{{background:#e8f5e9;color:#2e7d32;font-weight:600}}
.grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:12px;margin-bottom:14px}}
.cell{{background:#fafafa;padding:10px 14px;border-radius:6px}}.cell-label{{font-size:11px;color:#888;margin-bottom:3px}}
.cell-value{{font-size:15px;font-weight:600;color:#333}}.price-up{{color:#d32f2f}}.price-support{{color:#1565c0;font-size:18px}}
.desc{{font-size:13px;color:#666;line-height:1.6;margin-bottom:12px}}.chart{{text-align:center;margin-top:10px}}
.chart img{{max-width:100%;border-radius:8px;border:1px solid #e0e0e0}}.footer{{text-align:center;padding:20px;color:#999;font-size:11px}}
</style></head><body>
<div class="header"><h1>📈 N字形态买点报告</h1><div class="meta">生成时间：{today_str} | 数据来源：TickFlow + 东方财富</div></div>
<div class="strategy-box"><strong>策略说明：</strong>N字形态买点 = 涨停/大阳 → 缩量洗盘（不破主力底线） → 买点信号出现。<br><strong>买点信号：</strong>放量中阳/连续小阳/锤头线十字星。<br><strong>过滤：</strong>距支撑涨幅≤15%、洗盘缩量、成交额≥5000万。</div>
<div class="summary">共选出 <span style="color:#d32f2f;font-size:20px;font-weight:700">{len(stocks_data)}</span> 只符合N字形态的股票</div>"""
    for s in stocks_data:
        concepts_html = ""
        if s.get('concepts') and s['concepts'] != '-':
            for c in s['concepts'].split('、')[:5]:
                concepts_html += f'<span class="tag tag-concept">{c}</span>'
        html += f"""<div class="card"><div class="card-head"><div><span class="code">{s['symbol']}</span><span class="name">{s['name']}</span></div><div><span class="tag tag-industry">{s.get('industry','-')}</span><span class="tag tag-pattern">{s.get('pattern_type','-')}</span></div></div>{concepts_html}
<div class="grid">
<div class="cell"><div class="cell-label">主力底线</div><div class="cell-value price-support">¥{s.get('support_level','-')}</div></div>
<div class="cell"><div class="cell-label">当前价格</div><div class="cell-value">¥{s.get('current_price','-')}</div></div>
<div class="cell"><div class="cell-label">距支撑涨幅</div><div class="cell-value price-up">{s.get('gain_from_support','-')}</div></div>
<div class="cell"><div class="cell-label">今日涨跌</div><div class="cell-value price-up">{s.get('current_change','-')}</div></div>
<div class="cell"><div class="cell-label">涨停日期</div><div class="cell-value">{s.get('surge_date','-')}</div></div>
<div class="cell"><div class="cell-label">涨停涨幅</div><div class="cell-value">{s.get('surge_change','-')}</div></div>
<div class="cell"><div class="cell-label">洗盘天数</div><div class="cell-value">{s.get('days_after_surge','-')} 天</div></div></div>
<div class="desc"><strong>形态：</strong>{s.get('pattern_desc','-')} | <strong>支撑：</strong>{s.get('support_desc','-')}</div>
<div class="chart"><img src="{s.get('chart_path','')}" alt="{s['symbol']} K线图"></div></div>"""
    html += '<div class="footer"><p>本报告仅供参考，不构成投资建议。</p></div></body></html>'
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(html)

def generate_pdf_from_html(html_path: Path, pdf_path: Path):
    try:
        from weasyprint import HTML
        HTML(str(html_path)).write_pdf(str(pdf_path))
        return True
    except ImportError:
        pass
    logger.warning("weasyprint 未安装，无法生成 PDF")
    return False

_last_stocks_data: list = []

def main():
    global _last_stocks_data
    project_root = Path(__file__).resolve().parent
    os.chdir(project_root)
    logger.info("开始生成N字形态买点报告...")
    settings = get_settings()
    engine = DataEngine(settings)
    strategy = NShapeStrategy(engine=engine, settings=settings)
    selected = strategy.run()
    if not selected:
        print("没有选出符合条件的股票"); return
    selected = selected[:30]
    _load_em_cache()
    names_map = get_stock_info_tickflow_batch(selected)
    stocks_data = []
    charts_dir = OUTPUT_DIR / "charts"
    charts_dir.mkdir(exist_ok=True)
    for i, symbol in enumerate(selected):
        try:
            logger.info(f"[{i+1}/{len(selected)}] 处理 {symbol}...")
            info = names_map.get(symbol, {"name": "-", "industry": "-", "concepts": "-"})
            em_info = get_stock_info_em(symbol)
            if em_info['industry'] != '-': info['industry'] = em_info['industry']
            if em_info['concepts'] != '-': info['concepts'] = em_info['concepts']
            df = engine.get_ohlcv(symbol)
            if len(df) < 15: continue
            details = analyze_nshape_details(df)
            if not details: continue
            chart_file = f"{symbol}_nshape.png"
            generate_kline_chart(symbol, df, details, charts_dir / chart_file)
            stocks_data.append({
                "symbol": symbol, "name": info.get('name', '-'), "industry": info.get('industry', '-'),
                "concepts": info.get('concepts', '-'), "support_level": details.get('support_level', '-'),
                "current_price": details.get('current_price', '-'), "current_change": details.get('current_change', '-'),
                "gain_from_support": details.get('gain_from_support', '-'), "pattern_type": details.get('pattern_type', '-'),
                "pattern_desc": details.get('pattern_desc', '-'), "support_desc": details.get('support_desc', '-'),
                "surge_date": details.get('surge_date', '-'), "surge_change": details.get('surge_change', '-'),
                "days_after_surge": details.get('days_after_surge', '-'), "chart_path": f"charts/{chart_file}",
            })
            time.sleep(0.3)
        except Exception as e:
            logger.error(f"处理 {symbol} 失败: {e}"); continue
    _last_stocks_data = stocks_data
    _save_em_cache()
    if not stocks_data:
        print("没有成功生成任何股票数据"); return
    html_path = OUTPUT_DIR / f"nshape_report_{date.today().strftime('%Y%m%d')}.html"
    generate_html_report(stocks_data, html_path)
    pdf_path = OUTPUT_DIR / f"nshape_report_{date.today().strftime('%Y%m%d')}.pdf"
    generate_pdf_from_html(html_path, pdf_path)
    print(f"\n📊 报告生成完成！共 {len(stocks_data)} 只股票")
    print(f"  HTML: {html_path}\n  PDF:  {pdf_path}")

if __name__ == "__main__":
    main()
