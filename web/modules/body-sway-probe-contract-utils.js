"use strict";

export const SHA256 = /^[0-9a-f]{64}$/;
export const SAFE_ID = /^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$/;

export function objectValue(value, label) {
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    throw new Error(`${label}无效`);
  }
  return value;
}

export function exactFields(value, fields, label) {
  objectValue(value, label);
  const actual = Object.keys(value).sort();
  const expected = [...fields].sort();
  if (actual.length !== expected.length
      || actual.some((field, index) => field !== expected[index])) {
    throw new Error(`${label}字段无效`);
  }
  return value;
}

export function digestValue(value, label) {
  if (typeof value !== "string" || !SHA256.test(value)) {
    throw new Error(`${label}无效`);
  }
  return value;
}

export function safeId(value, label) {
  if (typeof value !== "string" || !SAFE_ID.test(value)) {
    throw new Error(`${label}无效`);
  }
  return value;
}

export function integer(value, minimum, label, maximum = Number.MAX_SAFE_INTEGER) {
  if (!Number.isInteger(value) || value < minimum || value > maximum) {
    throw new Error(`${label}无效`);
  }
  return value;
}

export function finiteNumber(value, label) {
  if (typeof value !== "number" || !Number.isFinite(value)) {
    throw new Error(`${label}无效`);
  }
  return value;
}

export function exactCopy(value) {
  return JSON.parse(JSON.stringify(value));
}

export function sameJson(left, right) {
  return stableJson(left) === stableJson(right);
}

function stableJson(value) {
  if (Array.isArray(value)) {
    return `[${value.map(stableJson).join(",")}]`;
  }
  if (value && typeof value === "object") {
    return `{${Object.keys(value).sort().map((key) =>
      `${JSON.stringify(key)}:${stableJson(value[key])}`).join(",")}}`;
  }
  return JSON.stringify(value);
}
