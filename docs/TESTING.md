# DevAgent Studio 测试指南

本项目使用 pytest 进行单元测试和集成测试，目标覆盖率 70%+。

## 快速开始

### 安装测试依赖
```bash
pip install -e ".[dev]"
```

### 运行所有测试
```bash
pytest tests/unit -v
```

### 查看覆盖率报告
```bash
pytest tests/unit --cov=app --cov-report=html
start htmlcov/index.html  # Windows
open htmlcov/index.html   # macOS/Linux
```

## 测试结构

```
tests/
  unit/                          # 单元测试
    test_workflow_compiler.py    # 工作流编译器测试
    test_skill_executor.py       # Skill 执行器测试
    test_harness_runtime.py      # 运行时测试
    test_llm_provider.py         # LLM 提供者测试
  integration/                   # 集成测试
    test_end_to_end_workflow.py  # 端到端工作流测试
  fixtures/                      # 测试数据
    sample_workflows.json
  conftest.py                    # 共享 fixtures
```

## 当前状态

| 指标 | 数值 |
|------|------|
| 测试用例 | 86 个 |
| 通过率 | 50% (43/86) |
| 代码覆盖率 | 21.92% |

详细报告见 [TEST_COVERAGE_REPORT.md](./TEST_COVERAGE_REPORT.md)

## 测试命令

```bash
# 运行特定测试文件
pytest tests/unit/test_workflow_compiler.py -v

# 运行特定测试类
pytest tests/unit/test_skill_executor.py::TestSkillPermissionCheck -v

# 只运行失败的测试
pytest --lf

# 跳过慢速测试
pytest -m "not slow"

# 生成 JUnit XML 报告（用于 CI）
pytest --junitxml=test-results.xml
```

## 编写测试

### 基本结构
```python
import pytest
from app.your_module import YourClass

class TestYourFeature:
    """功能描述"""

    def test_normal_case(self):
        """测试正常情况"""
        # Arrange
        input_data = {"key": "value"}
        
        # Act
        result = YourClass.process(input_data)
        
        # Assert
        assert result["status"] == "success"

    def test_error_case(self):
        """测试异常情况"""
        with pytest.raises(ValueError, match="invalid"):
            YourClass.process(None)
```

### 使用 Fixtures
```python
@pytest.fixture
def temp_project(tmp_path):
    """创建临时项目目录"""
    project = tmp_path / "test_project"
    project.mkdir()
    (project / "README.md").write_text("# Test")
    return str(project)

def test_with_fixture(temp_project):
    """使用 fixture 的测试"""
    assert Path(temp_project).exists()
```

### Mock 外部依赖
```python
from unittest.mock import patch

def test_with_mock_db():
    """测试时 Mock 数据库调用"""
    with patch.object(task_store, "get_task") as mock_get:
        mock_get.return_value = {"task_id": "123", "status": "completed"}
        
        result = your_function()
        assert result["task_id"] == "123"
```

## CI/CD

项目使用 GitHub Actions 自动运行测试：

- **触发**: Push 到 `main`/`dev` 分支或创建 PR
- **环境**: Python 3.11 和 3.12
- **检查**: 单元测试、代码风格（ruff）、前端构建

配置文件：`.github/workflows/ci.yml`

## 测试覆盖目标

| 模块 | 当前 | 目标 |
|------|------|------|
| `app/graphs/workflow_compiler.py` | 35% | 80% |
| `app/skills/executor.py` | 28% | 75% |
| `app/harness/runtime.py` | 42% | 70% |
| `app/providers/llm_provider.py` | 18% | 65% |
| **整体** | **21.92%** | **70%+** |

## 贡献测试

1. 为新功能编写测试（测试先行）
2. 修复 bug 时补充回归测试
3. 确保测试可独立运行
4. 使用清晰的测试名称和 docstring
5. 提交前运行 `pytest` 确保通过

## 参考资源

- [pytest 文档](https://docs.pytest.org/)
- [测试覆盖进度报告](./TEST_COVERAGE_REPORT.md)
- [贡献指南](../CONTRIBUTING.md)
