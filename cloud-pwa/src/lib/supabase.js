import { createClient } from "@supabase/supabase-js";

export const supabaseUrl = import.meta.env.VITE_SUPABASE_URL || "";
export const supabaseAnonKey = import.meta.env.VITE_SUPABASE_ANON_KEY || "";
export const isSupabaseConfigured = Boolean(supabaseUrl && supabaseAnonKey);

export const supabase = isSupabaseConfigured
  ? createClient(supabaseUrl, supabaseAnonKey, {
      auth: {
        persistSession: true,
        autoRefreshToken: true,
        detectSessionInUrl: true,
      },
      realtime: {
        params: {
          eventsPerSecond: 10,
        },
      },
    })
  : null;

export function normalizeLogin(login) {
  const value = String(login || "").trim();
  if (!value) return "";
  return value.includes("@") ? value : `${value}@dudair.local`;
}

export async function getProfile(userId) {
  const { data, error } = await supabase
    .from("profiles")
    .select("*")
    .eq("id", userId)
    .maybeSingle();
  if (error) throw error;
  return data;
}

export function roleCanManageMoney(role) {
  return role === "admin" || role === "caixa";
}

export function roleCanManageAdmin(role) {
  return role === "admin";
}

export function roleCanEditOrders(role) {
  return role === "admin" || role === "caixa" || role === "atendente";
}
