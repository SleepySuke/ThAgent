"""DatabaseSessionService 进程级单例（预研 §3.1：每次新建不 dispose = 13/50
aiosqlite 连接 GC 不可达的慢泄漏；单例后一进程一 AsyncEngine 一池）。"""

import agent_server


async def test_session_service_is_process_wide_singleton(tmp_path, monkeypatch):
    monkeypatch.setattr(agent_server, "RUNS", tmp_path)  # 隔离 tmp db
    try:
        assert agent_server._session_service() is agent_server._session_service()
    finally:
        agent_server._reset_session_service()  # 不把 tmp db 实例漏给其它测试


async def test_reset_session_service_yields_new_instance(tmp_path, monkeypatch):
    monkeypatch.setattr(agent_server, "RUNS", tmp_path)
    try:
        s1 = agent_server._session_service()
        agent_server._reset_session_service()
        assert agent_server._session_service() is not s1
    finally:
        agent_server._reset_session_service()
