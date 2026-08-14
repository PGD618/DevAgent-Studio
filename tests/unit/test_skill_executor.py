"""
Skill Executor 单元测试
测试 Skill 权限检查、契约校验、沙箱执行等核心逻辑
"""

import pytest
from unittest.mock import MagicMock, patch, call
from app.skills.executor import execute_skill, ensure_builtin_skills_seeded
from app.persistence.sqlite_store import task_store
from app.skills.base import SkillContext


class TestSkillPermissionCheck:
    """Skill 权限审批测试"""

    def test_execute_unapproved_skill_raises_error(self):
        """测试执行未审批的 Skill 应抛出权限错误"""
        with patch.object(task_store, "get_skill") as mock_get:
            mock_get.return_value = {
                "code": "test.skill",
                "enabled": True,
                "permissions": ["filesystem.write"],
                "input_schema": {"type": "object"},
                "output_schema": {"type": "object"},
                "execution_type": "agent",
            }
            with patch.object(task_store, "get_skill_approval") as mock_approval:
                mock_approval.return_value = None  # 未审批

                with pytest.raises(PermissionError, match="not approved"):
                    execute_skill("test.skill", {}, agent_code="workflow_runner")

    def test_execute_approved_skill_succeeds(self):
        """测试已审批的 Skill 可正常执行"""
        with patch.object(task_store, "get_skill") as mock_get:
            mock_get.return_value = {
                "code": "test.skill",
                "enabled": True,
                "permissions": ["safe"],
                "input_schema": {"type": "object"},
                "output_schema": {"type": "object"},
                "execution_type": "agent",
            }
            with patch.object(task_store, "get_skill_approval") as mock_approval:
                mock_approval.return_value = {"allowed": True}

                with patch.object(task_store, "save_skill_execution_log"):
                    # Mock registry.execute 返回
                    from app.skills.registry import skill_registry
                    with patch.object(skill_registry, "execute") as mock_execute:
                        mock_execute.return_value = {"result": "success"}

                        result = execute_skill("test.skill", {"input": "test"}, agent_code="skill_console")

                        assert result["status"] == "completed"
                        assert result["output"]["result"] == "success"
                        mock_execute.assert_called_once()

    def test_skill_with_no_permissions_does_not_require_approval(self):
        """测试无权限要求的 Skill 不需要审批"""
        with patch.object(task_store, "get_skill") as mock_get:
            mock_get.return_value = {
                "code": "safe.skill",
                "enabled": True,
                "permissions": [],  # 无权限要求
                "input_schema": {"type": "object"},
                "output_schema": {"type": "object"},
                "execution_type": "agent",
            }
            with patch.object(task_store, "get_skill_approval") as mock_approval:
                mock_approval.return_value = None  # 未审批但不需要

                with patch.object(task_store, "save_skill_execution_log"):
                    from app.skills.registry import skill_registry
                    with patch.object(skill_registry, "execute") as mock_execute:
                        mock_execute.return_value = {"result": "ok"}

                        result = execute_skill("safe.skill", {})
                        # 应该成功执行（因为无权限要求）


class TestSkillContractValidation:
    """Skill 契约校验测试"""

    def test_invalid_contract_raises_error(self):
        """测试契约无效的 Skill 应抛出错误"""
        with patch.object(task_store, "get_skill") as mock_get:
            mock_get.return_value = {
                "code": "invalid.skill",
                "enabled": True,
                "permissions": [],
                "input_schema": None,  # 缺少必需字段
                "output_schema": None,
                "execution_type": None,
            }
            with patch.object(task_store, "get_skill_approval") as mock_approval:
                mock_approval.return_value = {"allowed": True}

                with pytest.raises(ValueError, match="contract invalid"):
                    execute_skill("invalid.skill", {})

    def test_disabled_skill_raises_error(self):
        """测试禁用的 Skill 抛出错误"""
        with patch.object(task_store, "get_skill") as mock_get:
            mock_get.return_value = {
                "code": "disabled.skill",
                "enabled": False,  # 已禁用
                "permissions": [],
            }

            with pytest.raises(PermissionError, match="disabled"):
                execute_skill("disabled.skill", {})

    def test_nonexistent_skill_raises_error(self):
        """测试不存在的 Skill 抛出错误"""
        with patch.object(task_store, "get_skill") as mock_get:
            mock_get.return_value = None  # Skill 不存在

            with pytest.raises(KeyError, match="not found"):
                execute_skill("nonexistent.skill", {})


class TestSkillDependencyCheck:
    """Skill 依赖检测测试"""

    def test_missing_dependencies_raises_error(self):
        """测试缺少依赖应抛出错误"""
        with patch.object(task_store, "get_skill") as mock_get:
            mock_get.return_value = {
                "code": "dep.skill",
                "enabled": True,
                "permissions": [],
                "input_schema": {"type": "object"},
                "output_schema": {"type": "object"},
                "execution_type": "agent",
                "dependencies": {
                    "mcp_tools": ["filesystem.read_file"],
                    "rag_collections": ["project_docs"],
                },
            }
            with patch.object(task_store, "get_skill_approval") as mock_approval:
                mock_approval.return_value = {"allowed": True}

                # Mock 依赖检查失败
                with patch("app.skills.executor._missing_dependencies") as mock_missing:
                    mock_missing.return_value = ["mcp_tools:filesystem.read_file", "rag_collections:project_docs"]

                    with pytest.raises(RuntimeError, match="dependencies are missing"):
                        execute_skill("dep.skill", {})


class TestSkillExecution:
    """Skill 执行测试"""

    def test_execution_logs_are_saved(self):
        """测试执行日志被正确保存"""
        with patch.object(task_store, "get_skill") as mock_get:
            mock_get.return_value = {
                "code": "log.skill",
                "enabled": True,
                "permissions": [],
                "input_schema": {"type": "object"},
                "output_schema": {"type": "object"},
                "execution_type": "agent",
            }
            with patch.object(task_store, "get_skill_approval") as mock_approval:
                mock_approval.return_value = {"allowed": True}

                with patch.object(task_store, "save_skill_execution_log") as mock_save_log:
                    from app.skills.registry import skill_registry
                    with patch.object(skill_registry, "execute") as mock_execute:
                        mock_execute.return_value = {"output": "test"}

                        result = execute_skill("log.skill", {"input": "data"}, task_id="task_123")

                        # 验证日志被保存
                        mock_save_log.assert_called_once()
                        log_call = mock_save_log.call_args[0][0]
                        assert log_call["skill_code"] == "log.skill"
                        assert log_call["task_id"] == "task_123"
                        assert log_call["status"] == "completed"
                        assert log_call["input"] == {"input": "data"}

    def test_execution_failure_is_logged(self):
        """测试执行失败被记录"""
        with patch.object(task_store, "get_skill") as mock_get:
            mock_get.return_value = {
                "code": "fail.skill",
                "enabled": True,
                "permissions": [],
                "input_schema": {"type": "object"},
                "output_schema": {"type": "object"},
                "execution_type": "agent",
            }
            with patch.object(task_store, "get_skill_approval") as mock_approval:
                mock_approval.return_value = {"allowed": True}

                with patch.object(task_store, "save_skill_execution_log") as mock_save_log:
                    from app.skills.registry import skill_registry
                    with patch.object(skill_registry, "execute") as mock_execute:
                        mock_execute.side_effect = RuntimeError("Execution failed")

                        # execute_skill 在失败时重新抛出异常，而不是返回失败状态字典
                        with pytest.raises(RuntimeError, match="Execution failed"):
                            execute_skill("fail.skill", {})

                        # 验证失败仍被记录
                        mock_save_log.assert_called_once()
                        log_call = mock_save_log.call_args[0][0]
                        assert log_call["status"] == "failed"
                        assert "Execution failed" in log_call["error_message"]

    def test_default_input_is_merged(self):
        """测试默认输入被合并"""
        with patch.object(task_store, "get_skill") as mock_get:
            mock_get.return_value = {
                "code": "default.skill",
                "enabled": True,
                "permissions": [],
                "input_schema": {"type": "object"},
                "output_schema": {"type": "object"},
                "execution_type": "agent",
                "default_input": {"default_key": "default_value", "override_me": "default"},
            }
            with patch.object(task_store, "get_skill_approval") as mock_approval:
                mock_approval.return_value = {"allowed": True}

                with patch.object(task_store, "save_skill_execution_log"):
                    from app.skills.registry import skill_registry
                    with patch.object(skill_registry, "execute") as mock_execute:
                        mock_execute.return_value = {"result": "ok"}

                        execute_skill(
                            "default.skill",
                            {"user_key": "user_value", "override_me": "user_override"}
                        )

                        # 验证合并后的输入（execute 签名为 (skill_code, context, payload)，payload 在索引 2）
                        actual_input = mock_execute.call_args[0][2]
                        assert actual_input["default_key"] == "default_value"
                        assert actual_input["user_key"] == "user_value"
                        assert actual_input["override_me"] == "user_override"  # 用户输入覆盖默认


class TestBuiltinSkillsSeeding:
    """内置 Skill 种子数据测试"""

    def test_ensure_builtin_skills_seeded(self):
        """测试内置 Skill 被正确注册"""
        with patch.object(task_store, "seed_builtin_skills") as mock_seed:
            ensure_builtin_skills_seeded()
            mock_seed.assert_called_once()

            # seed_builtin_skills(plugin, skills) 接收两个独立参数：
            # 第一个是插件元数据（plugin_id/name/version...），第二个才是技能列表
            call_args = mock_seed.call_args[0]
            plugin_data, skills = call_args[0], call_args[1]
            assert "plugin_id" in plugin_data
            assert isinstance(skills, list)
