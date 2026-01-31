_NODE_RUNNER_SOURCE = r"""
import fs from "fs";
import path from "path";

const ENTRY = process.env.HSEMULATE_ENTRY;
const EVENT_PATH = process.env.HSEMULATE_EVENT_PATH;
const RESULT_PATH = process.env.HSEMULATE_RESULT_PATH;
const ERROR_PATH = process.env.HSEMULATE_ERROR_PATH;

function writeError(type, message, meta = {}) {
    fs.writeFileSync(ERROR_PATH, JSON.stringify({ error_type: type, message, meta }));
}

(async () => {
    try {
        const event = JSON.parse(fs.readFileSync(EVENT_PATH, "utf8"));
        const mod = await import(path.resolve(ENTRY));
        if (typeof mod.main !== "function") {
            writeError("MissingMain", "export async function main(event)");
            process.exit(1);
        }
        const result = await mod.main(event);
        JSON.stringify(result);
        fs.writeFileSync(RESULT_PATH, JSON.stringify(result));
        process.exit(0);
    } catch (e) {
        writeError("ExecutionError", e.stack);
        process.exit(1);
    }
})();
"""
