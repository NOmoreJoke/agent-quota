import { describe, expect, it } from "vitest";
import contractDocument from "../agent_quota/resources/renderer_contract_v1.json";
import {
  COMMAND_IDS,
  rendererContract,
  validateCommandRequest,
  validateSchema,
} from "./renderer";

type Field = {
  name: string;
  type: string;
  required: boolean;
  ref?: string;
  allowed_values?: string[];
};

const schemas = new Map(
  contractDocument.dto_schemas.map((schema) => [schema.schema_ref, schema]),
);

function validValue(field: Field): unknown {
  if (field.type === "string") return field.allowed_values?.[0] ?? "x";
  if (field.type === "integer") return 0;
  if (field.type === "boolean") return false;
  if (field.type === "object") return validObject(field.ref!);
  if (field.type === "array") return [];
  throw new Error(`unsupported ${field.type}`);
}

function validObject(schemaRef: string): Record<string, unknown> {
  const schema = schemas.get(schemaRef);
  if (!schema) throw new Error(`missing ${schemaRef}`);
  return Object.fromEntries(
    schema.fields
      .filter((field) => field.required)
      .map((field) => [field.name, validValue(field)]),
  );
}

describe("renderer contract", () => {
  it("closes exactly ten commands and twenty-nine schemas", () => {
    expect(COMMAND_IDS).toHaveLength(10);
    expect(new Set(COMMAND_IDS).size).toBe(10);
    expect(rendererContract.schemaCount).toBe(29);
  });

  it("accepts one synthesized value for every closed schema", () => {
    for (const schema of contractDocument.dto_schemas) {
      expect(validateSchema(schema.schema_ref, validObject(schema.schema_ref))).toEqual(
        validObject(schema.schema_ref),
      );
    }
  });

  it("keeps keychain lock distinct from Provider availability", () => {
    expect(
      validateSchema("aq-renderer-dto://v1/shared-safe-error", {
        code: "keychain-locked",
        retryable: false,
      }),
    ).toEqual({ code: "keychain-locked", retryable: false });
  });

  it("rejects unknown commands, extra fields, nested extras and bad bounds", () => {
    expect(() => validateCommandRequest("unknown", {})).toThrow("unknown renderer command");
    expect(() => validateCommandRequest("bootstrap_state", { injected: true })).toThrow(
      "unknown field",
    );
    expect(() =>
      validateSchema("aq-renderer-dto://v1/shared-application-state", {
        launch_state: "ready",
        offline: false,
        nested_attack: "x",
      }),
    ).toThrow("unknown field");
    expect(() =>
      validateCommandRequest("accounts_read", { scope_ref: "x".repeat(129) }),
    ).toThrow("string too large");
    expect(() =>
      validateSchema("aq-renderer-dto://v1/shared-application-state", {
        launch_state: "untrusted",
        offline: false,
      }),
    ).toThrow("enum mismatch");
    expect(() =>
      validateSchema("aq-renderer-dto://v1/shared-nondestructive-config-change-set", {
        changes: [],
        expected_generation: -1,
      }),
    ).toThrow("invalid integer");
  });
});
