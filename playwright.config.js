// The outer test loop: canvas.html in a real browser against the running
// stack (`make up`). Few journeys, in the user's terms; the rules themselves
// are tested in canvas-model.test.js.
const { defineConfig } = require("@playwright/test");

module.exports = defineConfig({
    testDir: "e2e",
    timeout: 20_000,
    retries: 0,
    use: { headless: true },
});
