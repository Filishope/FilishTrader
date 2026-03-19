#!/usr/bin/env python3
"""
FilishTrader Daily Runner
~~~~~~~~~~~~~~~~~~~~~~~~~
每天晚上 6:20 运行的定时选股任务。
通过 cron 调用此脚本，它会:
1. 运行完整的选股流程
2. 在关键步骤输出通知标记
3. 生成 HTML 报告
"""
import subprocess
import sys
import json
import os
from pathlib import Path
from datetime import datetime

ROOT = Path(__file__).resolve().parent

def log_notify(step: int, status: str, message: str, detail: str = ""):
    """输出通知标记，供外部解析"""
    notify_data = {
        "timestamp": datetime.now().isoformat(),
        "step": step,
        "status": status,  # "start", "done", "error"
        "message": message,
        "detail": detail
    }
    # 输出 JSON 格式的通知，便于解析
    print(f"\n[NOTIFY] {json.dumps(notify_data, ensure_ascii=False)}\n", flush=True)

def main():
    print(f"\n{'='*70}")
    print(f"🚀 FilishTrader 定时选股任务")
    print(f"⏰ 开始时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'='*70}\n")
    
    # 发送开始通知
    log_notify(0, "start", "选股任务开始", "正在初始化...")
    
    # 激活虚拟环境并运行选股流程
    venv_python = ROOT / "venv" / "bin" / "python"
    if not venv_python.exists():
        venv_python = Path(sys.executable)  # fallback
    
    # 设置环境变量
    env = os.environ.copy()
    env["PYTHONPATH"] = str(ROOT)
    
    # 步骤 1: 下载数据
    log_notify(1, "start", "开始下载 K 线数据")
    result = subprocess.run(
        [str(venv_python), "-m", "pipeline.fetch_kline"],
        cwd=str(ROOT),
        env=env,
        capture_output=True,
        text=True
    )
    if result.returncode != 0:
        log_notify(1, "error", "数据下载失败", result.stderr[:200])
        print(result.stderr)
        return 1
    log_notify(1, "done", "K 线数据下载完成", f"输出: {result.stdout[-500:] if result.stdout else 'OK'}")
    
    # 步骤 2: 量化初选
    log_notify(2, "start", "开始量化初选")
    result = subprocess.run(
        [str(venv_python), "-m", "pipeline.cli", "preselect"],
        cwd=str(ROOT),
        env=env,
        capture_output=True,
        text=True
    )
    if result.returncode != 0:
        log_notify(2, "error", "量化初选失败", result.stderr[:200])
        print(result.stderr)
        return 1
    
    # 读取候选数量
    candidates_file = ROOT / "data" / "candidates" / "candidates_latest.json"
    candidate_count = 0
    if candidates_file.exists():
        try:
            with open(candidates_file) as f:
                data = json.load(f)
                candidate_count = len(data.get("candidates", []))
        except:
            pass
    log_notify(2, "done", "量化初选完成", f"筛选出 {candidate_count} 只候选股票")
    
    # 步骤 3: 导出图表
    log_notify(3, "start", "开始导出 K 线图表")
    result = subprocess.run(
        [str(venv_python), str(ROOT / "dashboard" / "export_kline_charts.py")],
        cwd=str(ROOT),
        env=env,
        capture_output=True,
        text=True
    )
    if result.returncode != 0:
        log_notify(3, "error", "图表导出失败", result.stderr[:200])
        print(result.stderr)
        return 1
    log_notify(3, "done", "图表导出完成")
    
    # 步骤 4: AI 复评
    log_notify(4, "start", "开始 AI 图表复评")
    result = subprocess.run(
        [str(venv_python), str(ROOT / "agent" / "gemini_review.py")],
        cwd=str(ROOT),
        env=env,
        capture_output=True,
        text=True
    )
    if result.returncode != 0:
        log_notify(4, "error", "AI 复评失败", result.stderr[:200])
        print(result.stderr)
        return 1
    log_notify(4, "done", "AI 复评完成")
    
    # 读取结果
    try:
        with open(candidates_file) as f:
            pick_date = json.load(f).get("pick_date", "")
    except:
        pick_date = ""
    
    suggestion_file = ROOT / "data" / "review" / pick_date / "suggestion.json"
    recommendations = []
    total = 0
    min_score = 0
    
    if suggestion_file.exists():
        try:
            with open(suggestion_file) as f:
                suggestion = json.load(f)
                recommendations = suggestion.get("recommendations", [])
                total = suggestion.get("total_reviewed", 0)
                min_score = suggestion.get("min_score_threshold", 0)
        except:
            pass
    
    # 生成最终通知
    if recommendations:
        top_stocks = [f"{r.get('code', '?')}({r.get('total_score', 0):.1f})" for r in recommendations[:3]]
        final_msg = f"选股完成！推荐 {len(recommendations)} 只股票，Top3: {', '.join(top_stocks)}"
    else:
        final_msg = f"选股完成，暂无推荐股票（评审{total}只，未达门槛{min_score}）"
    
    log_notify(5, "done", final_msg, json.dumps({
        "pick_date": pick_date,
        "total": total,
        "recommended": len(recommendations),
        "threshold": min_score,
        "top_stocks": recommendations[:3] if recommendations else []
    }, ensure_ascii=False))
    
    print(f"\n{'='*70}")
    print(f"✅ 任务完成: {final_msg}")
    print(f"⏰ 结束时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'='*70}\n")
    
    return 0

if __name__ == "__main__":
    sys.exit(main())
