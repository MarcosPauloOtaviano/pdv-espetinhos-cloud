export function groupProductsByCategory(products, categoryName) {
  const groups = new Map();

  for (const product of products || []) {
    const resolved = String(categoryName(product) || "Outros").trim() || "Outros";
    if (!groups.has(resolved)) groups.set(resolved, []);
    groups.get(resolved).push(product);
  }

  return [...groups.entries()]
    .sort(([left], [right]) => left.localeCompare(right, "pt-BR"))
    .map(([name, items]) => ({ name, items }));
}
