import { existsSync, readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it, vi } from "vitest";

import {
  CONSENT_REQUIRED_MESSAGE,
  LEGAL_LINKS,
  NO_CONSENT,
  canCreateAccount,
  consentFields,
} from "@/lib/signup-consent";

vi.mock("next/navigation", () => ({ useRouter: () => ({ replace: () => {} }) }));

const root = (path: string) => fileURLToPath(new URL(`../../${path}`, import.meta.url));

async function render(mode: "login" | "signup"): Promise<string> {
  const { default: AuthForm } = await import("@/components/AuthForm");
  return renderToStaticMarkup(createElement(AuthForm, { mode }));
}

describe("sign-up consent", () => {
  it("allows an account only with both boxes ticked", () => {
    expect(canCreateAccount(NO_CONSENT)).toBe(false);
    expect(canCreateAccount({ privacyPolicy: true, terms: false })).toBe(false);
    expect(canCreateAccount({ privacyPolicy: false, terms: true })).toBe(false);
    expect(canCreateAccount({ privacyPolicy: true, terms: true })).toBe(true);
  });

  it("sends both acceptances to the backend", () => {
    expect(consentFields({ privacyPolicy: true, terms: true })).toEqual({
      accepted_privacy_policy: true,
      accepted_terms: true,
    });
  });

  it("links to the existing privacy and terms pages", () => {
    expect(LEGAL_LINKS.privacyPolicy.href).toBe("/privacy");
    expect(LEGAL_LINKS.terms.href).toBe("/terms");
    expect(existsSync(root("app/privacy/page.tsx"))).toBe(true);
    expect(existsSync(root("app/terms/page.tsx"))).toBe(true);
  });

  it("explains the refusal in the backend's own words", () => {
    const backend = readFileSync(root("../app/routes/auth.py"), "utf8").replace(/"\s*\n\s*"/g, "");
    expect(backend).toContain(CONSENT_REQUIRED_MESSAGE);
  });
});

describe("the create-account form", () => {
  it("starts with both boxes unticked and Create account disabled", async () => {
    const html = await render("signup");
    const boxes = html.match(/<input type="checkbox"[^>]*>/g) ?? [];
    expect(boxes).toHaveLength(2);
    for (const box of boxes) expect(box).not.toContain("checked");
    expect(html).toMatch(/<button class="btn" type="submit" aria-disabled="true">Create account<\/button>/);
  });

  it("labels each box with its line, the link opening the page in a new tab", async () => {
    const html = await render("signup");
    const line = (href: string, label: string) =>
      `<label class="consent"><input type="checkbox"/><span>By clicking this, you agree to our <a href="${href}" target="_blank" rel="noopener noreferrer">${label}</a></span></label>`;
    expect(html).toContain(line("/privacy", "Privacy Policy"));
    expect(html).toContain(line("/terms", "Terms and Conditions"));
    // Both boxes sit just above the button.
    expect(html.indexOf("Terms and Conditions")).toBeLessThan(html.indexOf("Create account"));
  });

  it("leaves sign-in as it was", async () => {
    const html = await render("login");
    expect(html).not.toContain('type="checkbox"');
    expect(html).not.toContain("aria-disabled");
  });
});
