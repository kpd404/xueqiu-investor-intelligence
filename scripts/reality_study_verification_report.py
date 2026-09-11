"""Render a read-only human verification report for Reality Study candidates."""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
from pathlib import Path
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from collectors.xueqiu.cdp_tabs import CdpTabDescriptor, discover_cdp_tabs
from scripts.audit_intelligence_data import _fetchall
from scripts.reality_study_registry import (
    RealityStudyCandidate,
    RealityStudyCandidateRegistry,
    get_reality_study_candidate_registry,
)


class DatabaseInvestorRecord(BaseModel):
    """Read-only database identity used for candidate mapping."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    investor_id: UUID
    name: str
    platform: str | None = None
    xueqiu_user_id: str | None = None


class RealityStudyCandidateMapping(BaseModel):
    """One registry candidate mapped to database identity and open tabs."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    candidate: RealityStudyCandidate
    database_investor: DatabaseInvestorRecord | None = None
    database_xueqiu_id_matches: bool = False
    matching_tabs: tuple[CdpTabDescriptor, ...] = ()
    verification_state: str


class RealityStudyVerificationReport(BaseModel):
    """Human-facing snapshot of current tabs and candidate identity matches."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    cdp_endpoint: str
    context_count: int = Field(ge=0)
    page_count: int = Field(ge=0)
    database_candidate_count: int = Field(ge=0)
    verified_candidate_count: int = Field(ge=0)
    tabs: tuple[CdpTabDescriptor, ...] = ()
    candidate_mappings: tuple[RealityStudyCandidateMapping, ...] = ()
    unmapped_tabs: tuple[CdpTabDescriptor, ...] = ()


def load_database_investors() -> dict[UUID, DatabaseInvestorRecord]:
    """Load only Investor identity columns needed by the verification report."""

    rows = _fetchall(
        """
        SELECT id, name, platform, platform_user_id
        FROM investors
        ORDER BY name, id
        """
    )
    return {
        UUID(str(row[0])): DatabaseInvestorRecord(
            investor_id=UUID(str(row[0])),
            name=str(row[1]),
            platform=str(row[2]) if row[2] is not None else None,
            xueqiu_user_id=str(row[3]).strip() if row[3] is not None else None,
        )
        for row in rows
    }


async def build_human_verification_report(
    *,
    cdp_endpoint: str,
    registry: RealityStudyCandidateRegistry | None = None,
    database_investors: dict[UUID, DatabaseInvestorRecord] | None = None,
) -> RealityStudyVerificationReport:
    """Build a report without navigating, collecting, or changing any state."""

    candidate_registry = registry or get_reality_study_candidate_registry()
    database_records = database_investors or load_database_investors()
    discovery = await discover_cdp_tabs(cdp_endpoint)
    tabs_by_user_id: dict[str, list[CdpTabDescriptor]] = {}
    for tab in discovery.tabs:
        if tab.detected_xueqiu_user_id is not None:
            tabs_by_user_id.setdefault(tab.detected_xueqiu_user_id, []).append(tab)

    mappings: list[RealityStudyCandidateMapping] = []
    for candidate in candidate_registry.candidates:
        database_investor = database_records.get(candidate.investor_id)
        database_id_matches = bool(
            database_investor is not None
            and database_investor.xueqiu_user_id == candidate.xueqiu_user_id
        )
        matching_tabs = tuple(tabs_by_user_id.get(candidate.xueqiu_user_id, ()))
        if database_investor is None:
            verification_state = "DATABASE_CANDIDATE_NOT_FOUND"
        elif not database_id_matches:
            verification_state = "DATABASE_XUEQIU_ID_MISMATCH"
        elif not matching_tabs:
            verification_state = "TAB_NOT_OPEN"
        elif len(matching_tabs) > 1:
            verification_state = "MULTIPLE_MATCHING_TABS"
        else:
            verification_state = "VERIFIED"
        mappings.append(
            RealityStudyCandidateMapping(
                candidate=candidate,
                database_investor=database_investor,
                database_xueqiu_id_matches=database_id_matches,
                matching_tabs=matching_tabs,
                verification_state=verification_state,
            )
        )

    registry_user_ids = {candidate.xueqiu_user_id for candidate in candidate_registry.candidates}
    mapped_tab_ids = {
        tab for tab in discovery.tabs if tab.detected_xueqiu_user_id in registry_user_ids
    }
    unmapped_tabs = tuple(tab for tab in discovery.tabs if tab not in mapped_tab_ids)

    return RealityStudyVerificationReport(
        cdp_endpoint=discovery.cdp_endpoint,
        context_count=discovery.context_count,
        page_count=discovery.page_count,
        database_candidate_count=sum(mapping.database_investor is not None for mapping in mappings),
        verified_candidate_count=sum(
            mapping.verification_state == "VERIFIED" for mapping in mappings
        ),
        tabs=discovery.tabs,
        candidate_mappings=tuple(mappings),
        unmapped_tabs=unmapped_tabs,
    )


def _cell(value: object) -> str:
    return str(value).replace("|", "\\|").replace("\n", " ")


def render_markdown(report: RealityStudyVerificationReport) -> str:
    """Render a compact report suitable for a human preflight review."""

    lines = [
        "# Reality Study Human Verification Report",
        "",
        f"- CDP endpoint: `{_cell(report.cdp_endpoint)}`",
        f"- Browser contexts: {report.context_count}",
        f"- Open pages: {report.page_count}",
        f"- Database candidates found: {report.database_candidate_count}",
        f"- Verified single-tab matches: {report.verified_candidate_count}",
        "- Collection status: NOT RUN",
        "",
        "## Open tabs",
        "",
        "| Context | Page | URL | Title | Detected Xueqiu user id | Registry match |",
        "|---:|---:|---|---|---|---|",
    ]
    registry_by_user_id = {
        mapping.candidate.xueqiu_user_id: mapping.candidate for mapping in report.candidate_mappings
    }
    for tab in report.tabs:
        candidate = registry_by_user_id.get(tab.detected_xueqiu_user_id or "")
        match = candidate.xueqiu_user_id if candidate is not None else "—"
        lines.append(
            "| "
            + " | ".join(
                (
                    str(tab.context_index),
                    str(tab.page_index),
                    _cell(tab.url),
                    _cell(tab.title),
                    _cell(tab.detected_xueqiu_user_id or "—"),
                    _cell(match),
                )
            )
            + " |"
        )

    lines.extend(
        [
            "",
            "## Database candidate mapping",
            "",
            "| Investor | Investor id | Xueqiu user id | Registry status | "
            "Verification state | Matching tabs |",
            "|---|---|---|---|---|---:|",
        ]
    )
    for mapping in report.candidate_mappings:
        database_investor = mapping.database_investor
        lines.append(
            "| "
            + " | ".join(
                (
                    _cell(database_investor.name if database_investor else "<not found>"),
                    str(mapping.candidate.investor_id),
                    mapping.candidate.xueqiu_user_id,
                    mapping.candidate.status.value,
                    mapping.verification_state,
                    str(len(mapping.matching_tabs)),
                )
            )
            + " |"
        )

    lines.extend(["", "## Unmapped tabs", ""])
    if not report.unmapped_tabs:
        lines.append("None.")
    else:
        for tab in report.unmapped_tabs:
            lines.append(
                f"- context={tab.context_index} page={tab.page_index} "
                f"url={tab.url or '<blank>'} detected_user_id="
                f"{tab.detected_xueqiu_user_id or '<none>'}"
            )
    return "\n".join(lines) + "\n"


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Read-only Reality Study candidate and Edge CDP tab verification report"
    )
    parser.add_argument(
        "--endpoint",
        default=os.getenv("XUEQIU_CDP_ENDPOINT", "http://127.0.0.1:9222"),
        help="existing Edge Chromium CDP endpoint",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="emit structured JSON instead of the human-readable Markdown report",
    )
    return parser.parse_args()


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    args = _parse_args()
    try:
        report = asyncio.run(build_human_verification_report(cdp_endpoint=args.endpoint))
    except Exception as exc:
        print(f"Reality Study verification failed: {exc}", file=sys.stderr)
        return 2
    if args.json:
        print(report.model_dump_json(indent=2))
    else:
        print(render_markdown(report), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
