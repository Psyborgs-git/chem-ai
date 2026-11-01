import { useState } from 'react';
import { Link } from 'react-router';
import { useLazyLoadQuery } from 'react-relay';
import { PageHeader, Panel, TechnicalDetails } from '../../components/layout/StudioLayout';
import { Button } from '../../components/atoms/Button';
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
  const labels: Record<string, string> = { cpu_cores: 'CPU cores', memory_bytes: 'Memory', gpu_devices: 'GPU devices', storage_bytes: 'Storage', concurrency: 'Concurrent runs' };
  const format = (value: number) => name.endsWith('_bytes') ? gib(value) : String(value);
  return (
    <tr key={name}>
      <td className="cs-table__identity">{labels[name] ?? name}</td>
      <td>{cap === null || cap === undefined ? 'unobserved' : format(cap)}</td>
      <td>{format(res ?? 0)}</td>
      <td>{format(used ?? 0)}</td>
      <td>{effective === null ? 'not schedulable' : format(effective)}</td>
    </tr>
  );
}

export function ComputePanel() {
  const [fetchKey, setFetchKey] = useState(0);
  const data = useLazyLoadQuery<operationsComputeResourcesQuery>(
    ComputeResourcesQuery,
    {},
    { fetchKey, fetchPolicy: 'store-and-network' },
  );
  const view = data.computeResources as ComputeResources;
  const hw = view.hardware;

  return (
    <section className="cs-family-page">
      <PageHeader eyebrow="Local resources" title="Compute capability" description="Know what this device can run. Capacity is observed, and configured reserves keep the studio responsive during calculations." actions={<Button onClick={() => setFetchKey((k) => k + 1)}>Refresh report</Button>} />
      <dl className="cs-compute-summary">
        <div><dt>Available memory</dt><dd>{gib(hw.ram_available_bytes)}</dd></div>
        <div><dt>Logical CPU cores</dt><dd>{hw.cpu_count_logical ?? 'Unknown'}</dd></div>
        <div><dt>Free storage</dt><dd>{gib(hw.disk_free_bytes)}</dd></div>
      </dl>
      <div className="cs-callout"><strong>Run a calculation from a research task</strong><p>Select a project and open its task to calculate molecular descriptors. Results remain linked to the research context. <Link to="/projects">Open projects →</Link></p></div>
      <Panel title="Device & hardware" description={<>Observed at {new Date(hw.observed_at).toLocaleString()}. Unobservable fields remain unknown.</>}>
      <div
        className="cs-table-wrap"
        role="region"
        aria-label="hardware"
        tabIndex={0}
      >
        <table className="cs-table cs-table--fit kv">
          <tbody>
            <tr><td className="cs-table__identity">OS / arch</td><td>{hw.os} / {hw.arch}</td></tr>
            <tr><td className="cs-table__identity">Memory model</td><td>{hw.memory_model}</td></tr>
            <tr><td className="cs-table__identity">CPU (logical / physical)</td><td>{hw.cpu_count_logical ?? 'unknown'} / {hw.cpu_count_physical ?? 'unknown'}</td></tr>
            <tr><td className="cs-table__identity">RAM total / available</td><td>{gib(hw.ram_total_bytes)} / {gib(hw.ram_available_bytes)}</td></tr>
            <tr><td className="cs-table__identity">Disk free</td><td>{gib(hw.disk_free_bytes)}</td></tr>
            <tr>
              <td className="cs-table__identity">GPUs</td>
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
      </div>
      <TechnicalDetails value={{ runtimes: hw.runtimes, isolation: hw.isolation, python_version: hw.python_version }} label="Inspect runtime & isolation report" />
      </Panel>

      {view.groups.map((g) => (
        <Panel key={g.name} title={`Resource group: ${g.name}`} description="Available capacity accounts for the configured reserve and current reservations.">
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
        </Panel>
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
