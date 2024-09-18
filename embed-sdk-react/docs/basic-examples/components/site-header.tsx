import { MainNav } from "./main-nav";

export function SiteHeader() {
  return (
    <header className="supports-backdrop-blur:bg-background/60 sticky top-0 z-50 w-full border-b bg-background/95 backdrop-blur">
      <div className="container mx-auto flex h-20 items-center">
        <MainNav />
      </div>
    </header>
  );
}
