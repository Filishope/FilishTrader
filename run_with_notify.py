#!/usr/bin/env python3
"""
run_with_notify.py
~~~~~~~~~~~~~~~~~~
增强版选股流程，支持飞书消息通知和HTML报告生成。

环境变量:
    FEISHU_CHAT_ID - 飞书聊天ID (可选，默认使用当前对话)
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent
PYTHON = sys.executable
FEISHU_CHAT_ID = os.environ.get("FEISHU_CHAT_ID", "")

# 飞书通知函数 (通过 OpenClaw 消息通道)
def send_feishu_message(content: str):
    """发送飞书消息到当前对话"""
    # 通过写入文件方式通知，OpenClaw 会读取并发送
    print(f"\n[NOTIFY] {content}\n")
    # 同时写入通知文件供外部读取
    notify_file = ROOT / "data" / ".notify_last"
    notify_file.write_text(content, encoding="utf-8")


def send_progress(step: int, total: int, message: str, detail: str = ""):
    """发送进度通知"""
    emoji = ["📊", "🎯", "📈", "🤖", "✅"][min(step - 1, 4)]
    progress = f"[{step}/{total}]"
    content = f"{emoji} {progress} {message}"
    if detail:
        content += f"\n   {detail}"
    send_feishu_message(content)


def send_error(message: str):
    """发送错误通知"""
    send_feishu_message(f"❌ 选股流程出错\n   {message}")


def _run(step_num: int, step_name: str, cmd: list[str]) -> bool:
    """运行子进程，失败时返回 False"""
    print(f"\n{'='*60}")
    print(f"[步骤 {step_num}/5] {step_name}")
    print(f"  命令: {' '.join(cmd)}")
    print(f"{'='*60}")
    result = subprocess.run(cmd, cwd=str(ROOT))
    if result.returncode != 0:
        print(f"\n[ERROR] 步骤「{step_name}」返回非零退出码 {result.returncode}，流程已中止。")
        send_error(f"步骤 {step_num}/5「{step_name}」执行失败")
        return False
    return True


def generate_html_report(pick_date: str, suggestion: dict) -> Path:
    """生成 HTML 报告"""
    recommendations = suggestion.get("recommendations", [])
    min_score = suggestion.get("min_score_threshold", 0)
    total = suggestion.get("total_reviewed", 0)
    
    html = f'''<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>FilishTrader - {pick_date} 选股报告</title>
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{ 
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            min-height: 100vh;
            padding: 20px;
        }}
        .container {{ 
            max-width: 1200px; 
            margin: 0 auto;
            background: white;
            border-radius: 20px;
            box-shadow: 0 20px 60px rgba(0,0,0,0.3);
            overflow: hidden;
        }}
        .header {{
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            padding: 40px;
            text-align: center;
        }}
        .header h1 {{ font-size: 2.5em; margin-bottom: 10px; }}
        .header .date {{ font-size: 1.2em; opacity: 0.9; }}
        .stats {{
            display: flex;
            justify-content: center;
            gap: 40px;
            padding: 30px;
            background: #f8f9fa;
            border-bottom: 1px solid #e9ecef;
        }}
        .stat {{
            text-align: center;
        }}
        .stat-value {{
            font-size: 2.5em;
            font-weight: bold;
            color: #667eea;
        }}
        .stat-label {{
            color: #666;
            margin-top: 5px;
        }}
        .content {{ padding: 40px; }}
        .section-title {{
            font-size: 1.5em;
            color: #333;
            margin-bottom: 20px;
            padding-bottom: 10px;
            border-bottom: 3px solid #667eea;
        }}
        .stock-list {{
            display: grid;
            gap: 15px;
        }}
        .stock-card {{
            display: flex;
            align-items: center;
            padding: 20px;
            background: linear-gradient(135deg, #f8f9fa 0%, #e9ecef 100%);
            border-radius: 12px;
            border-left: 4px solid #667eea;
            transition: transform 0.2s, box-shadow 0.2s;
        }}
        .stock-card:hover {{
            transform: translateX(5px);
            box-shadow: 0 5px 20px rgba(102, 126, 234, 0.2);
        }}
        .stock-rank {{
            width: 50px;
            height: 50px;
            border-radius: 50%;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            display: flex;
            align-items: center;
            justify-content: center;
            font-size: 1.5em;
            font-weight: bold;
            margin-right: 20px;
        }}
        .stock-info {{
            flex: 1;
        }}
        .stock-code {{
            font-size: 1.3em;
            font-weight: bold;
            color: #333;
        }}
        .stock-signal {{
            color: #667eea;
            font-weight: 600;
            margin-top: 5px;
        }}
        .stock-comment {{
            color: #666;
            margin-top: 5px;
            font-size: 0.9em;
        }}
        .stock-score {{
            text-align: center;
            padding: 10px 20px;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            border-radius: 8px;
        }}
        .score-value {{
            font-size: 1.8em;
            font-weight: bold;
        }}
        .score-label {{
            font-size: 0.8em;
            opacity: 0.9;
        }}
        .verdict {{
            display: inline-block;
            padding: 5px 15px;
            border-radius: 20px;
            font-weight: 600;
            margin-left: 10px;
        }}
        .verdict-buy {{ background: #d4edda; color: #155724; }}
        .verdict-hold {{ background: #fff3cd; color: #856404; }}
        .verdict-sell {{ background: #f8d7da; color: #721c24; }}
        .empty-state {{
            text-align: center;
            padding: 60px;
            color: #666;
        }}
        .empty-state .emoji {{ font-size: 4em; margin-bottom: 20px; }}
        .footer {{
            text-align: center;
            padding: 20px;
            color: #999;
            font-size: 0.9em;
            border-top: 1px solid #e9ecef;
        }}
        @media (max-width: 768px) {{
            .stats {{ flex-direction: column; gap: 20px; }}
            .stock-card {{ flex-direction: column; text-align: center; }}
            .stock-rank {{ margin-right: 0; margin-bottom: 15px; }}
            .stock-score {{ margin-top: 15px; }}
        }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>📈 FilishTrader</h1>
            <div class="date">{pick_date} 选股报告</div>
        </div>
        <div class="stats">
            <div class="stat">
                <div class="stat-value">{total}</div>
                <div class="stat-label">评审股票数</div>
            </div>
            <div class="stat">
                <div class="stat-value">{len(recommendations)}</div>
                <div class="stat-label">推荐买入</div>
            </div>
            <div class="stat">
                <div class="stat-value">{min_score}</div>
                <div class="stat-label">评分门槛</div>
            </div>
        </div>
        <div class="content">
            <h2 class="section-title">🎯 推荐股票列表</h2>
            <div class="stock-list">
'''
    
    if recommendations:
        for r in recommendations:
            rank = r.get("rank", "?")
            code = r.get("code", "?")
            score = r.get("total_score", 0)
            signal_type = r.get("signal_type", "")
            verdict = r.get("verdict", "")
            comment = r.get("comment", "")
            
            verdict_class = f"verdict-{verdict.lower()}" if verdict else ""
            
            html += f'''
                <div class="stock-card">
                    <div class="stock-rank">{rank}</div>
                    <div class="stock-info">
                        <div class="stock-code">{code} <span class="verdict {verdict_class}">{verdict}</span></div>
                        <div class="stock-signal">{signal_type}</div>
                        <div class="stock-comment">{comment}</div>
                    </div>
                    <div class="stock-score">
                        <div class="score-value">{score:.1f}</div>
                        <div class="score-label">综合评分</div>
                    </div>
                </div>
'''
    else:
        html += '''
                <div class="empty-state">
                    <div class="emoji">🔍</div>
                    <div>暂无达标推荐股票</div>
                    <div style="margin-top:10px;color:#999;">今日没有符合评分门槛的股票</div>
                </div>
'''
    
    html += f'''
            </div>
        </div>
        <div class="footer">
            由 FilishTrader AI 选股系统生成 | {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
        </div>
    </div>
</body>
</html>
'''
    
    # 保存 HTML 报告
    report_dir = ROOT / "dashboard" / "reports"
    report_dir.mkdir(parents=True, exist_ok=True)
    report_path = report_dir / f"report_{pick_date}.html"
    report_path.write_text(html, encoding="utf-8")
    
    return report_path


def main():
    parser = argparse.ArgumentParser(description="FilishTrader 增强版选股流程（带通知）")
    parser.add_argument("--skip-fetch", action="store_true", help="跳过行情下载")
    parser.add_argument("--start-from", type=int, default=1, help="从第 N 步开始")
    parser.add_argument("--no-notify", action="store_true", help="关闭通知")
    args = parser.parse_args()
    
    start = args.start_from
    if args.skip_fetch and start == 1:
        start = 2
    
    notify = not args.no_notify
    
    print(f"\n{'='*60}")
    print(f"🚀 FilishTrader 选股流程启动")
    print(f"⏰ 启动时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'='*60}\n")
    
    if notify:
        send_feishu_message(f"🚀 选股流程已启动\n   时间: {datetime.now().strftime('%H:%M:%S')}")
    
    # 步骤 1：拉取 K 线数据
    if start <= 1:
        if notify:
            send_progress(1, 5, "开始下载 K 线数据", "正在从 Tushare 获取最新行情...")
        if not _run(1, "拉取 K 线数据", [PYTHON, "-m", "pipeline.fetch_kline"]):
            return
        if notify:
            send_progress(1, 5, "K 线数据下载完成", "✓ 数据已保存到 data/raw/")
        time.sleep(1)
    
    # 步骤 2：量化初选
    if start <= 2:
        if notify:
            send_progress(2, 5, "开始量化初选", "执行 B1 选股策略...")
        if not _run(2, "量化初选", [PYTHON, "-m", "pipeline.cli", "preselect"]):
            return
        if notify:
            # 读取候选数量
            candidates_file = ROOT / "data" / "candidates" / "candidates_latest.json"
            if candidates_file.exists():
                with open(candidates_file) as f:
                    data = json.load(f)
                    count = len(data.get("candidates", []))
                    send_progress(2, 5, "量化初选完成", f"✓ 筛选出 {count} 只候选股票")
            else:
                send_progress(2, 5, "量化初选完成")
        time.sleep(1)
    
    # 步骤 3：导出 K 线图
    if start <= 3:
        if notify:
            send_progress(3, 5, "开始导出图表", "正在生成候选股票的 K 线图片...")
        if not _run(3, "导出 K 线图", [PYTHON, str(ROOT / "dashboard" / "export_kline_charts.py")]):
            return
        if notify:
            send_progress(3, 5, "图表导出完成", "✓ 图表已保存到 data/kline/")
        time.sleep(1)
    
    # 步骤 4：AI 复评
    if start <= 4:
        if notify:
            send_progress(4, 5, "开始 AI 复评", "ZenMux 正在分析图表并打分...")
        if not _run(4, "AI 图表分析", [PYTHON, str(ROOT / "agent" / "gemini_review.py")]):
            return
        if notify:
            send_progress(4, 5, "AI 复评完成", "✓ 评分结果已保存")
        time.sleep(1)
    
    # 步骤 5：生成报告并发送
    if notify:
        send_progress(5, 5, "正在生成最终报告...")
    
    # 读取推荐结果
    candidates_file = ROOT / "data" / "candidates" / "candidates_latest.json"
    if not candidates_file.exists():
        send_error("找不到候选文件")
        return
    
    with open(candidates_file) as f:
        pick_date = json.load(f).get("pick_date", "")
    
    if not pick_date:
        send_error("无法获取选股日期")
        return
    
    suggestion_file = ROOT / "data" / "review" / pick_date / "suggestion.json"
    if not suggestion_file.exists():
        send_error("找不到评分汇总文件")
        return
    
    with open(suggestion_file) as f:
        suggestion = json.load(f)
    
    # 生成 HTML 报告
    report_path = generate_html_report(pick_date, suggestion)
    
    recommendations = suggestion.get("recommendations", [])
    total = suggestion.get("total_reviewed", 0)
    min_score = suggestion.get("min_score_threshold", 0)
    
    # 发送最终通知
    if notify:
        if recommendations:
            top_stocks = [f"{r['code']}({r['total_score']:.1f})" for r in recommendations[:3]]
            msg = f"""✅ 选股流程全部完成！

📅 选股日期: {pick_date}
📊 评审股票: {total} 只
🎯 推荐买入: {len(recommendations)} 只 (门槛≥{min_score})
🏆  top3: {', '.join(top_stocks)}

📈 详细报告: {report_path}
🔗 在线看板: https://filishope.github.io/FilishTrader/dashboard/stock_review_dashboard.html"""
        else:
            msg = f"""⚠️ 选股流程完成，暂无推荐

📅 选股日期: {pick_date}
📊 评审股票: {total} 只
🎯 推荐买入: 0 只 (未达门槛{min_score})

今日没有符合评分标准的股票，建议观望。"""
        
        send_feishu_message(msg)
    
    print(f"\n{'='*60}")
    print(f"✅ 选股流程全部完成！")
    print(f"📄 HTML报告: {report_path}")
    print(f"{'='*60}\n")


if __name__ == "__main__":
    main()
