# -*- coding: UTF-8 -*-
'''
@Author ：suke
@Version ：1.0
@Date ：2026-04-22 22:02:47
@Description：读取配置服务
'''

import json
import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(BASE_DIR, "config.json")


def load_config():
    '''
    加载配置文件，获取知识库文件路径等信息
    '''
    with(open(CONFIG_PATH,'r',encoding='utf-8')) as f:
        config = json.load(f)
    return config