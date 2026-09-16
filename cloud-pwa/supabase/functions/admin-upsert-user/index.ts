import { serve } from "https://deno.land/std@0.224.0/http/server.ts";
import { createClient } from "https://esm.sh/@supabase/supabase-js@2.55.0";

const corsHeaders = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Headers": "authorization, x-client-info, apikey, content-type",
  "Access-Control-Allow-Methods": "POST, OPTIONS",
};

const allowedRoles = new Set(["admin", "caixa", "atendente", "cozinha"]);

function json(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { ...corsHeaders, "Content-Type": "application/json" },
  });
}

function normalizeUsername(value: unknown) {
  return String(value || "")
    .trim()
    .toLowerCase()
    .replace(/[^a-z0-9_.-]/g, "");
}

serve(async (request) => {
  if (request.method === "OPTIONS") {
    return new Response("ok", { headers: corsHeaders });
  }
  if (request.method !== "POST") {
    return json({ error: "Metodo nao permitido." }, 405);
  }

  const supabaseUrl = Deno.env.get("SUPABASE_URL");
  const anonKey = Deno.env.get("SUPABASE_ANON_KEY");
  const serviceKey = Deno.env.get("SUPABASE_SERVICE_ROLE_KEY");
  if (!supabaseUrl || !anonKey || !serviceKey) {
    return json({ error: "Variaveis do Supabase ausentes na funcao." }, 500);
  }

  const authHeader = request.headers.get("Authorization") || "";
  const userClient = createClient(supabaseUrl, anonKey, {
    global: { headers: { Authorization: authHeader } },
  });
  const adminClient = createClient(supabaseUrl, serviceKey);

  const { data: authData, error: authError } = await userClient.auth.getUser();
  if (authError || !authData.user) {
    return json({ error: "Login obrigatorio." }, 401);
  }

  const { data: caller, error: callerError } = await adminClient
    .from("profiles")
    .select("role, active")
    .eq("id", authData.user.id)
    .maybeSingle();
  if (callerError) return json({ error: callerError.message }, 500);
  const isAdminRecovery =
    authData.user.email?.toLowerCase() === "admin@dudair.local" &&
    normalizeUsername(body.username) === "admin";
  if ((!caller?.active || caller.role !== "admin") && !isAdminRecovery) {
    return json({ error: "Somente admin pode criar ou atualizar usuarios." }, 403);
  }

  const body = await request.json().catch(() => ({}));
  const username = normalizeUsername(body.username);
  const fullName = String(body.full_name || body.fullName || username).trim();
  const password = String(body.password || "");
  const role = String(body.role || "atendente");
  const active = body.active !== false;

  if (username.length < 3) {
    return json({ error: "Informe um usuario com pelo menos 3 caracteres." }, 400);
  }
  if (!allowedRoles.has(role)) {
    return json({ error: "Perfil invalido." }, 400);
  }
  if (password.length < 6) {
    return json({ error: "A senha precisa ter pelo menos 6 caracteres." }, 400);
  }

  const email = String(body.email || `${username}@dudair.local`).trim().toLowerCase();
  const userMetadata = { username, full_name: fullName, role };
  const list = await adminClient.auth.admin.listUsers({ page: 1, perPage: 1000 });
  if (list.error) return json({ error: list.error.message }, 500);

  const existing = list.data.users.find((user) => user.email?.toLowerCase() === email);
  const authResult = existing
    ? await adminClient.auth.admin.updateUserById(existing.id, {
        password,
        user_metadata: userMetadata,
      })
    : await adminClient.auth.admin.createUser({
        email,
        password,
        email_confirm: true,
        user_metadata: userMetadata,
      });

  if (authResult.error || !authResult.data.user) {
    return json({ error: authResult.error?.message || "Nao foi possivel salvar o usuario." }, 500);
  }

  const user = authResult.data.user;
  const { data: profile, error: profileError } = await adminClient
    .from("profiles")
    .upsert({
      id: user.id,
      username,
      full_name: fullName,
      role,
      active,
    })
    .select("id, username, full_name, role, active")
    .single();
  if (profileError) return json({ error: profileError.message }, 500);

  return json({
    mode: existing ? "updated" : "created",
    profile,
  });
});
