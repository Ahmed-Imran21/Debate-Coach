"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useMemo, useReducer, useRef, useState } from "react";
import type { ReactElement } from "react";

import SiteHeader from "@/components/SiteHeader";
import { ApiError, getAccessToken, redirectToLoginAfterSessionExpiry } from "@/lib/api";
import type { AdminUser, AdminUserSort } from "@/lib/types";

import { listUsers } from "../admin-api";
import DeleteUserModal from "./DeleteUserModal";
import {
  SEARCH_DEBOUNCE_MS,
  createDebouncer,
  formatLastSeen,
  formatSignedUp,
  initialListState,
  listReducer,
} from "./logic";

const SORTS: { value: AdminUserSort; label: string }[] = [
  { value: "newest", label: "Newest signups" },
  { value: "last_seen", label: "Recently seen" },
];

/**
 * Reaching this page already means middleware.ts confirmed an admin
 * (its /admin gate covers /admin/users). The backend enforces the
 * same on every call; the 401/404 handling below only covers a
 * session or admin status that changed after the page loaded.
 */
export default function AdminUsersPage(): ReactElement {
  const router = useRouter();
  const [state, dispatch] = useReducer(listReducer, initialListState);
  const [searchInput, setSearchInput] = useState("");
  const [search, setSearch] = useState("");
  const [sort, setSort] = useState<AdminUserSort>("newest");
  const [pendingDelete, setPendingDelete] = useState<AdminUser | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const nextRequestId = useRef(0);

  const debouncer = useMemo(
    () => createDebouncer((value: string) => setSearch(value.trim()), SEARCH_DEBOUNCE_MS),
    [],
  );
  useEffect(() => () => debouncer.cancel(), [debouncer]);

  const handleFailure = useCallback(
    (caught: unknown, requestId: number) => {
      if (caught instanceof ApiError && caught.status === 401) {
        redirectToLoginAfterSessionExpiry(router);
        return;
      }
      if (caught instanceof ApiError && (caught.status === 404 || caught.status === 403)) {
        router.replace("/");
        return;
      }
      dispatch({ type: "failed", requestId, message: "Could not load users. Try again." });
    },
    [router],
  );

  // A new search or sort starts over from the first page.
  useEffect(() => {
    if (!getAccessToken()) {
      router.replace("/login");
      return;
    }
    const requestId = ++nextRequestId.current;
    dispatch({ type: "start", requestId, search, sort });
    listUsers({ search, sort })
      .then((page) => dispatch({ type: "loaded", requestId, page, append: false }))
      .catch((caught) => handleFailure(caught, requestId));
  }, [search, sort, router, handleFailure]);

  function loadMore(): void {
    if (!state.nextCursor || state.status !== "idle") return;
    const requestId = ++nextRequestId.current;
    dispatch({ type: "more", requestId });
    listUsers({ search: state.search, sort: state.sort, cursor: state.nextCursor })
      .then((page) => dispatch({ type: "loaded", requestId, page, append: true }))
      .catch((caught) => handleFailure(caught, requestId));
  }

  function handleDeleted(user: AdminUser): void {
    setPendingDelete(null);
    dispatch({ type: "removed", id: user.id });
    setNotice(`Deleted ${user.email} and everything they recorded.`);
  }

  const loading = state.status === "loading";

  return (
    <div className="shell">
      <SiteHeader variant="app" />

      <main>
        <section className="block-tight" style={{ paddingTop: "2.5rem", paddingBottom: "4rem" }}>
          <div className="wrap">
            <p className="note" style={{ marginBottom: "0.5rem" }}>
              <Link href="/admin">Admin</Link> / Users
            </p>
            <h1 style={{ fontSize: "var(--step-4)", marginBottom: "1.5rem" }}>Users</h1>

            <div
              style={{
                display: "flex",
                flexWrap: "wrap",
                alignItems: "flex-end",
                gap: "1rem 1.5rem",
                marginBottom: "1.5rem",
              }}
            >
              <label className="field" style={{ flex: "1 1 18rem", maxWidth: "28rem", marginBottom: 0 }}>
                <span>Search by name or email</span>
                <input
                  id="admin-user-search"
                  type="search"
                  autoComplete="off"
                  spellCheck={false}
                  value={searchInput}
                  onChange={(event) => {
                    setSearchInput(event.target.value);
                    debouncer.call(event.target.value);
                  }}
                />
              </label>

              <div className="btn-row" role="group" aria-label="Sort users">
                {SORTS.map((option) => (
                  <button
                    key={option.value}
                    type="button"
                    className="filter"
                    aria-pressed={sort === option.value}
                    onClick={() => setSort(option.value)}
                  >
                    {option.label}
                  </button>
                ))}
              </div>
            </div>

            {notice && (
              <p className="alert alert-quiet" role="status">
                {notice}
              </p>
            )}

            {state.error && (
              <p className="alert alert-quiet" role="status">
                {state.error}
              </p>
            )}

            {loading && <p className="note">Loading.</p>}

            {!loading && state.users.length === 0 && !state.error && (
              <p className="note">
                {state.search ? `No users match “${state.search}”.` : "No users yet."}
              </p>
            )}

            {state.users.length > 0 && (
              <div className="table-scroll">
                <table className="data-table">
                  <thead>
                    <tr>
                      <th scope="col">Name</th>
                      <th scope="col">Email</th>
                      <th scope="col">Signed up</th>
                      <th scope="col">Last seen</th>
                      <th scope="col" className="num">
                        Sessions
                      </th>
                      <th scope="col">
                        <span className="sr-only">Actions</span>
                      </th>
                    </tr>
                  </thead>
                  <tbody>
                    {state.users.map((user) => (
                      <tr key={user.id}>
                        <td className="row-title">
                          {user.first_name} {user.last_name}
                        </td>
                        <td className="row-meta">{user.email}</td>
                        <td className="row-meta">{formatSignedUp(user.created_at)}</td>
                        <td className="row-meta" title={user.last_seen_at ?? undefined}>
                          {formatLastSeen(user.last_seen_at)}
                        </td>
                        <td className="num">{user.session_count}</td>
                        <td className="actions">
                          {user.is_admin ? (
                            <span className="state">Admin</span>
                          ) : (
                            <button
                              type="button"
                              className="btn btn-quiet btn-sm"
                              data-tone="danger"
                              onClick={() => {
                                setNotice(null);
                                setPendingDelete(user);
                              }}
                              aria-label={`Delete ${user.email}`}
                            >
                              Delete
                            </button>
                          )}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}

            {state.users.length > 0 && (
              <div className="btn-row" style={{ marginTop: "1.5rem" }}>
                {state.nextCursor ? (
                  <button
                    type="button"
                    className="btn btn-quiet"
                    onClick={loadMore}
                    disabled={state.status !== "idle"}
                  >
                    {state.status === "loading-more" ? "Loading." : "Load more"}
                  </button>
                ) : (
                  <p className="note" style={{ margin: 0 }}>
                    Showing all {state.users.length} {state.users.length === 1 ? "user" : "users"}
                    {state.search ? " that match" : ""}.
                  </p>
                )}
              </div>
            )}
          </div>
        </section>
      </main>

      <DeleteUserModal
        user={pendingDelete}
        onClose={() => setPendingDelete(null)}
        onDeleted={handleDeleted}
      />
    </div>
  );
}
