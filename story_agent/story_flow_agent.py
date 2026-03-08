# -*- coding: UTF-8 -*-
'''
@Author ：自然醒
@Version ：1.0
'''
import asyncio

from google.adk.agents import BaseAgent, LoopAgent, SequentialAgent, LlmAgent, InvocationContext
from google.adk.events import Event
from google.adk.models.lite_llm import LiteLlm
from typing import AsyncGenerator
import logging
from google.adk.runners import Runner
from google.genai import types
from google.adk.sessions import InMemorySessionService
from typing_extensions import override
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


story_generator = LlmAgent(
    name="story_generator",
    model=LiteLlm(
        model="zai/glm-4.7",
    ),
    description="故事生成器，根据用户提示生成创意故事。",
    instruction="""
你是故事生成专家。根据用户提供的主题或提示，创作一个引人入胜的故事。

要求：
1. 故事结构完整，包含开头、发展和结尾
2. 人物形象鲜明，对话自然
3. 情节紧凑，有起伏和冲突
4. 语言生动，富有想象力

将生成的完整故事保存到 session state 的 'current_story' 字段中。
""",
    output_key="current_story",
)

critic = LlmAgent(
    name="critic",
    model=LiteLlm(model="dashscope/qwen-plus"),
    description="故事评论家，对故事进行批评和评价，提供改进建议。",
    instruction="""
你是专业的文学评论家。对当前故事（从 session state 的 'current_story' 读取）进行深入分析。

评价维度：
1. 情节连贯性和逻辑性
2. 人物塑造和对话质量
3. 语言表达和文风
4. 创新性和吸引力
5. 潜在的改进空间

提供具体、建设性的批评意见，帮助改进故事质量。
""",
)

reviser = LlmAgent(
    name="reviser",
    model=LiteLlm(model="dashscope/qwen-plus"),
    description="故事修订者，根据评论家的反馈对故事进行修订和完善。",
    instruction="""
你是专业的故事编辑。根据评论家的批评意见（从上一步获取），对当前故事进行修订。

修订原则：
1. 保持故事核心主题和风格
2. 修复评论家指出的情节和逻辑问题
3. 改善人物对话和描述
4. 提升语言表达质量
5. 增强故事吸引力和感染力

将修订后的故事更新到 session state 的 'current_story' 字段中。
""",
    output_key="current_story",
)

grammar_check = LlmAgent(
    name="grammar_check",
    model=LiteLlm(model="dashscope/qwen-plus"),
    description="语法检查器，检查故事的语法正确性和表达流畅度。",
    instruction="""
你是专业的语言编辑。检查当前故事的语法、拼写和表达。

检查内容：
1. 语法错误（时态、语态、句式结构）
2. 拼写和标点符号错误
3. 表达不通顺或歧义的地方
4. 用词不当或不准确的地方

如果发现错误，指出具体位置并给出修改建议。如果没有明显错误，说明故事语言质量良好。
""",
)

tone_check = LlmAgent(
    name="tone_check",
    model=LiteLlm(model="dashscope/qwen-plus"),
    description="语气检查器，分析故事的整体语气（积极/消极）。",
    instruction="""
你是专业的文本分析师。分析当前故事的整体语气和情感倾向。

分析维度：
1. 整体情感基调（积极/消极/中性）
2. 是否包含过度消极或负面的内容
3. 故事是否传达了积极的价值观念

判断结果：
- 如果故事语气消极或包含大量负面内容，输出 'negative'
- 如果故事语气积极或中性，输出 'positive'

将分析结果保存到 session state 的 'tone_check_result' 字段中。
""",
    output_key="tone_check_result",
)


class StoryFlowAgent(BaseAgent):
    """
    用于故事生成和优化流程的自定义智能体。

    该智能体编排一系列LLM智能体来生成故事、评论故事、修订故事、
    检查语法和语气，如果语气消极则可能重新生成故事。
    """

    # --- Pydantic 字段声明 ---
    # 将初始化时传入的智能体声明为带有类型提示的类属性
    story_generator: LlmAgent
    critic: LlmAgent
    reviser: LlmAgent
    grammar_check: LlmAgent
    tone_check: LlmAgent

    loop_agent: LoopAgent
    sequential_agent: SequentialAgent

    # model_config 允许设置 Pydantic 配置（如需要），例如 arbitrary_types_allowed
    model_config = {"arbitrary_types_allowed": True}

    def __init__(
        self,
        name: str,
        story_generator: LlmAgent,
        critic: LlmAgent,
        reviser: LlmAgent,
        grammar_check: LlmAgent,
        tone_check: LlmAgent,
    ):
        """
        初始化 StoryFlowAgent。

        参数:
            name: 智能体的名称。
            story_generator: 用于生成初始故事的 LlmAgent。
            critic: 用于评论故事的 LlmAgent。
            reviser: 根据评论修订故事的 LlmAgent。
            grammar_check: 用于检查语法的 LlmAgent。
            tone_check: 用于分析语气的 LlmAgent。
        """
        # 在调用 super().__init__ 之前创建内部智能体
        loop_agent = LoopAgent(
            name="CriticReviserLoop", sub_agents=[critic, reviser], max_iterations=2
        )
        sequential_agent = SequentialAgent(
            name="PostProcessing", sub_agents=[grammar_check, tone_check]
        )

        # 为框架定义子智能体列表
        sub_agents_list = [
            story_generator,
            loop_agent,
            sequential_agent,
        ]

        # Pydantic 将根据类注解进行验证和赋值。
        super().__init__(
            name=name,
            story_generator=story_generator,
            critic=critic,
            reviser=reviser,
            grammar_check=grammar_check,
            tone_check=tone_check,
            loop_agent=loop_agent,
            sequential_agent=sequential_agent,
            sub_agents=sub_agents_list, # 直接传递子智能体列表
        )

    @override
    async def _run_async_impl(
            self, ctx: InvocationContext
    ) -> AsyncGenerator[Event, None]:
        """
        Implements the custom orchestration logic for the story workflow.
        Uses the instance attributes assigned by Pydantic (e.g., self.story_generator).
        """
        logger.info(f"[{self.name}] Starting story generation workflow.")

        # 1. Initial Story Generation
        logger.info(f"[{self.name}] Running StoryGenerator...")
        async for event in self.story_generator.run_async(ctx):
            logger.info(
                f"[{self.name}] Event from StoryGenerator: {event.model_dump_json(indent=2, exclude_none=True)}")
            yield event

        # Check if story was generated before proceeding
        if "current_story" not in ctx.session.state or not ctx.session.state["current_story"]:
            logger.error(f"[{self.name}] Failed to generate initial story. Aborting workflow.")
            return  # Stop processing if initial story failed

        logger.info(f"[{self.name}] Story state after generator: {ctx.session.state.get('current_story')}")

        # 2. Critic-Reviser Loop
        logger.info(f"[{self.name}] Running CriticReviserLoop...")
        # Use the loop_agent instance attribute assigned during init
        async for event in self.loop_agent.run_async(ctx):
            logger.info(
                f"[{self.name}] Event from CriticReviserLoop: {event.model_dump_json(indent=2, exclude_none=True)}")
            yield event

        logger.info(f"[{self.name}] Story state after loop: {ctx.session.state.get('current_story')}")

        # 3. Sequential Post-Processing (Grammar and Tone Check)
        logger.info(f"[{self.name}] Running PostProcessing...")
        # Use the sequential_agent instance attribute assigned during init
        async for event in self.sequential_agent.run_async(ctx):
            logger.info(
                f"[{self.name}] Event from PostProcessing: {event.model_dump_json(indent=2, exclude_none=True)}")
            yield event

        # 4. Tone-Based Conditional Logic
        tone_check_result = ctx.session.state.get("tone_check_result")
        logger.info(f"[{self.name}] Tone check result: {tone_check_result}")

        if tone_check_result == "negative":
            logger.info(f"[{self.name}] Tone is negative. Regenerating story...")
            async for event in self.story_generator.run_async(ctx):
                logger.info(
                    f"[{self.name}] Event from StoryGenerator (Regen): {event.model_dump_json(indent=2, exclude_none=True)}")
                yield event
        else:
            logger.info(f"[{self.name}] Tone is not negative. Keeping current story.")
            pass

        logger.info(f"[{self.name}] Workflow finished.")

story_flow_agent = StoryFlowAgent(
    name="StoryFlowAgent",
    story_generator=story_generator,
    critic=critic,
    reviser=reviser,
    grammar_check=grammar_check,
    tone_check=tone_check,
)

APP_NAME = "story_agent_demo"
USER_ID = "test_user_001"
SESSION_ID = "demo_session_001"

INITIAL_STATE = {"topic": "a brave kitten exploring a haunted house"}

# --- Setup Runner and Session ---
async def setup_session_and_runner():
    session_service = InMemorySessionService()
    session = await session_service.create_session(app_name=APP_NAME, user_id=USER_ID, session_id=SESSION_ID, state=INITIAL_STATE)
    logger.info(f"Initial session state: {session.state}")
    runner = Runner(
        agent=story_flow_agent, # Pass the custom orchestrator agent
        app_name=APP_NAME,
        session_service=session_service
    )
    return session_service, runner

# --- Function to Interact with the Agent ---
async def call_agent_async(user_input_topic: str):
    """
    Sends a new topic to the agent (overwriting the initial one if needed)
    and runs the workflow.
    """

    session_service, runner = await setup_session_and_runner()

    current_session = session_service.sessions[APP_NAME][USER_ID][SESSION_ID]
    current_session.state["topic"] = user_input_topic
    logger.info(f"Updated session state topic to: {user_input_topic}")

    content = types.Content(role='user', parts=[types.Part(text=f"Generate a story about the preset topic.")])
    events = runner.run_async(user_id=USER_ID, session_id=SESSION_ID, new_message=content)

    final_response = "No final response captured."
    async for event in events:
        if event.is_final_response() and event.content and event.content.parts:
            logger.info(f"Potential final response from [{event.author}]: {event.content.parts[0].text}")
            final_response = event.content.parts[0].text

    print("\n--- Agent Interaction Result ---")
    print("Agent Final Response: ", final_response)

    final_session = await session_service.get_session(app_name=APP_NAME, 
                                                user_id=USER_ID, 
                                                session_id=SESSION_ID)
    print("Final Session State:")
    import json
    print(json.dumps(final_session.state, indent=2))
    print("-------------------------------\n")

# --- Run the Agent ---
async def main():
    await call_agent_async("a lonely robot finding a friend in a junkyard")

if __name__ == "__main__":
    asyncio.run(main())


