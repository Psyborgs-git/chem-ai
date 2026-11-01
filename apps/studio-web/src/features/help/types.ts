export type HelpSection = "usage" | "development" | "operations" | "reference";
export type HelpHeading = { id: string; text: string; depth: number; offset: number };
export type HelpArticle = {
  id: string;
  section: HelpSection;
  slug: string;
  title: string;
  summary: string;
  source: string;
  order: number;
  markdown: string;
  searchText: string;
  headings: HelpHeading[];
  linkMap: Record<string, string>;
};

export const HELP_SECTIONS: { id: HelpSection; title: string; description: string }[] = [
  { id: "usage", title: "Using the studio", description: "Research, edit records, and review your evidence." },
  { id: "development", title: "Development", description: "Understand, change, and extend the application." },
  { id: "operations", title: "Operations", description: "Install, configure, back up, and recover your workspace." },
  { id: "reference", title: "Reference", description: "Look up APIs, GraphQL operations, types, and settings." },
];
