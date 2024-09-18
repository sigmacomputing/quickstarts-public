// basic-example-wrapper.tsx
// The SignedIframe component is responsible for securely embedding a Sigma Computing dashboard into a React application.
// 	signEmbedUrl: This function is imported from the Sigma Embed SDK library and is used to generate a signed URL for secure access to a Sigma dashboard.

// Import the signEmbedUrl function from the utilities module
import { signEmbedUrl } from "@/lib/utils";
// Import the BasicExample component, which is responsible for rendering the iframe
import BasicExample from "./basic-example-embed";

// Define an asynchronous component to sign the URL and render the iframe
export default async function SignedIframe() {
  // Get the base URL from the environment variable
  const src = process.env.EMBED_URL || ""; // Use the value from the .env file

  try {
    // Await the signed URL by passing the base URL to the signEmbedUrl function
    const signedSrc = await signEmbedUrl(src);

    // Log the base and signed URLs as output in server-side terminal session
    console.log("Signed URL:", signedSrc);

    // Return the BasicExample component with the signed URL as a prop
    return <BasicExample src={signedSrc} />;
  } catch (error) {
    // Log any errors encountered during signing
    console.error("Error signing URL:", error);
    return <p>Error loading iframe</p>;
  }
}