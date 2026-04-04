# -*- coding: UTF-8 -*-
'''
@Author ：自然醒
@Version ：1.0
'''

#金融文本分类

from openai import OpenAI
client: OpenAI = OpenAI(
    api_key='',
    base_url='https://dashscope.aliyuncs.com/compatible-mode/v1'
)

example_data = {
    '新闻报道':'今日，股市经历了一轮震荡，受到宏观经济数据和全球贸易紧张局势的影响。投资者密切关注关联可能得政策调整，以适应市场的变化',
    '财务报告':'本公司年度财务报告显示，去年公司实现了稳步增长的盈利，同时资产负债表呈现强劲的状况。经济环境的稳定和管理层的有效战略执行为公司的健康发展提供了重要支持。',
    '公司公告':'本公司高兴地宣布完成最新一轮并购交易，收购了一家在人工智能领域领先的公司。这一战略举措有助于扩大我们的业务领域，提高市场竞争力',
    '分析师报告':'最新的行业分析报告指出，科技公司的创新将成为未来增长的主要推动力。云计算、人工智能和数字化转型被认为是引领行业发展的关键因素，投资在这些领域将获得良好回报。'
}

example_types = ['新闻报道', '财务报告', '公司公告', '分析师报告']

questions = [
    '今日，央行发布公告宣布降低利率，以刺激经济增长。这一降息举措将影响贷款利率，并在未来几个季度内对金融市场产生影响',
    'ABC公司今日发布公告称，已成功完成对XYZ公司股权的收购交易。本次交易是ABC公司在扩大业务范围、加强市场竞争力方面的重要举措。据悉，此次收购将进一步巩固公司发展。',
    '公司资产负债表显示，公司偿债能力强劲，现金流充足，为未来投资和扩张提供了坚实的财务基础',
    '最新的分析报告指出，可再生能源行业预计将在未来几年经历持续增长，投资者应该关注这一领域的投资机会',
    '小苏喜欢睡到自然醒'
]



messages = [
    {
        'role':'system',
        'content':'你是一个金融文本分类专家，请根据提供的文本内容，将文本分类为以下四种类型：新闻报道、财务报告、公司公告、分析师报告，如果为不清楚的文本，请返回“无法判断”。以下有示例：'
    }
]

for key,value in example_data.items():
    messages.append({'role':'user','content':value})
    messages.append({'role':'assistant','content':key})

for q in questions:
    response = client.chat.completions.create(
        model = 'qwen-plus-2025-12-01',
        messages=messages+[{'role':'user','content':f'按照示例，回答这段文本的分类结果：{q}'}]
    )
    print(response.choices[0].message.content)