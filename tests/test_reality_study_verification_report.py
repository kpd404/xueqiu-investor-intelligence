import asyncio
from uuid import UUID

from collectors.xueqiu.cdp_tabs import CdpTabDescriptor, CdpTabDiscoveryResult
from scripts.reality_study_registry import (
    RealityStudyCandidate,
    RealityStudyCandidateRegistry,
    RealityStudyCandidateStatus,
)
from scripts.reality_study_verification_report import (
    DatabaseInvestorRecord,
    build_human_verification_report,
    render_markdown,
)


def _candidate(investor_id: str, xueqiu_user_id: str) -> RealityStudyCandidate:
    return RealityStudyCandidate(
        investor_id=UUID(investor_id),
        xueqiu_user_id=xueqiu_user_id,
        priority_reason="test candidate",
        target_round="test-round",
        status=RealityStudyCandidateStatus.PENDING_HUMAN_VERIFICATION,
    )


def test_report_maps_open_tabs_to_database_candidates(monkeypatch) -> None:
    first = _candidate("00000000-0000-0000-0000-000000000001", "100")
    second = _candidate("00000000-0000-0000-0000-000000000002", "200")
    registry = RealityStudyCandidateRegistry(candidates=(first, second))
    database = {
        first.investor_id: DatabaseInvestorRecord(
            investor_id=first.investor_id,
            name="first",
            platform="xueqiu",
            xueqiu_user_id="100",
        ),
        second.investor_id: DatabaseInvestorRecord(
            investor_id=second.investor_id,
            name="second",
            platform="xueqiu",
            xueqiu_user_id="200",
        ),
    }
    discovery = CdpTabDiscoveryResult(
        cdp_endpoint="http://127.0.0.1:9222",
        context_count=1,
        page_count=3,
        tabs=(
            CdpTabDescriptor(
                context_index=0,
                page_index=0,
                url="https://xueqiu.com/u/100",
                title="First",
                detected_xueqiu_user_id="100",
            ),
            CdpTabDescriptor(
                context_index=0,
                page_index=1,
                url="https://example.com/",
                title="Other",
            ),
            CdpTabDescriptor(
                context_index=0,
                page_index=2,
                url="https://xueqiu.com/u/999",
                title="Unmapped",
                detected_xueqiu_user_id="999",
            ),
        ),
    )

    async def fake_discovery(_endpoint: str) -> CdpTabDiscoveryResult:
        return discovery

    import scripts.reality_study_verification_report as report_module

    monkeypatch.setattr(report_module, "discover_cdp_tabs", fake_discovery)
    report = asyncio.run(
        build_human_verification_report(
            cdp_endpoint="http://127.0.0.1:9222",
            registry=registry,
            database_investors=database,
        )
    )

    assert report.database_candidate_count == 2
    assert report.verified_candidate_count == 1
    assert report.candidate_mappings[0].verification_state == "VERIFIED"
    assert report.candidate_mappings[1].verification_state == "TAB_NOT_OPEN"
    assert [tab.detected_xueqiu_user_id for tab in report.unmapped_tabs] == [None, "999"]

    markdown = render_markdown(report)
    assert "Collection status: NOT RUN" in markdown
    assert "DATABASE candidate mapping" not in markdown
    assert "TAB_NOT_OPEN" in markdown
    assert "https://xueqiu.com/u/999" in markdown
