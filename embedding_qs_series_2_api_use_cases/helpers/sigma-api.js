// utils/sigma-api.js
async function getSigmaAuthToken() {
  const res = await fetch(process.env.AUTH_URL, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      client_id: process.env.CLIENT_ID,
      client_secret: process.env.SECRET
    })
  });

  if (!res.ok) {
    const text = await res.text();
    throw new Error(`Failed to get token: ${res.status} - ${text}`);
  }

  const data = await res.json();
  return data.access_token;
}

async function createBookmark(token, payload) {
  const res = await fetch(`${process.env.BASE_URL}/bookmarks`, {
    method: "POST",
    headers: {
      Authorization: `Bearer ${token}`,
      "Content-Type": "application/json"
    },
    body: JSON.stringify(payload)
  });

  const data = await res.json();

  if (!res.ok) {
    console.error("Sigma API error:", data);
    throw new Error("Failed to create bookmark");
  }

  return data;
}

module.exports = {
  getSigmaAuthToken,
  createBookmark
};
