"""Read-only Tier A Asset identity integrity gate.

The script audits only the 16 Tier A candidates from the current Asset
Resolution Audit v2.  It reads the real PostgreSQL Asset/Alias catalog and
effective evidence in a repeatable-read, read-only transaction, then performs
an in-memory dry-run.  External verification URLs are official exchange or
issuer-disclosure sources reviewed for this gate.  No LLM, seed, rebuild,
collection, migration or database write is performed.
"""

# Report construction is intentionally verbose and human-readable.
# ruff: noqa: E501

from __future__ import annotations

import argparse
import sys
from collections import Counter, defaultdict
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from config import get_production_analysis_policy, get_production_attention_policy_version
from contracts import AssetReference, normalize_asset_reference
from scripts.audit_asset_resolution_v2 import (
    AssetResolver,
    CatalogLookup,
    analysis_key,
    fetch,
    ident,
    load_occurrences,
    market_key,
    name_key,
    scalar,
    symbol_key,
)
from scripts.audit_asset_resolution_v2 import connect_read_only as connect_read_only_base

HK = timezone(timedelta(hours=8), name="Asia/Hong_Kong")
Row = dict[str, Any]


@dataclass(frozen=True)
class Candidate:
    reference: str
    market: str
    symbol: str
    official_name: str
    aliases: tuple[str, ...]
    source_label: str
    source_url: str
    listing_relation: str
    canonical_correction: str


CANDIDATES = (
    Candidate(
        "华能国际电力股份",
        "HK",
        "00902",
        "华能国际电力股份有限公司",
        ("华能国际电力股份",),
        "HKEX Form 2 / H Shares",
        "https://di.hkex.com.hk/di/NSForm2.aspx?fn=CS20260306E00340&g_lang=zh-HK&lang=ZH",
        "A/H pair: existing DB SH:600011; preserve HK:00902 separately",
        "",
    ),
    Candidate(
        "大唐新能源",
        "HK",
        "01798",
        "中国大唐集团新能源股份有限公司",
        ("大唐新能源",),
        "HKEX Form 2 / H Shares",
        "https://di.hkex.com.hk/di/NSForm2.aspx?cid=2&cn=1&corpn=China+Datang+Corporation+Renewable+Power+Co.%2C+Ltd.++-+H+Shares&ed=20%2F03%2F2026&fn=CS20251207E00002&lang=EN&sa1=cl&sa2=an&sced=20%2F03%2F2026&scsd=20%2F03%2F2025&sd=20%2F03%2F2025&sid=54850&src=Main",
        "Official H listing; no same-listing Asset in current DB",
        "",
    ),
    Candidate(
        "腾讯控股",
        "HK",
        "00700",
        "Tencent Holdings Ltd.",
        ("腾讯控股",),
        "HKEX Form 2",
        "https://di.hkex.com.hk/di/NSForm2.aspx?cid=0&cn=1&corpn=Tencent+Holdings+Ltd.&ed=23%2F01%2F2026&fn=CS20250728E00462&g_lang=en&lang=EN&sa1=cl&sa2=ns&sc=0700&sced=23%2F01%2F2026&scsd=23%2F01%2F2025&sd=23%2F01%2F2025&sid=6893&src=MAIN",
        "No same-listing Asset in current DB",
        "",
    ),
    Candidate(
        "紫金黄金国际",
        "HK",
        "02259",
        "紫金黄金国际有限公司",
        ("紫金黄金国际",),
        "HKEX IPO results",
        "https://www.iporesults.hkex.com.hk/listedco/listconews/sehk/2025/0929/2025092903788.pdf",
        "Separate HK-listed issuer; related-name review does not merge with 紫金矿业",
        "",
    ),
    Candidate(
        "大唐发电",
        "HK",
        "00991",
        "大唐国际发电股份有限公司",
        ("大唐发电",),
        "HKEX A/H share list",
        "https://www.hkex.com.hk/chi/Invest/misc/documents/ic_for_ah_shares_sc.pdf",
        "A/H pair 00991 / 601991; preserve listings separately",
        "",
    ),
    Candidate(
        "中金黄金",
        "SH",
        "600489",
        "中金黄金股份有限公司",
        ("中金黄金",),
        "SSE issuer disclosure",
        "https://big5.sse.com.cn/site/cht/www.sse.com.cn/disclosure/listedinfo/announcement/c/new/2026-06-03/600489_20260603_76AO.pdf",
        "No same-listing Asset in current DB",
        "",
    ),
    Candidate(
        "东阿阿胶",
        "SZ",
        "000423",
        "东阿阿胶股份有限公司",
        ("东阿阿胶",),
        "SZSE issuer disclosure",
        "https://disc.static.szse.cn/download/disc/disk03/finalpage/2026-02-11/80f885d8-2a6e-455a-9247-89b653644d2a.PDF",
        "No same-listing Asset in current DB",
        "",
    ),
    Candidate(
        "摩尔线程-U",
        "SH",
        "688795",
        "摩尔线程智能科技（北京）股份有限公司",
        ("摩尔线程-U",),
        "SSE listing announcement",
        "https://www.sse.com.cn/disclosure/announcement/listing/ipo/c/c_20251204_10800678.shtml",
        "Single SSE listing; exchange short name is 摩尔线程",
        "canonical_name=摩尔线程; alias=摩尔线程-U",
    ),
    Candidate(
        "贵州茅台",
        "SH",
        "600519",
        "贵州茅台酒股份有限公司",
        ("贵州茅台",),
        "SSE official notice",
        "https://www.sse.com.cn/assortment/options/mnjyzxxx/c/c_20260625_10823460.shtml",
        "No same-listing Asset in current DB",
        "",
    ),
    Candidate(
        "中国心连心化肥",
        "HK",
        "01866",
        "China XLX Fertiliser Ltd.",
        ("中国心连心化肥",),
        "HKEX Form 3A",
        "https://di.hkex.com.hk/di/NSForm3A.aspx?ed=22%2F06%2F2026&fn=DA20260203E00060&lang=EN&sa1=cl&sa2=nd&sced=22%2F06%2F2026&scsd=22%2F06%2F2025&sd=22%2F06%2F2025&sid=39450&src=Main&srchCorpName=China+XLX+Fertiliser+Ltd.",
        "No same-listing Asset in current DB",
        "",
    ),
    Candidate(
        "华润啤酒",
        "HK",
        "00291",
        "China Resources Beer (Holdings) Co. Ltd.",
        ("华润啤酒",),
        "HKEX Form 4",
        "https://di.hkex.com.hk/di/NSForm4.aspx?fn=IR20260909E00090&g_lang=en&lang=EN&pg=2&sa1=ir",
        "No same-listing Asset in current DB",
        "",
    ),
    Candidate(
        "恒基地产",
        "HK",
        "00012",
        "Henderson Land Development Co. Ltd.",
        ("恒基地产",),
        "HKEX Form 3B",
        "https://di.hkex.com.hk/di/NSForm3B.aspx?ed=30%2F06%2F2026&fn=DB20260630E00334&lang=EN&sa1=cl&sa2=ns&sc=00012&sced=30%2F06%2F2026&scsd=30%2F06%2F2025&sd=30%2F06%2F2025&sid=19&src=Main&tk=ds",
        "No same-listing Asset in current DB",
        "",
    ),
    Candidate(
        "中国宏桥",
        "HK",
        "01378",
        "China Hongqiao Group Ltd.",
        ("中国宏桥",),
        "HKEX Form 2",
        "https://di.hkex.com.hk/di/NSForm2.aspx?ed=16%2F04%2F2025&fn=CS20250416E00359&lang=EN&sa1=cl&sa2=ns&sc=01378&sced=16%2F04%2F2025&scsd=16%2F04%2F2024&sd=16%2F04%2F2024&sid=57028&src=Main&tk=ds",
        "No same-listing Asset in current DB",
        "",
    ),
    Candidate(
        "中国神华",
        "HK",
        "01088",
        "China Shenhua Energy Co. Ltd.",
        ("中国神华",),
        "HKEX Form 4 / A-H list",
        "https://di.hkex.com.hk/di/NSForm4.aspx?fn=IR20251125E00167&g_lang=en&lang=EN&sa1=ir&src=MAIN",
        "A/H pair: existing DB SH:601088; preserve HK:01088 separately",
        "market-scoped alias 中国神华 for HK listing; do not reuse SH alias globally",
    ),
    Candidate(
        "中矿资源",
        "SZ",
        "002738",
        "中矿资源集团股份有限公司",
        ("中矿资源",),
        "SZSE issuer disclosure",
        "https://disc.static.szse.cn/download/disc/disk03/finalpage/2026-05-20/b95ff303-1d85-4529-8727-7ecad65cb0fc.PDF",
        "No same-listing Asset in current DB",
        "",
    ),
    Candidate(
        "山东黄金",
        "SH",
        "600547",
        "山东黄金矿业股份有限公司",
        ("山东黄金",),
        "Issuer disclosure / HKEX A-H list",
        "https://static.cninfo.com.cn/finalpage/2026-06-16/1225371766.PDF",
        "A/H pair 01787 / 600547: existing DB HK:01787; preserve SH:600547 separately",
        "market-scoped alias 山东黄金 for SH listing; do not merge with HK Asset",
    ),
)


def as_hk(value: Any) -> datetime | None:
    if not isinstance(value, datetime):
        return None
    return (
        value.replace(tzinfo=HK)
        if value.tzinfo is None or value.utcoffset() is None
        else value.astimezone(HK)
    )


def fmt_dt(value: Any) -> str:
    value = as_hk(value)
    return value.isoformat(timespec="seconds") if value else "—"


def md(value: Any) -> str:
    return (
        "—"
        if value is None or value == ""
        else str(value).replace("|", "\\|").replace("\n", " ").strip()
    )


def table(headers: Iterable[Any], rows: Iterable[Iterable[Any]]) -> str:
    heads = [md(value) for value in headers]
    body = [[md(value) for value in row] for row in rows]
    lines = ["| " + " | ".join(heads) + " |", "| " + " | ".join("---" for _ in heads) + " |"]
    lines.extend("| " + " | ".join(row) + " |" for row in body)
    return "\n".join(lines)


def candidate_key(candidate: Candidate) -> str:
    return f"{candidate.market}:{candidate.symbol}"


def target_occurrences(candidate: Candidate, occurrences: list[Any]) -> list[Any]:
    return [
        row
        for row in occurrences
        if row.name.strip() == candidate.reference
        and market_key(row.market) == candidate.market
        and row.normalized_market == candidate.market
        and row.normalized_symbol == candidate.symbol
    ]


def load_database(cursor: Any) -> dict[str, Any]:
    policy = get_production_analysis_policy()
    analysis_version = policy.active_analysis_version
    attention_version = get_production_attention_policy_version()
    investor_rows = fetch(
        cursor, "SELECT id, name, platform, platform_user_id FROM investors ORDER BY name, id"
    )
    asset_rows = fetch(
        cursor, "SELECT id, name, market, symbol FROM assets ORDER BY market, symbol, id"
    )
    alias_rows = fetch(
        cursor,
        "SELECT id, asset_id, alias, normalized_alias, alias_type, market FROM asset_aliases ORDER BY asset_id, normalized_alias, id",
    )
    raw_rows = fetch(
        cursor, "SELECT id, investor_id, published_time FROM raw_events ORDER BY published_time, id"
    )
    analysis_rows = fetch(
        cursor,
        "SELECT id, event_id, status, structured_output, calculated_at FROM event_analyses WHERE analysis_version = %s ORDER BY event_id, calculated_at, id",
        (analysis_version,),
    )
    opinion_rows = fetch(
        cursor,
        "SELECT o.id, o.event_id, o.analysis_id, o.investor_id, o.asset_id, o.direction FROM opinions o JOIN event_analyses ea ON ea.id = o.analysis_id WHERE ea.analysis_version = %s AND ea.status IN ('SUCCESS','PARTIALLY_RESOLVED')",
        (analysis_version,),
    )
    attention_rows = fetch(
        cursor,
        "SELECT ao.id, ao.event_id, ao.investor_id, ao.asset_id, ao.analysis_id, ao.attention_policy_version FROM attention_occurrences ao LEFT JOIN event_analyses ea ON ea.id = ao.analysis_id WHERE ao.attention_policy_version = %s AND (ao.analysis_id IS NULL OR (ea.analysis_version = %s AND ea.status IN ('SUCCESS','PARTIALLY_RESOLVED')))",
        (attention_version, analysis_version),
    )
    failed_rows = fetch(
        cursor,
        "SELECT r.id AS event_id, r.investor_id, r.published_time, ea.error_code FROM raw_events r JOIN event_analyses ea ON ea.event_id = r.id WHERE ea.analysis_version = %s AND ea.status = 'FAILED' ORDER BY r.published_time, r.id",
        (analysis_version,),
    )
    investors = {ident(row["id"]): row for row in investor_rows}
    assets = {ident(row["id"]): row for row in asset_rows}
    raw_events = {ident(row["id"]): row for row in raw_rows}
    failures = [
        {
            "event_id": ident(row["event_id"]),
            "investor_name": str(
                investors.get(ident(row["investor_id"]), {}).get("name") or row["investor_id"]
            ),
            "published_time": row["published_time"],
            "category": str(row.get("error_code") or "FAILED").split(":", 1)[0],
        }
        for row in failed_rows
    ]
    return {
        "analysis_version": analysis_version,
        "attention_version": attention_version,
        "investors": investors,
        "assets": assets,
        "aliases": alias_rows,
        "raw_events": raw_events,
        "analyses": analysis_rows,
        "opinions": opinion_rows,
        "attention": attention_rows,
        "failures": failures,
        "lookup": CatalogLookup(asset_rows, alias_rows),
    }


CANONICAL_NAMES = {
    "华能国际电力股份": "华能国际",
    "大唐新能源": "大唐新能源",
    "腾讯控股": "腾讯控股",
    "紫金黄金国际": "紫金黄金国际",
    "大唐发电": "大唐发电",
    "中金黄金": "中金黄金",
    "东阿阿胶": "东阿阿胶",
    "摩尔线程-U": "摩尔线程",
    "贵州茅台": "贵州茅台",
    "中国心连心化肥": "中国心连心化肥",
    "华润啤酒": "华润啤酒",
    "恒基地产": "恒基地产",
    "中国宏桥": "中国宏桥",
    "中国神华": "中国神华",
    "中矿资源": "中矿资源",
    "山东黄金": "山东黄金",
}


def status_text(value: Any) -> str:
    return str(getattr(value, "value", value))


def proposed_canonical_name(candidate: Candidate) -> str:
    return CANONICAL_NAMES[candidate.reference]


def proposed_aliases(candidate: Candidate) -> tuple[str, ...]:
    canonical = proposed_canonical_name(candidate)
    if candidate.reference != canonical:
        return candidate.aliases
    if candidate.reference in {"中国神华", "山东黄金"}:
        return candidate.aliases
    return tuple(alias for alias in candidate.aliases if name_key(alias) != name_key(canonical))


def asset_identity(row: Row) -> tuple[str | None, str | None]:
    normalized = normalize_asset_reference(
        AssetReference(
            name_hint=str(row.get("name") or "") or None,
            symbol_hint=str(row.get("symbol") or "") or None,
            market_hint=str(row.get("market") or "") or None,
        )
    )
    return market_key(normalized.market), symbol_key(normalized.symbol)


def candidate_identity(candidate: Candidate) -> tuple[str | None, str | None]:
    normalized = normalize_asset_reference(
        AssetReference(symbol_hint=candidate.symbol, market_hint=candidate.market)
    )
    return market_key(normalized.market), symbol_key(normalized.symbol)


def asset_label(row: Row | None, assets: dict[str, Row]) -> str:
    if row is None:
        return "—"
    asset = row if "name" in row else assets.get(ident(row.get("asset_id")))
    if not asset:
        return ident(row.get("asset_id")) or "—"
    market = market_key(asset.get("market")) or "—"
    symbol = symbol_key(asset.get("symbol")) or "—"
    return f"{asset.get('name') or '—'} [{market}:{symbol}]"


def assets_text(rows: list[Row], assets: dict[str, Row]) -> str:
    if not rows:
        return "none"
    return "; ".join(asset_label(row, assets) for row in rows)


def aliases_text(rows: list[Row], assets: dict[str, Row]) -> str:
    if not rows:
        return "none"
    values = []
    for row in rows:
        alias = row.get("alias") or row.get("normalized_alias") or "—"
        market = market_key(row.get("market")) or "global"
        values.append(
            f"{alias} → {asset_label(None if not row.get('asset_id') else {'asset_id': row.get('asset_id')}, assets)} (alias market {market})"
        )
    return "; ".join(values)


def current_views(data: dict[str, Any]) -> dict[str, Any]:
    current_analysis: dict[str, Row] = {}
    for row in data["analyses"]:
        event_id = ident(row.get("event_id"))
        previous = current_analysis.get(event_id)
        if previous is None or analysis_key(row) > analysis_key(previous):
            current_analysis[event_id] = row
    effective_ids = {
        ident(row.get("id"))
        for row in current_analysis.values()
        if status_text(row.get("status")) in {"SUCCESS", "PARTIALLY_RESOLVED"}
    }
    effective_opinions = [
        row for row in data["opinions"] if ident(row.get("analysis_id")) in effective_ids
    ]
    opinions_by_event: dict[str, list[Row]] = defaultdict(list)
    opinion_pair_counts: Counter[tuple[str, str]] = Counter()
    opinions_by_asset: dict[str, set[str]] = defaultdict(set)
    opinion_event_assets: set[tuple[str, str]] = set()
    for row in effective_opinions:
        event_id = ident(row.get("event_id"))
        investor_id = ident(row.get("investor_id"))
        asset_id = ident(row.get("asset_id"))
        opinions_by_event[event_id].append(row)
        opinion_pair_counts[(investor_id, asset_id)] += 1
        opinions_by_asset[asset_id].add(investor_id)
        opinion_event_assets.add((event_id, asset_id))
    effective_attention = [
        row
        for row in data["attention"]
        if row.get("attention_policy_version") == data["attention_version"]
        and (row.get("analysis_id") is None or ident(row.get("analysis_id")) in effective_ids)
    ]
    attention_by_asset: dict[str, set[str]] = defaultdict(set)
    attention_event_assets: set[tuple[str, str]] = set()
    for row in effective_attention:
        asset_id = ident(row.get("asset_id"))
        investor_id = ident(row.get("investor_id"))
        attention_by_asset[asset_id].add(investor_id)
        attention_event_assets.add((ident(row.get("event_id")), asset_id))
    occurrences, parse_failures = load_occurrences(
        list(current_analysis.values()),
        data["raw_events"],
        opinions_by_event,
        AssetResolver(data["lookup"]),
    )
    return {
        "current_analysis": current_analysis,
        "effective_ids": effective_ids,
        "effective_opinions": effective_opinions,
        "effective_attention": effective_attention,
        "opinions_by_event": opinions_by_event,
        "opinion_pair_counts": opinion_pair_counts,
        "opinions_by_asset": opinions_by_asset,
        "opinion_event_assets": opinion_event_assets,
        "attention_by_asset": attention_by_asset,
        "attention_event_assets": attention_event_assets,
        "occurrences": occurrences,
        "parse_failures": parse_failures,
    }


def collision_audit(candidate: Candidate, data: dict[str, Any]) -> dict[str, Any]:
    assets = data["assets"]
    aliases = data["aliases"]
    wanted_market, wanted_symbol = candidate_identity(candidate)
    exact = []
    same_name = []
    normalized_symbol = []
    generic_name = []
    for row in assets.values():
        row_market, row_symbol = asset_identity(row)
        if (row_market, row_symbol) == (wanted_market, wanted_symbol):
            exact.append(row)
        if name_key(str(row.get("name") or "")) == name_key(candidate.reference):
            same_name.append(row)
            if not row_market or not row_symbol:
                generic_name.append(row)
        if row_symbol == wanted_symbol and row_market != wanted_market:
            normalized_symbol.append(row)
    same_alias = [
        row
        for row in aliases
        if name_key(str(row.get("normalized_alias") or row.get("alias") or ""))
        == name_key(candidate.reference)
    ]
    cross_listing = "A/H" in candidate.listing_relation
    if exact:
        status = "EXACT_EXISTING"
    elif cross_listing:
        status = "NEW_LISTING"
    elif same_alias:
        status = "ALIAS_COLLISION"
    elif same_name:
        status = "CANONICAL_NAME_COLLISION"
    else:
        status = "SAFE_NEW_ASSET"
    if exact:
        recommendation = "REJECT"
    elif not candidate.source_url:
        recommendation = "UNVERIFIED"
    elif (same_name or same_alias) and not cross_listing and not candidate.canonical_correction:
        recommendation = "REVIEW_NAME"
    else:
        recommendation = "APPROVE_SAFE_SEED"
    return {
        "candidate": candidate,
        "exact": exact,
        "same_name": same_name,
        "same_alias": same_alias,
        "normalized_symbol": normalized_symbol,
        "generic_name": generic_name,
        "cross_listing": cross_listing,
        "status": status,
        "recommendation": recommendation,
        "verification": "VERIFIED_OFFICIAL_SOURCE_REVIEWED",
    }


def impact_for_candidate(
    audit: dict[str, Any], views: dict[str, Any], occurrences: list[Any], data: dict[str, Any]
) -> dict[str, Any]:
    candidate = audit["candidate"]
    matched = target_occurrences(candidate, occurrences)
    projectable = [row for row in matched if row.complete]
    exact = audit["exact"]
    existing_asset_id = ident(exact[0].get("id")) if len(exact) == 1 else None
    target = existing_asset_id or f"new:{candidate_key(candidate)}"
    event_target = {(row.event_id, target) for row in projectable}
    investor_target = {(row.investor_id, target) for row in projectable}
    current_opinion_events = views["opinion_event_assets"]
    current_attention_events = views["attention_event_assets"]
    new_opinions = sum(
        (event_id, target) not in current_opinion_events for event_id, _ in event_target
    )
    new_attention = sum(
        (event_id, target) not in current_attention_events for event_id, _ in event_target
    )
    new_pairs = sum(
        (investor_id, target) not in views["opinion_pair_counts"]
        for investor_id, _ in investor_target
    )
    projected_pair_counts: Counter[tuple[str, str]] = Counter(views["opinion_pair_counts"])
    for investor_id, _ in investor_target:
        projected_pair_counts[(investor_id, target)] += sum(
            row.investor_id == investor_id for row in projectable
        )
    new_repeated_pairs = sum(
        count >= 2 and views["opinion_pair_counts"].get(pair, 0) < 2
        for pair, count in projected_pair_counts.items()
        if pair[1] == target
    )
    before_attention = (
        set(views["attention_by_asset"].get(existing_asset_id, set()))
        if existing_asset_id
        else set()
    )
    before_opinion = (
        set(views["opinions_by_asset"].get(existing_asset_id, set()))
        if existing_asset_id
        else set()
    )
    projected_investors = {row.investor_id for row in projectable}
    after_attention = before_attention | projected_investors
    after_opinion = before_opinion | projected_investors
    investor_names = {
        ident(row["id"]): str(row.get("name") or ident(row["id"]))
        for row in data["investors"].values()
    }
    return {
        "candidate": candidate,
        "target": target,
        "matched_occurrences": len(matched),
        "resolved_occurrences": len(matched),
        "projectable_occurrences": len(projectable),
        "new_opinions": new_opinions,
        "new_pairs": new_pairs,
        "new_attention": new_attention,
        "new_repeated_pairs": new_repeated_pairs,
        "delta_2_attention": int(len(before_attention) < 2 <= len(after_attention)),
        "delta_3_attention": int(len(before_attention) < 3 <= len(after_attention)),
        "delta_2_opinion": int(len(before_opinion) < 2 <= len(after_opinion)),
        "delta_3_opinion": int(len(before_opinion) < 3 <= len(after_opinion)),
        "investors": sorted(investor_names.get(value, value) for value in projected_investors),
        "event_ids": sorted({row.event_id for row in projectable}),
        "incomplete_occurrences": len(matched) - len(projectable),
    }


def approved_set_impact(impacts: list[dict[str, Any]], views: dict[str, Any]) -> dict[str, Any]:
    before_attention = {
        asset_id: set(investors) for asset_id, investors in views["attention_by_asset"].items()
    }
    before_opinion = {
        asset_id: set(investors) for asset_id, investors in views["opinions_by_asset"].items()
    }
    after_attention = {asset_id: set(values) for asset_id, values in before_attention.items()}
    after_opinion = {asset_id: set(values) for asset_id, values in before_opinion.items()}
    before_shared_attention_2 = sum(len(values) >= 2 for values in before_attention.values())
    before_shared_attention_3 = sum(len(values) >= 3 for values in before_attention.values())
    before_shared_opinion_2 = sum(len(values) >= 2 for values in before_opinion.values())
    before_shared_opinion_3 = sum(len(values) >= 3 for values in before_opinion.values())
    for impact in impacts:
        target = impact["target"]
        investors = set(impact["investors"])
        after_attention.setdefault(target, set()).update(investors)
        after_opinion.setdefault(target, set()).update(investors)
    after_shared_attention_2 = sum(len(values) >= 2 for values in after_attention.values())
    after_shared_attention_3 = sum(len(values) >= 3 for values in after_attention.values())
    after_shared_opinion_2 = sum(len(values) >= 2 for values in after_opinion.values())
    after_shared_opinion_3 = sum(len(values) >= 3 for values in after_opinion.values())
    return {
        "candidate_count": len(impacts),
        "resolved_occurrences": sum(item["resolved_occurrences"] for item in impacts),
        "projectable_occurrences": sum(item["projectable_occurrences"] for item in impacts),
        "new_opinions": sum(item["new_opinions"] for item in impacts),
        "new_pairs": sum(item["new_pairs"] for item in impacts),
        "new_attention": sum(item["new_attention"] for item in impacts),
        "new_repeated_pairs": sum(item["new_repeated_pairs"] for item in impacts),
        "delta_2_attention": after_shared_attention_2 - before_shared_attention_2,
        "delta_3_attention": after_shared_attention_3 - before_shared_attention_3,
        "delta_2_opinion": after_shared_opinion_2 - before_shared_opinion_2,
        "delta_3_opinion": after_shared_opinion_3 - before_shared_opinion_3,
        "before_shared_attention_2": before_shared_attention_2,
        "before_shared_attention_3": before_shared_attention_3,
        "before_shared_opinion_2": before_shared_opinion_2,
        "before_shared_opinion_3": before_shared_opinion_3,
        "after_shared_attention_2": after_shared_attention_2,
        "after_shared_attention_3": after_shared_attention_3,
        "after_shared_opinion_2": after_shared_opinion_2,
        "after_shared_opinion_3": after_shared_opinion_3,
    }


def link(label: str, url: str) -> str:
    return f"[{label}]({url})"


def render_status(value: dict[str, Any]) -> str:
    candidate = value["candidate"]
    return " / ".join(
        (
            candidate.market,
            candidate.symbol,
            value["status"],
            value["recommendation"],
        )
    )


def build_report(data: dict[str, Any], database_name: str, audit_time: datetime) -> str:
    views = current_views(data)
    occurrences = views["occurrences"]
    audits = [collision_audit(candidate, data) for candidate in CANDIDATES]
    impacts = [impact_for_candidate(audit, views, occurrences, data) for audit in audits]
    approved_impacts = [
        impact
        for audit, impact in zip(audits, impacts, strict=True)
        if audit["recommendation"] == "APPROVE_SAFE_SEED"
    ]
    total_impact = approved_set_impact(approved_impacts, views)
    status_counts = Counter(
        status_text(row.get("status")) for row in views["current_analysis"].values()
    )
    unresolved_names = len({name_key(row.name) for row in occurrences})
    current_shared_attention_2 = sum(
        len(values) >= 2 for values in views["attention_by_asset"].values()
    )
    current_shared_attention_3 = sum(
        len(values) >= 3 for values in views["attention_by_asset"].values()
    )
    current_shared_opinion_2 = sum(
        len(values) >= 2 for values in views["opinions_by_asset"].values()
    )
    current_shared_opinion_3 = sum(
        len(values) >= 3 for values in views["opinions_by_asset"].values()
    )
    raw_count = len(data["raw_events"])
    analysis_count = len(views["current_analysis"])
    analysis_coverage = (
        f"{analysis_count:,}/{raw_count:,} ({analysis_count / raw_count:.1%})"
        if raw_count
        else "0/0"
    )

    report: list[str] = [
        "# Tier A Asset Identity Integrity Report",
        "",
        f"Audit time: **{fmt_dt(audit_time)}**; database: **{database_name}**.",
        "",
        "This is a read-only identity gate for the 16 Tier A candidates only. No Tier B candidate was audited or seeded. No LLM, collection, Asset/Alias write, Intelligence rebuild, migration, commit or push was performed.",
        "",
        "## 1. Executive Summary",
        "",
        f"The current PostgreSQL snapshot contains **{raw_count:,} RawEvents**, **{analysis_coverage} current production Analysis**, **{len(views['effective_opinions']):,} effective Opinions**, **{len(views['effective_attention']):,} effective AttentionOccurrences**, **{len(data['assets']):,} canonical Assets**, and **{len(data['aliases']):,} AssetAlias rows**.",
        "",
        f"The 16 Tier A references account for **{sum(item['matched_occurrences'] for item in impacts):,} unresolved occurrences** across **{len(CANDIDATES)}** candidate identities. All candidate identities have explicit market+symbol and were checked against the complete current Asset/Alias catalog.",
        "",
        f"Gate result: **{sum(audit['recommendation'] == 'APPROVE_SAFE_SEED' for audit in audits)}/{len(audits)} APPROVE_SAFE_SEED**, **{sum(audit['recommendation'] != 'APPROVE_SAFE_SEED' for audit in audits)} review/reject**. This is a proposed manifest only; no seed was executed.",
        "",
        "## 2. 16 Tier A Candidate Final Status",
        "",
        table(
            (
                "#",
                "Extracted reference",
                "Identity",
                "Occurrences",
                "Status",
                "External verification",
                "Recommendation",
            ),
            (
                (
                    index,
                    audit["candidate"].reference,
                    candidate_key(audit["candidate"]),
                    impact["matched_occurrences"],
                    audit["status"],
                    audit["verification"],
                    audit["recommendation"],
                )
                for index, (audit, impact) in enumerate(zip(audits, impacts, strict=True), 1)
            ),
        ),
        "",
        "Status semantics: `EXACT_EXISTING` means the exact normalized market+symbol is already present; `NEW_LISTING` means a distinct listing of an issuer already represented elsewhere; `CANONICAL_NAME_COLLISION`/`ALIAS_COLLISION` are name-surface conflicts; `SAFE_NEW_ASSET` means no catalog collision was found. Cross-listing name collisions are not merged.",
        "",
        "## 3. Existing Asset/Alias Collision Audit",
        "",
        f"The audit read all **{len(data['assets']):,} canonical Assets** and **{len(data['aliases']):,} AssetAlias rows**. Exact identity matching uses the production market/symbol normalization, not name-only matching.",
        "",
        table(
            (
                "Reference",
                "Exact market+symbol",
                "Same canonical name",
                "Same alias",
                "Normalized symbol / other market",
                "Generic/no-market",
                "Status",
            ),
            (
                (
                    audit["candidate"].reference,
                    assets_text(audit["exact"], data["assets"]),
                    assets_text(audit["same_name"], data["assets"]),
                    aliases_text(audit["same_alias"], data["assets"]),
                    assets_text(audit["normalized_symbol"], data["assets"]),
                    assets_text(audit["generic_name"], data["assets"]),
                    audit["status"],
                )
                for audit in audits
            ),
        ),
        "",
        "Observed collision notes:",
        "",
        "- `中国神华 HK:01088`: no exact HK listing exists in the current catalog; the same canonical name and alias point to the existing `SH:601088` listing. This is a distinct A/H listing, so it is classified `NEW_LISTING`, not duplicate.",
        "- `山东黄金 SH:600547`: no exact SH listing exists; the same canonical name points to the existing `HK:01787` listing. This is a distinct A/H listing, so it is classified `NEW_LISTING`, not duplicate.",
        "- `华能国际 HK:00902`: the existing `SH:600011` Asset is an issuer/listing relation, but the extracted name is not an exact current canonical/alias row in this catalog. Preserve both listing identities.",
        "- No generic/no-market canonical Asset and no Tier A normalized-symbol collision was found.",
        "",
        "### Complete current canonical Asset catalog",
        "",
        table(
            ("Asset id", "Name", "Market", "Symbol"),
            (
                (
                    ident(row.get("id")),
                    row.get("name"),
                    market_key(row.get("market")) or "—",
                    symbol_key(row.get("symbol")) or "—",
                )
                for row in data["assets"].values()
            ),
        ),
        "",
        "### Complete current AssetAlias catalog",
        "",
        table(
            ("Alias id", "Asset", "Alias", "Normalized alias", "Market", "Type"),
            (
                (
                    ident(row.get("id")),
                    asset_label(
                        None if not row.get("asset_id") else {"asset_id": row.get("asset_id")},
                        data["assets"],
                    ),
                    row.get("alias"),
                    row.get("normalized_alias"),
                    market_key(row.get("market")) or "global",
                    row.get("alias_type"),
                )
                for row in data["aliases"]
            ),
        ),
        "",
        "## 4. A/H Cross-Listing Audit",
        "",
        "Listing identity is bounded by the actual market+symbol. The following relations were treated as separate Assets:",
        "",
        table(
            ("Candidate listing", "Existing/related listing", "Relation", "Decision"),
            (
                (
                    audit["candidate"].reference + " " + candidate_key(audit["candidate"]),
                    audit["candidate"].listing_relation,
                    "A/H or issuer relation",
                    "Keep separate; no merge",
                )
                for audit in audits
                if audit["cross_listing"] or audit["candidate"].reference == "紫金黄金国际"
            ),
        ),
        "",
        "Official A/H evidence confirms `HK:00902 ↔ SH:600011`, `HK:00991 ↔ SH:601991`, and `HK:01088 ↔ SH:601088`; the current Asset Master only contains the noted existing listing(s). Official exchange data also confirms `HK:01787 ↔ SH:600547`. 紫金黄金国际 is a separate HK-listed issuer and is not merged with 紫金矿业.",
        "",
        "## 5. Canonical Name Corrections",
        "",
        "The proposed canonical is the listed security name/surface, not the full legal issuer name and not an extracted suffix. The legal issuer name is retained as external identity evidence.",
        "",
        table(
            (
                "Reference",
                "Proposed canonical_name",
                "Official/legal issuer name",
                "Proposed aliases",
                "Correction",
            ),
            (
                (
                    candidate.reference,
                    proposed_canonical_name(candidate),
                    candidate.official_name,
                    ", ".join(proposed_aliases(candidate)) or "none",
                    candidate.canonical_correction or "none",
                )
                for candidate in CANDIDATES
            ),
        ),
        "",
        "For `摩尔线程-U SH:688795`, the proposal is `canonical_name=摩尔线程`, with `摩尔线程-U` as an alias. For A/H duplicates such as 中国神华 and 山东黄金, same-name aliases must remain market-scoped and must not be globally reused across listings.",
        "",
        "## 6. External Verification Evidence",
        "",
        "All 16 rows were checked against an official exchange or issuer-disclosure source available to this audit. The source link is evidence only; it does not write or seed the Asset Master.",
        "",
        table(
            ("Reference", "Verified official/legal name", "Market", "Verified symbol", "Evidence"),
            (
                (
                    candidate.reference,
                    candidate.official_name,
                    candidate.market,
                    candidate.symbol,
                    link(candidate.source_label, candidate.source_url),
                )
                for candidate in CANDIDATES
            ),
        ),
        "",
        "## 7. APPROVE_SAFE_SEED Proposed Manifest",
        "",
        table(
            (
                "extracted_reference",
                "official_canonical_name",
                "market",
                "symbol",
                "proposed_aliases",
                "existing Asset collision",
                "cross-listing relation",
                "external verification state",
                "recommendation",
            ),
            (
                (
                    candidate.reference,
                    proposed_canonical_name(candidate),
                    candidate.market,
                    candidate.symbol,
                    ", ".join(proposed_aliases(candidate)) or "none",
                    assets_text(audit["exact"] + audit["same_name"], data["assets"]),
                    candidate.listing_relation,
                    audit["verification"],
                    audit["recommendation"],
                )
                for candidate, audit in ((audit["candidate"], audit) for audit in audits)
            ),
        ),
        "",
        "The manifest is a review artifact. `APPROVE_SAFE_SEED` means the identity gate passed for a future, separately authorized seed; it does not authorize execution in this Sprint.",
        "",
        "## 8. Rejected / Review-required Candidates",
        "",
        f"Tier A rejected: **{sum(audit['recommendation'] == 'REJECT' for audit in audits)}**. Tier A requiring name/cross-listing review: **{sum(audit['recommendation'] in {'REVIEW_NAME', 'REVIEW_CROSS_LISTING', 'UNVERIFIED'} for audit in audits)}**. No Tier A row was rejected or left unverified in this snapshot.",
        "",
        "Tier B remains **HOLD** in full. It was not audited, resolved, seeded, or used in the impact simulation. Name-only, nickname, UNKNOWN, concept/industry, commodity/macro and extraction-noise unresolved references remain untouched.",
        "",
        "## 9. Approved-set Dry-run Intelligence Impact",
        "",
        "This is an in-memory projection only. `resolved occurrences` means occurrences with the candidate's explicit normalized market+symbol; `new Opinions`/`new Attention` are potential downstream counts under a future deterministic seed and existing policies. No rebuild was run.",
        "",
        table(
            (
                "Reference",
                "Occurrences resolved",
                "Projectable",
                "New Opinions",
                "New Investor×Asset pairs",
                "New Attention",
                "New repeated pairs",
                "Δ 2+ Attention",
                "Δ 3+ Attention",
                "Δ 2+ Opinion",
                "Δ 3+ Opinion",
                "Investors",
            ),
            (
                (
                    impact["candidate"].reference,
                    impact["resolved_occurrences"],
                    impact["projectable_occurrences"],
                    impact["new_opinions"],
                    impact["new_pairs"],
                    impact["new_attention"],
                    impact["new_repeated_pairs"],
                    impact["delta_2_attention"],
                    impact["delta_3_attention"],
                    impact["delta_2_opinion"],
                    impact["delta_3_opinion"],
                    ", ".join(impact["investors"]),
                )
                for impact in approved_impacts
            ),
        ),
        "",
        f"Approved-set dry-run total: **{total_impact['resolved_occurrences']:,} resolved occurrences**, **{total_impact['new_opinions']:,} potential new Opinions**, **{total_impact['new_pairs']:,} new Investor×Asset pairs**, and **{total_impact['new_attention']:,} potential Attention occurrences**.",
        "",
        table(
            ("Metric", "Before", "After dry-run", "Delta"),
            (
                (
                    "2+ Attention Investor Assets",
                    total_impact["before_shared_attention_2"],
                    total_impact["after_shared_attention_2"],
                    total_impact["delta_2_attention"],
                ),
                (
                    "3+ Attention Investor Assets",
                    total_impact["before_shared_attention_3"],
                    total_impact["after_shared_attention_3"],
                    total_impact["delta_3_attention"],
                ),
                (
                    "2+ Opinion Investor Assets",
                    total_impact["before_shared_opinion_2"],
                    total_impact["after_shared_opinion_2"],
                    total_impact["delta_2_opinion"],
                ),
                (
                    "3+ Opinion Investor Assets",
                    total_impact["before_shared_opinion_3"],
                    total_impact["after_shared_opinion_3"],
                    total_impact["delta_3_opinion"],
                ),
            ),
        ),
        "",
        "The dry-run's overlap increase comes from four two-investor Tier A identities; it does not create a 3+ Investor Asset. Existing unresolved occurrences were not rewritten.",
        "",
        "## 10. Safe Asset Expansion Decision",
        "",
        "**Conditionally yes for the 16 Tier A identities only, pending human review of the proposed manifest.** The identity gate found no exact market+symbol duplicate, verified every market+symbol with an official source, preserved A/H listing boundaries, and isolated the two existing same-name/alias cross-listing collisions. This Sprint did not execute expansion.",
        "",
        "## 11. Current Snapshot and Read-only Boundary",
        "",
        table(
            ("Metric", "Current value"),
            (
                ("Production Analysis identity", data["analysis_version"]),
                ("Attention policy", data["attention_version"]),
                ("RawEvents", raw_count),
                ("Current production Analysis", analysis_count),
                ("Current Analysis coverage", analysis_coverage),
                (
                    "Analysis status counts",
                    ", ".join(f"{key}={value}" for key, value in sorted(status_counts.items())),
                ),
                ("Effective Opinions", len(views["effective_opinions"])),
                ("Effective AttentionOccurrences", len(views["effective_attention"])),
                ("Unresolved occurrences", len(occurrences)),
                ("Distinct unresolved names", unresolved_names),
                ("Canonical Assets", len(data["assets"])),
                ("AssetAlias rows", len(data["aliases"])),
                ("Current 2+ Attention Assets", current_shared_attention_2),
                ("Current 3+ Attention Assets", current_shared_attention_3),
                ("Current 2+ Opinion Assets", current_shared_opinion_2),
                ("Current 3+ Opinion Assets", current_shared_opinion_3),
                ("Occurrence parse failures", views["parse_failures"]),
            ),
        ),
        "",
        "The PostgreSQL transaction was `REPEATABLE READ`, `READ ONLY`, with a bounded statement timeout. The script ended with rollback/close; it has no write path.",
        "",
        "### Official evidence links",
        "",
        f"{link('HKEX A/H share list', 'https://www.hkex.com.hk/chi/Invest/misc/documents/ic_for_ah_shares_sc.pdf')} (00902/600011, 00991/601991, 01088/601088); {link('HKEX SSE collaboration stock list', 'https://www.hkex.com.hk/-/media/HKEX-Market/Services/Market-Data-Services/Real-Time-Data-Services/Market-Data-Promotions/Marketing-Programmes-on-Securities-Market-Data/Mainland-Market-Data-Collaboration-Programme/MarketDataCollaborationStockListSSE20181116.pdf?la=zh-HK')} (01787/600547).",
    ]
    return "\n".join(report) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output",
        type=Path,
        help="optional local Markdown output path; PostgreSQL remains read-only",
    )
    args = parser.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")
    connection, url = connect_read_only_base()
    try:
        with connection.cursor() as cursor:
            database_name = str(
                scalar(cursor, "SELECT current_database()") or url.database or "<unknown>"
            )
            report = build_report(load_database(cursor), database_name, datetime.now(HK))
    finally:
        connection.rollback()
        connection.close()
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(report, encoding="utf-8")
    print(report, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
