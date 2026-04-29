/**
 * Shared wire-shape primitives that aren't tied to any single namespace.
 *
 * Types here are referenced from multiple protocol files (e.g. `JsonSchema`
 * appears in `SessionDetails.metadata_schema` and the catalog `/metadata/schema`
 * REST response).
 */

// ==================== JSON Schema ====================
//
// Subset of the full JSON Schema spec — just the fields the metadata form
// renderer cares about. Mirrors what `pydantic.BaseModel.model_json_schema()`
// returns.

export interface JsonSchemaProperty {
  type?: string;
  default?: unknown;
  description?: string;
  enum?: string[];
  items?: { type: string };
  title?: string;
  isAnnotation?: boolean;
}

export interface JsonSchema {
  title: string;
  type: string;
  properties: Record<string, JsonSchemaProperty>;
  required?: string[];
}
