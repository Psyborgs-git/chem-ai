export type ChatSummary = { id: string; title: string; createdAt?: string; updatedAt?: string; messageCount?: number; lastMessagePreview?: string; lastRunStatus?: string };
export function chatTitle(value: string | undefined) { return value?.replace(/\s+/g, " ").trim() || "New chat"; }
export function historyGroups(chats: ChatSummary[], query = "", now = new Date(), serverSearch = false) {
  const start = new Date(now.getFullYear(), now.getMonth(), now.getDate()).getTime();
  const yesterday = new Date(start); yesterday.setDate(yesterday.getDate() - 1);
  const week = new Date(start); week.setDate(week.getDate() - 7);
  const filtered = chats.filter((chat) => serverSearch || !query.trim() || `${chat.title} ${chat.lastMessagePreview ?? ""}`.toLowerCase().includes(query.trim().toLowerCase()));
  const sorted = filtered.map((chat, index) => ({ chat, index, time: Date.parse(chat.updatedAt ?? chat.createdAt ?? "") || 0 })).sort((a, b) => b.time - a.time || a.index - b.index);
  const groups = new Map<string, ChatSummary[]>();
  for (const item of sorted) {
    const label = item.time >= start ? "Today" : item.time >= yesterday.getTime() ? "Yesterday" : item.time >= week.getTime() ? "Previous 7 days" : "Older";
    groups.set(label, [...(groups.get(label) ?? []), item.chat]);
  }
  return [...groups].map(([label, threads]) => ({ label, threads }));
}
export function chatDate(chat: ChatSummary) {
  const value = chat.updatedAt ?? chat.createdAt;
  if (!value || Number.isNaN(Date.parse(value))) return "Saved chat";
  return new Date(value).toLocaleDateString(undefined, { month: "short", day: "numeric" });
}
