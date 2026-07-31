import contractDocument from "../agent_quota/resources/renderer_contract_v1.json";

type JsonObject = Record<string, unknown>;

type ContractField = {
  name: string;
  type: "array" | "boolean" | "integer" | "object" | "string";
  required: boolean;
  ref?: string;
  allowed_values?: string[];
  max_utf8_bytes?: number;
  max_items?: number;
  minimum?: number;
  maximum?: number;
};

type ContractSchema = {
  schema_ref: string;
  fields: ContractField[];
  additional_properties: false;
};

type CommandDefinition = {
  command_id: string;
  request_schema_ref: string;
  response_schema_ref: string;
};

const document = contractDocument as {
  command_ids: string[];
  commands: CommandDefinition[];
  dto_schemas: ContractSchema[];
  forbidden_renderer_fields: string[];
};

export const COMMAND_IDS = document.command_ids as readonly string[];
export type CommandId = (typeof COMMAND_IDS)[number];

const schemas = new Map(document.dto_schemas.map((schema) => [schema.schema_ref, schema]));
const commands = new Map(document.commands.map((command) => [command.command_id, command]));

if (schemas.size !== 29 || commands.size !== 10) {
  throw new Error("renderer contract closure mismatch");
}

function isObject(value: unknown): value is JsonObject {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function utf8Bytes(value: string): number {
  return new TextEncoder().encode(value).byteLength;
}

function validateField(field: ContractField, value: unknown, path: string): unknown {
  switch (field.type) {
    case "string": {
      if (typeof value !== "string") throw new Error(`${path}: expected string`);
      if (utf8Bytes(value) > (field.max_utf8_bytes ?? -1)) {
        throw new Error(`${path}: string too large`);
      }
      if ((field.allowed_values?.length ?? 0) > 0 && !field.allowed_values?.includes(value)) {
        throw new Error(`${path}: enum mismatch`);
      }
      return value;
    }
    case "integer":
      if (
        !Number.isSafeInteger(value) ||
        (value as number) < (field.minimum ?? Number.POSITIVE_INFINITY) ||
        (value as number) > (field.maximum ?? Number.NEGATIVE_INFINITY)
      ) {
        throw new Error(`${path}: invalid integer`);
      }
      return value;
    case "boolean":
      if (typeof value !== "boolean") throw new Error(`${path}: expected boolean`);
      return value;
    case "object":
      if (!field.ref) throw new Error(`${path}: missing schema reference`);
      return validateSchema(field.ref, value, path);
    case "array":
      if (!Array.isArray(value) || value.length > (field.max_items ?? -1) || !field.ref) {
        throw new Error(`${path}: invalid array`);
      }
      return value.map((item, index) => validateSchema(field.ref!, item, `${path}[${index}]`));
  }
}

export function validateSchema(schemaRef: string, payload: unknown, path = schemaRef): JsonObject {
  const schema = schemas.get(schemaRef);
  if (!schema || !isObject(payload)) throw new Error(`${path}: invalid DTO`);

  const fields = new Map(schema.fields.map((field) => [field.name, field]));
  for (const key of Object.keys(payload)) {
    if (!fields.has(key)) throw new Error(`${path}.${key}: unknown field`);
  }
  for (const field of schema.fields) {
    if (field.required && !(field.name in payload)) {
      throw new Error(`${path}.${field.name}: required field missing`);
    }
  }

  return Object.fromEntries(
    Object.entries(payload).map(([key, value]) => {
      const field = fields.get(key);
      if (!field) throw new Error(`${path}.${key}: unknown field`);
      return [key, validateField(field, value, `${path}.${key}`)];
    }),
  );
}

function command(commandId: string): CommandDefinition {
  const definition = commands.get(commandId);
  if (!definition) throw new Error("unknown renderer command");
  return definition;
}

export function validateCommandRequest(commandId: string, payload: unknown): JsonObject {
  return validateSchema(command(commandId).request_schema_ref, payload, `${commandId}.request`);
}

export function validateCommandResponse(commandId: string, payload: unknown): JsonObject {
  return validateSchema(command(commandId).response_schema_ref, payload, `${commandId}.response`);
}

export const rendererContract = Object.freeze({
  commandCount: commands.size,
  schemaCount: schemas.size,
  forbiddenFields: Object.freeze([...document.forbidden_renderer_fields]),
});
