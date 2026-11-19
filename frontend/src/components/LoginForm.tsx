import { useState, type FormEvent } from "react";
import { AlertCircle, Lock, LoaderCircle, Shield } from "lucide-react";
import { useAuth } from "../context/AuthContext";
import { ApiError } from "../api";

export function LoginForm() {
  const { login } = useAuth();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    setLoading(true);
    try {
      await login({ email: email.trim(), password });
    } catch (err) {
      if (err instanceof ApiError) {
        if (err.status === 401 || err.code === "invalid_credentials") {
          setError("Invalid email or password.");
        } else if (err.status === 429 || err.code === "account_locked") {
          setError("Account is temporarily locked. Please try again later.");
        } else {
          setError(err.message || "Authentication failed. Please try again.");
        }
      } else {
        setError("Unable to connect to the authentication service.");
      }
    } finally {
      setLoading(false);
      setPassword(""); // Clear password from memory after submit attempt
    }
  }

  return (
    <div className="login-container" style={{ maxWidth: 440, margin: "60px auto", padding: "0 16px" }}>
      <section className="panel" style={{ padding: "32px 28px" }}>
        <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 16 }}>
          <span className="health-orbit" style={{ width: 36, height: 36 }}>
            <Shield size={18} />
          </span>
          <div>
            <h2 style={{ fontSize: 18, margin: 0, fontWeight: 600 }}>Console sign in</h2>
            <p className="subtle" style={{ margin: 0, fontSize: 13 }}>
              Protected operations workspace
            </p>
          </div>
        </div>

        {error && (
          <div
            role="alert"
            style={{
              display: "flex",
              alignItems: "center",
              gap: 10,
              padding: "10px 14px",
              marginBottom: 18,
              borderRadius: 6,
              background: "rgba(180, 40, 40, 0.08)",
              border: "1px solid rgba(180, 40, 40, 0.25)",
              color: "#922",
              fontSize: 13,
            }}
          >
            <AlertCircle size={16} style={{ flexShrink: 0 }} />
            <span>{error}</span>
          </div>
        )}

        <form onSubmit={handleSubmit}>
          <label>
            Email address
            <input
              type="email"
              name="email"
              autoComplete="email"
              required
              autoFocus
              value={email}
              disabled={loading}
              onChange={(e) => setEmail(e.target.value)}
              placeholder="operator@example.com"
            />
          </label>

          <label style={{ marginTop: 14 }}>
            Password
            <input
              type="password"
              name="password"
              autoComplete="current-password"
              required
              value={password}
              disabled={loading}
              onChange={(e) => setPassword(e.target.value)}
              placeholder="••••••••••••"
            />
          </label>

          <div style={{ marginTop: 24 }}>
            <button
              type="submit"
              className="button primary"
              disabled={loading}
              style={{ width: "100%", justifyContent: "center" }}
            >
              {loading ? (
                <>
                  <LoaderCircle size={15} className="spinner" />
                  Authenticating…
                </>
              ) : (
                <>
                  <Lock size={15} />
                  Sign in to console
                </>
              )}
            </button>
          </div>
        </form>

        <p className="small-note" style={{ marginTop: 20, textAlign: "center", fontSize: 12, opacity: 0.7 }}>
          Append-only session and audit events are recorded for every attempt.
        </p>
      </section>
    </div>
  );
}
