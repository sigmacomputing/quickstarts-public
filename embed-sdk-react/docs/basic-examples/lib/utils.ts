import { type ClassValue, clsx } from "clsx";
import { twMerge } from "tailwind-merge";
import { v4 as uuid } from "uuid";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

/**
 * Buffer to hex string:
 * - convert buffer to byte array
 * - convert bytes to hex string
 * @see https://developer.mozilla.org/en-US/docs/Web/API/SubtleCrypto/digest#converting_a_digest_to_a_hex_string
 */
export function bufferToHex(buffer: ArrayBuffer) {
  return Array.from(new Uint8Array(buffer))
    .map((b) => b.toString(16).padStart(2, "0"))
    .join("");
}

/**
 * Uses Web Crypto API to create a SHA256 HMAC hex string.
 */
async function simpleHmac({ key, data }: { key: string; data: string }) {
  const encoder = new TextEncoder();
  const encodedKey = encoder.encode(key);
  const encodedData = encoder.encode(data);
  /**
   * @see https://developer.mozilla.org/en-US/docs/Web/API/SubtleCrypto/importKey
   */
  const hmacKey = await crypto.subtle.importKey(
    "raw",
    encodedKey,
    {
      name: "HMAC",
      hash: "SHA-256",
    },
    true,
    ["sign", "verify"],
  );
  /**
   * @see https://developer.mozilla.org/en-US/docs/Web/API/SubtleCrypto/sign#hmac_2
   */
  const signature = await crypto.subtle.sign("HMAC", hmacKey, encodedData);

  const hex = bufferToHex(signature);

  return { hex };
}

export async function signEmbedUrl(dashboard: string): Promise<string> {
  const { EMBED_SECRET, EMBED_CLIENT_ID } = process.env;
  if (!EMBED_SECRET || !EMBED_CLIENT_ID) {
    throw new Error("SIGMA_EMBED_SECRET is not set");
  }

  const searchParamsObject = {
    ":mode": "userbacked",
    ":email": "demo@embed.com",
    ":external_user_team": "Sales_People",
    ":account_type": "viewer",
    ":nonce": uuid(),
    ":time": `${Math.floor(new Date().getTime() / 1000)}`,
    ":session_length": "36000",
    ":client_id": EMBED_CLIENT_ID,
    ":external_user_id": "123",
  };

  const searchParams = new URLSearchParams(searchParamsObject);

  // EMBED_PATH - Generated on your workbook
  const urlWithSearchParams = `${dashboard}?${searchParams.toString()}`;

  // EMBED_SECRET - Sigma Embed Secret generated in your admin portal
  const SIGNATURE = await simpleHmac({
    key: EMBED_SECRET,
    data: urlWithSearchParams,
  });

  searchParams.append(":signature", SIGNATURE.hex);

  const signedUrl = `${dashboard}?${searchParams.toString()}`;

  return signedUrl;
}
