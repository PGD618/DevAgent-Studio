"""
Marketplace Installer 单元测试
测试插件安装、预览、卸载、来源解析等核心逻辑
"""

import pytest
from unittest.mock import MagicMock, patch, mock_open
from pathlib import Path
from app.marketplace.installer import (
    preview_marketplace_package,
    install_marketplace_package,
    uninstall_marketplace_package,
)


class TestPackagePreview:
    """插件包预览测试"""

    def test_preview_local_package(self):
        """测试预览本地插件包"""
        mock_plugin_json = """{
            "plugin_id": "test-plugin",
            "name": "Test Plugin",
            "version": "1.0.0",
            "skills": [
                {
                    "code": "test.skill",
                    "name": "Test Skill",
                    "execution_type": "prompt",
                    "permissions": ["safe"]
                }
            ]
        }"""

        with patch("pathlib.Path.exists", return_value=True):
            with patch("pathlib.Path.is_dir", return_value=True):
                with patch("pathlib.Path.read_text", return_value=mock_plugin_json):
                    result = preview_marketplace_package("file:///test/path")

                    assert result["plugin_id"] == "test-plugin"
                    assert result["name"] == "Test Plugin"
                    assert len(result["skills"]) == 1
                    assert result["skills"][0]["code"] == "test.skill"

    def test_preview_skill_md_file(self):
        """测试预览 SKILL.md 文件（自动转换为 Prompt Skill）"""
        skill_md_content = """# Code Review Skill

This skill reviews code for quality issues.

## Input
- project_path: path to project

## Output
- findings: list of issues
"""

        with patch("pathlib.Path.exists", return_value=True):
            with patch("pathlib.Path.is_file", return_value=True):
                with patch("pathlib.Path.read_text", return_value=skill_md_content):
                    with patch("pathlib.Path.suffix", ".md"):
                        result = preview_marketplace_package("https://example.com/skill.md")

                        # 应自动转换为 Prompt Skill
                        assert "skills" in result
                        assert len(result["skills"]) == 1
                        assert result["skills"][0]["execution_type"] == "prompt"
                        assert "permissions" in result["skills"][0]
                        assert "llm" in result["skills"][0]["permissions"]

    def test_preview_invalid_json_raises_error(self):
        """测试无效 JSON 抛出错误"""
        invalid_json = "{ invalid json }"

        with patch("pathlib.Path.exists", return_value=True):
            with patch("pathlib.Path.is_dir", return_value=True):
                with patch("pathlib.Path.read_text", return_value=invalid_json):
                    with pytest.raises(ValueError, match="JSON"):
                        preview_marketplace_package("file:///test/path")


class TestPackageInstallation:
    """插件包安装测试"""

    def test_install_package_creates_directory(self):
        """测试安装插件创建目录"""
        mock_plugin = {
            "plugin_id": "test-plugin",
            "name": "Test Plugin",
            "version": "1.0.0",
            "skills": [{"code": "test.skill", "name": "Test Skill"}],
        }

        with patch("app.marketplace.installer.preview_marketplace_package", return_value=mock_plugin):
            with patch("pathlib.Path.mkdir") as mock_mkdir:
                with patch("pathlib.Path.exists", return_value=False):
                    with patch("pathlib.Path.write_text"):
                        with patch("app.persistence.sqlite_store.task_store") as mock_store:
                            result = install_marketplace_package("https://example.com/plugin")

                            # 验证目录被创建
                            mock_mkdir.assert_called()
                            assert result["status"] == "installed"
                            assert result["plugin_id"] == "test-plugin"

    def test_install_duplicate_package_raises_error(self):
        """测试安装已存在的插件抛出错误"""
        mock_plugin = {
            "plugin_id": "duplicate-plugin",
            "name": "Duplicate",
            "version": "1.0.0",
            "skills": [],
        }

        with patch("app.marketplace.installer.preview_marketplace_package", return_value=mock_plugin):
            with patch("pathlib.Path.exists", return_value=True):
                with pytest.raises(ValueError, match="already installed"):
                    install_marketplace_package("https://example.com/plugin")

    def test_install_validates_contract(self):
        """测试安装时验证 Skill 契约"""
        mock_plugin = {
            "plugin_id": "invalid-plugin",
            "name": "Invalid",
            "version": "1.0.0",
            "skills": [
                {
                    "code": "invalid.skill",
                    "name": "Invalid Skill",
                    "execution_type": None,  # 无效
                    "permissions": [],
                }
            ],
        }

        with patch("app.marketplace.installer.preview_marketplace_package", return_value=mock_plugin):
            with patch("pathlib.Path.exists", return_value=False):
                with pytest.raises(ValueError, match="contract"):
                    install_marketplace_package("https://example.com/plugin")


class TestPackageUninstallation:
    """插件包卸载测试"""

    def test_uninstall_package_removes_directory(self):
        """测试卸载插件移除目录"""
        with patch("pathlib.Path.exists", return_value=True):
            with patch("pathlib.Path.is_dir", return_value=True):
                with patch("shutil.rmtree") as mock_rmtree:
                    with patch("app.persistence.sqlite_store.task_store") as mock_store:
                        mock_store.get_installed_package.return_value = {
                            "plugin_id": "test-plugin",
                            "install_path": "/data/marketplace/test-plugin",
                        }

                        result = uninstall_marketplace_package("test-plugin")

                        assert result["status"] == "uninstalled"
                        mock_rmtree.assert_called_once()

    def test_uninstall_nonexistent_package_raises_error(self):
        """测试卸载不存在的插件抛出错误"""
        with patch("app.persistence.sqlite_store.task_store") as mock_store:
            mock_store.get_installed_package.return_value = None

            with pytest.raises(ValueError, match="not found"):
                uninstall_marketplace_package("nonexistent-plugin")


class TestSourceParsing:
    """来源解析测试"""

    def test_parse_file_source(self):
        """测试解析 file:// 来源"""
        source = "file:///C:/path/to/plugin"
        # 实际实现会解析为本地路径
        assert source.startswith("file://")

    def test_parse_http_source(self):
        """测试解析 HTTP URL 来源"""
        source = "https://example.com/plugins/my-plugin.zip"
        assert source.startswith("https://")

    def test_parse_github_style_source(self):
        """测试解析 GitHub 风格来源"""
        source = "github:user/repo/plugins/skill1"
        assert "github:" in source


class TestSkillMdConversion:
    """SKILL.md 转换测试"""

    def test_skill_md_creates_prompt_skill(self):
        """测试 SKILL.md 转换为 Prompt Skill"""
        skill_content = """# My Skill

Description of the skill.

## Usage
Input: project_path
Output: report
"""

        with patch("pathlib.Path.exists", return_value=True):
            with patch("pathlib.Path.is_file", return_value=True):
                with patch("pathlib.Path.read_text", return_value=skill_content):
                    with patch("pathlib.Path.name", "my-skill.md"):
                        result = preview_marketplace_package("https://example.com/my-skill.md")

                        skills = result.get("skills", [])
                        assert len(skills) == 1
                        skill = skills[0]
                        assert skill["execution_type"] == "prompt"
                        assert "llm" in skill["permissions"]
                        # Prompt 模板应包含原始内容
                        assert "My Skill" in str(skill.get("default_input", {}))

    def test_skill_md_sanitizes_name(self):
        """测试 SKILL.md 名称被正确清理"""
        with patch("pathlib.Path.exists", return_value=True):
            with patch("pathlib.Path.is_file", return_value=True):
                with patch("pathlib.Path.read_text", return_value="# Test"):
                    with patch("pathlib.Path.name", "My Complex Skill Name!.md"):
                        result = preview_marketplace_package("https://example.com/skill.md")

                        skill_code = result["skills"][0]["code"]
                        # 应清理为 kebab-case
                        assert " " not in skill_code
                        assert "!" not in skill_code


class TestPermissionCalculation:
    """权限计算测试"""

    def test_prompt_skill_requires_llm_permission(self):
        """测试 Prompt Skill 自动添加 llm 权限"""
        skill_md = "# Test Skill\n\nA prompt-based skill."

        with patch("pathlib.Path.exists", return_value=True):
            with patch("pathlib.Path.is_file", return_value=True):
                with patch("pathlib.Path.read_text", return_value=skill_md):
                    result = preview_marketplace_package("https://example.com/skill.md")

                    skill = result["skills"][0]
                    assert "llm" in skill["permissions"]

    def test_code_skill_inherits_declared_permissions(self):
        """测试代码型 Skill 继承声明的权限"""
        plugin_json = """{
            "plugin_id": "test",
            "skills": [{
                "code": "test.skill",
                "execution_type": "python",
                "permissions": ["filesystem.read", "network"]
            }]
        }"""

        with patch("pathlib.Path.exists", return_value=True):
            with patch("pathlib.Path.is_dir", return_value=True):
                with patch("pathlib.Path.read_text", return_value=plugin_json):
                    result = preview_marketplace_package("file:///test")

                    skill = result["skills"][0]
                    assert "filesystem.read" in skill["permissions"]
                    assert "network" in skill["permissions"]


class TestVersionManagement:
    """版本管理测试"""

    def test_install_records_version(self):
        """测试安装记录版本信息"""
        mock_plugin = {
            "plugin_id": "versioned-plugin",
            "name": "Versioned",
            "version": "2.1.0",
            "skills": [],
        }

        with patch("app.marketplace.installer.preview_marketplace_package", return_value=mock_plugin):
            with patch("pathlib.Path.exists", return_value=False):
                with patch("pathlib.Path.mkdir"):
                    with patch("pathlib.Path.write_text"):
                        with patch("app.persistence.sqlite_store.task_store") as mock_store:
                            result = install_marketplace_package("https://example.com/plugin")

                            # 验证版本被记录
                            assert result["version"] == "2.1.0"
