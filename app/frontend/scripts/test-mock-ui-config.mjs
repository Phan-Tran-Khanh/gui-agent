import assert from "node:assert/strict";

const { isMockUiEnabled } = await import("../src/mockUiConfig.js");

assert.equal(isMockUiEnabled(undefined), false);
assert.equal(isMockUiEnabled(""), false);
assert.equal(isMockUiEnabled("false"), false);
assert.equal(isMockUiEnabled("TRUE"), true);
assert.equal(isMockUiEnabled(" true "), true);

console.log("mock UI configuration tests passed");
