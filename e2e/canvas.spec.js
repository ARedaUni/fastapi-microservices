const path = require("node:path");
const { test, expect } = require("@playwright/test");

const USERS_API = "http://localhost:8000";
const CANVAS_API = "http://localhost:8001";
const PAGE = "file://" + path.resolve(__dirname, "../canvas.html");

async function logIn(page, request) {
    const res = await request.post(`${USERS_API}/api/v1/login/`, {
        form: { username: "admin@admin.com", password: "password" },
    });
    const { access_token: token } = await res.json();
    const sub = JSON.parse(Buffer.from(token.split(".")[1], "base64url")).sub;
    await page.addInitScript(([t, s]) => {
        localStorage.setItem("jwt_token", t);
        localStorage.setItem("jwt_owner", s);
    }, [token, sub]);
    await page.goto(PAGE);
    await expect(page.getByLabel("(0, 0)", { exact: true })).toBeVisible();
}

// Journeys write real rows, like `make contract`, so each picks a 4x4 spot
// nobody holds right now instead of assuming an empty canvas.
async function aFreeSpot(request) {
    const live = await (await request.get(`${CANVAS_API}/api/v1/claims/`)).json();
    const clashes = (x, y) => live.some((c) => x < c.x1 && c.x0 < x + 4 && y < c.y1 && c.y0 < y + 4);
    // ponytail: confirmed blocks from past runs pile up in the dev database;
    // reset it when this gives up, or give journeys a reset hook if it's often.
    for (let tries = 0; tries < 1000; tries++) {
        const x = Math.floor(Math.random() * 96), y = Math.floor(Math.random() * 96);
        if (!clashes(x, y)) return { x, y };
    }
    throw new Error("No free 4x4 spot left on the canvas; reset the dev database");
}

const tile = (page, x, y) => page.getByLabel(`(${x}, ${y})`, { exact: true });

async function drag(page, from, to) {
    await tile(page, from.x, from.y).hover();
    await page.mouse.down();
    await tile(page, to.x, to.y).hover();
    await page.mouse.up();
}

test("drag out a block and reserve it", async ({ page, request }) => {
    const { x, y } = await aFreeSpot(request);
    await logIn(page, request);

    await drag(page, { x, y }, { x: x + 2, y: y + 2 });
    await expect(page.getByText("3×3 = 9 tiles")).toBeVisible();
    await page.getByRole("button", { name: "Reserve" }).click();

    await expect(page.getByText(`(${x}, ${y}) · 9 tiles`)).toBeVisible();
});

test("confirm a reserved block from your holds", async ({ page, request }) => {
    const { x, y } = await aFreeSpot(request);
    await logIn(page, request);
    await drag(page, { x, y }, { x: x + 2, y: y + 2 });
    await page.getByRole("button", { name: "Reserve" }).click();
    const hold = page.locator(".hold-row", { hasText: `(${x}, ${y}) · 9 tiles` });

    await hold.getByRole("button", { name: "Confirm" }).click();

    await expect(page.getByText(`🔒 (${x}, ${y}) is yours`)).toBeVisible();
    await expect(hold).toHaveCount(0);
});

test("a block reserved in one tab shows as taken in another", async ({ browser, request }) => {
    const { x, y } = await aFreeSpot(request);
    const alice = await (await browser.newContext()).newPage();
    const bob = await (await browser.newContext()).newPage();
    await logIn(alice, request);
    await logIn(bob, request);

    await drag(alice, { x, y }, { x: x + 2, y: y + 2 });
    await alice.getByRole("button", { name: "Reserve" }).click();
    await expect(alice.getByText(`(${x}, ${y}) · 9 tiles`)).toBeVisible();

    // Bob never reloads: the block reaches him over the stream. His drag starts
    // on a free tile; pressing a taken one doesn't start a selection.
    await drag(bob, { x: x + 3, y: y + 3 }, { x: x + 1, y: y + 1 });
    await expect(bob.getByText("4 of these tiles are taken")).toBeVisible();
    await expect(bob.getByRole("button", { name: "Reserve" })).toBeDisabled();
});
