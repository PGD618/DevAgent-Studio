"""
Harness Runtime 单元测试
测试任务生命周期管理、事件记录、状态转换等核心逻辑
"""

import pytest
from unittest.mock import MagicMock, patch, ANY
from app.harness.runtime import HarnessRuntime, harness_runtime
from app.harness.context import AgentExecutionContext
from app.persistence.sqlite_store import task_store


class TestContextCreation:
    """任务上下文创建测试"""

    def test_create_context_with_minimal_params(self):
        """测试最小参数创建上下文"""
        with patch.object(task_store, "create_task"):
            with patch.object(task_store, "append_event"):
                runtime = HarnessRuntime()
                context = runtime.create_context(goal="测试目标")

                assert context.goal == "测试目标"
                assert context.project_path is None
                assert context.variables == {}
                assert context.task_id is not None
                assert context.status == "created"

    def test_create_context_with_full_params(self):
        """测试完整参数创建上下文"""
        with patch.object(task_store, "create_task"):
            with patch.object(task_store, "append_event"):
                runtime = HarnessRuntime()
                context = runtime.create_context(
                    goal="完整测试",
                    project_path="/test/path",
                    variables={"key1": "value1", "key2": 123}
                )

                assert context.goal == "完整测试"
                assert context.project_path == "/test/path"
                assert context.variables == {"key1": "value1", "key2": 123}

    def test_context_creation_persists_task(self):
        """测试上下文创建会持久化任务"""
        with patch.object(task_store, "create_task") as mock_create:
            with patch.object(task_store, "append_event"):
                runtime = HarnessRuntime()
                context = runtime.create_context(goal="持久化测试", project_path="/path")

                mock_create.assert_called_once()
                call_args = mock_create.call_args[0]
                assert call_args[0] == context.task_id
                assert call_args[1] == "持久化测试"
                assert call_args[2] == "/path"
                assert call_args[3] == "created"

    def test_context_creation_emits_event(self):
        """测试上下文创建会发出事件"""
        with patch.object(task_store, "create_task"):
            with patch.object(task_store, "append_event") as mock_append:
                runtime = HarnessRuntime()
                context = runtime.create_context(goal="事件测试")

                mock_append.assert_called_once()
                event = mock_append.call_args[0][0]
                assert event["task_id"] == context.task_id
                assert event["type"] == "task"
                assert event["status"] == "created"


class TestGraphExecution:
    """工作流图执行测试"""

    def test_run_graph_updates_status_to_running(self):
        """测试运行图更新状态为 running"""
        with patch.object(task_store, "create_task"):
            with patch.object(task_store, "update_task") as mock_update:
                with patch.object(task_store, "append_event"):
                    with patch.object(task_store, "save_artifact"):
                        runtime = HarnessRuntime()
                        context = runtime.create_context(goal="测试")

                        def mock_graph_runner(state):
                            return {"events": [], "final_report": "报告"}

                        runtime.run_graph(context, mock_graph_runner, {})

                        # 验证状态更新被调用
                        update_calls = [call[0] for call in mock_update.call_args_list]
                        assert any("running" in str(call) for call in update_calls)

    def test_run_graph_saves_artifacts(self):
        """测试运行图保存产物"""
        with patch.object(task_store, "create_task"):
            with patch.object(task_store, "update_task"):
                with patch.object(task_store, "append_event"):
                    with patch.object(task_store, "save_artifact") as mock_save:
                        runtime = HarnessRuntime()
                        context = runtime.create_context(goal="测试")

                        def mock_graph_runner(state):
                            return {
                                "events": [],
                                "final_report": "测试报告",
                                "result": {"data": "test"}
                            }

                        result = runtime.run_graph(context, mock_graph_runner, {})

                        # 验证 graph_result 被保存
                        assert mock_save.called
                        artifact_calls = [call[0] for call in mock_save.call_args_list]
                        assert any("graph_result" in str(call) for call in artifact_calls)

    def test_run_graph_handles_exception(self):
        """测试运行图处理异常"""
        with patch.object(task_store, "create_task"):
            with patch.object(task_store, "update_task") as mock_update:
                with patch.object(task_store, "append_event") as mock_append:
                    runtime = HarnessRuntime()
                    context = runtime.create_context(goal="测试")

                    def failing_graph_runner(state):
                        raise RuntimeError("图执行失败")

                    with pytest.raises(RuntimeError, match="图执行失败"):
                        runtime.run_graph(context, failing_graph_runner, {})

                    # 验证状态更新为 failed
                    update_calls = [call[0] for call in mock_update.call_args_list]
                    assert any("failed" in str(call) for call in update_calls)

    def test_run_graph_returns_task_result(self):
        """测试运行图返回完整任务结果"""
        with patch.object(task_store, "create_task"):
            with patch.object(task_store, "update_task"):
                with patch.object(task_store, "append_event"):
                    with patch.object(task_store, "save_artifact"):
                        runtime = HarnessRuntime()
                        context = runtime.create_context(goal="测试")

                        def mock_graph_runner(state):
                            return {
                                "events": [{"type": "agent", "content": "测试事件"}],
                                "final_report": "最终报告",
                                "result": {"output": "结果"}
                            }

                        result = runtime.run_graph(context, mock_graph_runner, {})

                        assert result["task_id"] == context.task_id
                        assert result["status"] in ["completed", "waiting_review"]
                        assert "events" in result
                        assert "result" in result


class TestStatusResolution:
    """任务状态解析测试"""

    def test_status_resolved_to_waiting_review(self):
        """测试状态解析为 waiting_review"""
        with patch.object(task_store, "create_task"):
            with patch.object(task_store, "update_task"):
                with patch.object(task_store, "append_event"):
                    with patch.object(task_store, "save_artifact"):
                        runtime = HarnessRuntime()
                        context = runtime.create_context(goal="测试")

                        def mock_graph_runner(state):
                            return {
                                "events": [],
                                "result": {
                                    "human_review_required": True,
                                    "human_review_packet": {"node_id": "review_node"},
                                    "final_report": "等待审核"
                                }
                            }

                        result = runtime.run_graph(context, mock_graph_runner, {})

                        assert result["status"] == "waiting_review"

    def test_status_resolved_to_completed(self):
        """测试状态解析为 completed"""
        with patch.object(task_store, "create_task"):
            with patch.object(task_store, "update_task"):
                with patch.object(task_store, "append_event"):
                    with patch.object(task_store, "save_artifact"):
                        runtime = HarnessRuntime()
                        context = runtime.create_context(goal="测试")

                        def mock_graph_runner(state):
                            return {
                                "events": [],
                                "result": {
                                    "final_report": "任务完成"
                                }
                            }

                        result = runtime.run_graph(context, mock_graph_runner, {})

                        assert result["status"] == "completed"


class TestEventPropagation:
    """事件传播测试"""

    def test_graph_events_are_appended_to_store(self):
        """测试图事件被追加到存储"""
        with patch.object(task_store, "create_task"):
            with patch.object(task_store, "update_task"):
                with patch.object(task_store, "append_event") as mock_append:
                    with patch.object(task_store, "save_artifact"):
                        runtime = HarnessRuntime()
                        context = runtime.create_context(goal="测试")

                        graph_events = [
                            {"task_id": context.task_id, "type": "agent", "content": "事件1"},
                            {"task_id": context.task_id, "type": "llm", "content": "事件2"},
                        ]

                        def mock_graph_runner(state):
                            return {
                                "events": graph_events,
                                "final_report": "报告"
                            }

                        runtime.run_graph(context, mock_graph_runner, {})

                        # 验证图事件被追加（除了初始创建事件和完成事件）
                        append_calls = mock_append.call_args_list
                        assert len(append_calls) >= 2 + len(graph_events)


class TestResumeCheckpoint:
    """断点续传测试"""

    def test_resume_checkpoint_is_saved(self):
        """测试断点续传检查点被保存"""
        with patch.object(task_store, "create_task"):
            with patch.object(task_store, "update_task"):
                with patch.object(task_store, "append_event"):
                    with patch.object(task_store, "save_artifact") as mock_save:
                        runtime = HarnessRuntime()
                        context = runtime.create_context(goal="测试")

                        def mock_graph_runner(state):
                            return {
                                "events": [],
                                "result": {
                                    "resume_checkpoint": {
                                        "workflow_name": "test_workflow",
                                        "paused_node_id": "review_node",
                                        "state": {"key": "value"}
                                    },
                                    "final_report": "已暂停"
                                }
                            }

                        runtime.run_graph(context, mock_graph_runner, {})

                        # 验证 workflow_checkpoint 被保存
                        artifact_calls = mock_save.call_args_list
                        checkpoint_saved = any(
                            "workflow_checkpoint" in str(call[0]) for call in artifact_calls
                        )
                        assert checkpoint_saved