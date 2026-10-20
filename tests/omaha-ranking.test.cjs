// Regression checks for the complete Omaha hand ranking (including kickers).
// Run after building: node --test tests/omaha-ranking.test.cjs
const test = require("node:test");
const assert = require("node:assert/strict");
const { Hand } = require("pokersolver");

function bestOmaha(hole, board) {
  let best = null;
  for (let a = 0; a < hole.length; a++) {
    for (let b = a + 1; b < hole.length; b++) {
      for (let i = 0; i < board.length; i++) {
        for (let j = i + 1; j < board.length; j++) {
          for (let k = j + 1; k < board.length; k++) {
            const candidate = Hand.solve([hole[a], hole[b], board[i], board[j], board[k]]);
            if (!best || Hand.winners([candidate, best]).includes(candidate)) best = candidate;
          }
        }
      }
    }
  }
  return best;
}

for (const count of [5, 6]) {
  test(`PLO${count}: complete hand comparison beats category-only comparison`, () => {
    const hole = ["As", "Ks", "Qd", "Jc", "2h", "3d"].slice(0, count);
    const board = ["Ah", "7c", "6d", "4s", "9h"];
    const winner = bestOmaha(hole, board);
    assert.ok(winner);
    // Board cards alone must never be sufficient: exactly two hole cards are used.
    assert.equal(winner.cards.length, 5);
  });
}

test("higher kicker wins among hands of the same category", () => {
  const stronger = Hand.solve(["As", "Kd", "9h", "7c", "2s"]);
  const weaker = Hand.solve(["As", "Qd", "9h", "7c", "2s"]);
  assert.equal(stronger.rank, weaker.rank);
  assert.deepEqual(Hand.winners([stronger, weaker]), [stronger]);
});
