"""HTTP smoke test for the Intelligence Read API against configured PostgreSQL."""

from __future__ import annotations

from collections.abc import Iterable

from fastapi.testclient import TestClient

from backend.app.main import app

BASE_PATH = "/api/v1/intelligence"
EXPECTED_PATHS = {
    f"{BASE_PATH}/assets",
    f"{BASE_PATH}/assets/{{asset_id}}",
    f"{BASE_PATH}/assets/{{asset_id}}/timeline",
}


def _find_item(items: Iterable[dict[str, object]], market: str, symbol: str) -> dict[str, object]:
    matches = [
        item for item in items if item.get("market") == market and item.get("symbol") == symbol
    ]
    if len(matches) != 1:
        raise AssertionError(f"expected one {market}:{symbol} list item, got {len(matches)}")
    return matches[0]


def _run() -> int:
    with TestClient(app) as client:
        openapi_response = client.get("/openapi.json")
        if openapi_response.status_code != 200:
            raise AssertionError(f"OpenAPI status={openapi_response.status_code}")
        paths = set(openapi_response.json()["paths"])
        if not EXPECTED_PATHS <= paths:
            raise AssertionError(f"missing Intelligence paths: {EXPECTED_PATHS - paths}")

        list_response = client.get(f"{BASE_PATH}/assets")
        if list_response.status_code != 200:
            raise AssertionError(f"Asset list status={list_response.status_code}")
        list_payload = list_response.json()
        items = list_payload["items"]
        print("# Intelligence Read API V0 PostgreSQL HTTP Smoke")
        print(f"GET {BASE_PATH}/assets -> {list_response.status_code}")
        print(
            f"total={list_payload['total']} page_items={len(items)} "
            f"limit={list_payload['limit']} offset={list_payload['offset']} "
            f"has_more={list_payload['has_more']}"
        )
        if list_payload["total"] != 45:
            raise AssertionError(
                f"expected current calibration total 45, got {list_payload['total']}"
            )
        if any("event_timeline" in item for item in items):
            raise AssertionError("Asset list response leaked full event_timeline")

        cases = (
            ("招商轮船", "SH", "601872"),
            ("龙源电力", "HK", "00916"),
            ("贵州茅台", "SH", "600519"),
            ("华能国际", "HK", "00902"),
            ("大唐发电", "HK", "00991"),
        )
        for expected_name, market, symbol in cases:
            item = _find_item(items, market, symbol)
            asset_id = item["asset_id"]
            detail_response = client.get(f"{BASE_PATH}/assets/{asset_id}")
            timeline_response = client.get(f"{BASE_PATH}/assets/{asset_id}/timeline")
            if detail_response.status_code != 200 or timeline_response.status_code != 200:
                raise AssertionError(
                    f"{market}:{symbol} detail/timeline status="
                    f"{detail_response.status_code}/{timeline_response.status_code}"
                )
            detail = detail_response.json()
            timeline = timeline_response.json()
            if detail["asset_name"] != expected_name:
                raise AssertionError(
                    f"{market}:{symbol} expected {expected_name}, got {detail['asset_name']}"
                )
            print(
                f"GET {BASE_PATH}/assets/{asset_id} -> {detail_response.status_code}; "
                f"timeline -> {timeline_response.status_code}; "
                f"asset={detail['asset_name']} {market}:{symbol}; "
                f"attention={detail['attention_summary']['attention_investor_count']}; "
                f"investors={len(detail['investor_views'])}; "
                f"events={len(timeline['events'])}; "
                f"missing_thesis={detail['data_quality']['missing_thesis_comparison_count']}"
            )
            if timeline["completeness"] != "UNKNOWN":
                raise AssertionError(f"{market}:{symbol} completeness was not UNKNOWN")

            if symbol == "601872":
                sequence = detail["observed_attention_sequence"]
                names = [
                    sequence["first_observed"]["investor_name"],
                    *[value["investor_name"] for value in sequence["later_observations"]],
                ]
                if names != ["笨笨的投资者2", "沈阳城", "Captain-Nemo船长", "看好股市的新人"]:
                    raise AssertionError(f"招商轮船 order mismatch: {names}")
            elif symbol == "00916":
                if detail["alignment"]["directional_alignment_state"] != "MIXED_DIRECTION":
                    raise AssertionError("龙源电力 Alignment mismatch")
                if detail["consensus"]["consensus_state"] != "DIVERGENT":
                    raise AssertionError("龙源电力 Consensus mismatch")
            elif symbol == "600519":
                attention_investors = detail["attention_summary"]["attention_investor_count"]
                opinion_investors = sum(
                    value["opinion_count"] > 0 for value in detail["investor_views"]
                )
                if (attention_investors, opinion_investors) != (3, 1):
                    raise AssertionError(
                        f"贵州茅台 breadth mismatch: {attention_investors}/{opinion_investors}"
                    )
            elif symbol == "00991":
                opinion_count = sum(value["opinion_count"] for value in detail["investor_views"])
                thesis_count = sum(
                    value["thesis_change_count"] for value in detail["investor_views"]
                )
                missing = detail["data_quality"]["missing_thesis_comparison_count"]
                if (opinion_count, thesis_count, missing) != (14, 13, 1):
                    raise AssertionError(
                        f"大唐发电 gap mismatch: {opinion_count}/{thesis_count}/{missing}"
                    )

        hk_item = _find_item(items, "HK", "01787")
        sh_item = _find_item(items, "SH", "600547")
        if hk_item["asset_id"] == sh_item["asset_id"]:
            raise AssertionError("山东黄金 A/H listing ids were merged")
        hk_detail = client.get(f"{BASE_PATH}/assets/{hk_item['asset_id']}").json()
        sh_detail = client.get(f"{BASE_PATH}/assets/{sh_item['asset_id']}").json()
        if (hk_detail["market"], hk_detail["symbol"]) != ("HK", "01787"):
            raise AssertionError("HK:01787 detail identity mismatch")
        if (sh_detail["market"], sh_detail["symbol"]) != ("SH", "600547"):
            raise AssertionError("SH:600547 detail identity mismatch")
        print(
            f"山东黄金 separation -> HK id={hk_item['asset_id']}; "
            f"SH id={sh_item['asset_id']}; distinct=True"
        )
        print("OpenAPI paths: PASS")
        print("Real PostgreSQL HTTP smoke: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(_run())
