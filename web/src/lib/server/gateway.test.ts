import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("server-only", () => ({}));
vi.mock("next/navigation", () => ({
  redirect: (to: string) => {
    throw new Error(`redirect ${to}`);
  },
}));
vi.mock("./env", () => ({ env: { gatewayUrl: () => "http://gw" } }));
vi.mock("./session", () => ({
  getSession: async () => ({ userId: "u", email: "a@b.test", accessToken: "tok" }),
}));

import { gateway, GatewayError, NO_ACCOUNT } from "./gateway";

const json = (status: number, body: unknown) =>
  new Response(JSON.stringify(body), { status, headers: { "content-type": "application/json" } });

let fetchMock: ReturnType<typeof vi.fn>;

beforeEach(() => {
  fetchMock = vi.fn();
  vi.stubGlobal("fetch", fetchMock);
});
afterEach(() => vi.unstubAllGlobals());

const calls = () => fetchMock.mock.calls.map(([url, init]) => `${init?.method ?? "GET"} ${url}`);

describe("gateway()", () => {
  it("creates a missing account and retries the call once", async () => {
    fetchMock
      .mockResolvedValueOnce(json(403, { detail: NO_ACCOUNT }))
      .mockResolvedValueOnce(json(200, { handle: "alice" }))
      .mockResolvedValueOnce(json(200, [{ id: "p1" }]));

    await expect(gateway("/v1/problems")).resolves.toEqual([{ id: "p1" }]);
    expect(calls()).toEqual(["GET http://gw/v1/problems", "POST http://gw/v1/me", "GET http://gw/v1/problems"]);
  });

  it("does not retry other refusals", async () => {
    fetchMock.mockResolvedValueOnce(json(403, { detail: "something else" }));

    await expect(gateway("/v1/problems")).rejects.toEqual(new GatewayError(403, "something else"));
    expect(calls()).toEqual(["GET http://gw/v1/problems"]);
  });

  it("reports the original refusal when the account can't be created", async () => {
    fetchMock
      .mockResolvedValueOnce(json(403, { detail: NO_ACCOUNT }))
      .mockResolvedValueOnce(json(400, { detail: "the token carries no email" }));

    await expect(gateway("/v1/me")).rejects.toEqual(new GatewayError(403, NO_ACCOUNT));
    expect(calls()).toHaveLength(2);
  });
});
