const WORKFLOW_DISPATCH_URL =
  "https://api.github.com/repos/chun-mura/CaliNE/actions/workflows/daily_sync.yml/dispatches";
const MAX_ATTEMPTS = 3;

function defaultSleep(milliseconds) {
  return new Promise((resolve) => setTimeout(resolve, milliseconds));
}

export function targetDateForSchedule(scheduledTime) {
  const millisecondsPerDay = 24 * 60 * 60 * 1000;
  const jstOffset = 9 * 60 * 60 * 1000;
  return new Date(scheduledTime + jstOffset + millisecondsPerDay).toISOString().slice(0, 10);
}

export async function dispatchWorkflow(
  githubToken,
  targetDate,
  fetchImpl = fetch,
  sleepImpl = defaultSleep,
) {
  if (!githubToken) {
    throw new Error("GITHUB_TOKEN is not configured");
  }

  for (let attempt = 0; attempt < MAX_ATTEMPTS; attempt += 1) {
    let response;
    try {
      response = await fetchImpl(WORKFLOW_DISPATCH_URL, {
        method: "POST",
        headers: {
          Accept: "application/vnd.github+json",
          Authorization: `Bearer ${githubToken}`,
          "Content-Type": "application/json",
          "User-Agent": "caline-cloudflare-scheduler",
          "X-GitHub-Api-Version": "2026-03-10",
        },
        body: JSON.stringify({ ref: "main", inputs: { target_date: targetDate } }),
        signal: AbortSignal.timeout(10_000),
      });
    } catch (error) {
      if (attempt === MAX_ATTEMPTS - 1) {
        throw new Error("GitHub workflow dispatch failed: network error", { cause: error });
      }
      await sleepImpl(2 ** attempt * 1000);
      continue;
    }

    if (response.ok) {
      const body = response.status === 204 ? {} : await response.json();
      return {
        workflowRunId: body.workflow_run_id ?? null,
        htmlUrl: body.html_url ?? null,
      };
    }

    const retryable = response.status === 429 || response.status >= 500;
    if (retryable && attempt < MAX_ATTEMPTS - 1) {
      const retryAfterHeader = response.headers.get("Retry-After");
      const retryAfter = retryAfterHeader === null ? Number.NaN : Number(retryAfterHeader);
      const delay =
        Number.isFinite(retryAfter) && retryAfter >= 0
          ? retryAfter * 1000
          : 2 ** attempt * 1000;
      await sleepImpl(Math.min(delay, 30_000));
      continue;
    }

    const requestId = response.headers.get("X-GitHub-Request-Id");
    const suffix = requestId ? ` (request id: ${requestId})` : "";
    throw new Error(`GitHub workflow dispatch failed: ${response.status}${suffix}`);
  }

  throw new Error("GitHub workflow dispatch failed: retry limit exceeded");
}

export default {
  async scheduled(controller, env) {
    const targetDate = targetDateForSchedule(controller.scheduledTime);
    const result = await dispatchWorkflow(env.GITHUB_TOKEN, targetDate);
    console.log(
      JSON.stringify({
        message: "GitHub workflow dispatch accepted",
        cron: controller.cron,
        scheduledTime: new Date(controller.scheduledTime).toISOString(),
        targetDate,
        workflowRunId: result.workflowRunId,
        htmlUrl: result.htmlUrl,
      }),
    );
  },
};
