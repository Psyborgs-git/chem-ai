import { Environment, RecordSource, Store } from "relay-runtime";

import { createNetwork } from "./network";

/**
 * ONE Relay environment + ONE canonical server-state cache (§8.2).
 * A second environment per screen, or a mirrored entity store, would
 * fork the truth — forbidden by contract and checked in CI.
 */
let environment: Environment | null = null;

export function getRelayEnvironment(): Environment {
  if (!environment) {
    environment = new Environment({
      network: createNetwork(),
      store: new Store(new RecordSource()),
    });
  }
  return environment;
}

/** Scoped cache is dropped on logout or workspace change (§8.2). */
export function resetRelayEnvironment(): void {
  environment = null;
}
