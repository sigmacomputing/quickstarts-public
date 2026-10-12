import { createEmbedJwt } from "./jwt.js";

const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

// Accepts a workbook URL or a slug (the last segment of the URL) and returns
// the org and slug. Sigma's internal workbook ID is rejected because it does
// not work in a workbook URL.
export function parseWorkbookRef({ workbookSlug, workbookUrl }, config) {
  let orgSlug = config.orgSlug;
  let slug = (workbookSlug || "").trim();

  if (!slug && workbookUrl) {
    let url;
    try {
      url = new URL(workbookUrl);
    } catch {
      throw new Error(`"${workbookUrl}" is not a valid workbook URL.`);
    }
    const parts = url.pathname.split("/").filter(Boolean);
    const at = parts.indexOf("workbook");
    if (at === -1 || !parts[at + 1]) {
      throw new Error(`"${workbookUrl}" is not a Sigma workbook URL.`);
    }
    slug = parts[at + 1];
    if (at > 0) orgSlug = parts[at - 1];
  }

  if (!slug) throw new Error("Provide a workbookSlug or a workbookUrl.");
  if (UUID.test(slug)) {
    throw new Error(
      "That looks like an internal workbook ID. Use the slug or URL returned by search_workbooks.",
    );
  }
  return { orgSlug, slug };
}

// Builds the workbook URL with a freshly signed, single-use JWT and the
// optional embed parameters from the .env file.
export function buildEmbedUrl({ orgSlug, slug }, config) {
  const page = config.pageId ? `/page/${encodeURIComponent(config.pageId)}` : "";
  const params = [
    ":embed=true",
    `:jwt=${encodeURIComponent(createEmbedJwt(config))}`,
    ...Object.entries(config.embedParameters).map(
      ([key, value]) => `:${key}=${encodeURIComponent(value)}`,
    ),
  ];
  return `${config.appUrl}/${orgSlug}/workbook/${slug}${page}?${params.join("&")}`;
}
