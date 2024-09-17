export default function ExampleLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <main className="container mx-auto">
      <div className="grid grid-cols-2 gap-8 p-8">{children}</div>
    </main>
  );
}
