"""会话层意图识别：打断后新 query 的三分类（resume / new / 指代）。

LLM 失败/非法输出 → fallback（前端二选一弹窗兜底，设计 §3.4 D5）。
指代歧义取最近暂停的 run + guessed 标记（D4：取最近+可纠）。
"""
from __future__ import annotations

import json
import re

_SYSTEM = (
    "你是任务路由器。用户在同一会话里有若干挂起的代码审查任务，"
    "现在发来一条新消息。判断意图并只输出 JSON：\n"
    '继续/补充之前任务 → {"intent":"resume","trace_id":"<挂起任务的trace_id>"}\n'
    '全新任务 → {"intent":"new"}\n'
    '模糊指代（如"继续之前那个"）→ {"intent":"refer"}\n'
    "挂起任务列表条目含 state 字段：paused=执行中等人补充（继续/补充即 resume）；"
    "review_pending=报告已出等人裁决——用户明确表示接受/通过/认可某 review_pending "
    "任务时路由到它（如「接受那份报告」）；带修改意见的重做不是路由意图"
    "（用户应走页面审阅卡，模糊即 fallback）。\n"
    "挂起任务列表：%s")


def classify_intent(query: str, paused: list[dict], complete=None) -> dict:
    if not paused:
        return {"intent": "new"}  # 无挂起：不触发识别（D6）
    if complete is None:
        complete = _default_complete
    try:
        reply = complete(_SYSTEM % json.dumps(paused, ensure_ascii=False)
                         + "\n用户消息：" + query)
        if not isinstance(reply, str):  # OpenAI 形状响应 → 取 content 字段
            reply = reply["choices"][0]["message"]["content"]
        data = json.loads(_extract_json(reply))
    except Exception:
        return {"intent": "fallback", "candidates": paused}  # D5 降级
    if data.get("intent") == "resume" and any(
            p["trace_id"] == data.get("trace_id") for p in paused):
        return {"intent": "resume", "trace_id": data["trace_id"]}
    if data.get("intent") == "refer":
        recent = paused[-1]  # 最近暂停（D4 取最近+可纠）
        return {"intent": "resume", "trace_id": recent["trace_id"],
                "guessed": True}
    return {"intent": "new"}


def _extract_json(text: str) -> str:
    m = re.search(r"\{.*\}", text, re.S)
    if not m:
        raise ValueError("no json in reply")
    return m.group(0)


def _default_complete(prompt: str) -> str:
    """真实 LLM（litellm 同步 completion；模型走两级 env 解析）。

    调用方（app 路由）经 asyncio.to_thread 把阻塞调用移出事件循环。
    """
    import litellm

    from harness.config import resolve_model
    model = resolve_model("intake", "xiaomi_mimo/mimo-v2.5-pro")
    out = litellm.completion(
        model=model, messages=[{"role": "user", "content": prompt}])
    return out["choices"][0]["message"]["content"]
