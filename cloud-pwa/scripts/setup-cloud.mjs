import fs from "node:fs";
import path from "node:path";
import process from "node:process";
import { fileURLToPath } from "node:url";
import pg from "pg";
import { createClient } from "@supabase/supabase-js";

const { Client } = pg;

const rootDir = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const defaultSchemaPath = path.join(rootDir, "supabase", "schema.sql");
const defaultUsersPath = path.join(rootDir, "scripts", "setup-users.json");
const usersExamplePath = path.join(rootDir, "scripts", "setup-users.example.json");
const args = process.argv.slice(2);

const flags = new Set(args.filter((arg) => arg.startsWith("--")));
const runAll = flags.has("--all");
const runSchema = runAll || flags.has("--schema");
const runUsers = runAll || flags.has("--users");
const runCheck = flags.has("--check") || (!runSchema && !runUsers);

main().catch((error) => {
  console.error(`\nErro: ${error.message}`);
  process.exitCode = 1;
});

async function main() {
  const env = loadEnv();
  const config = {
    supabaseUrl: env.VITE_SUPABASE_URL || env.SUPABASE_URL || "",
    anonKey: env.VITE_SUPABASE_ANON_KEY || "",
    serviceRoleKey: env.SUPABASE_SERVICE_ROLE_KEY || "",
    databaseUrl: env.DATABASE_URL || env.SUPABASE_DB_URL || "",
    schemaPath: readArg("--schema-file") || defaultSchemaPath,
    usersPath: readArg("--users-file") || defaultUsersPath,
  };

  if (runCheck) {
    printCheck(config);
  }

  if (runSchema) {
    await applySchema(config);
  }

  if (runUsers) {
    await setupUsers(config);
  }

  if (runSchema || runUsers) {
    console.log("\nSetup cloud concluido.");
  }
}

function loadEnv() {
  const values = {};
  for (const fileName of [".env", ".env.local"]) {
    const filePath = path.join(rootDir, fileName);
    if (!fs.existsSync(filePath)) continue;
    Object.assign(values, parseEnv(fs.readFileSync(filePath, "utf8")));
  }
  return { ...values, ...process.env };
}

function parseEnv(content) {
  const values = {};
  for (const rawLine of content.split(/\r?\n/)) {
    const line = rawLine.trim();
    if (!line || line.startsWith("#")) continue;
    const equalsIndex = line.indexOf("=");
    if (equalsIndex === -1) continue;

    const key = line.slice(0, equalsIndex).trim();
    let value = line.slice(equalsIndex + 1).trim();
    if (
      (value.startsWith('"') && value.endsWith('"')) ||
      (value.startsWith("'") && value.endsWith("'"))
    ) {
      value = value.slice(1, -1);
    }
    values[key] = value;
  }
  return values;
}

function readArg(name) {
  const index = args.indexOf(name);
  if (index === -1) return "";
  return args[index + 1] || "";
}

function printCheck(config) {
  console.log("DU'DAIR PDV Cloud - checagem de configuracao\n");
  console.log(`VITE_SUPABASE_URL: ${describe(config.supabaseUrl)}`);
  console.log(`VITE_SUPABASE_ANON_KEY: ${describeSecret(config.anonKey)}`);
  console.log(`SUPABASE_SERVICE_ROLE_KEY: ${describeSecret(config.serviceRoleKey)}`);
  console.log(`DATABASE_URL/SUPABASE_DB_URL: ${describeSecret(config.databaseUrl)}`);
  console.log(`schema.sql: ${fs.existsSync(config.schemaPath) ? config.schemaPath : "nao encontrado"}`);
  console.log(
    `usuarios: ${
      fs.existsSync(config.usersPath)
        ? config.usersPath
        : `nao encontrado; copie ${usersExamplePath} para ${config.usersPath}`
    }`
  );

  const warnings = [];
  if (!hasRealValue(config.supabaseUrl)) warnings.push("preencha VITE_SUPABASE_URL");
  if (!hasRealValue(config.anonKey)) warnings.push("preencha VITE_SUPABASE_ANON_KEY");
  if (!hasRealValue(config.databaseUrl)) warnings.push("preencha DATABASE_URL para aplicar o schema");
  if (!hasRealValue(config.serviceRoleKey)) {
    warnings.push("preencha SUPABASE_SERVICE_ROLE_KEY para criar usuarios");
  }

  if (warnings.length) {
    console.log("\nPendencias:");
    for (const warning of warnings) console.log(`- ${warning}`);
  } else {
    console.log("\nConfiguracao minima encontrada.");
  }
}

async function applySchema(config) {
  requireRealValue(config.databaseUrl, "DATABASE_URL ou SUPABASE_DB_URL");
  if (!fs.existsSync(config.schemaPath)) {
    throw new Error(`schema nao encontrado em ${config.schemaPath}`);
  }

  console.log(`\nAplicando schema em ${maskDatabaseUrl(config.databaseUrl)}...`);
  const client = new Client({
    connectionString: config.databaseUrl,
    ssl: shouldUseSsl(config.databaseUrl) ? { rejectUnauthorized: false } : false,
  });

  try {
    await client.connect();
    await client.query(fs.readFileSync(config.schemaPath, "utf8"));
    await validateSchema(client);
    console.log("Schema aplicado e validado.");
  } finally {
    await client.end().catch(() => {});
  }
}

async function validateSchema(client) {
  const { rows } = await client.query(`
    select
      to_regclass('public.commands') as commands_table,
      to_regclass('public.cash_sessions') as cash_sessions_table,
      to_regclass('public.payments') as payments_table,
      exists (
        select 1
        from pg_proc p
        join pg_namespace n on n.oid = p.pronamespace
        where n.nspname = 'public' and p.proname = 'finalize_command'
      ) as finalize_command_exists
  `);
  const row = rows[0];
  if (
    !row.commands_table ||
    !row.cash_sessions_table ||
    !row.payments_table ||
    !row.finalize_command_exists
  ) {
    throw new Error("schema aplicado, mas a validacao nao encontrou tabelas/funcoes essenciais");
  }
}

async function setupUsers(config) {
  requireRealValue(config.supabaseUrl, "VITE_SUPABASE_URL");
  requireRealValue(config.serviceRoleKey, "SUPABASE_SERVICE_ROLE_KEY");
  if (!fs.existsSync(config.usersPath)) {
    throw new Error(`arquivo de usuarios nao encontrado. Copie ${usersExamplePath} para ${config.usersPath}`);
  }

  const users = JSON.parse(fs.readFileSync(config.usersPath, "utf8"));
  if (!Array.isArray(users) || users.length === 0) {
    throw new Error("arquivo de usuarios precisa conter uma lista");
  }

  const admin = createClient(config.supabaseUrl, config.serviceRoleKey, {
    auth: {
      persistSession: false,
      autoRefreshToken: false,
    },
  });

  console.log(`\nCriando/atualizando ${users.length} usuario(s)...`);
  for (const user of users) {
    validateUser(user);
    const authUser = await upsertAuthUser(admin, user);
    const { error } = await admin.from("profiles").upsert(
      {
        id: authUser.id,
        username: user.username,
        full_name: user.full_name || user.username,
        role: user.role,
      },
      { onConflict: "id" }
    );
    if (error) throw new Error(`falha ao atualizar profile de ${user.email}: ${error.message}`);
    console.log(`- ${user.email} (${user.role}) pronto`);
  }
}

async function upsertAuthUser(admin, user) {
  const existing = await findUserByEmail(admin, user.email);
  if (existing) {
    const { data, error } = await admin.auth.admin.updateUserById(existing.id, {
      email_confirm: true,
      user_metadata: {
        username: user.username,
        full_name: user.full_name || user.username,
      },
    });
    if (error) throw new Error(`falha ao atualizar usuario ${user.email}: ${error.message}`);
    return data.user;
  }

  const { data, error } = await admin.auth.admin.createUser({
    email: user.email,
    password: user.password,
    email_confirm: true,
    user_metadata: {
      username: user.username,
      full_name: user.full_name || user.username,
    },
  });
  if (error) throw new Error(`falha ao criar usuario ${user.email}: ${error.message}`);
  return data.user;
}

async function findUserByEmail(admin, email) {
  const normalizedEmail = email.toLowerCase();
  let page = 1;
  const perPage = 1000;

  while (true) {
    const { data, error } = await admin.auth.admin.listUsers({ page, perPage });
    if (error) throw new Error(`falha ao listar usuarios: ${error.message}`);

    const found = data.users.find((user) => user.email?.toLowerCase() === normalizedEmail);
    if (found) return found;
    if (data.users.length < perPage) return null;
    page += 1;
  }
}

function validateUser(user) {
  const requiredFields = ["username", "email", "password", "role"];
  for (const field of requiredFields) {
    if (!user[field] || typeof user[field] !== "string") {
      throw new Error(`usuario invalido: campo ${field} e obrigatorio`);
    }
  }

  if (!["admin", "caixa", "atendente", "cozinha"].includes(user.role)) {
    throw new Error(`role invalida para ${user.email}: ${user.role}`);
  }
  if (user.password.length < 8 || /troque|senha-forte/i.test(user.password)) {
    throw new Error(`defina uma senha real com pelo menos 8 caracteres para ${user.email}`);
  }
}

function hasRealValue(value) {
  return Boolean(value) && !/SEU-|SUA_|SUA-|troque|exemplo|example/i.test(value);
}

function requireRealValue(value, label) {
  if (!hasRealValue(value)) {
    throw new Error(`${label} ausente ou ainda com valor de exemplo`);
  }
}

function describe(value) {
  return hasRealValue(value) ? value : "ausente/placeholder";
}

function describeSecret(value) {
  return hasRealValue(value) ? mask(value) : "ausente/placeholder";
}

function mask(value) {
  if (!value) return "";
  if (value.length <= 12) return "***";
  return `${value.slice(0, 6)}...${value.slice(-4)}`;
}

function maskDatabaseUrl(value) {
  try {
    const url = new URL(value);
    if (url.password) url.password = "***";
    if (url.username) url.username = mask(url.username);
    return url.toString();
  } catch {
    return mask(value);
  }
}

function shouldUseSsl(databaseUrl) {
  return !/localhost|127\.0\.0\.1/i.test(databaseUrl);
}
