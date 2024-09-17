"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

import { cn } from "@/lib/utils";
import SigmaIcon from "./ui/sigma-icon";

export function MainNav() {
  const pathname = usePathname();

  return (
    <div className="mr-4 hidden md:flex">
      <Link href="/" className="mr-6 flex items-center space-x-2">
        <span className="hidden font-bold sm:inline-block">
          <div className="flex items-center text-lg font-medium">
            <SigmaIcon size={32} />
            sigma
          </div>
        </span>
      </Link>
      <nav className="mr-4 flex items-center space-x-6 text-sm font-medium">
        <Link
          href="/examples/basic-example"
          className={cn(
            "transition-colors hover:text-foreground/80",
            pathname === "/examples/basic-example"
              ? "text-foreground"
              : "text-foreground/60",
          )}
        >
          Examples
        </Link>
      </nav>
    </div>
  );
}
