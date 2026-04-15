// utils.js
import { type ClassValue, clsx } from "clsx";
import { twMerge } from "tailwind-merge";
import { v4 as uuid } from "uuid";

// Embed Configuration and User-Specific Values
export const EMBED_PATH = "your_sigma_base_url_to_embed"; // Ensure this is exported

const CLIENT_ID = "your_client_id";
const SECRET = "your_secret";
const EMAIL = "your_embed_user_email";
const ACCOUNT_TYPE = "Pro";
const TEAM = "your_team";
const SESSION_LENGTH = 3600; // Default session length in seconds

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

function base64urlEncodeString(str: string): string {
  const bytes = new TextEncoder().encode(str);
  let binary = "";
  for (const byte of bytes) {
    binary += String.fromCharCode(byte);
  }
  return btoa(binary)
    .replace(/\+/g, "-")
    .replace(/\//g, "_")
    .replace(/=/g, "");
}

function base64urlEncodeBuffer(buffer: ArrayBuffer): string {
  const bytes = new Uint8Array(buffer);
  let binary = "";
  for (const byte of bytes) {
    binary += String.fromCharCode(byte);
  }
  return btoa(binary)
    .replace(/\+/g, "-")
    .replace(/\//g, "_")
    .replace(/=/g, "");
}

async function generateJWT(): Promise<string> {
  const header = { alg: "HS256", typ: "JWT", kid: CLIENT_ID };
  const time = Math.floor(Date.now() / 1000);
  const expirationTime = time + Math.min(SESSION_LENGTH, 2592000);

  const payload = {
    sub: EMAIL,
    iss: CLIENT_ID,
    jti: uuid(),
    iat: time,
    exp: expirationTime,
    account_type: ACCOUNT_TYPE,
    teams: [TEAM],
  };

  const encodedHeader = base64urlEncodeString(JSON.stringify(header));
  const encodedPayload = base64urlEncodeString(JSON.stringify(payload));
  const signingInput = `${encodedHeader}.${encodedPayload}`;

  const encoder = new TextEncoder();
  const keyData = encoder.encode(SECRET);
  const data = encoder.encode(signingInput);

  const key = await crypto.subtle.importKey(
    "raw",
    keyData,
    { name: "HMAC", hash: "SHA-256" },
    false,
    ["sign"]
  );
  const signature = await crypto.subtle.sign("HMAC", key, data);
  const encodedSignature = base64urlEncodeBuffer(signature);

  return `${signingInput}.${encodedSignature}`;
}

export async function signEmbedUrl(dashboard: string): Promise<string> {
  if (!SECRET || !CLIENT_ID) {
    throw new Error("The Embed SECRET or CLIENT_ID is missing in the code");
  }

  const token = await generateJWT();
  const separator = dashboard.includes("?") ? "&" : "?";
  return `${dashboard}${separator}:jwt=${encodeURIComponent(token)}&:embed=true`;
}