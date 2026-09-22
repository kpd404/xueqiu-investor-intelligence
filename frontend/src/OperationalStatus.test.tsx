import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { OperationalStatusIndicator } from "./App";
import type { OperationalStatusResponse } from "./types";

function status(overrides: Partial<OperationalStatusResponse>): OperationalStatusResponse {
  return {
    status: "HEALTHY",
    freshness: "FRESH",
    freshness_age_seconds: 12 * 60,
    last_refresh_started_at: "2026-09-20T08:00:00Z",
    last_refresh_finished_at: "2026-09-20T08:01:00Z",
    last_successful_refresh_at: "2026-09-20T08:01:00Z",
    latest_status: "SUCCESS",
    latest_trigger: "SCHEDULED",
    latest_failure_stage: null,
    latest_failure_code: null,
    next_expected_refresh_at: "2026-09-20T09:01:00Z",
    cdp_requirement: "AUTHENTICATED_EDGE_CDP_REQUIRED",
    ...overrides
  };
}

describe("OperationalStatusIndicator", () => {
  it("shows healthy freshness in user language", () => {
    render(<OperationalStatusIndicator status={status({})} error={null} />);
    expect(screen.getByText("运行正常")).toBeInTheDocument();
    expect(screen.getByText("数据刷新于 12分钟前")).toBeInTheDocument();
  });

  it("shows stale freshness without exposing implementation details", () => {
    render(
      <OperationalStatusIndicator
        status={status({ status: "STALE", freshness: "STALE", freshness_age_seconds: 2 * 3600 })}
        error={null}
      />
    );
    expect(screen.getByText("数据较旧")).toBeInTheDocument();
    expect(screen.getByText("数据刷新于 2小时前")).toBeInTheDocument();
    expect(screen.queryByText(/CollectionRun|stage|Postgres/i)).not.toBeInTheDocument();
  });

  it("translates authentication failure", () => {
    render(
      <OperationalStatusIndicator
        status={status({
          status: "ACTION_REQUIRED",
          latest_status: "FAILED",
          latest_failure_code: "AUTH_REQUIRED"
        })}
        error={null}
      />
    );
    expect(screen.getByText("需要重新登录雪球")).toBeInTheDocument();
  });

  it("translates CDP unavailability as an action", () => {
    render(
      <OperationalStatusIndicator
        status={status({
          status: "ACTION_REQUIRED",
          latest_status: "FAILED",
          latest_failure_code: "CDP_UNAVAILABLE"
        })}
        error={null}
      />
    );
    expect(screen.getByText("需要重新登录雪球")).toBeInTheDocument();
  });

  it("translates risk control", () => {
    render(
      <OperationalStatusIndicator
        status={status({
          status: "SOURCE_LIMITED",
          latest_status: "FAILED",
          latest_failure_code: "RISK_CONTROLLED"
        })}
        error={null}
      />
    );
    expect(screen.getByText("数据源暂时受限")).toBeInTheDocument();
  });

  it("translates generic refresh failure", () => {
    render(
      <OperationalStatusIndicator
        status={status({
          status: "ACTION_REQUIRED",
          latest_status: "FAILED",
          latest_failure_code: "DOWNSTREAM_FAILURE"
        })}
        error={null}
      />
    );
    expect(screen.getByText("刷新失败")).toBeInTheDocument();
  });

  it("shows unknown when no run exists", () => {
    render(
      <OperationalStatusIndicator
        status={status({
          status: "UNKNOWN",
          freshness: "UNKNOWN",
          freshness_age_seconds: null,
          latest_status: null,
          latest_trigger: null,
          last_successful_refresh_at: null
        })}
        error={null}
      />
    );
    expect(screen.getByText("刷新状态未知")).toBeInTheDocument();
    expect(screen.getByText("暂无成功刷新记录")).toBeInTheDocument();
  });

  it("shows a safe unavailable state when the status API fails", () => {
    render(<OperationalStatusIndicator status={null} error={new Error("network")} />);
    expect(screen.getByText("刷新状态不可用")).toBeInTheDocument();
    expect(screen.queryByText("network")).not.toBeInTheDocument();
  });
});
