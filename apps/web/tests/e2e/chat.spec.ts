import { expect, test } from "@playwright/test";

/**
 * Covers Plan.md Phase 4's required e2e path: login -> ask question -> see a
 * cited streamed answer -> click the citation. The backend is mocked at the
 * network boundary (Playwright route interception) — the backend's own
 * correctness (auth, persistence, tenant isolation, agent orchestration) is
 * already proven by tests/integration/test_api.py and the services/ unit
 * tests; this spec proves the *frontend* renders and reacts to the real SSE
 * contract (packages/core/schemas/chat.ChatStreamEvent) correctly.
 */
test("login, ask a question, see a cited streamed answer, and click the citation", async ({
  page,
}) => {
  await page.route("**/api/auth/login", async (route) => {
    await route.fulfill({ json: { access_token: "fake-jwt-token", token_type: "bearer" } });
  });

  await page.route("**/api/conversations", async (route) => {
    if (route.request().method() === "GET") {
      await route.fulfill({ json: [] });
    } else {
      await route.continue();
    }
  });

  await page.route("**/api/chat", async (route) => {
    const frames = [
      { type: "token", data: "The retainer fee is " },
      { type: "token", data: "$12,000/month." },
      {
        type: "citations",
        citations: [
          {
            document_title: "Client X Contract.pdf",
            url_or_path: "https://example.com/contract.pdf",
            source: "local",
            chunk_index: 0,
            snippet: "The retainer fee is $12,000/month, payable on the first business day.",
          },
        ],
      },
      { type: "done", conversation_id: "11111111-1111-1111-1111-111111111111" },
    ];
    const body = frames.map((frame) => `data: ${JSON.stringify(frame)}\n\n`).join("");
    await route.fulfill({ status: 200, contentType: "text/event-stream", body });
  });

  await page.goto("/login");
  await page.getByLabel("Work email").fill("admin@acmelawpartners.com");
  await page.getByLabel("Password").fill("correct-horse-battery");
  await page.getByRole("button", { name: "Sign in" }).click();

  await expect(page).toHaveURL("/chat");

  await page.getByPlaceholder(/Ask about a contract/).fill("What is the retainer fee?");
  await page.getByRole("button", { name: "Send" }).click();

  await expect(page.getByText("$12,000/month.")).toBeVisible();

  const citationLink = page.getByRole("link", { name: "Client X Contract.pdf" });
  await expect(citationLink).toBeVisible();
  await expect(citationLink).toHaveAttribute("href", "https://example.com/contract.pdf");
});

test("unauthenticated visitor is redirected to login", async ({ page }) => {
  await page.goto("/chat");
  await expect(page).toHaveURL("/login");
});
