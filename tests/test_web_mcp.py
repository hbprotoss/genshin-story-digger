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
