"""
MCP Provider 单元测试
测试 Local MCP 适配器的文件系统操作、安全检查等核心逻辑
"""

import pytest
from pathlib import Path
from unittest.mock import MagicMock, patch
from app.providers.mcp_provider import LocalMCPProvider, MCPProvider, mcp_provider


class TestLocalMCPProviderSafety:
    """Local MCP Provider 安全性测试"""

    def test_root_path_must_be_directory(self):
        """测试根路径必须是目录"""
        provider = LocalMCPProvider()

        with pytest.raises(NotADirectoryError):
            provider._root("/nonexistent/path")

    def test_safe_target_rejects_path_traversal(self, tmp_path):
        """测试拒绝路径遍历攻击"""
        provider = LocalMCPProvider()
        root = tmp_path / "root"
        root.mkdir()

        # 尝试访问父目录
        with pytest.raises(PermissionError, match="outside root path"):
            provider._safe_target(str(root), "../..")

    def test_safe_target_allows_subdirectories(self, tmp_path):
        """测试允许访问子目录"""
        provider = LocalMCPProvider()
        root = tmp_path / "root"
        subdir = root / "subdir"
        subdir.mkdir(parents=True)

        # 应该允许访问子目录
        root_path, target = provider._safe_target(str(root), "subdir")
        assert target == subdir

    def test_safe_target_allows_root_itself(self, tmp_path):
        """测试允许访问根目录本身"""
        provider = LocalMCPProvider()
        root = tmp_path / "root"
        root.mkdir()

        root_path, target = provider._safe_target(str(root), ".")
        assert target == root


class TestLocalMCPListFiles:
    """列出文件测试"""

    def test_list_files_returns_all_files(self, tmp_path):
        """测试列出所有文件"""
        provider = LocalMCPProvider()
        root = tmp_path / "project"
        root.mkdir()
        (root / "file1.txt").write_text("content1")
        (root / "file2.py").write_text("content2")
        subdir = root / "subdir"
        subdir.mkdir()
        (subdir / "file3.md").write_text("content3")

        result = provider.list_files(str(root), max_files=100)

        assert result["provider"] == "local"
        assert len(result["files"]) == 3
        assert "file1.txt" in result["files"]
        assert "file2.py" in result["files"]
        assert "subdir/file3.md" in result["files"]

    def test_list_files_respects_max_limit(self, tmp_path):
        """测试遵守最大文件数限制"""
        provider = LocalMCPProvider()
        root = tmp_path / "project"
        root.mkdir()

        # 创建 10 个文件
        for i in range(10):
            (root / f"file{i}.txt").write_text(f"content{i}")

        result = provider.list_files(str(root), max_files=5)

        assert len(result["files"]) == 5

    def test_list_files_excludes_common_dirs(self, tmp_path):
        """测试排除常见目录（node_modules, .git 等）"""
        provider = LocalMCPProvider()
        root = tmp_path / "project"
        root.mkdir()
        (root / "src.txt").write_text("source")

        # 创建应该被排除的目录
        node_modules = root / "node_modules"
        node_modules.mkdir()
        (node_modules / "package.json").write_text("{}")

        result = provider.list_files(str(root), max_files=100)

        # node_modules 里的文件不应被包含
        assert len(result["files"]) == 1
        assert result["files"][0] == "src.txt"


class TestLocalMCPReadFile:
    """读取文件测试"""

    def test_read_file_returns_content(self, tmp_path):
        """测试读取文件内容"""
        provider = LocalMCPProvider()
        root = tmp_path / "project"
        root.mkdir()
        test_file = root / "test.txt"
        test_file.write_text("Hello, World!")

        result = provider.read_file(str(root), "test.txt")

        assert result["content"] == "Hello, World!"
        assert result["path"] == "test.txt"

    def test_read_file_respects_max_chars(self, tmp_path):
        """测试遵守最大字符数限制"""
        provider = LocalMCPProvider()
        root = tmp_path / "project"
        root.mkdir()
        test_file = root / "large.txt"
        test_file.write_text("A" * 10000)

        result = provider.read_file(str(root), "large.txt", max_chars=100)

        assert len(result["content"]) == 100

    def test_read_file_raises_on_nonexistent(self, tmp_path):
        """测试读取不存在的文件抛出错误"""
        provider = LocalMCPProvider()
        root = tmp_path / "project"
        root.mkdir()

        with pytest.raises(FileNotFoundError):
            provider.read_file(str(root), "nonexistent.txt")

    def test_read_file_rejects_path_traversal(self, tmp_path):
        """测试拒绝路径遍历"""
        provider = LocalMCPProvider()
        root = tmp_path / "project"
        root.mkdir()

        with pytest.raises(PermissionError, match="outside root path"):
            provider.read_file(str(root), "../../etc/passwd")


class TestLocalMCPListDirectory:
    """列出目录测试"""

    def test_list_directory_returns_entries(self, tmp_path):
        """测试列出目录条目"""
        provider = LocalMCPProvider()
        root = tmp_path / "project"
        root.mkdir()
        (root / "file.txt").write_text("content")
        (root / "subdir").mkdir()

        result = provider.list_directory(str(root), ".")

        assert len(result["entries"]) == 2
        entries_by_name = {e["name"]: e for e in result["entries"]}
        assert entries_by_name["file.txt"]["type"] == "file"
        assert entries_by_name["subdir"]["type"] == "directory"

    def test_list_directory_sorts_dirs_first(self, tmp_path):
        """测试目录排在文件前面"""
        provider = LocalMCPProvider()
        root = tmp_path / "project"
        root.mkdir()
        (root / "z_file.txt").write_text("content")
        (root / "a_dir").mkdir()

        result = provider.list_directory(str(root), ".")

        # 目录应排在前面
        assert result["entries"][0]["name"] == "a_dir"
        assert result["entries"][0]["type"] == "directory"

    def test_list_directory_respects_limit(self, tmp_path):
        """测试遵守条目限制"""
        provider = LocalMCPProvider()
        root = tmp_path / "project"
        root.mkdir()

        for i in range(10):
            (root / f"file{i}.txt").write_text("content")

        result = provider.list_directory(str(root), ".", limit=5)

        assert len(result["entries"]) == 5

    def test_list_directory_excludes_common_dirs(self, tmp_path):
        """测试排除常见目录"""
        provider = LocalMCPProvider()
        root = tmp_path / "project"
        root.mkdir()
        (root / "src").mkdir()
        (root / "node_modules").mkdir()

        result = provider.list_directory(str(root), ".")

        # node_modules 应被排除
        names = [e["name"] for e in result["entries"]]
        assert "src" in names
        assert "node_modules" not in names


class TestLocalMCPDirectoryTree:
    """目录树测试"""

    def test_directory_tree_returns_nested_structure(self, tmp_path):
        """测试返回嵌套结构"""
        provider = LocalMCPProvider()
        root = tmp_path / "project"
        root.mkdir()
        (root / "file1.txt").write_text("content")
        subdir = root / "subdir"
        subdir.mkdir()
        (subdir / "file2.txt").write_text("content")

        result = provider.directory_tree(str(root), ".", max_depth=2)

        assert len(result["tree"]) >= 2
        paths = [item["path"] for item in result["tree"]]
        assert "file1.txt" in paths
        assert "subdir/file2.txt" in paths

    def test_directory_tree_respects_max_depth(self, tmp_path):
        """测试遵守最大深度限制"""
        provider = LocalMCPProvider()
        root = tmp_path / "project"
        root.mkdir()
        level1 = root / "level1"
        level1.mkdir()
        level2 = level1 / "level2"
        level2.mkdir()
        level3 = level2 / "level3"
        level3.mkdir()
        (level3 / "deep.txt").write_text("content")

        result = provider.directory_tree(str(root), ".", max_depth=2)

        # 深度 3 的文件不应被包含
        paths = [item["path"] for item in result["tree"]]
        assert "level1/level2/level3/deep.txt" not in paths

    def test_directory_tree_includes_depth_info(self, tmp_path):
        """测试包含深度信息"""
        provider = LocalMCPProvider()
        root = tmp_path / "project"
        root.mkdir()
        (root / "file.txt").write_text("content")
        subdir = root / "subdir"
        subdir.mkdir()
        (subdir / "nested.txt").write_text("content")

        result = provider.directory_tree(str(root), ".", max_depth=3)

        for item in result["tree"]:
            assert "depth" in item
            assert item["depth"] >= 1


class TestLocalMCPSearchFiles:
    """搜索文件测试"""

    def test_search_files_by_name_pattern(self, tmp_path):
        """测试按名称模式搜索"""
        provider = LocalMCPProvider()
        root = tmp_path / "project"
        root.mkdir()
        (root / "test.py").write_text("content")
        (root / "test.txt").write_text("content")
        (root / "main.py").write_text("content")

        result = provider.search_files(str(root), "test", ".")

        matches = result["matches"]
        paths = [m["path"] for m in matches]
        assert "test.py" in paths
        assert "test.txt" in paths
        assert "main.py" not in paths

    def test_search_files_respects_limit(self, tmp_path):
        """测试遵守结果限制"""
        provider = LocalMCPProvider()
        root = tmp_path / "project"
        root.mkdir()

        for i in range(10):
            (root / f"match{i}.txt").write_text("content")

        result = provider.search_files(str(root), "match", ".", limit=5)

        assert len(result["matches"]) == 5


class TestMCPProviderMode:
    """MCP Provider 模式切换测试"""

    def test_mcp_provider_defaults_to_local(self):
        """测试默认使用 local 模式"""
        with patch.dict("os.environ", {"DEV_AGENT_MCP_PROVIDER": "local"}, clear=True):
            provider = MCPProvider()
            assert provider.provider_kind == "local"

    def test_mcp_provider_can_switch_to_mcp_mode(self):
        """测试可以切换到 mcp 模式"""
        with patch.dict("os.environ", {"DEV_AGENT_MCP_PROVIDER": "mcp"}, clear=True):
            provider = MCPProvider()
            assert provider.provider_kind == "mcp"

    def test_mcp_provider_status_reflects_mode(self):
        """测试状态反映当前模式"""
        with patch.dict("os.environ", {"DEV_AGENT_MCP_PROVIDER": "local"}, clear=True):
            provider = MCPProvider()
            status = provider.status()

            assert status["provider"] == "local"
            assert "server_count" in status
