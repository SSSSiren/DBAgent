"""CancelEventRegistry 单元测试"""

import asyncio
import pytest
from app.agent.cancel import CancelEventRegistry, get_cancel_registry, reset_cancel_registry


@pytest.fixture(autouse=True)
def _reset():
    """每个测试前重置单例"""
    reset_cancel_registry()
    yield
    reset_cancel_registry()


class TestCancelEventRegistryBasic:
    """基本 CRUD 操作"""

    def test_create_returns_event(self):
        registry = CancelEventRegistry()
        event = registry.create("session-1")
        assert isinstance(event, asyncio.Event)
        assert not event.is_set()

    def test_cancel_sets_event(self):
        registry = CancelEventRegistry()
        event = registry.create("session-1")
        result = registry.cancel("session-1")
        assert result is True
        assert event.is_set()

    def test_cancel_nonexistent_returns_false(self):
        registry = CancelEventRegistry()
        result = registry.cancel("nonexistent")
        assert result is False

    def test_remove_cleans_up(self):
        registry = CancelEventRegistry()
        registry.create("session-1")
        registry.remove("session-1")
        result = registry.cancel("session-1")
        assert result is False

    def test_remove_nonexistent_no_error(self):
        registry = CancelEventRegistry()
        # 不应抛异常
        registry.remove("nonexistent")

    def test_create_replaces_existing(self):
        registry = CancelEventRegistry()
        event1 = registry.create("session-1")
        event2 = registry.create("session-1")
        assert event1 is not event2
        # 旧 event 不应再被 registry 管理
        assert not event1.is_set()
        registry.cancel("session-1")
        assert event2.is_set()
        assert not event1.is_set()


class TestCancelEventRegistryTTL:
    """TTL 过期机制"""

    def test_purge_expired_removes_old_events(self):
        registry = CancelEventRegistry()
        registry._TTL_SECONDS = 0.01  # 10ms TTL for testing
        registry.create("session-1")

        # 等待 TTL 过期
        import time
        time.sleep(0.02)

        # create 触发 purge
        registry.create("session-2")
        # session-1 应已过期
        result = registry.cancel("session-1")
        assert result is False

    def test_purge_only_removes_expired(self):
        registry = CancelEventRegistry()
        registry._TTL_SECONDS = 999  # very long TTL
        registry.create("session-1")
        registry.create("session-2")

        # 不应清理任何事件
        assert registry.cancel("session-1") is True
        assert registry.cancel("session-2") is True


class TestCancelEventRegistrySingleton:
    """单例工厂"""

    def test_get_cancel_registry_returns_same_instance(self):
        r1 = get_cancel_registry()
        r2 = get_cancel_registry()
        assert r1 is r2

    def test_reset_cancel_registry_creates_new_instance(self):
        r1 = get_cancel_registry()
        reset_cancel_registry()
        r2 = get_cancel_registry()
        assert r1 is not r2


class TestCancelEventRegistryConcurrency:
    """并发安全性"""

    @pytest.mark.asyncio
    async def test_cancel_wakes_waiters(self):
        registry = CancelEventRegistry()
        event = registry.create("session-1")

        async def waiter():
            await event.wait()
            return "woken"

        task = asyncio.create_task(waiter())
        # 给 waiter 一点时间进入等待
        await asyncio.sleep(0.01)
        registry.cancel("session-1")

        result = await asyncio.wait_for(task, timeout=1)
        assert result == "woken"

    @pytest.mark.asyncio
    async def test_multiple_cancels_idempotent(self):
        registry = CancelEventRegistry()
        registry.create("session-1")
        assert registry.cancel("session-1") is True
        # 第二次取消应仍返回 True（事件存在）
        assert registry.cancel("session-1") is True

    @pytest.mark.asyncio
    async def test_session_isolation(self):
        registry = CancelEventRegistry()
        event_a = registry.create("session-A")
        event_b = registry.create("session-B")

        registry.cancel("session-A")
        assert event_a.is_set()
        assert not event_b.is_set()