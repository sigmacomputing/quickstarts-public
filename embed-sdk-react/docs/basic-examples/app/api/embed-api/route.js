// app/api/embed-api/route.js

import { signEmbedUrl } from "@/lib/utils";
import { EMBED_PATH } from "@/lib/utils";

export async function GET(req) {
  console.log("API endpoint accessed"); // Log when the endpoint is accessed

  try {
    // Ensure EMBED_PATH is passed to signEmbedUrl
    const signedUrl = await signEmbedUrl(EMBED_PATH);
    console.log("Signed URL generated:", signedUrl); // Log the generated signed URL
    return new Response(JSON.stringify({ signedUrl }), {
      status: 200,
      headers: { "Content-Type": "application/json" },
    });
  } catch (error) {
    console.error("Error in API signing:", error);
    return new Response(
      JSON.stringify({ error: "Error signing URL" }),
      { status: 500, headers: { "Content-Type": "application/json" } }
    );
  }
}