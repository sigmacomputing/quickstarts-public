// main-nav.tsx
"use client";
import Link from 'next/link';
import { usePathname } from 'next/navigation';
import SigmaIcon from './ui/sigma-icon'; // Custom Sigma logo icon component
import PlugsLogo from './ui/plugs-icon'; // Custom Parent application logo icon component

export function MainNav() {
  const pathname = usePathname();

  // Determine which logo to display and what header text to use based on the pathname
  const isBasicExample = pathname.includes("/examples/basic-example");
  const LogoComponent = isBasicExample ? PlugsLogo : SigmaIcon;
  const headerText = isBasicExample ? "Sample Parent Application with Sigma Embed" : "Welcome to the Embedding SDK for React";

  return (
    <div className="flex items-center space-x-4 p-4">
      {/* Conditionally render the button only for the PlugsLogo */}
      {isBasicExample && (
        <Link href="/" className="text-white bg-[rgb(23,69,68)] hover:bg-[rgb(23,69,68)]/90 font-bold py-2 px-4 rounded">
          Go Back
        </Link>
      )}
      <LogoComponent size={50} />  {/* Ensure logo size is appropriate */}
      <h2 className="font-bold text-2xl whitespace-nowrap my-auto">{headerText}</h2>
    </div>
  );
}