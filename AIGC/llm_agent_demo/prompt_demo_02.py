# -*- coding: UTF-8 -*-
'''
@Author ：自然醒
@Version ：1.0
'''

#few-shot少量样例的提示词模版
from langchain_core.prompts import FewShotPromptTemplate
from langchain_core.prompts import PromptTemplate
from langchain_community.llms import Tongyi
model = Tongyi(api_key="",model="qwen-plus")
prompt_template = PromptTemplate.from_template("单词:{word},反义词:{antonym}")
example_data = [
    {
        "word": "good",
        "antonym": "bad"
    },
    {
        "word": "happy",
        "antonym": "sad"
    }
]

few_shot_prompt = FewShotPromptTemplate(
    example_prompt=prompt_template,
    examples = example_data,
    prefix="这是反义词的示例",
    suffix="基于示例，请给出单词的相反词：{input}",
    input_variables=["input"]
)
print(few_shot_prompt.invoke(input={"input":"hello"}).to_string())
res = model.invoke(input = few_shot_prompt.format(input="hello"))
print(res)