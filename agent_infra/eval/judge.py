"""V 层：判定链②——校准过的 LLM judge（语义等价判定）。

定位：判定链三段之一——规则判定（① evaluate.py 的 file+line 容差）覆盖约 80%，
本模块补语义等价类：同一问题、说法/行号略有出入时规则会误判 miss，judge 仲裁。
**judge 上岗前必须过校准集**（judge_calibration.json，人工标注的等价/不等价对）：
准确率 ≥ CALIBRATION_GATE 才可用于评测；判错的对子回流校准集迭代。

未接线进 gate（设计如此）：先以校准器形态存在，接线点是 evaluate_commit 的
miss 复核通道（规则判 miss 的条目过 judge 复核，防低估）——见设计文档 §3。
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from harness.config import register_model_capabilities, resolve_model  # noqa: E402

CALIB_PATH = Path(__file__).resolve().parent / "judge_calibration.json"
CALIBRATION_GATE = 0.90   # 准确率门槛：过不了不许进评测链路

_JUDGE_PROMPT = """你是代码审查结果的等价判定器。给定两条 CR issue（JSON），
判断它们是否指向**同一个底层问题**。

等价（EQUIV）的判据：
- 同一文件、同一处代码（行号允许相差几行）
- 问题描述可以措辞不同，但根因相同（同一处逻辑/同一次违规）

不等价（NEQ）的判据（即使文件行号完全相同）：
- 根因不同：一个是行为 bug、另一个是风格/命名/死代码/测试同步等不同性质的问题
- 指向不同代码位置或不同缺陷

只输出一个词：EQUIV 或 NEQ。不要任何解释。

issue A: {a}
issue B: {b}"""


def judge_pair(a: dict, b: dict, model: str | None = None) -> bool | None:
    """判两条 issue 是否语义等价；解析失败返回 None（计为无效，不猜）。"""
    import litellm

    model = model or resolve_model("judge", "")
    if not model:
        return None
    r = litellm.completion(
        model=model, max_tokens=1024, temperature=0.0,
        messages=[{"role": "user", "content": _JUDGE_PROMPT.format(
            a=json.dumps(a, ensure_ascii=False), b=json.dumps(b, ensure_ascii=False))}],
    )
    # thinking 模型的答案在 content；若 content 空（预算被思考链吃掉），兜底看
    # reasoning_content 末行——判定词通常出现在思考结尾
    msg = r.choices[0].message
    text = (getattr(msg, "content", None) or "").strip()
    if not text:
        reasoning = getattr(msg, "reasoning_content", None) or ""
        text = reasoning.strip().splitlines()[-1] if reasoning.strip() else ""
    text = text.upper()
    if "EQUIV" in text and "NEQ" not in text:
        return True
    if "NEQ" in text:
        return False
    return None   # 输出形态漂移：无效判定，不参与准确率分子


def run_calibration(model: str | None = None) -> float:
    pairs = json.loads(CALIB_PATH.read_text(encoding="utf-8"))
    ok = invalid = 0
    fails: list[str] = []
    for p in pairs:
        got = judge_pair(p["a"], p["b"], model)
        if got is None:
            invalid += 1
            fails.append(f"#{p['id']}: 无效输出（格式漂移）")
            continue
        if got == p["expect"]:
            ok += 1
        else:
            fails.append(f"#{p['id']}: 期望{'EQUIV' if p['expect'] else 'NEQ'}"
                         f" 判成{'EQUIV' if got else 'NEQ'}")
    acc = ok / len(pairs)
    print(f"judge 校准：{ok}/{len(pairs)} 正确（无效输出 {invalid}）→ 准确率 {acc:.2f}")
    for f in fails:
        print(f"  miss {f}")
    print((f"✅ 通过校准门槛（≥{CALIBRATION_GATE:.2f}），judge 可用于评测链路")
          if acc >= CALIBRATION_GATE else
          f"❌ 未过校准门槛（{CALIBRATION_GATE}）——不可上岗；"
          "判错对子回流 judge_calibration.json 迭代 prompt")
    return acc


def main() -> None:
    register_model_capabilities()
    model = resolve_model("judge", "")
    print(f"judge model: {model or '(未配置 AGENT_INFRA_MODEL，跳过)'}")
    if not model:
        sys.exit(2)
    run_calibration(model)


if __name__ == "__main__":
    main()
