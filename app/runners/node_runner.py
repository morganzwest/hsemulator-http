"""
Node.js Runner for Novocode Runtime

This module provides Node.js execution capabilities for workflow actions.
It contains the embedded JavaScript code that runs as a sandboxed process
to execute user-provided Node.js workflow actions.

Execution Environment:
- Sandboxed Node.js process with isolated execution
- Environment-based configuration for file paths
- Structured error handling and result reporting
- Process exit codes for success/failure indication

Environment Variables:
- HSEMULATE_ENTRY: Path to the user's Node.js entry file
- HSEMULATE_EVENT_PATH: Path to the event data JSON file
- HSEMULATE_RESULT_PATH: Path to write execution results
- HSEMULATE_ERROR_PATH: Path to write error information

Error Handling:
- Structured error reporting with error types
- Stack trace capture for debugging
- Process exit codes for status indication
- JSON-based result and error communication

Security Considerations:
- Sandboxed execution environment
- Controlled file system access via environment variables
- No direct access to host system resources
"""

_NODE_RUNNER_SOURCE = r"""
import fs from "fs";
import path from "path";

// Configuration from environment variables
const ENTRY = process.env.HSEMULATE_ENTRY;
const EVENT_PATH = process.env.HSEMULATE_EVENT_PATH;
const RESULT_PATH = process.env.HSEMULATE_RESULT_PATH;
const ERROR_PATH = process.env.HSEMULATE_ERROR_PATH;

// Error writing utility function
function writeError(type, message, meta = {}) {
    fs.writeFileSync(ERROR_PATH, JSON.stringify({ error_type: type, message, meta }));
}

// Main execution wrapper with error handling
(async () => {
    try {
        // Read and parse event data
        const event = JSON.parse(fs.readFileSync(EVENT_PATH, "utf8"));
        
        // Dynamically import the user's entry module
        const mod = await import(path.resolve(ENTRY));
        
        // Validate that the module exports a main function
        if (typeof mod.main !== "function") {
            writeError("MissingMain", "export async function main(event)");
            process.exit(1);
        }
        
        // Execute the user's main function with event data
        const result = await mod.main(event);
        
        // Validate and write the result
        JSON.stringify(result); // Validate JSON serializability
        fs.writeFileSync(RESULT_PATH, JSON.stringify(result));
        process.exit(0);
        
    } catch (e) {
        // Capture and report execution errors
        writeError("ExecutionError", e.stack);
        process.exit(1);
    }
})();
"""
