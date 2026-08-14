"""
测试配置与共享 Fixtures
"""

import pytest
from pathlib import Path


@pytest.fixture
def temp_project_dir(tmp_path):
    """创建临时项目目录用于测试"""
    project = tmp_path / "test_project"
    project.mkdir()
    (project / "README.md").write_text("# Test Project")
    (project / "src").mkdir()
    (project / "src" / "main.py").write_text("def main():\n    pass\n")
    return str(project)


@pytest.fixture
def mock_llm_response():
    """Mock LLM 响应，避免真实调用 API"""
    return {
        "text": "这是一个测试响应",
        "answer_source": "llm",
        "model": "deepseek-chat",
        "trace_id": "test_trace_123",
        "latency_ms": 100,
        "token_usage": {"input_tokens": 10, "output_tokens": 20},
    }


@pytest.fixture
def sample_workflow_nodes():
    """示例工作流节点"""
    return [
        {
            "id": "planner",
            "type": "planner",
            "config": {"goal": "分析项目"},
        },
        {
            "id": "analyzer",
            "type": "agent",
            "config": {"agent": "project_analyzer"},
        },
        {
            "id": "reporter",
            "type": "reporter",
            "config": {},
        },
    ]


@pytest.fixture
def sample_workflow_edges():
    """示例工作流边"""
    return [
        {"from": "planner", "to": "analyzer", "condition": "always"},
        {"from": "analyzer", "to": "reporter", "condition": "always"},
    ]
