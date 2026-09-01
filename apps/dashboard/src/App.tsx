import { useState } from "react";
import { LiveRiskPanel } from "./LiveRiskPanel";

export function App() {
  const [portfolioId, setPortfolioId] = useState("");
  const [activePortfolioId, setActivePortfolioId] = useState<string | null>(null);

  return (
    <main>
      <h1>Meridian</h1>
      <form
        onSubmit={(event) => {
          event.preventDefault();
          const id = portfolioId.trim();
          if (id) {
            setActivePortfolioId(id);
          }
        }}
      >
        <label>
          Portfolio ID
          <input value={portfolioId} onChange={(event) => setPortfolioId(event.target.value)} />
        </label>
        <button type="submit">Load</button>
      </form>

      {activePortfolioId && <LiveRiskPanel key={activePortfolioId} portfolioId={activePortfolioId} />}
    </main>
  );
}
