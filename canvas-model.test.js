// The canvas page's rules, without a browser: `node --test`.
// Whatever replaces canvas.html keeps these passing by wrapping the same model.
const { test } = require("node:test");
const assert = require("node:assert/strict");
const m = require("./canvas-model.js");

const NOW = Date.parse("2026-11-08T12:00:00Z");
const inMinutes = (n) => new Date(NOW + n * 60_000).toISOString();

function aBlock(overrides = {}) {
    return {
        id: 1, x0: 4, y0: 7, x1: 6, y1: 9, owner: "1", colour: "#ff0055",
        status: "held", expires_at: inMinutes(10), ...overrides,
    };
}

function boardWith(...claims) {
    const tiles = {};
    claims.forEach((c) => m.applyClaim(tiles, c));
    return tiles;
}

test("dragging either way picks the same half-open block", () => {
    const forwards = m.blockBetween({ x: 2, y: 3 }, { x: 5, y: 4 });
    const backwards = m.blockBetween({ x: 5, y: 4 }, { x: 2, y: 3 });

    assert.deepEqual(forwards, { x0: 2, y0: 3, x1: 6, y1: 5 });
    assert.deepEqual(backwards, forwards);
});

test("a press without a drag picks one tile", () => {
    assert.deepEqual(m.blockBetween({ x: 9, y: 9 }, { x: 9, y: 9 }), { x0: 9, y0: 9, x1: 10, y1: 10 });
});

test("reserving sends the picked block and colour", () => {
    assert.deepEqual(m.reserveRequest({ x0: 2, y0: 3, x1: 6, y1: 5 }, "#00ff00"), {
        x0: 2, y0: 3, x1: 6, y1: 5, colour: "#00ff00",
    });
});

test("a held block covers every tile in it", () => {
    const tiles = boardWith(aBlock());

    assert.equal(m.takenIn(tiles, { x0: 0, y0: 0, x1: 100, y1: 100 }), 4);
    assert.equal(m.takenIn(tiles, { x0: 6, y0: 7, x1: 8, y1: 9 }), 0); // x1=6 is not included
});

test("a released block frees its tiles", () => {
    const tiles = boardWith(aBlock(), aBlock({ status: "released" }));

    assert.equal(m.takenIn(tiles, { x0: 0, y0: 0, x1: 100, y1: 100 }), 0);
});

test("a late release of an old block doesn't wipe the newer block on its tiles", () => {
    const tiles = boardWith(aBlock({ id: 1 }), aBlock({ id: 2, owner: "bob" }));

    m.applyClaim(tiles, aBlock({ id: 1, status: "released" }));

    assert.equal(m.claimAt(tiles, 4, 7).id, 2);
});

test("applying a claim reports which tiles to repaint", () => {
    assert.deepEqual(m.applyClaim({}, aBlock()), [[4, 7], [5, 7], [4, 8], [5, 8]]);
});

test("a tile shows whose hold it is, and greys out once the deadline passes", () => {
    const mine = aBlock();
    const theirs = aBlock({ owner: "bob" });
    const lapsed = aBlock({ expires_at: inMinutes(-1) });

    assert.equal(m.tileState(undefined, "1", NOW), "free");
    assert.equal(m.tileState(mine, "1", NOW), "held-mine");
    assert.equal(m.tileState(theirs, "1", NOW), "held");
    assert.equal(m.tileState(lapsed, "1", NOW), "lapsed");
    assert.equal(m.tileState(aBlock({ status: "confirmed" }), "1", NOW), "confirmed");
    assert.equal(m.tileState(aBlock({ status: "released" }), "1", NOW), "free");
});

test("pressing a free tile starts picking a block", () => {
    assert.deepEqual(m.pressAction({}, 4, 7, "1"), { kind: "select" });
});

test("pressing your own held block doesn't confirm it by accident", () => {
    const action = m.pressAction(boardWith(aBlock()), 4, 7, "1");

    assert.equal(action.kind, "info");
    assert.match(action.message, /Your holds/);
});

test("pressing someone else's block says whose it is", () => {
    const action = m.pressAction(boardWith(aBlock({ owner: "bob" })), 5, 8, "1");

    assert.deepEqual(action, { kind: "info", message: "(5, 8) is held by bob" });
});

test("your holds are your held blocks, once each, soonest deadline first", () => {
    const later = aBlock({ id: 1, expires_at: inMinutes(9) });
    const sooner = aBlock({ id: 2, x0: 20, x1: 25, expires_at: inMinutes(2) });
    const theirs = aBlock({ id: 3, x0: 40, x1: 41, owner: "bob" });
    const kept = aBlock({ id: 4, x0: 60, x1: 61, status: "confirmed" });

    const holds = m.myHolds(boardWith(later, sooner, theirs, kept), "1");

    assert.deepEqual(holds.map((c) => c.id), [2, 1]);
});

test("the countdown reads m:ss, and says when the hold has lapsed", () => {
    assert.equal(m.countdown(aBlock({ expires_at: inMinutes(9.5) }), NOW), "9:30");
    assert.equal(m.countdown(aBlock({ expires_at: inMinutes(-1) }), NOW), null);
});
