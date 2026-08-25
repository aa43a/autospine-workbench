import assert from "node:assert/strict";
import test from "node:test";

import {
  candidatesAtPointer,
  nearestCandidate,
  nextCandidateForPointer,
} from "../modules/candidate-review-overlay.js";

const identity = ([x, y]) => ({ x, y });
const candidates = [
  { candidate_id: "left", xy: [10, 10] },
  { candidate_id: "middle", xy: [20, 10] },
  { candidate_id: "right", xy: [30, 10] },
];

test("dense candidate pointer hit resolves to the nearest point", () => {
  assert.equal(nearestCandidate(candidates, { x: 18, y: 10 }, identity)?.candidate_id, "middle");
  assert.equal(nearestCandidate(candidates, { x: 27, y: 10 }, identity)?.candidate_id, "right");
});

test("pointer hit respects the 44px target diameter and stable ties", () => {
  assert.equal(nearestCandidate(candidates, { x: 52.1, y: 10 }, identity), null);
  assert.equal(nearestCandidate(candidates, { x: 15, y: 10 }, identity)?.candidate_id, "left");
});

test("repeated pointer hits cycle through every member of a dense cluster", () => {
  const dense = [
    { candidate_id: "first", xy: [10, 10] },
    { candidate_id: "second", xy: [12, 10] },
    { candidate_id: "third", xy: [14, 10] },
  ];
  const pointer = { x: 12, y: 10 };
  let selected = "second";
  const visited = [];
  for (let click = 0; click < dense.length; click += 1) {
    selected = nextCandidateForPointer(dense, pointer, identity, selected).candidate_id;
    visited.push(selected);
  }
  assert.deepEqual(visited, ["first", "third", "second"]);
});

test("a pointer outside the selected cluster still chooses its local nearest candidate", () => {
  const separated = [
    { candidate_id: "selected-elsewhere", xy: [10, 10] },
    { candidate_id: "local-nearest", xy: [100, 100] },
    { candidate_id: "local-second", xy: [104, 100] },
  ];
  assert.equal(
    nextCandidateForPointer(
      separated,
      { x: 101, y: 100 },
      identity,
      "selected-elsewhere",
    ).candidate_id,
    "local-nearest",
  );
});

test("cluster order is distance-first and stable for equal distances", () => {
  const stable = [
    { candidate_id: "source-first", xy: [8, 10] },
    { candidate_id: "nearest", xy: [10, 10] },
    { candidate_id: "source-second", xy: [12, 10] },
  ];
  assert.deepEqual(
    candidatesAtPointer(stable, { x: 10, y: 10 }, identity).map(({ candidate_id: id }) => id),
    ["nearest", "source-first", "source-second"],
  );
});

test("cluster hit radius includes its exact boundary and rejects invalid radii", () => {
  const boundary = [{ candidate_id: "edge", xy: [22, 0] }];
  assert.equal(candidatesAtPointer(boundary, { x: 0, y: 0 }, identity, 22).length, 1);
  assert.equal(candidatesAtPointer(boundary, { x: 0, y: 0 }, identity, 21.999).length, 0);
  assert.deepEqual(candidatesAtPointer(boundary, { x: 0, y: 0 }, identity, -1), []);
  assert.deepEqual(candidatesAtPointer(boundary, { x: 0, y: 0 }, identity, Number.NaN), []);
});
