import { request } from "@/lib/api";
import type { AdminStats } from "@/lib/types";

// Lives here, imported only by this route's page, so the admin API
// path is in this route's own bundle — which middleware.ts never
// serves to a non-admin — not in code every visitor downloads.
export function getAdminStats(): Promise<AdminStats> {
  return request<AdminStats>("/v1/admin/stats");
}
