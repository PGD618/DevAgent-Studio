"""
Collaboration Runner 单元测试
测试多 Agent 协作流程编排、事件记录、输出格式化等逻辑
"""

import pytest
from unittest.mock import MagicMock, patch
from app.graphs.collaboration_runner import (
    run_collaboration_task,
    build_collaboration_mermaid,
    COLLABORATION_NODES,
)


class TestCollaborationTaskExecution:
    """协作任务执行测试"""

    def test_run_collaboration_with_minimal_input(self):
        """测试最小输入执行协作任务"""
        with patch("app.graphs.collaboration_runner.collaboration_graph") as mock_graph:
            mock_graph.invoke.return_value = {
                "result": {
                    "plan": ["步骤1", "步骤2"],
                    "worker_results": [],
                    "supervisor_notes": [],
                    "final_report": "协作完成",
                    "events": [],
                }
            }

            result = run_collaboration_task({"goal": "测试目标"})

            assert result["final_report"] == "协作完成"
            assert "workflow_name" in result["result"]
            assert result["result"]["workflow_name"] == "multi_agent_collaboration"

    def test_run_collaboration_with_full_input(self):
        """测试完整输入执行协作任务"""
        input_state = {
            "goal": "完整测试",
            "project_path": "/test/path",
            "max_files": 100,
            "require_human_review": True,
            "task_id": "task_123",
        }

        with patch("app.graphs.collaboration_runner.collaboration_graph") as mock_graph:
            mock_graph.invoke.return_value = {
                "result": {
                    "plan": ["步骤1"],
                    "worker_results": [],
                    "supervisor_notes": [],
                    "final_report": "报告",
                    "events": [],
                }
            }

            result = run_collaboration_task(input_state)

            # 验证输入被正确传递
            call_args = mock_graph.invoke.call_args[0][0]
            assert call_args["goal"] == "完整测试"
            assert call_args["project_path"] == "/test/path"
            assert call_args["max_files"] == 100
            assert call_args["require_human_review"] is True
            assert call_args["task_id"] == "task_123"


class TestAgentOutputsFormatting:
    """Agent 输出格式化测试"""

    def test_planner_output_is_formatted(self):
        """测试 Planner 输出格式化"""
        with patch("app.graphs.collaboration_runner.collaboration_graph") as mock_graph:
            mock_graph.invoke.return_value = {
                "result": {
                    "plan": ["任务1", "任务2", "任务3"],
                    "worker_results": [],
                    "supervisor_notes": [],
                    "final_report": "报告",
                    "events": [],
                }
            }

            result = run_collaboration_task({"goal": "测试"})

            agent_outputs = result["result"]["agent_outputs"]
            planner_output = next((o for o in agent_outputs if o["node_id"] == "planner"), None)
            assert planner_output is not None
            assert "- 任务1" in planner_output["content"]
            assert "- 任务2" in planner_output["content"]

    def test_worker_results_are_formatted(self):
        """测试 Worker 结果格式化"""
        with patch("app.graphs.collaboration_runner.collaboration_graph") as mock_graph:
            mock_graph.invoke.return_value = {
                "result": {
                    "plan": [],
                    "worker_results": [
                        {"agent": "project_analyzer", "result": "项目分析结果"},
                        {"agent": "code_reviewer", "result": "代码审查结果"},
                    ],
                    "supervisor_notes": [],
                    "final_report": "报告",
                    "events": [],
                }
            }

            result = run_collaboration_task({"goal": "测试"})

            agent_outputs = result["result"]["agent_outputs"]
            assert len(agent_outputs) >= 2
            analyzer_output = next((o for o in agent_outputs if o["node_id"] == "project_analyzer"), None)
            assert analyzer_output is not None
            assert analyzer_output["content"] == "项目分析结果"


class TestMermaidDiagram:
    """Mermaid 流程图生成测试"""

    def test_build_collaboration_mermaid(self):
        """测试构建协作流程图"""
        mermaid = build_collaboration_mermaid()

        assert "flowchart LR" in mermaid
        assert "planner[Planner]" in mermaid
        assert "project_analyzer[Project Analyzer]" in mermaid
        assert "code_reviewer[Code Reviewer]" in mermaid
        assert "reporter[Reporter]" in mermaid
        # 验证箭头连接
        assert "planner --> project_analyzer" in mermaid

    def test_mermaid_includes_all_nodes(self):
        """测试 Mermaid 包含所有协作节点"""
        mermaid = build_collaboration_mermaid()

        for node_id, label in COLLABORATION_NODES:
            assert node_id in mermaid
            assert label in mermaid


class TestSuggestionsAndGovernance:
    """建议与治理信息测试"""

    def test_suggestions_are_collected(self):
        """测试建议被收集"""
        with patch("app.graphs.collaboration_runner.collaboration_graph") as mock_graph:
            mock_graph.invoke.return_value = {
                "result": {
                    "plan": [],
                    "worker_results": [],
                    "supervisor_notes": ["注意事项1", "注意事项2"],
                    "final_report": "报告",
                    "events": [],
                    "review_required": True,
                    "risk_level": "medium",
                }
            }

            result = run_collaboration_task({"goal": "测试"})

            # 验证治理信息被包含
            assert "risk_level" in result["result"]
            assert "review_required" in result["result"]

    def test_empty_suggestions_returns_empty_list(self):
        """测试无建议时返回空列表"""
        with patch("app.graphs.collaboration_runner.collaboration_graph") as mock_graph:
            mock_graph.invoke.return_value = {
                "result": {
                    "plan": [],
                    "worker_results": [],
                    "supervisor_notes": [],
                    "final_report": "报告",
                    "events": [],
                }
            }

            result = run_collaboration_task({"goal": "测试"})

            assert "suggestions" in result["result"]
            assert isinstance(result["result"]["suggestions"], list)


class TestEventEnrichment:
    """事件增强测试"""

    def test_events_are_enriched(self):
        """测试事件被增强"""
        with patch("app.graphs.collaboration_runner.collaboration_graph") as mock_graph:
            mock_graph.invoke.return_value = {
                "result": {
                    "plan": [],
                    "worker_results": [],
                    "supervisor_notes": [],
                    "final_report": "报告",
                    "events": [
                        {"type": "agent", "agent": "planner", "content": "规划完成"},
                        {"type": "agent", "agent": "project_analyzer", "content": "分析完成"},
                    ],
                }
            }

            result = run_collaboration_task({"goal": "测试"})

            workflow_events = result["result"]["workflow_events"]
            assert len(workflow_events) == 2
            assert workflow_events[0]["type"] == "agent"
            assert workflow_events[0]["agent"] == "planner"


class TestInputNormalization:
    """输入规范化测试"""

    def test_goal_from_input_text(self):
        """测试从 input_text 提取 goal"""
        with patch("app.graphs.collaboration_runner.collaboration_graph") as mock_graph:
            mock_graph.invoke.return_value = {
                "result": {
                    "plan": [],
                    "worker_results": [],
                    "supervisor_notes": [],
                    "final_report": "报告",
                    "events": [],
                }
            }

            # 只传 input_text，不传 goal
            result = run_collaboration_task({"input_text": "从文本提取的目标"})

            call_args = mock_graph.invoke.call_args[0][0]
            assert call_args["goal"] == "从文本提取的目标"

    def test_default_max_files(self):
        """测试默认 max_files"""
        with patch("app.graphs.collaboration_runner.collaboration_graph") as mock_graph:
            mock_graph.invoke.return_value = {
                "result": {
                    "plan": [],
                    "worker_results": [],
                    "supervisor_notes": [],
                    "final_report": "报告",
                    "events": [],
                }
            }

            result = run_collaboration_task({"goal": "测试"})

            call_args = mock_graph.invoke.call_args[0][0]
            assert call_args["max_files"] == 500  # 默认值
