export default function LibraryPage() {
  return (
    <div>
      <h1 className="text-2xl font-bold text-foreground">Knowledge Library</h1>
      <p className="mt-2 text-muted-foreground">
        Manage your knowledge base, upload documents, and view stored facts.
      </p>
      <div className="mt-8 rounded-lg border border-border p-8 text-center text-muted-foreground">
        Knowledge library is empty. Upload documents to build your knowledge base.
      </div>
    </div>
  );
}
