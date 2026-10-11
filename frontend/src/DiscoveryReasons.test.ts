import { describe, expect, it } from "vitest";

import { formatEnum } from "./presentation";

describe("Discovery current evidence labels", () => {
  it("describes both cross direction evidence keys neutrally", () => {
    expect(formatEnum("CROSS_INVESTOR_ACTIVITY")).toBe("多人观点方向证据");
    expect(formatEnum("CONSENSUS_ACTIVITY")).toBe("多人观点方向证据");
  });
});
