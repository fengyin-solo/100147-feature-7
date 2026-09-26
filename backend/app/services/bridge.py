"""桥梁档案业务规则：状态流转、字段校验与筛选口径都收在这里。"""
from __future__ import annotations

from typing import Any

from app.store import store

MODULE = "bridge"
REQUIRED_FIELDS = ["桥梁编码", "桥梁名称", "桥梁类型"]
STATUS_ORDER = ["待移交", "正常养护", "限载通行", "封闭施工"]
STATUS_FIELD = "桥梁状态"

# 状态流转规则：每个动作只允许从特定状态发起，不满足就拦下并说明原因。
# 限载期满重新评估、封闭加固完成，都走「恢复通行」回到正常养护。
ACTION_RULES = {
    "办理移交": {"from": ["待移交"], "to": "正常养护"},
    "申请限载": {"from": ["正常养护"], "to": "限载通行"},
    "封闭桥梁": {"from": ["正常养护", "限载通行"], "to": "封闭施工"},
    "恢复通行": {"from": ["限载通行", "封闭施工"], "to": "正常养护"},
}

# 待移交要办移交、限载要盯期满评估、封闭要盯加固完成，都算待处理；
# 限载与封闭都不是正常服役状态，计入异常量。运营概览与列表统计共用这套口径。
PENDING_STATUSES = ["待移交", "限载通行", "封闭施工"]
ABNORMAL_STATUSES = ["限载通行", "封闭施工"]

STAT_CARDS = [("在养桥梁", "正常养护"), ("限载桥梁", "限载通行"), ("危旧桥梁", "封闭施工")]


def apply_status(entry: dict[str, Any], status: str) -> None:
    """把状态、列表展示的「桥梁状态」字段与概览标志一次性对齐。"""
    entry["status"] = status
    entry[STATUS_FIELD] = status
    entry["pending"] = status in PENDING_STATUSES
    entry["abnormal"] = status in ABNORMAL_STATUSES


class BridgeService:
    def list_entries(
        self,
        *,
        keyword: str | None = None,
        status: str | None = None,
        page: int = 1,
        size: int = 20,
    ) -> tuple[list[dict[str, Any]], int]:
        rows = store.rows(MODULE)
        if keyword:
            rows = [row for row in rows if keyword in str(row.get("桥梁编码", ""))]
        if status:
            rows = [row for row in rows if row.get("status") == status]
        total = len(rows)
        start = max(page - 1, 0) * size
        return rows[start:start + size], total

    def get_entry(self, entry_id: int) -> dict[str, Any] | None:
        return store.find(MODULE, entry_id)

    def create_entry(self, values: dict[str, Any]) -> tuple[dict[str, Any] | None, list[str]]:
        missing = [field for field in REQUIRED_FIELDS if not str(values.get(field) or "").strip()]
        if missing:
            return None, missing
        rows = store.rows(MODULE)
        entry = {"id": max((int(row.get("id", 0)) for row in rows), default=0) + 1}
        entry.update({field: values.get(field) for field in REQUIRED_FIELDS})
        apply_status(entry, STATUS_ORDER[0])
        rows.append(entry)
        return entry, []

    def run_action(self, entry_id: int, action: str) -> tuple[dict[str, Any] | None, str]:
        entry = store.find(MODULE, entry_id)
        if entry is None:
            return None, f"桥梁设施 {entry_id} 不存在或已归档"
        if action not in ACTION_RULES:
            return None, f"动作「{action}」不属于桥梁档案可执行范围"
        rule = ACTION_RULES[action]
        target = rule["to"]
        if target not in STATUS_ORDER:
            return None, f"目标状态「{target}」不在允许的状态序列里"
        current = str(entry.get("status") or "")
        if current not in rule["from"]:
            allowed = "、".join(rule["from"])
            return None, f"当前状态「{current}」不允许执行「{action}」，仅「{allowed}」状态可办理"
        apply_status(entry, target)
        return entry, self._action_message(action, current)

    def stats(self) -> list[dict[str, Any]]:
        """列表页统计卡片：与运营概览用同一份状态数据，口径一致。"""
        rows = store.rows(MODULE)
        return [
            {"label": label, "value": sum(1 for row in rows if row.get("status") == status)}
            for label, status in STAT_CARDS
        ]

    @staticmethod
    def _action_message(action: str, current: str) -> str:
        if action == "恢复通行" and current == "限载通行":
            return "限载期满重新评估通过，桥梁已恢复正常养护"
        if action == "恢复通行" and current == "封闭施工":
            return "加固完成，桥梁已恢复通行并回到正常养护"
        return f"桥梁设施已{action}"
