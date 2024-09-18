// basic-example-embed.tsx
// Utilizes the Sigma Computing Embed SDK to integrate an iframe within a React application.

"use client"; // Next.js directive to ensure this component runs only on the client-side.

import React from "react";
// Import the useSigmaIframe hook from the Sigma Computing React Embed SDK
import { useSigmaIframe } from "@sigmacomputing/react-embed-sdk";

// Define the BasicExample component, which receives a 'src' prop for the iframe URL
export default function BasicExample({ src }: { src: string }) {
  // Destructure the iframeRef, loading, and error values from the useSigmaIframe hook
  const { iframeRef, loading, error } = useSigmaIframe();

  return (
    // Parent container with full height
    <div className="h-full">
      {/* Conditional rendering: Display loading text if the iframe is loading */}
      {loading && <p className="text-center">Loading...</p>}
      {/* Conditional rendering: Display error message if there is an error loading the iframe */}
      {error && <p className="text-center text-red-500">Error loading iframe</p>}
      {/* Render the iframe, filling the parent container */}
      <iframe
        src={src} // Source URL for the iframe
        ref={iframeRef} // Reference from useSigmaIframe hook for managing iframe interactions
        className={`w-full h-full ${loading || error ? "hidden" : ""}`} // CSS classes for full width/height and conditional visibility
        style={{ border: "none" }} // Inline style to remove default border
      />
    </div>
  );
}