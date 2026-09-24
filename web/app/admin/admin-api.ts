import { request } from "@/lib/api";
import type { AdminStats, AdminUserPage, AdminUserSort } from "@/lib/types";

// Lives here, imported only by the admin routes' own pages, so the
// admin API paths are in those routes' bundles — which middleware.ts
// never serves to a non-admin — not in code every visitor downloads.
export function getAdminStats(): Promise<AdminStats> {
  return request<AdminStats>("/v1/admin/stats");
}

export interface ListUsersParams {
  search?: string;
  sort?: AdminUserSort;
  cursor?: string | null;
  limit?: number;
}

export function listUsers(params: ListUsersParams = {}): Promise<AdminUserPage> {
  const query = new URLSearchParams();
  const search = params.search?.trim();
  if (search) query.set("search", search);
  if (params.sort && params.sort !== "newest") query.set("sort", params.sort);
  if (params.cursor) query.set("cursor", params.cursor);
  if (params.limit) query.set("limit", String(params.limit));
  const qs = query.toString();
  return request<AdminUserPage>(`/v1/admin/users${qs ? `?${qs}` : ""}`);
}

export function deleteUser(id: string): Promise<void> {
  return request<void>(`/v1/admin/users/${encodeURIComponent(id)}`, { method: "DELETE" });
}
