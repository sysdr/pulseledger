"use client";

import { useEffect, useState } from "react";

type HealthResponse = {
  status: string;
  day: number;
  service: string;
};

const API_BASE = process.env.NEXT_PUBLIC_API_BASE ?? "http://localhost:8001";

export default function Home() {
  const [health, setHealth] = useState<HealthResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fetch(`${API_BASE}/api/health`)
      .then((res) => {
        if (!res.ok) throw new Error(`Backend returned ${res.status}`);
        return res.json();
      })
      .then(setHealth)
      .catch((err) => setError(err.message));
  }, []);

  return (
    <main
      style={{
        maxWidth: 560,
        margin: "80px auto",
        padding: "0 24px",
        color: "#1a1a2e",
      }}
    >
      <h1 style={{ fontSize: 28, marginBottom: 4 }}>PulseLedger</h1>
      <p style={{ color: "#6b7280", marginTop: 0 }}>
        Day 1: Foundations Laid
      </p>

      <div
        style={{
          marginTop: 32,
          padding: 16,
          borderRadius: 8,
          border: "1px solid #e5e7eb",
          display: "flex",
          alignItems: "center",
          gap: 10,
        }}
      >
        <span
          style={{
            width: 10,
            height: 10,
            borderRadius: "50%",
            backgroundColor: health ? "#22c55e" : error ? "#ef4444" : "#d1d5db",
            display: "inline-block",
          }}
        />
        <span>
          {health
            ? `API: ${health.status} (day ${health.day})`
            : error
              ? `API unreachable: ${error}`
              : "Checking API…"}
        </span>
      </div>
    </main>
  );
}
