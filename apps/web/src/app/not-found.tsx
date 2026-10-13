import Link from "next/link";

export default function NotFound() {
  return (
    <div className="auth">
      <div className="card">
        <h1>Page not found</h1>
        <p className="muted">The link may be old, or the page moved.</p>
        <Link href="/" className="btn pri">Go to my home page</Link>
      </div>
    </div>
  );
}
