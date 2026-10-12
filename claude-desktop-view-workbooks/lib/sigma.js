import { requireConfig } from "./config.js";
import { debug } from "./log.js";

const PAGE_SIZE = 1000;
const MAX_PAGES = 10;
const REFRESH_BUFFER_SECONDS = 60;

let cachedToken = null;

export function clearTokenCache() {
  cachedToken = null;
}

async function readError(response) {
  const text = await response.text().catch(() => "");
  try {
    const body = JSON.parse(text);
    return body.error_description || body.message || body.error || text;
  } catch {
    return text || response.statusText;
  }
}

// Search signs in with the client credentials (the REST API capability of the
// same Client ID and Secret used to sign workbook links).
async function requestToken(config) {
  requireConfig(config, ["apiUrl", "embedClientId", "embedClientSecret"]);
  const response = await fetch(`${config.apiUrl}/v2/auth/token`, {
    method: "POST",
    headers: { "Content-Type": "application/x-www-form-urlencoded" },
    body: new URLSearchParams({
      grant_type: "client_credentials",
      client_id: config.embedClientId,
      client_secret: config.embedClientSecret,
    }),
  });

  if (!response.ok) {
    throw new Error(
      `Sigma rejected the sign-in (${response.status}): ${await readError(response)}`,
    );
  }
  const body = await response.json();
  const now = Math.floor(Date.now() / 1000);
  return { token: body.access_token, expiresAt: now + (body.expires_in || 300) };
}

export async function getBearerToken(config) {
  const now = Math.floor(Date.now() / 1000);
  if (cachedToken && now < cachedToken.expiresAt - REFRESH_BUFFER_SECONDS) {
    return cachedToken.token;
  }
  cachedToken = await requestToken(config);
  debug(config, "obtained a new Sigma access token");
  return cachedToken.token;
}

async function getJson(config, path) {
  const send = async () =>
    fetch(`${config.apiUrl}${path}`, {
      headers: {
        Authorization: `Bearer ${await getBearerToken(config)}`,
        Accept: "application/json",
      },
    });

  let response = await send();
  if (response.status === 401) {
    clearTokenCache();
    debug(config, "token rejected, retrying once with a new token");
    response = await send();
  }
  if (!response.ok) {
    throw new Error(
      `Sigma API request failed (${response.status}): ${await readError(response)}`,
    );
  }
  return response.json();
}

export function slugFromUrl(url) {
  try {
    return new URL(url).pathname.split("/").filter(Boolean).pop() || "";
  } catch {
    return "";
  }
}

function toWorkbook(entry) {
  return {
    name: entry.name,
    slug: slugFromUrl(entry.url) || entry.workbookUrlId || "",
    url: entry.url,
    path: entry.path || "",
    ownerId: entry.ownerId,
    updatedAt: entry.updatedAt,
    archived: Boolean(entry.isArchived),
  };
}

// Lists the workbooks the client credentials can see, a page at a time.
export async function listWorkbooks(config) {
  requireConfig(config, ["apiUrl"]);
  const workbooks = [];
  let page = "";
  let truncated = false;

  for (let count = 0; count < MAX_PAGES; count++) {
    const query = `limit=${PAGE_SIZE}${page ? `&page=${encodeURIComponent(page)}` : ""}`;
    const body = await getJson(config, `/v2/workbooks?${query}`);
    if (!Array.isArray(body.entries)) {
      throw new Error("Unexpected response from Sigma's workbook list.");
    }
    workbooks.push(...body.entries.map(toWorkbook));
    page = body.nextPage ?? "";
    if (!page) break;
    if (count === MAX_PAGES - 1) truncated = true;
  }

  const prefix = config.searchPathPrefix;
  const scoped = prefix
    ? workbooks.filter((workbook) => workbook.path.startsWith(prefix))
    : workbooks;
  return { workbooks: scoped, truncated };
}
