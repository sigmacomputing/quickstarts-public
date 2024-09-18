// example-link.tsx
"use client";
import { cn } from "@/lib/utils";
import { usePathname } from 'next/navigation';
import Link from "next/link";

// Define a type or interface for the component props
interface ExampleLinkProps {
  href: string;      // Ensure href is a string
  linkText: string;  // Ensure linkText is a string
}

export default function ExampleLink({ href, linkText }: ExampleLinkProps) {
  const pathname = usePathname();

  return (
    <Link
      href={href}
      className={cn(
        "transition-colors hover:text-foreground/80",
        pathname === href ? "text-foreground" : "text-foreground/60"
      )}
    >
      {linkText}
    </Link>
  );
}
