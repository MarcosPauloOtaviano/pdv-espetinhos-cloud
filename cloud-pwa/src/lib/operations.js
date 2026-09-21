export async function runMutationWithRefresh(action, refresh) {
  const result = await action();
  let refreshError = null;

  try {
    await refresh();
  } catch (error) {
    refreshError = error;
  }

  return { result, refreshError };
}
