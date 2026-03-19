#!/usr/bin/env python3
"""
FilishTrader Notifier Agent
~~~~~~~~~~~~~~~~~~~~~~~~~~~~
作为 OpenClaw cron 任务运行，调用 daily_runner.py 并实时转发通知到飞书。
"""
import subprocess
import sys
import json
import re
from pathlib import Path
from datetime import datetime

ROOT = Path(__file__).resolve().parent

def send_feishu(title: str, content: str):
    """发送飞书消息 - 通过标准输出触发 OpenClaw 消息"""
    # 输出特殊格式的消息，让 OpenClaw 捕获并发送
    print(f"\n[FEISHU_MSG]\nTITLE: {title}\nCONTENT:\n{content}\n[END_MSG]\n", flush=True)

def send_progress(step: int, message: str, detail: str = ""):
    """发送进度通知"""
    emojis = ["🚀", "📊", "🎯", "📈", "🤖", "✅"]
    emoji = emojis[min(step, len(emojis)-1)]
    title = f"{emoji} [{step}/5] {message}"
    content = detail if detail else "进行中..."
    send_feishu(title, content)

def send_error(step: int, message: str, detail: str = ""):
    """发送错误通知"""
    title = f"❌ 步骤 {step}/5 失败"
    content = f"{message}\n{detail}" if detail else message
    send_feishu(title, content)

def send_final_report(pick_date: str, suggestion: dict, has_error: bool = False):
    """发送最终报告"""
    recommendations = suggestion.get("recommendations", [])
    total = suggestion.get("total_reviewed", 0)
    min_score = suggestion.get("min_score_threshold", 0)
    
    if has_error:
        title = "❌ FilishTrader 选股流程异常结束"
        content = "部分步骤执行失败，请检查日志"
    elif recommendations:
        # 生成 HTML 报告链接
        report_url = f"https://filishope.github.io/FilishTrader/dashboard/stock_review_dashboard.html"
        
        title = f"✅ FilishTrader {pick_date} 选股完成"
        
        # 构建股票列表
        stock_lines = []
        for i, r in enumerate(recommendations[:5], 1):
            code = r.get("code", "?")
            score = r.get("total_score", 0)
            signal = r.get("signal_type", "")
            verdict = r.get("verdict", "")
            comment = r.get("comment", "")[:30]
            stock_lines.append(f"{i}. {code} | 评分: {score:.1f} | {signal} | {verdict}")
            if comment:
                stock_lines.append(f"   💡 {comment}")
        
        content = f"""📊 选股日期: {pick_date}
📈 评审总数: {total} 只
🎯 推荐买入: {len(recommendations)} 只 (门槛≥{min_score})

🏆 Top 推荐:
{"\n".join(stock_lines)}

🔗 详细看板: {report_url}
⏰ 生成时间: {datetime.now().strftime('%H:%M:%S')}"""
    else:
        title = f"⚠️ FilishTrader {pick_date} 选股完成 - 暂无推荐"
        content = f"""📊 选股日期: {pick_date}
📈 评审总数: {total} 只
🎯 推荐买入: 0 只

今日没有符合评分标准(≥{min_score})的股票，建议观望。

⏰ 生成时间: {datetime.now().strftime('%H:%M:%S')}"""
    
    send_feishu(title, content)

def main():
    # 运行 daily_runner 并解析输出
    runner = ROOT / "daily_runner.py"
    
    print(f"启动 FilishTrader 选股流程...\n")
    
    process = subprocess.Popen(
        [sys.executable, str(runner)],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        cwd=str(ROOT)
    )
    
    current_step = 0
    last_pick_date = ""
    suggestion_data = {}
    has_error = False
    
    # 实时读取输出
    for line in process.stdout:
        print(line, end="")  # 保留原始输出
        
        # 解析 [NOTIFY] 标记
        if "[NOTIFY]" in line:
            try:
                json_str = line.split("[NOTIFY] ")[1].strip()
                notify = json.loads(json_str)
                
                step = notify.get("step", 0)
                status = notify.get("status", "")
                message = notify.get("message", "")
                detail = notify.get("detail", "")
                
                if status == "start":
                    send_progress(step, message, detail)
                elif status == "done":
                    if step == 5:  # 最终完成
                        # 解析 detail 中的 JSON
                        try:
                            result = json.loads(detail) if detail else {}
                            last_pick_date = result.get("pick_date", "")
                            suggestion_data = {
                                "recommendations": result.get("top_stocks", []),
                                "total_reviewed": result.get("total", 0),
                                "min_score_threshold": result.get("threshold", 0)
                            }
                        except:
                            pass
                        send_final_report(last_pick_date, suggestion_data, has_error)
                    else:
                        send_progress(step, message + " ✓", detail)
                elif status == "error":
                    has_error = True
                    send_error(step, message, detail)
                    
            except Exception as e:
                print(f"解析通知失败: {e}")
    
    process.wait()
    
    if process.returncode != 0 and not has_error:
        send_feishu("❌ FilishTrader 运行异常", f"返回码: {process.returncode}\n请检查日志")
    
    return process.returncode

if __name__ == "__main__":
    sys.exit(main())
