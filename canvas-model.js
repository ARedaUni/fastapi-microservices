// The canvas page's rules, kept apart from the DOM so they're testable and
// survive a new UI (canvas-model.test.js). A classic script, not a module:
// canvas.html opens from file://, where browsers refuse to load ES modules.
//
// `tiles` maps "x,y" to the claim covering that tile. A claim is a block,
// half-open like the API: columns x0..x1-1, rows y0..y1-1.
(function (root) {
    function forEachTile(block, fn) {
        for (let y = block.y0; y < block.y1; y++) for (let x = block.x0; x < block.x1; x++) fn(x, y);
    }

    function inBlock(block, x, y) {
        return block.x0 <= x && x < block.x1 && block.y0 <= y && y < block.y1;
    }

    function overlaps(a, b) {
        return a.x0 < b.x1 && b.x0 < a.x1 && a.y0 < b.y1 && b.y0 < a.y1;
    }

    function blockBetween(a, b) {
        return {
            x0: Math.min(a.x, b.x), y0: Math.min(a.y, b.y),
            x1: Math.max(a.x, b.x) + 1, y1: Math.max(a.y, b.y) + 1,
        };
    }

    function reserveRequest(block, colour) {
        const { x0, y0, x1, y1 } = block;
        return { x0, y0, x1, y1, colour };
    }

    function claimAt(tiles, x, y) {
        return tiles[`${x},${y}`];
    }

    function isLive(claim) {
        return Boolean(claim && claim.status !== "released");
    }

    // Mutates `tiles` in place (a 10,000-entry copy per event buys nothing) and
    // returns the tiles to repaint.
    function applyClaim(tiles, claim) {
        const changed = [];
        forEachTile(claim, (x, y) => {
            const current = claimAt(tiles, x, y);
            // A late "released" for an old block mustn't wipe a newer one here.
            if (claim.status === "released" && current && current.id !== claim.id) return;
            tiles[`${x},${y}`] = claim;
            changed.push([x, y]);
        });
        return changed;
    }

    function takenIn(tiles, block) {
        let taken = 0;
        forEachTile(block, (x, y) => { if (isLive(claimAt(tiles, x, y))) taken++; });
        return taken;
    }

    // Browser clock vs Postgres's: fine for display, never for deciding.
    // The server's 409 is the real answer.
    function msLeft(claim, now) {
        return Date.parse(claim.expires_at) - now;
    }

    function tileState(claim, me, now) {
        if (!isLive(claim)) return "free";
        if (claim.status === "confirmed") return "confirmed";
        if (msLeft(claim, now) <= 0) return "lapsed";
        return claim.owner === me ? "held-mine" : "held";
    }

    function pressAction(tiles, x, y, me) {
        const claim = claimAt(tiles, x, y);
        if (!isLive(claim)) return { kind: "select" };
        if (claim.owner !== me) return { kind: "info", message: `(${x}, ${y}) is ${claim.status} by ${claim.owner}` };
        if (claim.status === "confirmed") return { kind: "info", message: `(${x}, ${y}) is already yours` };
        return { kind: "info", message: "Confirm it from Your holds, below the canvas" };
    }

    function liveBlocks(tiles) {
        const byId = new Map(Object.values(tiles).map((c) => [c.id, c]));
        return [...byId.values()].filter(isLive);
    }

    function myHolds(tiles, me) {
        return liveBlocks(tiles)
            .filter((c) => c.status === "held" && c.owner === me)
            .sort((a, b) => Date.parse(a.expires_at) - Date.parse(b.expires_at));
    }

    function countdown(claim, now) {
        const left = msLeft(claim, now);
        if (left <= 0) return null;
        return `${Math.floor(left / 60000)}:${String(Math.floor(left / 1000) % 60).padStart(2, "0")}`;
    }

    const model = {
        forEachTile, inBlock, overlaps, blockBetween, reserveRequest, claimAt, isLive,
        applyClaim, takenIn, tileState, pressAction, liveBlocks, myHolds, countdown,
    };
    if (typeof module !== "undefined") module.exports = model;
    else root.CanvasModel = model;
})(this);
