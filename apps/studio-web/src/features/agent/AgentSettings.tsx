import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Switch } from "@/components/ui/switch";
import { Slider } from "@/components/ui/slider";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Textarea } from "@/components/ui/textarea";
import type { AgentPolicy, AgentProvider } from "./AgentSidebar";

export function AgentSettings({ open, onOpenChange, restoreFocus, busy, role, onRoleChange, width, onWidthChange, policy, onPolicyChange, provider, disclosureChecked, onDisclosureChange, onSave, threadId, recurring, onRecurringChange, researchGoal, onResearchGoalChange, scheduleHours, onScheduleHoursChange, nextWakeAt, onSaveSchedule, background, onBackgroundChange }: {
  open: boolean; onOpenChange: (open: boolean) => void; restoreFocus: () => void; busy: boolean;
  role: string; onRoleChange: (role: string) => void; width: number; onWidthChange: (width: number) => void;
  policy: AgentPolicy; onPolicyChange: (policy: AgentPolicy) => void;
  provider?: AgentProvider; disclosureChecked: boolean; onDisclosureChange: (allow: boolean) => void; onSave: () => void;
  threadId: string; recurring: boolean; onRecurringChange: (enabled: boolean) => void;
  researchGoal: string; onResearchGoalChange: (goal: string) => void; scheduleHours: number; onScheduleHoursChange: (hours: number) => void; nextWakeAt?: string; onSaveSchedule: () => void;
  background?: { supported: boolean; installed: boolean; running: boolean } | null; onBackgroundChange: () => void;
}) {
  const [tab, setTab] = useState("general");
  return <Dialog open={open} onOpenChange={onOpenChange}><DialogContent className="cs-chat-settings-dialog" onCloseAutoFocus={(event) => { event.preventDefault(); restoreFocus(); }}>
    <DialogHeader><DialogTitle>Chat settings</DialogTitle><DialogDescription>Model access and research limits.</DialogDescription></DialogHeader>
    <Tabs value={tab} onValueChange={setTab}><TabsList className="cs-chat-settings-tabs"><TabsTrigger value="general">General</TabsTrigger><TabsTrigger value="autopilot">Autopilot</TabsTrigger><TabsTrigger value="schedule">Schedule</TabsTrigger></TabsList>
      <TabsContent value="general" className="cs-chat-settings-fields">
        <div className="cs-chat-settings-row"><label htmlFor="agent-role">Role</label><Select value={role} onValueChange={onRoleChange}><SelectTrigger id="agent-role" aria-label="Agent role"><SelectValue /></SelectTrigger><SelectContent>{["planner", "researcher", "extractor", "reviewer"].map((item) => <SelectItem key={item} value={item}>{item[0].toUpperCase() + item.slice(1)}</SelectItem>)}</SelectContent></Select></div>
        <div className="cs-chat-settings-field"><label id="agent-panel-width-label">Panel width <span className="cs-chat-settings-hint">{width} px</span></label><Slider aria-labelledby="agent-panel-width-label" min={340} max={640} step={10} value={[width]} onValueChange={([value]) => onWidthChange(value)} /></div>
        {provider && !provider.local && <div className="cs-chat-settings-access"><div className="cs-chat-switch-row"><label htmlFor="agent-private-access">Private research access<small>Allow {provider.name} to receive relevant notes, memory, and tool results.</small></label><Switch id="agent-private-access" checked={disclosureChecked} onCheckedChange={onDisclosureChange} /></div><small className="cs-chat-settings-endpoint">{provider.baseUrl}</small></div>}
        {background?.supported && <div className="cs-chat-settings-service"><div><strong>Background service</strong><p>{background.installed ? "Research can continue after the app closes while this Mac is awake." : "Keep research running after the app closes."}</p></div><Button variant="outline" size="sm" disabled={busy} onClick={onBackgroundChange}>{background.installed ? "Remove service" : "Enable service"}</Button></div>}
      </TabsContent>
      <TabsContent value="autopilot" className="cs-chat-settings-fields"><div className="cs-chat-switch-row"><label htmlFor="agent-autopilot">Enable autopilot<small>Continue research within your daily limits.</small></label><Switch id="agent-autopilot" checked={policy.autopilot.enabled} onCheckedChange={(enabled) => onPolicyChange({ ...policy, autopilot: { ...policy.autopilot, enabled } })} /></div>
        {([['maxHours', 'Compute hours/day', 24], ['maxDocumentsPerDay', 'Documents/day', 10000], ['maxPaidCostUsd', 'API budget USD/day', 10000]] as const).map(([key, label, max]) => <div className="cs-chat-settings-row" key={key}><label htmlFor={`agent-${key}`}>{label}</label><Input id={`agent-${key}`} type="number" min={key === "maxPaidCostUsd" ? 0 : 1} max={max} value={policy.autopilot[key]} onChange={(event) => onPolicyChange({ ...policy, autopilot: { ...policy.autopilot, [key]: Number(event.target.value) } })} /></div>)}<p className="cs-chat-settings-hint">One training job at a time.</p>
      </TabsContent>
      <TabsContent value="schedule" className="cs-chat-settings-fields"><div className="cs-chat-switch-row"><label htmlFor="agent-recurring">Schedule this chat<small>{threadId ? "Return to a saved research goal." : "Start a chat before scheduling research."}</small></label><Switch id="agent-recurring" checked={recurring} disabled={!threadId} onCheckedChange={onRecurringChange} /></div><div className="cs-chat-settings-field"><label htmlFor="agent-research-goal">Research goal</label><Textarea id="agent-research-goal" rows={3} value={researchGoal} onChange={(event) => onResearchGoalChange(event.target.value)} /></div><div className="cs-chat-settings-row"><label htmlFor="agent-schedule-hours">Repeat every (hours)</label><Input id="agent-schedule-hours" type="number" min={1} max={8760} value={scheduleHours} onChange={(event) => onScheduleHoursChange(Number(event.target.value))} /></div>{nextWakeAt && <p className="cs-chat-settings-hint">Next: {new Date(nextWakeAt).toLocaleString()}</p>}</TabsContent>
    </Tabs>
    <DialogFooter>{tab === "schedule" ? <Button disabled={busy || !threadId || (recurring && !researchGoal.trim())} onClick={onSaveSchedule}>Save research schedule</Button> : <Button disabled={busy} onClick={onSave}>Save settings</Button>}</DialogFooter>
  </DialogContent></Dialog>;
}
