from harness.intake import classify_intent

PAUSED = [
    {"trace_id": "aaa", "current_node": "cr", "context_id": "repo:demo_repo"},
    {"trace_id": "bbb", "current_node": "testing", "context_id": "repo:demo_repo"},
]


def _llm_of(reply):
    return lambda prompt: {"choices": [{"message": {"content": reply}}]}


def test_intent_new():
    out = classify_intent("重新分析 defect-3", PAUSED, _llm_of('{"intent":"new"}'))
    assert out == {"intent": "new"}


def test_intent_resume():
    out = classify_intent("继续，注意折扣", PAUSED,
                          _llm_of('{"intent":"resume","trace_id":"aaa"}'))
    assert out == {"intent": "resume", "trace_id": "aaa"}


def test_refer_grounds_to_most_recent():
    out = classify_intent("继续之前那个折扣审查", PAUSED,
                          _llm_of('{"intent":"refer"}'))
    # 指代歧义：取最近暂停的（列表末位）+ 可纠标记
    assert out == {"intent": "resume", "trace_id": "bbb", "guessed": True}


def test_llm_failure_falls_back():
    def boom(prompt):
        raise RuntimeError("llm down")
    out = classify_intent("x", PAUSED, boom)
    assert out["intent"] == "fallback" and len(out["candidates"]) == 2


def test_illegal_json_falls_back():
    out = classify_intent("x", PAUSED, _llm_of("不是 JSON"))
    assert out["intent"] == "fallback"


def test_no_paused_skips_classification():
    out = classify_intent("随便什么", [], _llm_of('{"intent":"resume"}'))
    assert out == {"intent": "new"}
