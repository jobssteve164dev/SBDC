import { createServer } from "node:http";

const port = Number(process.env.SBDC_TEST_BACKEND_PORT ?? 3108);
createServer((request, response) => {
  if (request.method === "GET" && request.url === "/health") {
    response.writeHead(200, { "content-type": "application/json" });
    response.end(JSON.stringify({ status: "ok" }));
    return;
  }
  response.writeHead(404, { "content-type": "application/json" });
  response.end(JSON.stringify({ detail: "not found" }));
}).listen(port, "127.0.0.1", () => {
  process.stdout.write(`backend stub ready on ${port}\n`);
});
