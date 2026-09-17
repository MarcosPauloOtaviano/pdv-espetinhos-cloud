export function profileDisplayName(profile) {
  if (!profile) return "Usuario nao identificado";
  return profile.full_name?.trim() || profile.username?.trim() || profile.email?.trim() || "Usuario nao identificado";
}

export function commandOwner(command, profiles) {
  return profileDisplayName((profiles || []).find((profile) => profile.id === command?.created_by));
}

export function isLowStock(product) {
  return Boolean(product?.track_stock) && Number(product.stock_quantity || 0) <= Number(product.low_stock_threshold || 0);
}

export function filterProducts(products, { search = "", categoryId = "", showInactive = false } = {}) {
  const term = search.trim().toLocaleLowerCase("pt-BR");
  return (products || []).filter((product) => {
    const matchesStatus = showInactive || product.active;
    const matchesCategory = !categoryId || product.category_id === categoryId;
    const matchesSearch =
      !term ||
      product.name?.toLocaleLowerCase("pt-BR").includes(term) ||
      product.categories?.name?.toLocaleLowerCase("pt-BR").includes(term) ||
      product.notes?.toLocaleLowerCase("pt-BR").includes(term);
    return matchesStatus && matchesCategory && matchesSearch;
  });
}

export function inventoryValue(products) {
  return (products || []).reduce((total, product) => {
    if (!product.track_stock || !product.active) return total;
    return total + Number(product.cost || 0) * Number(product.stock_quantity || 0);
  }, 0);
}
