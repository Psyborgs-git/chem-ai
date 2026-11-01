import { Select, SelectContent, SelectGroup, SelectItem, SelectLabel, SelectSeparator, SelectTrigger, SelectValue } from "@/components/ui/select";
import type { AgentProvider } from "./AgentSidebar";

type LocalModel = { id: string; name: string; backend: string; details: Record<string, unknown> };
export function AgentModelSelect({ providers, localModels, providerId, modelId, onChange }: {
  providers: AgentProvider[];
  localModels: LocalModel[];
  providerId: string;
  modelId: string;
  onChange: (providerId: string, modelId: string) => void;
}) {
  const local = localModels.filter((model) => ["mlx", "transformers"].includes(model.backend) && model.details.state === "ready");
  const selectedProvider = providers.find((provider) => provider.id === providerId);
  const selectedLocal = local.find((model) => `local:${model.id}` === providerId);
  const selectedModel = selectedProvider?.models.find((model) => model.modelId === modelId);
  const label = providerId === "$runtime" ? "Local llama.cpp runtime" : selectedLocal ? `Local · ${selectedLocal.name}` : selectedProvider
    ? `${selectedModel?.label ?? "Role default"} · ${selectedProvider.name}` : providerId ? "Model unavailable" : undefined;
  return <Select value={providerId ? JSON.stringify([providerId, modelId]) : ""} onValueChange={(value) => { const [provider, model] = JSON.parse(value); onChange(provider, model); }}>
    <SelectTrigger aria-label="Agent model" className="cs-chat-model-trigger" size="sm"><SelectValue placeholder="Choose a model">{label}</SelectValue></SelectTrigger>
    <SelectContent className="cs-chat-model-menu" position="popper" align="start">
      {providers.map((provider) => <SelectGroup key={provider.id}><SelectLabel>{provider.name}</SelectLabel>{provider.models.filter((model) => model.enabled).map((model) => <SelectItem disabled={!provider.enabled} key={model.id} value={JSON.stringify([provider.id, model.modelId])}>{model.label} · {provider.name}</SelectItem>)}<SelectItem disabled={!provider.enabled} value={JSON.stringify([provider.id, ""])}>{provider.name} · role default</SelectItem></SelectGroup>)}
      {providers.length > 0 && <SelectSeparator />}
      <SelectGroup><SelectLabel>On this Mac</SelectLabel>{local.map((model) => <SelectItem key={model.id} value={JSON.stringify([`local:${model.id}`, ""])}>Local · {model.name}</SelectItem>)}<SelectItem value={JSON.stringify(["$runtime", ""])}>Local llama.cpp runtime</SelectItem></SelectGroup>
    </SelectContent>
  </Select>;
}
