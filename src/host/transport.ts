import { invoke as tauriInvoke } from "@tauri-apps/api/core";
import {
  validateCommandRequest,
  validateCommandResponse,
  type CommandId,
} from "../contracts/renderer";
const fixtureMode = import.meta.env.VITE_AQ_FIXTURE_MODE === "1";
if (import.meta.env.PROD && fixtureMode) {
  throw new Error("fixture mode is forbidden in production");
}

export async function invokeHost(
  commandId: CommandId,
  payload: Record<string, unknown>,
): Promise<Record<string, unknown>> {
  const request = validateCommandRequest(commandId, payload);
  const response = fixtureMode
    ? await (await import("./fixtures")).fixtureInvoke(commandId, request)
    : await tauriInvoke(commandId, { request });
  return validateCommandResponse(commandId, response);
}

export const transportMode = fixtureMode ? "fixture" : "tauri";
