"""桥梁档案业务规则：状态流转、字段校验与筛选口径都收在这里。"""
from __future__ import annotations

from typing import Any

from app.store import store

MODULE = "bridge"
REQUIRED_FIELDS = ["桥梁编码", "桥梁名称", "桥梁类型"]
STATUS_ORDER = ["待移交", "正常养护", "限载通行", "封闭施工"]
STATUS_FIELD = "桥梁状态"

# 动作 -> (允许发起的当前状态, 目标状态)：限载与封闭之间的衔接只认这张表，
# 当前状态不在允许列表里时动作不生效。
ACTION_RULES: dict[str, tuple[list[str], str]] = {
    "办理移交": (["待移交"], "正常养护"),
    "申请限载": (["正常养护"], "限载通行"),
    "封闭桥梁": (["正常养护", "限载通行"], "封闭施工"),
    # 限载期满重新评估后恢复为正常养护；封闭施工期间不允许改为通行。
    "恢复通行": (["限载通行"], "正常养护"),
}

# 特定 (动作, 当前状态) 的拒绝原因，优先于通用的允许状态提示。
REJECT_REASONS = {
    ("申请限载", "封闭施工"): "封闭期间不允许再申请限载",
    ("恢复通行", "封闭施工"): "现场封闭期间不应改为通行",
    ("申请限载", "限载通行"): "桥梁已在限载期内，待限载期满重新评估",
    ("封闭桥梁", "封闭施工"): "桥梁已处于封闭施工",
}

# 待处理口径：待办移交与限载待复评都要有人盯着，会进运营概览的待处理数。
PENDING_STATUSES = {"待移交", "限载通行"}
# 异常口径：封闭施工。
ABNORMAL_STATUSES = {"封闭施工"}

# 列表页统计卡口径：与状态一一对应，和运营概览取自同一份数据。
STAT_LABELS = [("在养桥梁", "正常养护"), ("限载桥梁", "限载通行"), ("危旧桥梁", "封闭施工")]


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
        self._apply_status(entry, STATUS_ORDER[0])
        rows.append(entry)
        return entry, []

    def run_action(self, entry_id: int, action: str) -> tuple[dict[str, Any] | None, str]:
        entry = store.find(MODULE, entry_id)
        if entry is None:
            return None, f"桥梁设施 {entry_id} 不存在或已归档"
        if action not in ACTION_RULES:
            return None, f"动作「{action}」不属于桥梁档案可执行范围"
        sources, target = ACTION_RULES[action]
        current = str(entry.get("status") or "")
        if current not in sources:
            reason = REJECT_REASONS.get((action, current))
            if reason is None:
                reason = f"仅「{'、'.join(sources)}」状态可{action}"
            return None, f"当前状态「{current}」不允许{action}：{reason}"
        self._apply_status(entry, target)
        return entry, f"桥梁设施已{action}"

    def status_summary(self) -> list[dict[str, Any]]:
        """列表页统计卡：按状态计数，与运营概览的待处理/异常口径同源。"""
        rows = store.rows(MODULE)
        return [
            {"label": label, "value": sum(1 for row in rows if row.get("status") == status)}
            for label, status in STAT_LABELS
        ]

    def _apply_status(self, entry: dict[str, Any], status: str) -> None:
        """流转状态，并同步列表展示的桥梁状态字段与待处理/异常口径。"""
        entry["status"] = status
        entry[STATUS_FIELD] = status
        entry["pending"] = status in PENDING_STATUSES
        entry["abnormal"] = status in ABNORMAL_STATUSES
