"""桥梁档案接口：维护桥梁设施，覆盖办理移交、申请限载、封闭桥梁、恢复通行等动作。"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query

from app.schemas import ActionResult, EntryPayload, PageResult
from app.services.bridge import BridgeService

router = APIRouter(prefix="/api/bridge", tags=["桥梁档案"])

service = BridgeService()

LIST_FIELDS = ["桥梁编码", "桥梁名称", "桥梁类型", "跨越对象", "桥梁全长", "设计荷载", "建成年份", "桥梁状态"]
STATUSES = ["待移交", "正常养护", "限载通行", "封闭施工"]


@router.get("", response_model=PageResult[dict])
def list_entries(
    keyword: str | None = Query(default=None, description="按桥梁编码检索"),
    status: str | None = Query(default=None, description="待移交、正常养护、限载通行、封闭施工"),
    page: int = 1,
    size: int = 20,
) -> PageResult[dict]:
    """按桥梁编码与状态过滤桥梁档案列表；没有数据时返回空页，不报错。"""
    if size > 200:
        raise HTTPException(status_code=400, detail="每页最多 200 条，请缩小分页范围")
    items, total = service.list_entries(keyword=keyword, status=status, page=page, size=size)
    return PageResult(items=items, total=total, page=page, size=size)


@router.get("/stats")
def stats_entries() -> dict[str, Any]:
    """列表页统计卡：在养、限载、危旧桥梁数量，口径与运营概览一致。"""
    return {"module": "bridge", "stats": service.status_summary()}


@router.get("/export")
def export_entries() -> dict[str, Any]:
    """导出桥梁档案清单：返回当前过滤条件下的全量数据。"""
    items, total = service.list_entries(page=1, size=10000)
    return {"module": "bridge", "total": total, "items": items}


@router.get("/{entry_id}", response_model=dict)
def get_entry(entry_id: int) -> dict:
    """读取单条桥梁设施明细；不存在时给出可读的错误说明。"""
    entry = service.get_entry(entry_id)
    if entry is None:
        raise HTTPException(status_code=404, detail=f"桥梁设施 {entry_id} 不存在或已归档")
    return entry


@router.post("", response_model=ActionResult)
def create_entry(payload: EntryPayload) -> ActionResult:
    """登记一条桥梁设施，缺字段时说明原因而不是静默丢弃。"""
    entry, missing = service.create_entry(payload.values)
    if missing:
        return ActionResult(ok=False, message=f"缺少必填字段：{'、'.join(missing)}")
    return ActionResult(ok=True, message="桥梁设施已登记", entry=entry)


@router.post("/{entry_id}/actions", response_model=ActionResult)
def run_action(entry_id: int, payload: EntryPayload) -> ActionResult:
    """对单条桥梁设施执行办理移交、申请限载、封闭桥梁、恢复通行；当前状态不允许的动作会被拦下并说明原因。"""
    action = str(payload.values.get("action") or "").strip()
    entry, message = service.run_action(entry_id, action)
    if entry is None:
        return ActionResult(ok=False, message=message)
    return ActionResult(ok=True, message=message, entry=entry)
