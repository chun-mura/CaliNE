import assert from "node:assert/strict";
import test from "node:test";

import { dispatchWorkflow, targetDateForSchedule } from "../src/index.js";

test("dispatchWorkflow requests the CaliNE workflow on main", async () => {
  let capturedRequest;
  const fetchStub = async (url, init) => {
    capturedRequest = { url, init };
    return new Response(JSON.stringify({ workflow_run_id: 123 }), {
      status: 200,
      headers: { "Content-Type": "application/json" },
    });
  };

  const result = await dispatchWorkflow("github-token", "2026-10-20", fetchStub);

  assert.equal(
    capturedRequest.url,
    "https://api.github.com/repos/chun-mura/CaliNE/actions/workflows/daily_sync.yml/dispatches",
  );
  assert.equal(capturedRequest.init.method, "POST");
  assert.equal(capturedRequest.init.headers.Authorization, "Bearer github-token");
  assert.equal(capturedRequest.init.headers.Accept, "application/vnd.github+json");
  assert.equal(capturedRequest.init.headers["X-GitHub-Api-Version"], "2026-03-10");
  assert.deepEqual(JSON.parse(capturedRequest.init.body), {
    ref: "main",
    inputs: { target_date: "2026-10-20" },
  });
  assert.deepEqual(result, { workflowRunId: 123, htmlUrl: null });
});

test("dispatchWorkflow rejects a failed GitHub API response", async () => {
  const fetchStub = async () => new Response("Bad credentials", { status: 401 });

  await assert.rejects(
    dispatchWorkflow("invalid-token", "2026-10-20", fetchStub),
    /GitHub workflow dispatch failed: 401/,
  );
});

test("dispatchWorkflow retries a transient GitHub API failure", async () => {
  let attempts = 0;
  const fetchStub = async () => {
    attempts += 1;
    if (attempts === 1) {
      return new Response("Service unavailable", { status: 503 });
    }
    return new Response(
      JSON.stringify({ workflow_run_id: 456, html_url: "https://github.com/example/run/456" }),
      { status: 200, headers: { "Content-Type": "application/json" } },
    );
  };
  const delays = [];
  const sleepStub = async (milliseconds) => delays.push(milliseconds);

  const result = await dispatchWorkflow("github-token", "2026-10-20", fetchStub, sleepStub);

  assert.equal(attempts, 2);
  assert.deepEqual(delays, [1000]);
  assert.deepEqual(result, {
    workflowRunId: 456,
    htmlUrl: "https://github.com/example/run/456",
  });
});

test("dispatchWorkflow rejects a missing GitHub token before making a request", async () => {
  let called = false;
  const fetchStub = async () => {
    called = true;
    return new Response(null, { status: 200 });
  };

  await assert.rejects(
    dispatchWorkflow("", "2026-10-20", fetchStub),
    /GITHUB_TOKEN is not configured/,
  );
  assert.equal(called, false);
});

test("targetDateForSchedule returns the next day in JST", () => {
  assert.equal(targetDateForSchedule(Date.parse("2026-10-19T11:00:00Z")), "2026-10-20");
});
