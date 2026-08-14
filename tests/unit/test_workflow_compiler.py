"""
Workflow Compiler 单元测试
测试可视化工作流编译为 LangGraph 的核心逻辑
"""

import pytest
from app.graphs.workflow_compiler import (
    compile_workflow_graph,
    validate_workflow_definition,
    SUPPORTED_NODE_TYPES,
    SUPPORTED_EDGE_CONDITIONS,
)


class TestWorkflowValidation:
    """工作流定义校验测试"""

    def test_valid_simple_workflow(self):
        """测试简单有效的工作流（使用正确的 source/target 字段）"""
        nodes = [
            {"id": "start", "type": "planner", "config": {}},
            {"id": "end", "type": "reporter", "config": {}},
        ]
        edges = [{"source": "start", "target": "end", "condition": "always"}]

        result = validate_workflow_definition(nodes, edges)
        assert result["valid"] is True, f"Errors: {result['errors']}"
        assert len(result["errors"]) == 0

    def test_auto_connect_nodes_without_edges(self):
        """测试没有显式边时自动连接节点"""
        nodes = [
            {"id": "step1", "type": "planner", "config": {}},
            {"id": "step2", "type": "agent", "config": {}},
            {"id": "step3", "type": "reporter", "config": {}},
        ]
        # 不传 edges，应该自动按顺序连接
        edges = None

        result = validate_workflow_definition(nodes, edges)
        assert result["valid"] is True

    def test_invalid_node_type(self):
        """测试不支持的节点类型"""
        nodes = [{"id": "node1", "type": "unknown_type", "config": {}}]
        edges = []

        result = validate_workflow_definition(nodes, edges)
        assert result["valid"] is False
        assert any("unknown_type" in err for err in result["errors"])

    def test_duplicate_node_ids(self):
        """测试重复的节点 ID"""
        nodes = [
            {"id": "node1", "type": "agent", "config": {}},
            {"id": "node1", "type": "agent", "config": {}},  # 重复
        ]
        edges = []

        result = validate_workflow_definition(nodes, edges)
        assert result["valid"] is False
        assert any("unique" in err.lower() for err in result["errors"])

    def test_empty_nodes_falls_back_to_default_workflow(self):
        """测试空节点列表会回退到内置默认工作流（_normalize_nodes 对空列表使用 `nodes or [默认...]`）"""
        nodes = []
        edges = []

        result = validate_workflow_definition(nodes, edges)
        assert result["valid"] is True
        assert result["node_count"] == 4  # plan/analyze/review/report 默认节点

    def test_edge_references_nonexistent_node(self):
        """测试边引用不存在的节点"""
        nodes = [{"id": "node1", "type": "agent", "config": {}}]
        edges = [{"source": "node1", "target": "nonexistent", "condition": "always"}]

        result = validate_workflow_definition(nodes, edges)
        assert result["valid"] is False
        assert any("does not exist" in err for err in result["errors"])

    def test_invalid_retry_count_produces_warning_not_error(self):
        """测试超范围的重试次数只产生 warning，不影响 valid（校验逻辑里 retry_count 只进 warnings 列表）"""
        nodes = [
            {"id": "node1", "type": "agent", "config": {"retry_count": 10}}  # 超过最大值 5
        ]
        edges = []

        result = validate_workflow_definition(nodes, edges)
        assert result["valid"] is True
        assert any("retry" in warning.lower() for warning in result["warnings"])

    def test_unsupported_edge_condition(self):
        """测试不支持的边条件类型"""
        nodes = [
            {"id": "a", "type": "agent", "config": {}},
            {"id": "b", "type": "agent", "config": {}},
        ]
        edges = [{"source": "a", "target": "b", "condition": "invalid_condition"}]

        result = validate_workflow_definition(nodes, edges)
        assert result["valid"] is False
        assert any("condition" in err.lower() for err in result["errors"])

    def test_circular_dependency_warning(self):
        """测试循环依赖会产生警告"""
        nodes = [
            {"id": "a", "type": "agent", "config": {}},
            {"id": "b", "type": "agent", "config": {}},
        ]
        edges = [
            {"source": "a", "target": "b", "condition": "always"},
            {"source": "b", "target": "a", "condition": "always"},  # 形成环
        ]

        result = validate_workflow_definition(nodes, edges)
        # 可能有 warning 但不一定 invalid（取决于条件分支是否能终止）
        warnings = result.get("warnings", [])
        assert any("cycle" in w.lower() for w in warnings)


class TestWorkflowCompilation:
    """工作流编译测试"""

    def test_compile_single_node_workflow(self):
        """测试单节点工作流编译"""
        nodes = [{"id": "planner", "type": "planner", "config": {}}]
        edges = []

        graph = compile_workflow_graph("single_node", nodes, edges)
        assert graph is not None

    def test_compile_linear_workflow(self):
        """测试线性工作流编译"""
        nodes = [
            {"id": "step1", "type": "planner", "config": {}},
            {"id": "step2", "type": "agent", "config": {"agent": "project_analyzer"}},
            {"id": "step3", "type": "reporter", "config": {}},
        ]
        edges = [
            {"source": "step1", "target": "step2", "condition": "always"},
            {"source": "step2", "target": "step3", "condition": "always"},
        ]

        graph = compile_workflow_graph("linear", nodes, edges)
        assert graph is not None

    def test_compile_with_conditional_branch(self):
        """测试带条件分支的工作流编译"""
        nodes = [
            {"id": "start", "type": "planner", "config": {}},
            {"id": "path_a", "type": "agent", "config": {}},
            {"id": "path_b", "type": "agent", "config": {}},
            {"id": "end", "type": "reporter", "config": {}},
        ]
        edges = [
            {"source": "start", "target": "path_a", "condition": "truthy_output"},
            {"source": "start", "target": "path_b", "condition": "always"},
            {"source": "path_a", "target": "end", "condition": "always"},
            {"source": "path_b", "target": "end", "condition": "always"},
        ]

        graph = compile_workflow_graph("conditional", nodes, edges)
        assert graph is not None

    def test_compile_with_custom_entry_node(self):
        """测试自定义入口节点"""
        nodes = [
            {"id": "middle", "type": "agent", "config": {}},
            {"id": "start", "type": "planner", "config": {}},
        ]
        edges = [{"source": "start", "target": "middle", "condition": "always"}]

        graph = compile_workflow_graph("custom_entry", nodes, edges, entry_node_id="start")
        assert graph is not None

    def test_compile_fails_with_invalid_workflow(self):
        """测试无效工作流编译失败"""
        nodes = [{"id": "node1", "type": "invalid_type", "config": {}}]
        edges = []

        with pytest.raises(ValueError, match="Unsupported node type"):
            compile_workflow_graph("invalid", nodes, edges)

    def test_missing_entry_node_raises_error(self):
        """测试入口节点不存在时抛出错误"""
        nodes = [{"id": "node1", "type": "agent", "config": {}}]
        edges = []

        with pytest.raises(ValueError, match="entry node.*does not exist"):
            compile_workflow_graph("missing_entry", nodes, edges, entry_node_id="nonexistent")


class TestSupportedTypes:
    """测试支持的节点和边类型常量"""

    def test_supported_node_types(self):
        """验证支持的节点类型集合"""
        assert "planner" in SUPPORTED_NODE_TYPES
        assert "agent" in SUPPORTED_NODE_TYPES
        assert "rag" in SUPPORTED_NODE_TYPES
        assert "mcp_tool" in SUPPORTED_NODE_TYPES
        assert "skill" in SUPPORTED_NODE_TYPES
        assert "supervisor" in SUPPORTED_NODE_TYPES
        assert "human_review" in SUPPORTED_NODE_TYPES
        assert "reporter" in SUPPORTED_NODE_TYPES

    def test_supported_edge_conditions(self):
        """验证支持的边条件类型集合"""
        assert "always" in SUPPORTED_EDGE_CONDITIONS
        assert "on_status" in SUPPORTED_EDGE_CONDITIONS
        assert "contains" in SUPPORTED_EDGE_CONDITIONS
        assert "truthy_output" in SUPPORTED_EDGE_CONDITIONS
