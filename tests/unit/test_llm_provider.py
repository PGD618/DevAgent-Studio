"""
LLM Provider 单元测试
测试 LLM 调用、模型切换、Fallback、Token 统计等核心逻辑
"""

import pytest
from unittest.mock import MagicMock, patch, mock_open
from pathlib import Path
from app.providers.llm_provider import LLMProvider, llm_provider
from app.persistence.sqlite_store import task_store


class TestLLMConfiguration:
    """LLM 配置测试"""

    def test_read_config_from_env_file(self):
        """测试从 .env 文件读取配置"""
        env_content = """
OPENAI_API_KEY=sk-test-key-123
OPENAI_BASE_URL=https://api.test.com
DEV_AGENT_LLM_MODEL=test-model
"""
        with patch.object(Path, "exists", return_value=True):
            with patch.object(Path, "read_text", return_value=env_content):
                provider = LLMProvider()
                config = provider._config()

                assert config["api_key"] == "sk-test-key-123"
                assert config["base_url"] == "https://api.test.com"
                assert config["model"] == "test-model"
                assert config["source"] == ".env"

    def test_config_priority_process_env_over_file(self):
        """测试进程环境变量优先级高于 .env 文件"""
        env_content = "OPENAI_API_KEY=file-key\n"
        with patch.object(Path, "exists", return_value=True):
            with patch.object(Path, "read_text", return_value=env_content):
                with patch.dict("os.environ", {"OPENAI_API_KEY": "process-key"}):
                    provider = LLMProvider()
                    config = provider._config()

                    assert config["api_key"] == "process-key"
                    assert config["source"] == "process_env"

    def test_agent_specific_model_override(self):
        """测试 Agent 特定的模型覆盖"""
        env_content = """
DEV_AGENT_LLM_MODEL=default-model
DEV_AGENT_LLM_MODEL_CODE_REVIEWER=reviewer-model
"""
        with patch.object(Path, "exists", return_value=True):
            with patch.object(Path, "read_text", return_value=env_content):
                provider = LLMProvider()
                default_config = provider._config()
                reviewer_config = provider._config("code_reviewer")

                assert default_config["model"] == "default-model"
                assert reviewer_config["model"] == "reviewer-model"

    def test_batch_agent_model_override(self):
        """测试批量 Agent 模型配置"""
        env_content = """
DEV_AGENT_LLM_MODEL=base-model
DEV_AGENT_LLM_AGENT_MODELS=planner:plan-model,reporter:report-model
"""
        with patch.object(Path, "exists", return_value=True):
            with patch.object(Path, "read_text", return_value=env_content):
                provider = LLMProvider()
                planner_config = provider._config("planner")
                reporter_config = provider._config("reporter")
                other_config = provider._config("other_agent")

                assert planner_config["model"] == "plan-model"
                assert reporter_config["model"] == "report-model"
                assert other_config["model"] == "base-model"


class TestLLMGeneration:
    """LLM 生成测试"""

    def test_generate_with_no_api_key_returns_fallback(self):
        """测试无 API Key 时返回 Fallback"""
        env_content = "OPENAI_API_KEY=\n"
        with patch.object(Path, "exists", return_value=True):
            with patch.object(Path, "read_text", return_value=env_content):
                with patch.object(task_store, "save_llm_trace"):
                    provider = LLMProvider()
                    result = provider.generate_with_status(
                        system_prompt="测试",
                        user_prompt="用户输入",
                        fallback="Fallback 响应",
                        agent="test_agent"
                    )

                    assert result["text"] == "Fallback 响应"
                    assert result["fallback_used"] is True
                    assert result["answer_source"] == "fallback"
                    assert result["model"] is None

    def test_generate_with_valid_api_key_calls_llm(self):
        """测试有效 API Key 时调用 LLM"""
        env_content = """
OPENAI_API_KEY=sk-valid-key
DEV_AGENT_LLM_MODEL=gpt-4o-mini
"""
        with patch.object(Path, "exists", return_value=True):
            with patch.object(Path, "read_text", return_value=env_content):
                with patch.object(task_store, "save_llm_trace"):
                    with patch("langchain_openai.ChatOpenAI") as mock_llm_class:
                        mock_llm_instance = MagicMock()
                        mock_response = MagicMock()
                        mock_response.content = "LLM 响应内容"
                        mock_response.usage_metadata = {
                            "input_tokens": 10,
                            "output_tokens": 20,
                            "total_tokens": 30
                        }
                        mock_llm_instance.invoke.return_value = mock_response
                        mock_llm_class.return_value = mock_llm_instance

                        provider = LLMProvider()
                        result = provider.generate_with_status(
                            system_prompt="系统提示",
                            user_prompt="用户问题",
                            fallback="备用",
                            agent="test_agent"
                        )

                        assert result["text"] == "LLM 响应内容"
                        assert result["fallback_used"] is False
                        assert result["answer_source"] == "llm"
                        assert result["model"] == "gpt-4o-mini"
                        assert result["token_usage"]["input_tokens"] == 10
                        assert result["token_usage"]["output_tokens"] == 20

    def test_generate_with_llm_exception_returns_fallback(self):
        """测试 LLM 异常时返回 Fallback"""
        env_content = "OPENAI_API_KEY=sk-key\nDEV_AGENT_LLM_MODEL=gpt-4\n"
        with patch.object(Path, "exists", return_value=True):
            with patch.object(Path, "read_text", return_value=env_content):
                with patch.object(task_store, "save_llm_trace"):
                    with patch("langchain_openai.ChatOpenAI") as mock_llm_class:
                        mock_llm_class.side_effect = RuntimeError("API 调用失败")

                        provider = LLMProvider()
                        result = provider.generate_with_status(
                            system_prompt="测试",
                            user_prompt="输入",
                            fallback="异常 Fallback",
                            agent="test"
                        )

                        assert result["text"] == "异常 Fallback"
                        assert result["fallback_used"] is True
                        assert "error_message" in result


class TestPromptVersioning:
    """Prompt 版本控制测试"""

    def test_resolve_active_prompt_version(self):
        """测试解析激活的 Prompt 版本"""
        env_content = ""
        with patch.object(Path, "exists", return_value=True):
            with patch.object(Path, "read_text", return_value=env_content):
                with patch.object(task_store, "get_active_prompt_version") as mock_get:
                    mock_get.return_value = {
                        "agent": "planner",
                        "prompt_version": "planner.v2",
                        "system_suffix": "额外指令：请详细规划"
                    }

                    provider = LLMProvider()
                    resolved_prompt, version = provider._resolve_prompt(
                        agent="planner",
                        prompt_version="planner.v1",
                        system_prompt="原始系统提示",
                        use_active_prompt=True
                    )

                    assert version == "planner.v2"
                    assert "额外指令：请详细规划" in resolved_prompt

    def test_env_override_prompt_version(self):
        """测试环境变量覆盖 Prompt 版本"""
        env_content = "DEV_AGENT_PROMPT_PLANNER=planner.v3\n"
        with patch.object(Path, "exists", return_value=True):
            with patch.object(Path, "read_text", return_value=env_content):
                with patch.object(task_store, "get_prompt_version") as mock_get:
                    mock_get.return_value = {
                        "agent": "planner",
                        "prompt_version": "planner.v3",
                        "system_suffix": "V3 指令"
                    }

                    provider = LLMProvider()
                    resolved_prompt, version = provider._resolve_prompt(
                        agent="planner",
                        prompt_version="planner.v1",
                        system_prompt="原始提示",
                        use_active_prompt=True
                    )

                    assert version == "planner.v3"


class TestTokenUsageTracking:
    """Token 使用追踪测试"""

    def test_trace_is_saved_on_success(self):
        """测试成功调用保存 Trace"""
        env_content = "OPENAI_API_KEY=sk-key\n"
        with patch.object(Path, "exists", return_value=True):
            with patch.object(Path, "read_text", return_value=env_content):
                with patch.object(task_store, "save_llm_trace") as mock_save:
                    with patch("langchain_openai.ChatOpenAI") as mock_llm:
                        mock_response = MagicMock()
                        mock_response.content = "响应"
                        mock_response.usage_metadata = {"input_tokens": 5, "output_tokens": 10}
                        mock_llm.return_value.invoke.return_value = mock_response

                        provider = LLMProvider()
                        provider.generate("sys", "user", "fall", agent="test")

                        mock_save.assert_called_once()
                        trace = mock_save.call_args[0][0]
                        assert trace["agent"] == "test"
                        assert trace["fallback_used"] is False
                        assert trace["token_usage"]["input_tokens"] == 5

    def test_trace_is_saved_on_fallback(self):
        """测试 Fallback 时保存 Trace"""
        env_content = "OPENAI_API_KEY=\n"
        with patch.object(Path, "exists", return_value=True):
            with patch.object(Path, "read_text", return_value=env_content):
                with patch.object(task_store, "save_llm_trace") as mock_save:
                    provider = LLMProvider()
                    provider.generate("sys", "user", "fallback_text", agent="test")

                    mock_save.assert_called_once()
                    trace = mock_save.call_args[0][0]
                    assert trace["fallback_used"] is True
                    assert "OPENAI_API_KEY" in trace["error_message"]


class TestLLMStatus:
    """LLM 状态测试"""

    def test_status_returns_configuration(self):
        """测试状态返回完整配置"""
        env_content = """
OPENAI_API_KEY=sk-key
OPENAI_BASE_URL=https://custom.api
DEV_AGENT_LLM_MODEL=custom-model
"""
        with patch.object(Path, "exists", return_value=True):
            with patch.object(Path, "read_text", return_value=env_content):
                with patch.object(task_store, "list_prompt_versions", return_value=[]):
                    provider = LLMProvider()
                    status = provider.status()

                    assert status["enabled"] is True
                    assert status["model"] == "custom-model"
                    assert status["base_url"] == "https://custom.api"
                    assert "agent_models" in status
                    assert "planner" in status["agent_models"]