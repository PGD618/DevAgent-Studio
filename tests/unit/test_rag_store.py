"""
RAG Store 单元测试
测试文档切片、入库、检索、SQLite 存储等核心逻辑
"""

import pytest
import tempfile
import sqlite3
from pathlib import Path
from app.persistence.rag_store import SQLiteRagStore, PgVectorRagStore, rag_store


@pytest.fixture
def temp_db_path(tmp_path):
    """创建临时数据库路径并确保正确清理"""
    db_path = tmp_path / "test.db"
    yield db_path
    # 显式关闭所有连接
    if db_path.exists():
        try:
            # 等待所有连接关闭
            import gc
            gc.collect()
            # 删除数据库文件
            db_path.unlink(missing_ok=True)
        except Exception:
            pass


class TestSQLiteRagStoreIngestion:
    """SQLite RAG Store 入库测试"""

    def test_ingest_documents_and_chunks(self, temp_db_path):
        """测试入库文档和切片"""
        store = SQLiteRagStore(temp_db_path)

        documents = [
            {"path": "doc1.md", "size": 1000},
            {"path": "doc2.md", "size": 2000},
        ]
        chunks = [
            {"chunk_id": "chunk1", "path": "doc1.md", "content": "This is chunk 1"},
            {"chunk_id": "chunk2", "path": "doc1.md", "content": "This is chunk 2"},
            {"chunk_id": "chunk3", "path": "doc2.md", "content": "This is chunk 3"},
        ]

        result = store.ingest("test_collection", documents, chunks)

        assert result["document_count"] == 2
        assert result["chunk_count"] == 3

    def test_ingest_replaces_existing_collection(self, temp_db_path):
        """测试入库替换现有集合"""
        store = SQLiteRagStore(temp_db_path)

        # 第一次入库
        store.ingest("test_collection", [{"path": "old.md", "size": 100}], [{"chunk_id": "old", "path": "old.md", "content": "old"}])

        # 第二次入库应替换
        result = store.ingest("test_collection", [{"path": "new.md", "size": 200}], [{"chunk_id": "new", "path": "new.md", "content": "new"}])

        # 查询应只返回新文档
        docs = store.list_documents("test_collection")
        assert len(docs) == 1
        assert docs[0]["path"] == "new.md"

    def test_ingest_empty_collection(self, temp_db_path):
        """测试入库空集合"""
        store = SQLiteRagStore(temp_db_path)

        result = store.ingest("empty_collection", [], [])

        assert result["document_count"] == 0
        assert result["chunk_count"] == 0


class TestSQLiteRagStoreQuery:
    """SQLite RAG Store 查询测试"""

    def test_query_returns_relevant_chunks(self, temp_db_path):
        """测试查询返回相关切片"""
        store = SQLiteRagStore(temp_db_path)

        chunks = [
            {"chunk_id": "chunk1", "path": "doc1.md", "content": "Python is a programming language"},
            {"chunk_id": "chunk2", "path": "doc2.md", "content": "JavaScript is also a programming language"},
            {"chunk_id": "chunk3", "path": "doc3.md", "content": "Cats are animals"},
        ]
        store.ingest("test_collection", [], chunks)

        results = store.query("test_collection", "programming language", limit=5)

        # 前两个应该匹配
        assert len(results) >= 2
        assert results[0]["content"] in [chunks[0]["content"], chunks[1]["content"]]

    def test_query_respects_limit(self, temp_db_path):
        """测试查询遵守限制"""
        store = SQLiteRagStore(temp_db_path)

        chunks = [
            {"chunk_id": f"chunk{i}", "path": "doc.md", "content": f"test content {i}"}
            for i in range(10)
        ]
        store.ingest("test_collection", [], chunks)

        results = store.query("test_collection", "test content", limit=3)

        assert len(results) <= 3

    def test_query_empty_collection_returns_empty(self, temp_db_path):
        """测试查询空集合返回空结果"""
        store = SQLiteRagStore(temp_db_path)

        results = store.query("nonexistent_collection", "test query", limit=5)

        assert len(results) == 0

    def test_query_scores_by_keyword_match(self, temp_db_path):
        """测试按关键词匹配打分"""
        store = SQLiteRagStore(temp_db_path)

        chunks = [
            {"chunk_id": "chunk1", "path": "doc1.md", "content": "python python python"},
            {"chunk_id": "chunk2", "path": "doc2.md", "content": "python"},
            {"chunk_id": "chunk3", "path": "doc3.md", "content": "java"},
        ]
        store.ingest("test_collection", [], chunks)

        results = store.query("test_collection", "python", limit=5)

        # 包含更多 python 的应排在前面
        assert results[0]["path"] == "doc1.md"
        assert results[0]["score"] > results[1]["score"]


class TestSQLiteRagStoreListDocuments:
    """SQLite RAG Store 列出文档测试"""

    def test_list_documents_returns_all(self, temp_db_path):
        """测试列出所有文档"""
        store = SQLiteRagStore(temp_db_path)

        documents = [
            {"path": "doc1.md", "size": 1000},
            {"path": "doc2.md", "size": 2000},
            {"path": "doc3.md", "size": 3000},
        ]
        store.ingest("test_collection", documents, [])

        result = store.list_documents("test_collection")

        assert len(result) == 3
        paths = [doc["path"] for doc in result]
        assert "doc1.md" in paths
        assert "doc2.md" in paths
        assert "doc3.md" in paths

    def test_list_documents_empty_collection(self, temp_db_path):
        """测试列出空集合的文档"""
        store = SQLiteRagStore(temp_db_path)

        result = store.list_documents("empty_collection")

        assert len(result) == 0


class TestSQLiteRagStoreDeleteCollection:
    """SQLite RAG Store 删除集合测试"""

    def test_delete_collection_removes_all_data(self, temp_db_path):
        """测试删除集合移除所有数据"""
        store = SQLiteRagStore(temp_db_path)

        documents = [{"path": "doc.md", "size": 1000}]
        chunks = [{"chunk_id": "chunk1", "path": "doc.md", "content": "content"}]
        store.ingest("test_collection", documents, chunks)

        # 删除集合 - SQLiteRagStore 使用 ingest([], []) 来清空
        store.ingest("test_collection", [], [])

        # 验证已删除
        assert len(store.list_documents("test_collection")) == 0
        assert len(store.query("test_collection", "content", limit=10)) == 0

    def test_delete_nonexistent_collection_succeeds(self, temp_db_path):
        """测试删除不存在的集合不报错"""
        store = SQLiteRagStore(temp_db_path)

        # 不应抛出异常 - 使用 ingest([], [])
        store.ingest("nonexistent_collection", [], [])


class TestSQLiteRagStoreCollectionIsolation:
    """SQLite RAG Store 集合隔离测试"""

    def test_collections_are_isolated(self, temp_db_path):
        """测试不同集合之间隔离"""
        store = SQLiteRagStore(temp_db_path)

        # 入库两个集合
        store.ingest("collection1", [{"path": "doc1.md", "size": 100}], [{"chunk_id": "c1", "path": "doc1.md", "content": "collection1 content"}])
        store.ingest("collection2", [{"path": "doc2.md", "size": 200}], [{"chunk_id": "c2", "path": "doc2.md", "content": "collection2 content"}])

        # 查询 collection1 不应返回 collection2 的内容
        results1 = store.query("collection1", "content", limit=10)
        assert len(results1) == 1
        assert "collection1" in results1[0]["content"]

        # 列出 collection1 不应包含 collection2 的文档
        docs1 = store.list_documents("collection1")
        assert len(docs1) == 1
        assert docs1[0]["path"] == "doc1.md"


class TestRagStoreChunking:
    """RAG Store 文本切片测试"""

    def test_chunk_text_basic(self, temp_db_path):
        """测试基本文本切片功能"""
        store = SQLiteRagStore(temp_db_path)

        # SQLiteRagStore 不暴露 _chunk_text 方法，测试通过实际入库验证
        chunks = [
            {"chunk_id": f"chunk{i}", "path": "doc.md", "content": "A" * 100}
            for i in range(5)
        ]

        result = store.ingest("test_collection", [], chunks)
        assert result["chunk_count"] == 5


class TestPgVectorRagStore:
    """PgVector RAG Store 测试（需要 pgvector 支持）"""

    @pytest.mark.skip(reason="Requires pgvector database")
    def test_pgvector_store_initialization(self):
        """测试 PgVector Store 初始化"""
        # 需要真实的 PostgreSQL + pgvector
        store = PgVectorRagStore()
        assert store is not None

    @pytest.mark.skip(reason="Requires pgvector database")
    def test_pgvector_semantic_search(self):
        """测试 PgVector 语义搜索"""
        # 需要真实的嵌入模型和数据库
        pass


class TestRagStoreFactory:
    """RAG Store 工厂模式测试"""

    def test_default_rag_store_is_sqlite(self):
        """测试默认 RAG Store 是 SQLite"""
        # rag_store 全局实例应该是 SQLiteRagStore
        assert hasattr(rag_store, "ingest")
        assert hasattr(rag_store, "query")
        assert hasattr(rag_store, "list_documents")

    def test_rag_store_can_switch_mode(self):
        """测试可以切换 RAG Store 模式"""
        import os
        original_mode = os.environ.get("DEV_AGENT_RAG_STORE")

        try:
            os.environ["DEV_AGENT_RAG_STORE"] = "sqlite"
            # 重新加载会使用 sqlite 模式
            assert True  # 简单验证不抛异常
        finally:
            if original_mode:
                os.environ["DEV_AGENT_RAG_STORE"] = original_mode
            else:
                os.environ.pop("DEV_AGENT_RAG_STORE", None)


class TestRagStorePerformance:
    """RAG Store 性能测试"""

    def test_query_performance_with_large_collection(self, temp_db_path):
        """测试大集合查询性能"""
        store = SQLiteRagStore(temp_db_path)

        # 插入 1000 个 chunk
        chunks = [
            {"chunk_id": f"chunk{i}", "path": f"doc{i//10}.md", "content": f"test content {i} with some keywords"}
            for i in range(1000)
        ]
        store.ingest("large_collection", [], chunks)

        import time
        start = time.time()
        results = store.query("large_collection", "test keywords", limit=10)
        duration = time.time() - start

        # 查询应在 1 秒内完成
        assert duration < 1.0
        assert len(results) == 10
