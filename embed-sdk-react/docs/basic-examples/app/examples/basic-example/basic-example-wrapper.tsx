// basic-example-wrapper.tsx
"use client";

import { useEffect, useState } from "react";
import BasicExample from "./basic-example-embed";

export default function SignedIframe() {
  const [signedSrc, setSignedSrc] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const fetchSignedUrl = async () => {
      try {
        const response = await fetch("/api/embed-api");
        if (!response.ok) throw new Error("Failed to fetch signed URL from API");
  
        const data = await response.json();
        if (!data.signedUrl) throw new Error("API response missing signed URL");
  
        console.log("Signed URL received:", data.signedUrl);
        setSignedSrc(data.signedUrl);
      } catch (err) {
        console.error("Error fetching signed URL:", err);
        setError(`Error loading iframe: ${err.message}`);
      }
    };
  
    fetchSignedUrl();
  }, []);

  // Conditional rendering based on signing state
  if (error) return <p>{error}</p>;
  if (!signedSrc) return <p>Loading...</p>;

  return <BasicExample src={signedSrc} />;
}
