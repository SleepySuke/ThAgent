# -*- coding: UTF-8 -*-
'''
@Author ：自然醒
@Version ：1.0
'''
from google.adk.tools.base_toolset import BaseToolset,BaseTool
from google.adk.tools.tool_context import ToolContext
from typing import Any, Dict, List, Optional
from google.adk.tools.function_tool import FunctionTool
from google.adk.agents.llm_agent import LlmAgent
import asyncio
from google.adk.agents.readonly_context import ReadonlyContext


# 1. Define the individual tool functions
def add_numbers(a: int, b: int, tool_context: ToolContext) -> Dict[str, Any]:
    """Adds two integer numbers.
    Args:
        a: The first number.
        b: The second number.
    Returns:
        A dictionary with the sum, e.g., {'status': 'success', 'result': 5}
    """
    print(f"Tool: add_numbers called with a={a}, b={b}")
    result = a + b
    # Example: Storing something in tool_context state
    tool_context.state["last_math_operation"] = "addition"
    return {"status": "success", "result": result}


def subtract_numbers(a: int, b: int) -> Dict[str, Any]:
    """Subtracts the second number from the first.
    Args:
        a: The first number.
        b: The second number.
    Returns:
        A dictionary with the difference, e.g., {'status': 'success', 'result': 1}
    """
    print(f"Tool: subtract_numbers called with a={a}, b={b}")
    return {"status": "success", "result": a - b}


# 2. Create the Toolset by implementing BaseToolset
class SimpleMathToolset(BaseToolset):
    def __init__(self, prefix: str = "math_"):
        self.prefix = prefix
        # Create FunctionTool instances once
        self._add_tool = FunctionTool(
            func=add_numbers,
            name=f"{self.prefix}add_numbers",  # Toolset can customize names
        )
        self._subtract_tool = FunctionTool(
            func=subtract_numbers, name=f"{self.prefix}subtract_numbers"
        )
        print(f"SimpleMathToolset initialized with prefix '{self.prefix}'")

    async def get_tools(
        self, readonly_context: Optional[ReadonlyContext] = None
    ) -> List[BaseTool]:
        print(f"SimpleMathToolset.get_tools() called.")
        # Example of dynamic behavior:
        # Could use readonly_context.state to decide which tools to return
        # For instance, if readonly_context.state.get("enable_advanced_math"):
        #    return [self._add_tool, self._subtract_tool, self._multiply_tool]

        # For this simple example, always return both tools
        tools_to_return = [self._add_tool, self._subtract_tool]
        print(f"SimpleMathToolset providing tools: {[t.name for t in tools_to_return]}")
        return tools_to_return

    async def close(self) -> None:
        # No resources to clean up in this simple example
        print(f"SimpleMathToolset.close() called for prefix '{self.prefix}'.")
        await asyncio.sleep(0)  # Placeholder for async cleanup if needed


# 3. Define an individual tool (not part of the toolset)
def greet_user(name: str = "User") -> Dict[str, str]:
    """Greets the user."""
    print(f"Tool: greet_user called with name={name}")
    return {"greeting": f"Hello, {name}!"}


greet_tool = FunctionTool(func=greet_user)

# 4. Instantiate the toolset
math_toolset_instance = SimpleMathToolset(prefix="calculator_")

# 5. Define an agent that uses both the individual tool and the toolset
calculator_agent = LlmAgent(
    name="CalculatorAgent",
    model="gemini-2.0-flash",  # Replace with your desired model
    instruction="You are a helpful calculator and greeter. "
    "Use 'greet_user' for greetings. "
    "Use 'calculator_add_numbers' to add and 'calculator_subtract_numbers' to subtract. "
    "Announce the state of 'last_math_operation' if it's set.",
    tools=[greet_tool, math_toolset_instance],  # Individual tool  # Toolset instance
)
