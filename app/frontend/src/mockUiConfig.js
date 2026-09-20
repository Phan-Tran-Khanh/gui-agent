export function isMockUiEnabled(value) {
  return typeof value === "string" && value.trim().toLowerCase() === "true";
}
