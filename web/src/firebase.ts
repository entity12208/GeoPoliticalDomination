function toFirestoreValue(value: unknown): Record<string, unknown> {
  if (value === null || value === undefined) return { nullValue: null };
  if (typeof value === 'boolean') return { booleanValue: value };
  if (typeof value === 'number') {
    if (Number.isInteger(value)) return { integerValue: String(value) };
    return { doubleValue: value };
  }
  if (typeof value === 'string') return { stringValue: value };
  if (Array.isArray(value)) {
    return { arrayValue: { values: value.map((entry) => toFirestoreValue(entry)) } };
  }
  if (typeof value === 'object') {
    return {
      mapValue: {
        fields: Object.fromEntries(
          Object.entries(value as Record<string, unknown>).map(([key, val]) => [key, toFirestoreValue(val)])
        )
      }
    };
  }
  return { stringValue: String(value) };
}

function fromFirestoreValue(input: Record<string, unknown>): unknown {
  if (!input || typeof input !== 'object') return null;
  if ('stringValue' in input) return input.stringValue;
  if ('booleanValue' in input) return input.booleanValue;
  if ('integerValue' in input) return Number(input.integerValue);
  if ('doubleValue' in input) return Number(input.doubleValue);
  if ('arrayValue' in input) {
    const values = (input.arrayValue as { values?: Record<string, unknown>[] })?.values ?? [];
    return values.map((entry) => fromFirestoreValue(entry as Record<string, unknown>));
  }
  if ('mapValue' in input) {
    const fields = (input.mapValue as { fields?: Record<string, unknown> })?.fields ?? {};
    return Object.fromEntries(
      Object.entries(fields).map(([key, value]) => [key, fromFirestoreValue(value as Record<string, unknown>)] )
    );
  }
  if ('nullValue' in input) return null;
  return null;
}

export type FirestoreDocument = Record<string, unknown>;

export function firestoreFieldsFromObject(data: Record<string, unknown>): Record<string, unknown> {
  return Object.fromEntries(
    Object.entries(data).map(([key, value]) => [key, toFirestoreValue(value)])
  );
}

export function firestoreObjectFromDocument(input: { fields?: Record<string, unknown> } | null | undefined): Record<string, unknown> {
  const fields = input?.fields ?? {};
  return Object.fromEntries(
    Object.entries(fields).map(([key, value]) => [key, fromFirestoreValue(value as Record<string, unknown>)] )
  );
}
