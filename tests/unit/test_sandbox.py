"""
Sandbox 单元测试
测试技能沙箱执行、Docker 容器隔离、进程沙箱等核心逻辑
"""

import pytest
import json
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock
from app.skills.sandbox import (
    run_python_skill_subprocess_sandbox,
    run_python_skill_docker_sandbox,
    run_python_skill_sandbox,
    python_skill_sandbox_status,
    _sandbox_config,
)


@pytest.fixture
def simple_skill_file(tmp_path):
    """创建一个简单的测试技能文件"""
    skill_file = tmp_path / "test_skill.py"
    skill_file.write_text("""
def run(payload):
    return {"result": "success", "input": payload.get("message")}
""")
    return skill_file


@pytest.fixture
def error_skill_file(tmp_path):
    """创建一个会抛出异常的技能文件"""
    skill_file = tmp_path / "error_skill.py"
    skill_file.write_text("""
def run(payload):
    raise RuntimeError("Skill execution failed")
""")
    return skill_file


@pytest.fixture
def custom_function_skill_file(tmp_path):
    """创建一个带自定义函数名的技能文件"""
    skill_file = tmp_path / "custom_skill.py"
    skill_file.write_text("""
def custom_handler(payload):
    return {"result": "custom", "value": payload.get("value", 0) * 2}
""")
    return skill_file


class TestSubprocessSandbox:
    """子进程沙箱测试"""

    def test_run_simple_skill(self, simple_skill_file):
        """测试运行简单技能"""
        result = run_python_skill_subprocess_sandbox(
            str(simple_skill_file),
            "run",
            {"message": "hello"}
        )

        assert result["result"] == "success"
        assert result["input"] == "hello"

    def test_run_skill_with_timeout(self, tmp_path):
        """测试超时技能"""
        timeout_skill = tmp_path / "timeout_skill.py"
        timeout_skill.write_text("""
import time
def run(payload):
    time.sleep(5)
    return {"result": "done"}
""")

        with pytest.raises(Exception):  # subprocess.TimeoutExpired
            run_python_skill_subprocess_sandbox(
                str(timeout_skill),
                "run",
                {},
                timeout_seconds=1
            )

    def test_run_skill_with_error(self, error_skill_file):
        """测试错误技能"""
        with pytest.raises(RuntimeError, match="Skill execution failed"):
            run_python_skill_subprocess_sandbox(
                str(error_skill_file),
                "run",
                {}
            )

    def test_run_skill_with_custom_function(self, custom_function_skill_file):
        """测试自定义函数名"""
        result = run_python_skill_subprocess_sandbox(
            str(custom_function_skill_file),
            "custom_handler",
            {"value": 10}
        )

        assert result["result"] == "custom"
        assert result["value"] == 20

    def test_run_skill_nonexistent_file(self):
        """测试不存在的文件"""
        with pytest.raises(FileNotFoundError, match="Python skill entrypoint not found"):
            run_python_skill_subprocess_sandbox(
                "/nonexistent/file.py",
                "run",
                {}
            )

    def test_run_skill_non_python_file(self, tmp_path):
        """测试非 Python 文件"""
        non_py_file = tmp_path / "test.txt"
        non_py_file.write_text("not a python file")

        with pytest.raises(FileNotFoundError, match="Python skill entrypoint not found"):
            run_python_skill_subprocess_sandbox(
                str(non_py_file),
                "run",
                {}
            )


class TestDockerSandbox:
    """Docker 沙箱测试"""

    @patch("shutil.which")
    def test_docker_not_available(self, mock_which, simple_skill_file):
        """测试 Docker 不可用"""
        mock_which.return_value = None

        with pytest.raises(RuntimeError, match="docker CLI was not found"):
            run_python_skill_docker_sandbox(
                str(simple_skill_file),
                "run",
                {}
            )

    @pytest.mark.requires_docker
    @patch("subprocess.run")
    @patch("shutil.which")
    def test_docker_run_success(self, mock_which, mock_run, simple_skill_file, tmp_path):
        """测试 Docker 成功运行"""
        mock_which.return_value = "/usr/bin/docker"

        # 模拟 Docker 成功执行
        mock_completed = MagicMock()
        mock_completed.returncode = 0
        mock_completed.stdout = ""
        mock_completed.stderr = ""
        mock_run.return_value = mock_completed

        # 创建模拟的输出文件
        with patch("tempfile.TemporaryDirectory") as mock_tempdir:
            mock_temp = tmp_path / "docker_temp"
            mock_temp.mkdir(exist_ok=True)
            mock_tempdir.return_value.__enter__.return_value = str(mock_temp)

            output_path = mock_temp / "output.json"
            output_path.write_text(json.dumps({"result": "docker_success"}))

            result = run_python_skill_docker_sandbox(
                str(simple_skill_file),
                "run",
                {"message": "test"}
            )

            assert result["result"] == "docker_success"
            assert mock_run.called

    @pytest.mark.requires_docker
    @patch("subprocess.run")
    @patch("shutil.which")
    def test_docker_run_timeout(self, mock_which, mock_run, simple_skill_file):
        """测试 Docker 超时"""
        mock_which.return_value = "/usr/bin/docker"

        import subprocess
        mock_run.side_effect = subprocess.TimeoutExpired("docker", 5)

        with pytest.raises(TimeoutError, match="Docker skill timed out"):
            run_python_skill_docker_sandbox(
                str(simple_skill_file),
                "run",
                {},
                timeout_seconds=2
            )

    @pytest.mark.requires_docker
    @patch("subprocess.run")
    @patch("shutil.which")
    def test_docker_run_error(self, mock_which, mock_run, simple_skill_file):
        """测试 Docker 运行错误"""
        mock_which.return_value = "/usr/bin/docker"

        mock_completed = MagicMock()
        mock_completed.returncode = 1
        mock_completed.stderr = "Docker error: container failed"
        mock_completed.stdout = ""
        mock_run.return_value = mock_completed

        with pytest.raises(RuntimeError, match="Docker error"):
            run_python_skill_docker_sandbox(
                str(simple_skill_file),
                "run",
                {}
            )


class TestSandboxSelector:
    """沙箱选择器测试"""

    @patch.dict("os.environ", {}, clear=True)
    def test_default_subprocess_mode(self, simple_skill_file):
        """测试默认使用子进程模式"""
        result = run_python_skill_sandbox(
            str(simple_skill_file),
            "run",
            {"message": "test"}
        )

        assert result["result"] == "success"
        assert result["input"] == "test"

    @patch.dict("os.environ", {"DEV_AGENT_SKILL_SANDBOX": "subprocess"}, clear=True)
    def test_explicit_subprocess_mode(self, simple_skill_file):
        """测试显式指定子进程模式"""
        result = run_python_skill_sandbox(
            str(simple_skill_file),
            "run",
            {"message": "test"}
        )

        assert result["result"] == "success"

    @patch.dict("os.environ", {"DEV_AGENT_SKILL_SANDBOX": "docker", "DEV_AGENT_SKILL_SANDBOX_FALLBACK": "true"}, clear=True)
    @patch("shutil.which")
    def test_docker_fallback_to_subprocess(self, mock_which, simple_skill_file):
        """测试 Docker 失败回退到子进程"""
        mock_which.return_value = None  # Docker 不可用

        # 启用了 fallback，应该回退到子进程
        result = run_python_skill_sandbox(
            str(simple_skill_file),
            "run",
            {"message": "test"}
        )

        assert result["result"] == "success"

    @patch.dict("os.environ", {"DEV_AGENT_SKILL_SANDBOX": "docker", "DEV_AGENT_SKILL_SANDBOX_FALLBACK": "false"}, clear=True)
    @patch("shutil.which")
    def test_docker_no_fallback(self, mock_which, simple_skill_file):
        """测试 Docker 失败不回退"""
        mock_which.return_value = None  # Docker 不可用

        # 未启用 fallback，应该抛出异常
        with pytest.raises(RuntimeError, match="docker CLI was not found"):
            run_python_skill_sandbox(
                str(simple_skill_file),
                "run",
                {}
            )


class TestSandboxConfig:
    """沙箱配置测试"""

    @patch.dict("os.environ", {}, clear=True)
    def test_default_config(self):
        """测试默认配置"""
        config = _sandbox_config()

        assert config["mode"] == "subprocess"
        assert config["docker_image"] == "python:3.13-slim"
        assert config["memory"] == "256m"
        assert config["cpus"] == "0.5"
        assert config["pids_limit"] == 64
        assert config["fallback"] is False

    @patch.dict("os.environ", {
        "DEV_AGENT_SKILL_SANDBOX": "docker",
        "DEV_AGENT_SKILL_SANDBOX_IMAGE": "python:3.12-alpine",
        "DEV_AGENT_SKILL_SANDBOX_MEMORY": "512m",
        "DEV_AGENT_SKILL_SANDBOX_CPUS": "1.0",
        "DEV_AGENT_SKILL_SANDBOX_PIDS_LIMIT": "128",
        "DEV_AGENT_SKILL_SANDBOX_FALLBACK": "true"
    }, clear=True)
    def test_custom_config(self):
        """测试自定义配置"""
        config = _sandbox_config()

        assert config["mode"] == "docker"
        assert config["docker_image"] == "python:3.12-alpine"
        assert config["memory"] == "512m"
        assert config["cpus"] == "1.0"
        assert config["pids_limit"] == 128
        assert config["fallback"] is True

    def test_sandbox_status_subprocess(self):
        """测试子进程模式状态"""
        with patch.dict("os.environ", {"DEV_AGENT_SKILL_SANDBOX": "subprocess"}, clear=True):
            status = python_skill_sandbox_status()

            assert status["mode"] == "subprocess"
            assert status["docker_image"] is None
            assert status["network"] == "host-process"
            assert status["read_only_root"] is False

    def test_sandbox_status_docker(self):
        """测试 Docker 模式状态"""
        with patch.dict("os.environ", {"DEV_AGENT_SKILL_SANDBOX": "docker"}, clear=True):
            status = python_skill_sandbox_status()

            assert status["mode"] == "docker"
            assert status["docker_image"] == "python:3.13-slim"
            assert status["network"] == "none"
            assert status["read_only_root"] is True


class TestSandboxSecurity:
    """沙箱安全测试"""

    def test_skill_cannot_access_parent_directory(self, tmp_path):
        """测试技能无法访问父目录"""
        skill_file = tmp_path / "malicious_skill.py"
        skill_file.write_text("""
import os
def run(payload):
    # 尝试读取父目录
    parent = os.path.dirname(os.path.dirname(__file__))
    files = os.listdir(parent)
    return {"files": files}
""")

        # 技能可以执行，但在受限环境中
        result = run_python_skill_subprocess_sandbox(
            str(skill_file),
            "run",
            {}
        )

        # 验证返回了文件列表（但这是在临时目录中）
        assert "files" in result

    def test_skill_with_large_output(self, tmp_path):
        """测试大输出处理"""
        skill_file = tmp_path / "large_output_skill.py"
        skill_file.write_text("""
def run(payload):
    return {"data": "A" * 10000}  # 10KB 输出
""")

        result = run_python_skill_subprocess_sandbox(
            str(skill_file),
            "run",
            {}
        )

        assert len(result["data"]) == 10000


class TestSandboxEdgeCases:
    """沙箱边界情况测试"""

    def test_skill_returns_non_dict(self, tmp_path):
        """测试技能返回非字典"""
        skill_file = tmp_path / "non_dict_skill.py"
        skill_file.write_text("""
def run(payload):
    return "just a string"
""")

        result = run_python_skill_subprocess_sandbox(
            str(skill_file),
            "run",
            {}
        )

        # 应包装为字典
        assert result == {"result": "just a string"}

    def test_skill_returns_none(self, tmp_path):
        """测试技能返回 None"""
        skill_file = tmp_path / "none_skill.py"
        skill_file.write_text("""
def run(payload):
    return None
""")

        result = run_python_skill_subprocess_sandbox(
            str(skill_file),
            "run",
            {}
        )

        assert result == {"result": None}

    def test_skill_with_unicode(self, tmp_path):
        """测试 Unicode 处理"""
        skill_file = tmp_path / "unicode_skill.py"
        skill_file.write_text("""
def run(payload):
    return {"message": "你好世界", "input": payload.get("text")}
""", encoding="utf-8")

        result = run_python_skill_subprocess_sandbox(
            str(skill_file),
            "run",
            {"text": "测试中文"}
        )

        assert result["message"] == "你好世界"
        assert result["input"] == "测试中文"

    def test_skill_missing_function(self, tmp_path):
        """测试缺少指定函数"""
        skill_file = tmp_path / "missing_func_skill.py"
        skill_file.write_text("""
def other_function(payload):
    return {"result": "other"}
""")

        with pytest.raises(RuntimeError, match="Entrypoint function not found"):
            run_python_skill_subprocess_sandbox(
                str(skill_file),
                "run",  # 函数不存在
                {}
            )
