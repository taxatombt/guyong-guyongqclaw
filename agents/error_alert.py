"""
error_alert.py — 出错主动告警系统

来源：小谷要求"出问题要报告"+"出错就写日志"
设计：
1. 工具执行失败 → 自动记录到日志
2. 连续失败 → 生成告警文件，心跳时汇报
3. 异常中断 → 写入待报告队列

核心原则：出问题要主动汇报，不是自己扛着等问
"""

import json
import time
import traceback
import logging
from pathlib import Path
from typing import Optional, List, Dict, Any
from dataclasses import dataclass, asdict

log = logging.getLogger("qclaw.error_alert")

WORKSPACE = Path(r"C:\Users\yiseg\.qclaw\workspace")
MEMORY_DIR = WORKSPACE / "memory"
ERROR_LOG = MEMORY_DIR / "error_log.jsonl"
ALERT_QUEUE = MEMORY_DIR / "alert_queue.jsonl"

MEMORY_DIR.mkdir(parents=True, exist_ok=True)


@dataclass
class ErrorRecord:
    """错误记录"""
    timestamp: float = 0.0
    error_type: str = ""        # tool_failure / encoding / timeout / crash / unknown
    tool: str = ""              # 哪个工具
    task: str = ""              # 什么任务
    error_message: str = ""     # 错误信息
    stack_trace: str = ""       # 堆栈
    recovery_action: str = ""   # 怎么绕过的
    severity: str = "warn"      # info / warn / error / critical
    reported: bool = False      # 是否已汇报给小谷

    def to_dict(self) -> dict:
        return asdict(self)


class ErrorAlertSystem:
    """出错主动告警系统"""

    # 连续失败阈值
    CONSECUTIVE_FAIL_THRESHOLD = 3
    # 最近5分钟内的失败阈值
    RECENT_FAIL_THRESHOLD = 5

    _recent_errors: List[ErrorRecord] = []
    _consecutive_fails: int = 0
    _last_alert_time: float = 0.0

    def record_error(self, error_type: str, tool: str = "", task: str = "",
                     error_message: str = "", stack_trace: str = "",
                     recovery_action: str = "", severity: str = "warn") -> ErrorRecord:
        """
        记录一次错误

        在每次工具执行失败、编码问题、超时等场景调用。
        """
        record = ErrorRecord(
            timestamp=time.time(),
            error_type=error_type,
            tool=tool,
            task=task[:200],
            error_message=error_message[:500],
            stack_trace=stack_trace[:500],
            recovery_action=recovery_action[:200],
            severity=severity,
        )

        self._recent_errors.append(record)
        self._consecutive_fails += 1

        # 写入日志
        self._write_log(record)

        # 检查是否需要告警
        self._check_alert_needed()

        return record

    def record_success(self, tool: str = "", task: str = ""):
        """记录成功，重置连续失败计数"""
        self._consecutive_fails = 0

    def _write_log(self, record: ErrorRecord):
        """写入错误日志"""
        try:
            with open(ERROR_LOG, "a", encoding="utf-8") as f:
                f.write(json.dumps(record.to_dict(), ensure_ascii=False) + "\n")
        except Exception as e:
            log.warning(f"[error_alert] log write failed: {e}")

    def _check_alert_needed(self):
        """检查是否需要生成告警"""
        should_alert = False
        alert_reason = ""

        # 条件1：连续失败超阈值
        if self._consecutive_fails >= self.CONSECUTIVE_FAIL_THRESHOLD:
            should_alert = True
            alert_reason = f"连续{self._consecutive_fails}次失败"

        # 条件2：5分钟内失败过多
        now = time.time()
        recent_5min = [e for e in self._recent_errors if now - e.timestamp < 300]
        if len(recent_5min) >= self.RECENT_FAIL_THRESHOLD:
            should_alert = True
            alert_reason = f"5分钟内{len(recent_5min)}次失败"

        # 条件3：严重错误
        if self._recent_errors and self._recent_errors[-1].severity == "critical":
            should_alert = True
            alert_reason = "严重错误"

        # 防止告警风暴：至少间隔5分钟
        if should_alert and now - self._last_alert_time > 300:
            self._generate_alert(alert_reason)
            self._last_alert_time = now

    def _generate_alert(self, reason: str):
        """生成告警，写入告警队列"""
        now = time.time()
        recent = self._recent_errors[-5:]  # 最近5条错误

        alert = {
            "timestamp": now,
            "reason": reason,
            "errors": [e.to_dict() for e in recent],
            "status": "pending",  # pending / reported / resolved
        }

        try:
            with open(ALERT_QUEUE, "a", encoding="utf-8") as f:
                f.write(json.dumps(alert, ensure_ascii=False) + "\n")
        except Exception as e:
            log.warning(f"[error_alert] alert write failed: {e}")

        log.warning(f"[error_alert] ALERT: {reason}")

    def get_pending_alerts(self) -> List[Dict]:
        """获取待报告的告警（心跳时调用）"""
        if not ALERT_QUEUE.exists():
            return []

        alerts = []
        try:
            with open(ALERT_QUEUE, "r", encoding="utf-8") as f:
                lines = [l.strip() for l in f if l.strip()]
            for line in lines:
                alert = json.loads(line)
                if alert.get("status") == "pending":
                    alerts.append(alert)
        except Exception:
            pass

        return alerts

    def mark_reported(self, alert_index: int = -1):
        """标记告警已报告"""
        if not ALERT_QUEUE.exists():
            return

        try:
            with open(ALERT_QUEUE, "r", encoding="utf-8") as f:
                lines = [l.strip() for l in f if l.strip()]
            alerts = [json.loads(l) for l in lines]

            if alerts and abs(alert_index) <= len(alerts):
                alerts[alert_index]["status"] = "reported"

            with open(ALERT_QUEUE, "w", encoding="utf-8") as f:
                for alert in alerts:
                    f.write(json.dumps(alert, ensure_ascii=False) + "\n")
        except Exception:
            pass

    def format_alert_summary(self) -> str:
        """格式化告警摘要（用于汇报给小谷）"""
        alerts = self.get_pending_alerts()
        if not alerts:
            return ""

        lines = ["⚠️ 错误告警："]
        for alert in alerts:
            ts = time.strftime("%H:%M:%S", time.localtime(alert["timestamp"]))
            lines.append(f"  [{ts}] {alert['reason']}")
            for err in alert.get("errors", [])[-3:]:
                lines.append(f"    - {err.get('tool', '?')}: {err.get('error_message', '')[:80]}")
                if err.get("recovery_action"):
                    lines.append(f"      绕过方式：{err['recovery_action'][:80]}")

        return "\n".join(lines)

    def get_error_stats(self, hours: int = 24) -> Dict[str, Any]:
        """获取错误统计"""
        if not ERROR_LOG.exists():
            return {"total": 0, "by_type": {}, "by_tool": {}}

        cutoff = time.time() - hours * 3600
        by_type: Dict[str, int] = {}
        by_tool: Dict[str, int] = {}
        total = 0

        try:
            with open(ERROR_LOG, "r", encoding="utf-8") as f:
                for line in f:
                    if not line.strip():
                        continue
                    try:
                        record = json.loads(line)
                        if record.get("timestamp", 0) < cutoff:
                            continue
                        total += 1
                        et = record.get("error_type", "unknown")
                        by_type[et] = by_type.get(et, 0) + 1
                        tool = record.get("tool", "unknown")
                        by_tool[tool] = by_tool.get(tool, 0) + 1
                    except:
                        continue
        except Exception:
            pass

        return {
            "total": total,
            "hours": hours,
            "by_type": by_type,
            "by_tool": by_tool,
        }


# 全局单例
_alert_system: Optional[ErrorAlertSystem] = None

def get_error_alert() -> ErrorAlertSystem:
    global _alert_system
    if _alert_system is None:
        _alert_system = ErrorAlertSystem()
    return _alert_system

def report_error(error_type: str, tool: str = "", task: str = "",
                 error_message: str = "", recovery_action: str = "",
                 severity: str = "warn") -> ErrorRecord:
    """快捷函数：记录错误并检查告警"""
    return get_error_alert().record_error(
        error_type=error_type, tool=tool, task=task,
        error_message=error_message, recovery_action=recovery_action,
        severity=severity
    )


if __name__ == "__main__":
    import sys
    sys.stdout.reconfigure(encoding='utf-8')

    # 自测
    ea = ErrorAlertSystem()

    # 模拟3次连续失败 → 触发告警
    for i in range(3):
        ea.record_error(
            error_type="encoding",
            tool="exec",
            task="读取GitHub API响应",
            error_message=f"GBK编码错误 #{i+1}",
            recovery_action="用Python脚本绕过PowerShell"
        )

    # 检查告警
    alerts = ea.get_pending_alerts()
    print(f"待报告告警: {len(alerts)}条")
    if alerts:
        print(ea.format_alert_summary())

    # 统计
    print(f"\nStats: {ea.get_error_stats()}")

    # 清理测试数据
    if ERROR_LOG.exists():
        ERROR_LOG.unlink()
    if ALERT_QUEUE.exists():
        ALERT_QUEUE.unlink()
    print("Test cleaned. OK")
