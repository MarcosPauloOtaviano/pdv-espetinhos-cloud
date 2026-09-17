import crypto from "node:crypto";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { createClient } from "@supabase/supabase-js";

const rootDir = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const credentialsPath = path.join(rootDir, "scripts", "ronaldo-access.local.json");

function parseEnv(content) {
  return Object.fromEntries(
    content
      .split(/\r?\n/)
      .map((line) => line.trim())
      .filter((line) => line && !line.startsWith("#") && line.includes("="))
      .map((line) => {
        const separator = line.indexOf("=");
        const key = line.slice(0, separator).trim();
        const value = line.slice(separator + 1).trim().replace(/^['"]|['"]$/g, "");
        return [key, value];
      }),
  );
}

function loadEnv() {
  const values = {};
  for (const name of [".env", ".env.local"]) {
    const file = path.join(rootDir, name);
    if (fs.existsSync(file)) Object.assign(values, parseEnv(fs.readFileSync(file, "utf8")));
  }
  return { ...values, ...process.env };
}

function fail(error) {
  throw new Error(error?.message || String(error));
}

const env = loadEnv();
const url = env.VITE_SUPABASE_URL;
const key = env.VITE_SUPABASE_PUBLISHABLE_KEY || env.VITE_SUPABASE_ANON_KEY;
if (!url || !key) fail("Supabase URL/chave publica ausentes.");

const setupUsersPath = path.join(rootDir, "scripts", "setup-users.json");
const setupUsers = JSON.parse(fs.readFileSync(setupUsersPath, "utf8"));
const platformAdmin = setupUsers.find((user) => user.role === "admin");
if (!platformAdmin?.email || !platformAdmin?.password) fail("Admin inicial nao encontrado.");

const platform = createClient(url, key, { auth: { persistSession: false, autoRefreshToken: false } });
const { error: loginError } = await platform.auth.signInWithPassword({
  email: platformAdmin.email,
  password: platformAdmin.password,
});
if (loginError) fail(loginError);

const { data: establishment, error: establishmentError } = await platform
  .from("establishments")
  .select("id, name, slug")
  .eq("slug", "espetinho-do-ronaldo")
  .single();
if (establishmentError) fail(establishmentError);

const password = `Ron!${crypto.randomBytes(9).toString("base64url")}`;
const { data: created, error: createError } = await platform.functions.invoke("admin-upsert-user", {
  body: {
    establishment_id: establishment.id,
    username: "ronaldo",
    full_name: "Ronaldo",
    password,
    role: "admin",
    active: true,
  },
});
if (createError) fail(createError);
if (created?.error) fail(created.error);

const tenant = createClient(url, key, { auth: { persistSession: false, autoRefreshToken: false } });
const { error: tenantLoginError } = await tenant.auth.signInWithPassword({
  email: "ronaldo@dudair.local",
  password,
});
if (tenantLoginError) fail(tenantLoginError);

const { data: profile, error: profileError } = await tenant
  .from("profiles")
  .select("id, username, role, active, establishment_id, establishments(name, slug)")
  .single();
if (profileError) fail(profileError);
if (profile.establishment_id !== establishment.id || profile.role !== "admin" || !profile.active) {
  fail("Perfil do Ronaldo nao ficou vinculado corretamente.");
}

for (const name of ["Espetinhos", "Bebidas", "Porcoes"]) {
  const { data: existing, error: selectError } = await tenant
    .from("categories")
    .select("id")
    .eq("name", name)
    .maybeSingle();
  if (selectError) fail(selectError);
  if (!existing) {
    const { error } = await tenant.from("categories").insert({ name, created_by: profile.id });
    if (error) fail(error);
  }
}

const { data: categories, error: categoriesError } = await tenant
  .from("categories")
  .select("id, name");
if (categoriesError) fail(categoriesError);
const byName = Object.fromEntries(categories.map((category) => [category.name, category.id]));

const demoProducts = [
  { name: "Espetinho bovino", category: "Espetinhos", price: 9, cost: 4.5, stock_quantity: 40 },
  { name: "Espetinho de frango", category: "Espetinhos", price: 8, cost: 3.8, stock_quantity: 35 },
  { name: "Coca-Cola lata", category: "Bebidas", price: 6, cost: 3.2, stock_quantity: 30 },
  { name: "Porcao de mandioca", category: "Porcoes", price: 16, cost: 6.5, stock_quantity: 20 },
];

for (const item of demoProducts) {
  const { data: existing, error: selectError } = await tenant
    .from("products")
    .select("id")
    .eq("name", item.name)
    .maybeSingle();
  if (selectError) fail(selectError);
  if (!existing) {
    const { error } = await tenant.from("products").insert({
      name: item.name,
      category_id: byName[item.category],
      price: item.price,
      cost: item.cost,
      track_stock: true,
      stock_quantity: item.stock_quantity,
      low_stock_threshold: 5,
      created_by: profile.id,
    });
    if (error) fail(error);
  }
}

const { data: visibleProducts, error: productsError } = await tenant
  .from("products")
  .select("id, establishment_id");
if (productsError) fail(productsError);
if (visibleProducts.some((product) => product.establishment_id !== establishment.id)) {
  fail("RLS permitiu visualizar produto de outro estabelecimento.");
}

fs.writeFileSync(
  credentialsPath,
  `${JSON.stringify({ url, username: "ronaldo", email: "ronaldo@dudair.local", password }, null, 2)}\n`,
  { mode: 0o600 },
);

console.log(`Ronaldo configurado em ${establishment.name}.`);
console.log(`${visibleProducts.length} produto(s) visiveis e isolados pelo RLS.`);
console.log(`Credenciais salvas localmente em ${credentialsPath}.`);
