import type { components } from "../../../../contracts/generated/typescript/service-api";

export type RiskSnapshot = components["schemas"]["RiskSnapshot"];

const BASE_URL = import.meta.env.VITE_CORE_SERVICE_URL ?? "";

export async function getLatestRisk(portfolioId: string): Promise<RiskSnapshot | null> {
  const response = await fetch(`${BASE_URL}/portfolios/${encodeURIComponent(portfolioId)}/risk`);

  if (response.status === 404) {
    return null;
  }
  if (!response.ok) {
    throw new Error(`getLatestRisk(${portfolioId}) failed: ${response.status} ${response.statusText}`);
  }
  return (await response.json()) as RiskSnapshot;
}
