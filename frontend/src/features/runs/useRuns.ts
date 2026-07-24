/**
 * Run + dead-letter queries and DLQ governance mutations (doc 03 §4.4, doc 07
 * §4, doc 08 §4).
 *
 *  - Reads (runs, dead letters) are org-scoped queries so an org switch
 *    invalidates cleanly (INV-FE-5).
 *  - DLQ writes follow the governed state machine (INV-DLQ-2/3): `propose`
 *    advances open → investigating with an advisory diagnosis; `resolve`
 *    closes investigating → resolved under mandatory explicit approval. Each
 *    mutation invalidates the dead-letter query so the UI reflects server
 *    truth, never an optimistic guess.
 *
 * All transport flows through the single typed client (doc 08 §1).
 */
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { dlqApi, orgScopedKey, runsApi } from "@/api";
import type {
  DeadLettersResponse,
  RunsResponse,
} from "@/api/generated/schema";
import { useSession } from "@/app/session/useSession";

const RUNS_RESOURCE = "runs";
const DLQ_RESOURCE = "dead-letters";

export function useRuns() {
  const { session } = useSession();
  const organizationId = session?.organizationId;

  return useQuery<RunsResponse>({
    queryKey: orgScopedKey(organizationId ?? "none", RUNS_RESOURCE),
    queryFn: ({ signal }) => runsApi.list(signal),
    enabled: Boolean(organizationId),
  });
}

export function useDeadLetters() {
  const { session } = useSession();
  const organizationId = session?.organizationId;

  return useQuery<DeadLettersResponse>({
    queryKey: orgScopedKey(organizationId ?? "none", DLQ_RESOURCE),
    queryFn: ({ signal }) => dlqApi.list(signal),
    enabled: Boolean(organizationId),
  });
}

/**
 * The governed DLQ transitions (INV-DLQ-2/3). `resolve` demands explicit
 * approval at the call site; the server re-checks the same gate — the client
 * never trusts itself (doc 08 §3).
 */
export function useDlqGovernance() {
  const queryClient = useQueryClient();
  const { session } = useSession();
  const organizationId = session?.organizationId ?? "none";

  function invalidateDeadLetters(): Promise<void> {
    return queryClient.invalidateQueries({
      queryKey: orgScopedKey(organizationId, DLQ_RESOURCE),
    });
  }

  const propose = useMutation({
    mutationFn: ({
      deadLetterId,
      note,
    }: {
      deadLetterId: string;
      note: string;
    }) =>
      dlqApi.propose(deadLetterId, {
        diagnosis: { note, source: "operator" },
      }),
    onSuccess: invalidateDeadLetters,
  });

  const resolve = useMutation({
    mutationFn: (deadLetterId: string) =>
      dlqApi.resolve(deadLetterId, { explicit_approval: true }),
    onSuccess: invalidateDeadLetters,
  });

  return { propose, resolve };
}
