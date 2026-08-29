export function createLoadGuard() {
  let generation = 0;
  return {
    begin() { generation += 1; return generation; },
    invalidate() { generation += 1; },
    isCurrent(token) { return token === generation; },
  };
}

export function sameIdentitySnapshot(expected, current) {
  return expected.policy === current.policy
    && expected.foot === current.foot
    && expected.depth === current.depth
    && expected.policyJson === current.policyJson
    && expected.footJson === current.footJson
    && expected.depthJson === current.depthJson
    && expected.policySha === current.policySha
    && expected.footSha === current.footSha
    && expected.depthSha === current.depthSha;
}
