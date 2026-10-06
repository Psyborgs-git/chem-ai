import { useLazyLoadQuery } from 'react-relay';
import { ComputeResourcesQuery } from './operations';
import type { operationsComputeResourcesQuery } from '../../__generated__/operationsComputeResourcesQuery.graphql';

interface GpuInfo {
  backend: string;
  device?: string | null;
  memory_total_bytes?: number | null;
  memory_free_bytes?: number | null;
  unified: boolean;
}

interface HardwareReport {
  os: string;
  arch: string;
  python_version: string;
  observed_at: string;
  memory_model: string;
  cpu_count_logical?: number | null;
  cpu_count_physical?: number | null;
  ram_total_bytes?: number | null;
  ram_available_bytes?: number | null;
  disk_free_bytes?: number | null;
  gpus: GpuInfo[];
  runtimes: Record<string, string | null>;
  isolation: Record<string, unknown>;
}

interface ResourceGroupView {
  name: string;
  capacity: Record<string, number | null>;
  reserve: Record<string, number>;
  reserved: Record<string, number>;
}

interface ComputeResources {
  hardware: HardwareReport;
  groups: ResourceGroupView[];
}

function gib(v?: number | null): string {
  if (v === null || v === undefined) return 'unknown';
  return `${(v / 1024 ** 3).toFixed(1)} GiB`;
}

function dimRow(name: string, cap: number | null | undefined, res: number | undefined, used: number | undefined) {
  const effective =
    cap === null || cap === undefined ? null : cap - (res ?? 0) - (used ?? 0);
  return (
    <tr key={name}>
      <td className="cs-table__identity">{name}</td>
      <td>{cap === null || cap === undefined ? 'unobserved' : String(cap)}</td>
      <td>{res ?? 0}</td>
      <td>{used ?? 0}</td>
      <td>{effective === null ? 'not schedulable' : String(effective)}</td>
    </tr>
  );
}

export function ComputePanel() {
  const data = useLazyLoadQuery<operationsComputeResourcesQuery>(
    ComputeResourcesQuery,
    {},
  );
  const view = data.computeResources as ComputeResources;
  const hw = view.hardware;

  return (
    <section className="panel">
      <header>
        <h2>Compute capability</h2>
        <p className="muted">
          Observed at {hw.observed_at}. Fields that cannot be observed are
          reported unknown — nothing is estimated or fabricated. Admission
          reserves the configured headroom so the UI and API stay responsive
          while heavy work runs.
        </p>
      </header>

      <h3>Hardware</h3>
      <table className="cs-table kv">
        <tbody>
          <tr><td>OS / arch</td><td>{hw.os} / {hw.arch}</td></tr>
          <tr><td>Memory model</td><td>{hw.memory_model}</td></tr>
          <tr><td>CPU (logical / physical)</td><td>{hw.cpu_count_logical ?? 'unknown'} / {hw.cpu_count_physical ?? 'unknown'}</td></tr>
          <tr><td>RAM total / available</td><td>{gib(hw.ram_total_bytes)} / {gib(hw.ram_available_bytes)}</td></tr>
          <tr><td>Disk free</td><td>{gib(hw.disk_free_bytes)}</td></tr>
          <tr>
            <td>GPUs</td>
            <td>
              {hw.gpus.length === 0
                ? 'none detected'
                : hw.gpus
                    .map(
                      (g) =>
                        `${g.backend}${g.device ? ` (${g.device})` : ''}${
                          g.unified ? ' — unified memory' : ''
                        }`,
                    )
                    .join('; ')}
            </td>
          </tr>
        </tbody>
      </table>

      {view.groups.map((g) => (
        <section key={g.name}>
          <h3>Resource group: {g.name}</h3>
          <div
            className="cs-table-wrap"
            role="region"
            aria-label={`resource group ${g.name}`}
            tabIndex={0}
          >
            <table className="cs-table data">
              <thead>
                <tr>
                  <th scope="col" className="cs-table__identity">
                    dimension
                  </th>
                  <th scope="col">capacity</th>
                  <th scope="col">reserve</th>
                  <th scope="col">reserved</th>
                  <th scope="col">available</th>
                </tr>
              </thead>
              <tbody>
                {(['cpu_cores', 'memory_bytes', 'gpu_devices', 'storage_bytes', 'concurrency'] as const).map(
                  (d) => dimRow(d, g.capacity[d], g.reserve[d], g.reserved[d]),
                )}
              </tbody>
            </table>
          </div>
        </section>
      ))}
      {view.groups.length === 0 && (
        <p className="muted">
          No resource groups are configured — every heavy run will be
          reported blocked rather than scheduled.
        </p>
      )}
    </section>
  );
}
