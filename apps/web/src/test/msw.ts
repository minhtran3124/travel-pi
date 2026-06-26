import { setupServer } from "msw/node";
import type { RequestHandler } from "msw";

// Base handler set is intentionally empty; individual tests register
// handlers via `server.use(...)` for the endpoints they exercise.
export const handlers: RequestHandler[] = [];

export const server = setupServer(...handlers);
