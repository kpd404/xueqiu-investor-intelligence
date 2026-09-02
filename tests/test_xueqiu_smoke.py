import asyncio
from datetime import UTC, datetime
from types import SimpleNamespace

import pytest

from collectors.xueqiu import FollowingFeedBatch, smoke
from contracts import FeedPostItem, FeedPostKind


def make_batch() -> FollowingFeedBatch:
    return FollowingFeedBatch(
        items=(
            FeedPostItem(
                source_event_id="smoke-event",
                author_id="author-1",
                post_kind=FeedPostKind.ORIGINAL,
                content="dry-run content",
                published_time=datetime(2026, 8, 27, 8, 0, tzinfo=UTC),
            ),
        ),
        observed_at=datetime(2026, 8, 27, 8, 0, tzinfo=UTC),
    )


def test_feed_cli_arguments_and_no_legacy_max_pages() -> None:
    args = smoke.build_parser().parse_args(
        [
            "--feed",
            "--headless",
            "--max-batches",
            "2",
            "--only-investor-ids",
            "author-1",
            "author-2",
            "--dry-run",
        ]
    )

    assert args.feed is True
    assert args.headless is True
    assert args.max_batches == 2
    assert args.only_investor_ids == ["author-1", "author-2"]
    assert args.dry_run is True

    with pytest.raises(SystemExit):
        smoke.build_parser().parse_args(["--feed", "--max-pages", "2"])


def test_dry_run_does_not_open_database(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    batch = make_batch()
    browser = SimpleNamespace(last_following_stop_reason="MAX_BATCHES")

    async def fake_capture_feed(
        *_: object,
    ) -> tuple[tuple[FollowingFeedBatch, ...], tuple[FeedPostItem, ...], object]:
        return (batch,), batch.items, browser

    def fail_if_database_is_opened() -> object:
        raise AssertionError("dry-run must not open a database session")

    monkeypatch.setattr(smoke, "_capture_feed", fake_capture_feed)
    monkeypatch.setattr(smoke, "session_scope", fail_if_database_is_opened)
    args = smoke.build_parser().parse_args(["--feed", "--dry-run"])

    assert asyncio.run(smoke.run(args)) == 0
    output = capsys.readouterr().out
    assert "Following Feed confirmed" in output
    assert "mode=DRY_RUN" in output
    assert "inserted=0" in output
    assert "duplicates=0" in output
    assert "stop_reason=MAX_BATCHES" in output
    assert "batch=1 items=1 valid=1 skipped=0" in output


def test_normal_feed_mode_calls_ingestion(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    batch = make_batch()
    browser = SimpleNamespace(last_following_stop_reason="MAX_BATCHES")
    calls: list[tuple[object, ...]] = []

    async def fake_capture_feed(
        *_: object,
    ) -> tuple[tuple[FollowingFeedBatch, ...], tuple[FeedPostItem, ...], object]:
        return (batch,), batch.items, browser

    class FakeSessionScope:
        def __enter__(self) -> object:
            return object()

        def __exit__(self, *args: object) -> None:
            return None

    class FakeIngestionService:
        def __init__(self, session: object) -> None:
            calls.append((session,))

        async def ingest(self, items: tuple[FeedPostItem, ...]) -> object:
            calls.append(tuple(items))
            return SimpleNamespace(
                inserted_event_count=1,
                duplicate_event_count=0,
                created_investor_count=1,
                reused_investor_count=0,
                event_ids=(),
            )

    monkeypatch.setattr(smoke, "_capture_feed", fake_capture_feed)
    monkeypatch.setattr(smoke, "session_scope", lambda: FakeSessionScope())
    monkeypatch.setattr(smoke, "FeedIngestionService", FakeIngestionService)
    monkeypatch.setattr(
        smoke,
        "_print_ingestion_summary",
        lambda result, request, session: print("ingestion-called"),
    )
    args = smoke.build_parser().parse_args(["--feed", "--max-batches", "1"])

    assert asyncio.run(smoke.run(args)) == 0
    assert len(calls) == 2
    assert calls[1] == batch.items
    output = capsys.readouterr().out
    assert "mode=INGEST" not in output
    assert "ingestion-called" in output
