require('dotenv').config();
const axios = require('axios');

const { SIGMA_BASE_URL, CLIENT_ID, SECRET, LIBRARY_WORKBOOK_ID, TARGET_FOLDER_ID } = process.env;

let token = null;
let tokenExpires = 0;

async function getToken() {
  if (token && Date.now() < tokenExpires) return token;
  const body = new URLSearchParams({
    grant_type: 'client_credentials',
    client_id: CLIENT_ID,
    client_secret: SECRET,
  });
  const res = await axios.post(`${SIGMA_BASE_URL}/v2/auth/token`, body);
  token = res.data.access_token;
  tokenExpires = Date.now() + (res.data.expires_in - 60) * 1000;
  return token;
}

async function sigma(method, path, data) {
  const res = await axios({
    method,
    url: `${SIGMA_BASE_URL}${path}`,
    data,
    headers: { Authorization: `Bearer ${await getToken()}` },
  });
  return res.data;
}

// The API accepts the short ID from a browser URL; resolve it to the UUID once.
let resolved = null;
async function resolveIds() {
  if (resolved) return resolved;
  const workbook = await sigma('get', `/v2/workbooks/${LIBRARY_WORKBOOK_ID}`);
  const folder = await sigma('get', `/v2/files/${TARGET_FOLDER_ID}`);
  resolved = { libraryWorkbookId: workbook.workbookId, folderId: folder.id };
  return resolved;
}

// The embed user is created by Sigma the first time its JWT loads, so this fails until then.
let embedMember = null;
async function getEmbedMember() {
  if (embedMember) return embedMember;
  const res = await sigma('get', `/v2/members?email=${encodeURIComponent(process.env.EMBED_EMAIL)}`);
  const member = res.entries && res.entries[0];
  if (!member) throw new Error('The embed user does not exist yet. Generate a layout and let the workbook load once, then try again.');
  embedMember = { memberId: member.memberId, homeFolderId: member.homeFolderId };
  return embedMember;
}

// Workbooks the embed user has saved to their own My Documents.
async function listSavedWorkbooks() {
  const { memberId } = await getEmbedMember();
  const res = await sigma('get', `/v2/members/${memberId}/files?typeFilters=workbook&limit=100`);
  return res.entries.filter((f) => f.path === 'My Documents').map((f) => ({ workbookId: f.id, name: f.name }));
}

module.exports = { sigma, resolveIds, getEmbedMember, listSavedWorkbooks };
