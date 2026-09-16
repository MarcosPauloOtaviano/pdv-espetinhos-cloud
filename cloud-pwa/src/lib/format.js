export const COMMAND_STATUS = {
  aberto: "Em aberto",
  aguardando_pagamento: "Aguardando pagamento",
  paga: "Paga",
  cancelada: "Cancelada",
  fiado: "Fiado / Pendente",
};

export const PAYMENT_LABELS = {
  dinheiro: "Dinheiro",
  pix: "Pix",
  debito: "Cartao de Debito",
  credito: "Cartao de Credito",
};

export const ROLE_LABELS = {
  admin: "Administrador",
  caixa: "Caixa",
  atendente: "Atendente",
  cozinha: "Cozinha",
};

export function currency(value) {
  return new Intl.NumberFormat("pt-BR", {
    style: "currency",
    currency: "BRL",
  }).format(Number(value || 0));
}

export function number(value, digits = 2) {
  return Number(value || 0).toLocaleString("pt-BR", {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  });
}

export function parseCurrency(input) {
  if (input == null) return 0;
  const text = String(input).replace("R$", "").trim();
  const normalized = text.includes(",") ? text.replace(/\./g, "").replace(",", ".") : text;
  const parsed = Number(normalized);
  return Number.isFinite(parsed) ? Math.round(parsed * 100) / 100 : 0;
}

export function todayISO() {
  const now = new Date();
  const offset = now.getTimezoneOffset();
  return new Date(now.getTime() - offset * 60_000).toISOString().slice(0, 10);
}

export function dateTime(value) {
  if (!value) return "-";
  return new Date(value).toLocaleString("pt-BR");
}

export function dateOnly(value) {
  if (!value) return "-";
  return new Date(value).toLocaleDateString("pt-BR");
}
