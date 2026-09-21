import { serve } from "https://deno.land/std@0.224.0/http/server.ts";
import { createClient } from "https://esm.sh/@supabase/supabase-js@2.110.1";

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

function isUuid(value: unknown) {
  return /^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i.test(String(value || ""));
}

async function clearUserReferences(adminClient: ReturnType<typeof createClient>, userId: string) {
  const references = [
    ["settings", "updated_by"],
    ["categories", "created_by"],
    ["products", "created_by"],
    ["cash_sessions", "closed_by"],
    ["commands", "created_by"],
    ["commands", "closed_by"],
    ["command_items", "created_by"],
    ["payments", "created_by"],
    ["cash_movements", "created_by"],
    ["audit_logs", "user_id"],
    ["service_queue", "claimed_by"],
    ["service_queue", "completed_by"],
    ["establishments", "created_by"],
  ] as const;

  for (const [table, column] of references) {
    const { error } = await adminClient.from(table).update({ [column]: null }).eq(column, userId);
    if (error) throw new Error(`Nao foi possivel preservar o historico antes da exclusao (${table}.${column}).`);
  }
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

  const body = await request.json().catch(() => ({}));

  const { data: caller, error: callerError } = await adminClient
    .from("profiles")
    .select("role, active, establishment_id, platform_role")
    .eq("id", authData.user.id)
    .maybeSingle();
  if (callerError) return json({ error: callerError.message }, 500);
  const isSuperAdmin = caller?.platform_role === "super_admin";
  if (!caller?.active || (caller.role !== "admin" && !isSuperAdmin)) {
    return json({ error: "Somente admin pode criar ou atualizar usuarios." }, 403);
  }

  if (body.action === "delete_inactive") {
    const targetId = String(body.user_id || body.userId || "").trim();
    if (!isUuid(targetId)) return json({ error: "Usuario invalido para exclusao." }, 400);
    if (targetId === authData.user.id) return json({ error: "O proprio usuario nao pode ser excluido." }, 400);

    const { data: target, error: targetError } = await adminClient
      .from("profiles")
      .select("id, username, full_name, role, active, establishment_id, platform_role")
      .eq("id", targetId)
      .maybeSingle();
    if (targetError) return json({ error: targetError.message }, 500);
    if (!target) return json({ error: "Usuario nao encontrado." }, 404);
    if (target.active) return json({ error: "Somente usuarios inativos podem ser excluidos." }, 409);
    if (target.platform_role === "super_admin") return json({ error: "O Super Admin nao pode ser excluido por esta tela." }, 403);
    if (target.establishment_id !== caller.establishment_id) {
      return json({ error: "O usuario pertence a outro estabelecimento." }, 403);
    }

    const { data: openedCash, error: cashError } = await adminClient
      .from("cash_sessions")
      .select("id")
      .eq("opened_by", targetId)
      .limit(1);
    if (cashError) return json({ error: cashError.message }, 500);
    if (openedCash?.length) {
      return json({ error: "Este usuario possui historico de abertura de caixa e deve permanecer apenas inativo." }, 409);
    }

    let auditId: number | null = null;
    try {
      const { data: audit, error: auditError } = await adminClient
        .from("audit_logs")
        .insert({
          establishment_id: target.establishment_id,
          user_id: authData.user.id,
          action: "user_deleted",
          entity: "profiles",
          entity_id: target.id,
          old_value: target,
          new_value: { reason: "inactive_user_cleanup" },
        })
        .select("id")
        .single();
      if (auditError) throw new Error(auditError.message);
      auditId = audit.id;
      await clearUserReferences(adminClient, targetId);
      const { error: deleteError } = await adminClient.auth.admin.deleteUser(targetId);
      if (deleteError) throw new Error(deleteError.message);
    } catch (error) {
      if (auditId !== null) await adminClient.from("audit_logs").delete().eq("id", auditId);
      return json({ error: error instanceof Error ? error.message : "Nao foi possivel excluir o usuario." }, 500);
    }

    return json({ mode: "deleted", profile: { id: target.id, username: target.username, establishment_id: target.establishment_id } });
  }

  const requestedEstablishmentId = String(body.establishment_id || "").trim();
  const establishmentId = isSuperAdmin && requestedEstablishmentId
    ? requestedEstablishmentId
    : caller.establishment_id;
  if (!establishmentId) {
    return json({ error: "Estabelecimento obrigatorio para criar o usuario." }, 400);
  }

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

  const email = String(body.email || username + "@dudair.local").trim().toLowerCase();
  const userMetadata = { username, full_name: fullName };
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
      establishment_id: establishmentId,
      platform_role: "member",
    })
    .select("id, username, full_name, role, active, establishment_id, platform_role")
    .single();
  if (profileError) return json({ error: profileError.message }, 500);

  return json({
    mode: existing ? "updated" : "created",
    profile,
  });
});
