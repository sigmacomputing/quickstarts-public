// basic-example-wrapper.tsx
"use client"; // This directive tells Next.js to treat this as a Client Component

import { useEffect, useState } from "react";
import { signEmbedUrl } from "@/lib/utils";
import BasicExample from "./basic-example-embed";

export default function SignedIframe() {
  const [signedSrc, setSignedSrc] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const src = "https://app.sigmacomputing.com/embed/1-24vP6WRI5BK8C8dLX4kzac"; // Hardcoded URL as discussed

  useEffect(() => {
    const getSignedUrl = async () => {
      try {
        const signedUrl = await signEmbedUrl(src);
        console.log("Signed URL:", signedUrl);
        setSignedSrc(signedUrl); // Set the signed URL in state
      } catch (err) {
        console.error("Error signing URL:", err);
        setError("Error loading iframe");
      }
    };

    getSignedUrl(); // Call the async function to sign the URL
  }, [src]); // Empty dependency array since `src` is hardcoded and won't change

  // Conditional rendering based on signing state
  if (error) return <p>{error}</p>;
  if (!signedSrc) return <p>Loading...</p>;

  return <BasicExample src={signedSrc} />; // Pass signed URL to the iframe component
}
