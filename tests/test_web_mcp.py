"""mcp_server streamable-http 模式（CLI 参数解析）测试。

真实拉起 HTTP 需要 MongoDB，故只测 main 的参数解析与 transport 选择。
"""

import inspect

import mcp_server


def test_main_has_transport_option():
    main_src = inspect.getsource(mcp_server.main)
    assert "--transport" in main_src
    assert "--host" in main_src
    assert "--port" in main_src


def test_spawn_command_points_to_http(fixtures_cfg):
    from mongo_mcp import mcp_cmd
    from config import load_config
    cfg = load_config(fixtures_cfg)
    cmd = mcp_cmd(cfg)
    assert "--transport" in cmd
    assert "streamable-http" in cmd
    assert str(cfg.web.mcp_port) in cmd
    assert "--uri" in cmd
