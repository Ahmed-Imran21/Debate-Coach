/**
 * The two sign-up checkboxes: both start unticked and both must be
 * ticked before an account can be created. The backend enforces the
 * same rule (POST /v1/auth/signup refuses without them) and records
 * when each was accepted; this module is the form's side of it.
 */

export interface SignupConsent {
  privacyPolicy: boolean;
  terms: boolean;
}

export const NO_CONSENT: SignupConsent = { privacyPolicy: false, terms: false };

/** Opened in a new tab, so a half-filled form isn't lost. */
export const LEGAL_LINKS = {
  privacyPolicy: { href: "/privacy", label: "Privacy Policy" },
  terms: { href: "/terms", label: "Terms and Conditions" },
} as const;

export const CONSENT_LINE_PREFIX = "By clicking this, you agree to our ";

/** Same wording as the backend's refusal, so either reads the same. */
export const CONSENT_REQUIRED_MESSAGE =
  "To create an account, agree to the Privacy Policy and the Terms and Conditions.";

export function canCreateAccount(consent: SignupConsent): boolean {
  return consent.privacyPolicy && consent.terms;
}

/** The request fields for POST /v1/auth/signup. */
export function consentFields(consent: SignupConsent): {
  accepted_privacy_policy: boolean;
  accepted_terms: boolean;
} {
  return { accepted_privacy_policy: consent.privacyPolicy, accepted_terms: consent.terms };
}
