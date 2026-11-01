"""CR Agent 组装：模型、工具、技能注入。三层 callback 由 harness 通用供给。"""
from __future__ import annotations

from pathlib import Path

from google.adk.agents import LlmAgent
from google.adk.models.lite_llm import LiteLlm

from harness.callbacks import build_callbacks
from harness.config import register_model_capabilities, resolve_model
from harness.contract import RunContext
from harness.policy import NodePolicy
from harness.sandbox.manager import SandboxManager
from harness.tools import build_tools

_AGENT_DIR = Path(__file__).parent


class AgentEvents:
    """收集 event_sink 事件（测试与 executor 复用）。"""

    def __init__(self) -> None:
        self.items: list[dict] = []

    def sink(self, event: str, payload: dict) -> None:
        self.items.append({"event": event, **payload})

    def has(self, event: str) -> bool:
        return any(i["event"] == event for i in self.items)


def _load_skills() -> tuple[str, list]:
    """ADK SkillToolset 原生加载；异常时降级 instruction 注入。

    不走 skills_folder=（那条路强制配 environment = 开放 skill 脚本执行面，
    绕过沙箱白名单治理）；用 skills= 收解析好的 Skill 列表，脚本资源恒空。
    """
    instruction = ""
    try:
        # ponytail: _load_skills_from_dir 是 adk 内部解析器（SKILL.md → Skill），
        # 公开等价物只有 skills_folder+environment 一条路，故取私有 API
        from google.adk.skills._utils import _load_skills_from_dir
        from google.adk.tools.skill_toolset import SkillToolset
        skills = _load_skills_from_dir(_AGENT_DIR / "skills")
        return instruction, [SkillToolset(skills=list(skills))]
    except Exception:
        skill = (_AGENT_DIR / "skills" / "code-review" / "SKILL.md").read_text(
            encoding="utf-8")
        return "\n\n# 技能：code-review\n" + skill, []


def build_agent(run: RunContext, manager: SandboxManager,
                policy: NodePolicy) -> LlmAgent:
    extra_instruction, skill_tools = _load_skills()
    base = (_AGENT_DIR / "prompt.md").read_text(encoding="utf-8")
    # 两级模型解析：AGENT_INFRA_MODEL_CR_AGENT > AGENT_INFRA_MODEL > 默认值。
    # thinking disabled 仅是 glm-4.x 的兼容补丁：4.x 把推理独白写进 content.text
    # 顶掉契约 JSON；5.x 的 thinking 已与 content 分离（reasoning_content 独立），
    # 关掉反而废掉推理链（实测 5.3 关 thinking 后 hit_rate 0.25，开启即恢复）
    model = resolve_model("cr_agent", "zai/glm-4.6")
    # 能力补丁：某些 provider（xiaomi_mimo 等）在 litellm 里缺模型元数据，
    # 工具能力会被误判为不支持 → 建模型前补进 model_cost
    register_model_capabilities()
    llm_kwargs = ({ "extra_body": {"thinking": {"type": "disabled"}}}
                  if model.startswith("zai/glm-4") else {})
    return LlmAgent(
        name="cr_agent",
        model=LiteLlm(model=model, **llm_kwargs),
        instruction=base + extra_instruction,
        description="代码质量管控：对指定 commit 做证据驱动的 CR",
        tools=[*build_tools(run, manager,
                            ["read_diff", "read_file", "list_files", "run_cmd",
                             "request_human", "search_knowledge"]),
               *skill_tools],
        **build_callbacks(run, policy),
    )
