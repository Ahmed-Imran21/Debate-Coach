/**
 * The user-management page's logic, kept free of React and the DOM
 * so it's unit-tested directly (web/lib/__tests__/admin-users.test.ts).
 */

import type { AdminUser, AdminUserPage, AdminUserSort } from "@/lib/types";

export const SEARCH_DEBOUNCE_MS = 300;

/** Calls `fn` with the latest value once `ms` pass without another call. */
export function createDebouncer<T>(fn: (value: T) => void, ms: number) {
  let timer: ReturnType<typeof setTimeout> | null = null;
  return {
    call(value: T): void {
      if (timer !== null) clearTimeout(timer);
      timer = setTimeout(() => {
        timer = null;
        fn(value);
      }, ms);
    },
    cancel(): void {
      if (timer !== null) clearTimeout(timer);
      timer = null;
    },
  };
}

const UNITS: [limitSeconds: number, sizeSeconds: number, name: string][] = [
  [60 * 60, 60, "minute"],
  [24 * 60 * 60, 60 * 60, "hour"],
  [30 * 24 * 60 * 60, 24 * 60 * 60, "day"],
  [365 * 24 * 60 * 60, 30 * 24 * 60 * 60, "month"],
  [Infinity, 365 * 24 * 60 * 60, "year"],
];

/** "never", "just now", "1 minute ago", "3 days ago", ... */
export function formatLastSeen(iso: string | null, now: number = Date.now()): string {
  if (iso === null) return "never";
  const seconds = Math.floor((now - new Date(iso).getTime()) / 1000);
  // Under a minute, or slightly in the future from clock skew.
  if (seconds < 60) return "just now";
  for (const [limit, size, name] of UNITS) {
    if (seconds < limit) {
      const n = Math.floor(seconds / size);
      return `${n} ${name}${n === 1 ? "" : "s"} ago`;
    }
  }
  return "just now";
}

export function formatSignedUp(iso: string): string {
  return new Date(iso).toLocaleDateString(undefined, {
    day: "numeric",
    month: "short",
    year: "numeric",
  });
}

/** The delete button only enables on the target's exact email. */
export function canConfirmDelete(typed: string, email: string): boolean {
  return typed.trim() === email;
}

/**
 * Exactly what the modal's delete button's `disabled` is derived from:
 * the target's exact email AND the admin's own password, never while a
 * delete is already in flight.
 */
export function deleteButtonEnabled(
  typed: string,
  email: string | undefined,
  password: string,
  busy: boolean,
): boolean {
  return email !== undefined && !busy && password.length > 0 && canConfirmDelete(typed, email);
}

/* ---------------------------------------------------------- */
/* List state                                                  */
/* ---------------------------------------------------------- */

export interface ListState {
  search: string;
  sort: AdminUserSort;
  users: AdminUser[];
  nextCursor: string | null;
  status: "loading" | "loading-more" | "idle" | "error";
  error: string | null;
  // Every request gets a new id; only the latest one's answer is
  // applied, so a slow response for an old search can't overwrite
  // the results for what's typed now.
  requestId: number;
}

export type ListAction =
  | { type: "start"; requestId: number; search: string; sort: AdminUserSort }
  | { type: "more"; requestId: number }
  | { type: "loaded"; requestId: number; page: AdminUserPage; append: boolean }
  | { type: "failed"; requestId: number; message: string }
  | { type: "removed"; id: string };

export const initialListState: ListState = {
  search: "",
  sort: "newest",
  users: [],
  nextCursor: null,
  status: "loading",
  error: null,
  requestId: 0,
};

export function listReducer(state: ListState, action: ListAction): ListState {
  switch (action.type) {
    case "start":
      return {
        ...state,
        search: action.search,
        sort: action.sort,
        users: [],
        nextCursor: null,
        status: "loading",
        error: null,
        requestId: action.requestId,
      };
    case "more":
      return { ...state, status: "loading-more", error: null, requestId: action.requestId };
    case "loaded": {
      if (action.requestId !== state.requestId) return state;
      const base = action.append ? state.users : [];
      const seen = new Set(base.map((u) => u.id));
      return {
        ...state,
        users: [...base, ...action.page.users.filter((u) => !seen.has(u.id))],
        nextCursor: action.page.next_cursor,
        status: "idle",
        error: null,
      };
    }
    case "failed":
      if (action.requestId !== state.requestId) return state;
      return { ...state, status: "error", error: action.message };
    case "removed":
      return { ...state, users: state.users.filter((u) => u.id !== action.id) };
  }
}
