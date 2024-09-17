"use client";
import { useSigmaIframe } from "@sigmacomputing/react-embed-sdk";

export default function BasicExample({ src }: { src: string }) {
  const { iframeRef, loading, error } = useSigmaIframe();
  return (
    <>
      <p className={loading ? "show" : "hidden"}> Loading...</p>
      <p className={error ? "show" : "hidden"}> Error loading iframe</p>
      <iframe
        src={src}
        ref={iframeRef}
        className={loading || error ? "hidden" : "show"}
        width={"100%"}
        height={"100%"}
      />
    </>
  );
}
