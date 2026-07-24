/**
 * Typed handling of `application/problem+json` (doc 04 §2.3). Views render the
 * `code`/`title` — never a raw stack or blank screen (INV-FE-6, doc 08 §5).
 */
import type { Problem } from "@/api/generated/schema";

export type { Problem };

/** Error thrown by the API client for any non-2xx response. */
export class ProblemError extends Error {
  readonly status: number;
  readonly code: string;
  readonly requestId: string | undefined;
  readonly problem: Problem | undefined;

  constructor(problem: Problem);
  constructor(status: number, code: string, title: string);
  constructor(
    problemOrStatus: Problem | number,
    code?: string,
    title?: string,
  ) {
    if (typeof problemOrStatus === "number") {
      super(title ?? code ?? "Request failed");
      this.status = problemOrStatus;
      this.code = code ?? "request_failed";
      this.requestId = undefined;
      this.problem = undefined;
    } else {
      super(problemOrStatus.title || problemOrStatus.code || "Request failed");
      this.status = problemOrStatus.status;
      this.code = problemOrStatus.code;
      this.requestId = problemOrStatus.request_id;
      this.problem = problemOrStatus;
    }
    this.name = "ProblemError";
  }

  get isAuthFailure(): boolean {
    return this.status === 401 || this.code === "authentication_failed";
  }
}

/** Narrow an unknown JSON body to a {@link Problem}. */
export function isProblem(value: unknown): value is Problem {
  if (typeof value !== "object" || value === null) return false;
  const candidate = value as Record<string, unknown>;
  return (
    typeof candidate.code === "string" &&
    typeof candidate.status === "number" &&
    typeof candidate.title === "string"
  );
}

/** Best-effort conversion of any thrown value into a user-facing message. */
export function toMessage(error: unknown): string {
  if (error instanceof ProblemError) return error.message;
  if (error instanceof Error) return error.message;
  return "An unexpected error occurred.";
}
