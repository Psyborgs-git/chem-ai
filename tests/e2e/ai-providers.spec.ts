import { selectVisibleOption } from "./ux-helpers";
import { createServer, type Server } from "node:http";
import { randomUUID } from "node:crypto";
import { expect, test } from "@playwright/test";
import { decodeGlobalId, gql, signIn } from "./at-1103-helpers";

test("configure a provider and run precise, consented research tools", async ({ page, context }) => {
  test.setTimeout(120_000);
  const fakeKey = `fixture-key-${randomUUID()}`;
  const title = `Synthetic provider ${randomUUID()}`;
  const model = "synthetic-model-v2";
  const observed: { body: Record<string, any>; authenticated: boolean }[] = [];
  let fixtureError: string | null = null;
  let modelsAuthenticated = false;
  let taskUuid = "";
  const server: Server = createServer((request, response) => {
    const reply = (body: object, status = 200) => { response.writeHead(status, { "content-type": "application/json" }); response.end(JSON.stringify(body)); };
    if (request.url === "/v1/models" && request.method === "GET") { modelsAuthenticated = request.headers.authorization === `Bearer ${fakeKey}`; return reply({data:[{id:model}]}); }
    if (request.url !== "/v1/chat/completions" || request.method !== "POST") return reply({error:"unexpected endpoint"},404);
    const chunks: Buffer[] = [];
    request.on("data", (chunk: Buffer) => chunks.push(chunk));
    request.on("end", () => {
      try {
        const body = JSON.parse(Buffer.concat(chunks).toString("utf8"));
        observed.push({body,authenticated:request.headers.authorization === `Bearer ${fakeKey}`});
        const last = body.messages.at(-1);
        const usage={prompt_tokens:35,completion_tokens:12,total_tokens:47};
        if (last.role === "user") {
          const isFollowup = last.content.includes("invalid identifier");
          const call = isFollowup ? {name:"read_candidate_revision",arguments:JSON.stringify({candidate_revision_id:"invalid-uuid"})} : {name:"summarize_task_evidence",arguments:JSON.stringify({task_id:taskUuid})};
          return reply({choices:[{message:{role:"assistant",content:null,tool_calls:[{id:isFollowup ? "call_bad" : "call_summary",type:"function",function:call}]}}],usage});
        }
        if (last.role !== "tool") throw new Error("Expected a tool result");
        const result = JSON.parse(last.content);
        if (last.tool_call_id === "call_summary" && result.ok === true && result.data.candidate_revisions === 0)
          return reply({choices:[{message:{role:"assistant",content:"Synthetic fixture: zero candidate revisions are recorded."}}],usage});
        if (last.tool_call_id === "call_bad" && result.ok === false && result.error.code === "INVALID_INPUT")
          return reply({choices:[{message:{role:"assistant",content:"Synthetic fixture: the invalid identifier was rejected."}}],usage});
        throw new Error("Unexpected tool identity or domain result");
      } catch (error) { fixtureError = String(error); return reply({error:"fixture rejected request"},500); }
    });
  });
  await new Promise<void>((resolve) => server.listen(0,"127.0.0.1",resolve));
  const address = server.address(); if (!address || typeof address === "string") throw new Error("No mock provider port");
  const baseUrl = `http://127.0.0.1:${address.port}/v1`;
  const token = await signIn(context);
  let providerId: string | undefined;
  try {
    await page.goto("/settings/providers");
    await page.getByRole("button",{name:"Add provider",exact:true}).click();
    const sheet = page.getByRole("dialog",{name:"Add provider"});
    await sheet.getByLabel("Provider name").fill(title);
    await selectVisibleOption(page, sheet.getByLabel("Provider type"), { label: "OpenAI-compatible endpoint" });
    await sheet.getByLabel("API endpoint").fill(baseUrl);
    await sheet.getByLabel("Model ID").fill("synthetic-model");
    await sheet.getByLabel("New API key").fill(fakeKey);
    await sheet.getByLabel("Make available in research").check();
    await sheet.getByRole("button",{name:"Save provider"}).click();
    const card = page.getByRole("article",{name:title,exact:true});
    await expect(card).toBeVisible();
    await expect(card).toContainText("Key stored securely");
    let providers = await gql(token,`query { inferenceProviders { id name revision hasApiKey } }`);
    expect(JSON.stringify(providers)).not.toContain(fakeKey);
    providerId = providers.data.inferenceProviders.find((entry:{name:string}) => entry.name === title)?.id;
    expect(providerId).toBeTruthy();
    await card.getByRole("button",{name:"Edit"}).click();
    const edit = page.getByRole("dialog",{name:"Edit provider"});
    await expect(edit.getByLabel("Replacement API key")).toHaveValue("");
    await edit.getByLabel("Model ID").fill(model);
    await edit.getByRole("button",{name:"Save provider"}).click();
    await expect(card).toContainText(model);
    await card.getByRole("button",{name:"Test connection"}).click();
    await expect(page.getByText(/saved endpoint answered the models check/i)).toBeVisible();
    expect(modelsAuthenticated).toBe(true);

    const createdProject = await gql(token,`mutation { projectCreate(input:{slug:"ai-test-${randomUUID()}",name:"Synthetic provider test"}){project{id} errors{message}} }`);
    const project = createdProject.data.projectCreate.project.id;
    const createdTask = await gql(token,`mutation($project:ID!){taskCreate(input:{projectId:$project,title:"Synthetic provider workflow",mode:"discover",targetKind:"molecule",objective:"Test a local fixture"}){task{id} errors{message}}}`,{project});
    const taskId = createdTask.data.taskCreate.task.id; taskUuid=decodeGlobalId(taskId);
    await gql(token,`mutation($id:ID!){taskTransition(input:{taskId:$id,toState:"active"}){task{id} errors{message}}}`,{id:taskId});
    const createdSession = await gql(token,`mutation($id:ID!){research{sessionStart(input:{taskId:$id}){session{id} errors{message}}}}`,{id:taskId});
    expect(createdSession.data.research.sessionStart.session.id).toBeTruthy();
    await page.goto(`/tasks/${encodeURIComponent(taskId)}/research`);
    const stream = page.locator("details").filter({has:page.locator("summary",{hasText:"stream"})}).first();
    await expect(stream).toBeVisible();
    if (!(await stream.evaluate((node:HTMLDetailsElement)=>node.open))) await stream.locator("summary").click();
    const composer = page.getByRole("form",{name:"research composer"});
    await selectVisibleOption(page, composer.getByLabel("Research model"), providerId!);
    await composer.getByLabel("ask the research agent").fill("Summarize the current task evidence.");
    await expect(composer.getByRole("button",{name:"send"})).toBeDisabled();
    expect(observed).toHaveLength(0);
    await composer.getByLabel("Allow this provider to receive data for this turn").check();
    await composer.getByRole("button",{name:"send"}).click();
    await expect(page.getByText("Synthetic fixture: zero candidate revisions are recorded.")).toBeVisible({timeout:20_000});
    await expect(page.locator('[data-kind="tool_result"][data-ok="true"]')).toContainText("summarize_task_evidence");
    expect(observed[0].authenticated).toBe(true);
    expect(observed[0].body.model).toBe(model);
    expect(observed[0].body.messages[0].content).toContain(taskUuid);
    expect(observed[1].body.messages.at(-1).tool_call_id).toBe("call_summary");
    expect(JSON.stringify(observed.map(({body})=>body))).not.toContain(fakeKey);
    await expect(composer.getByLabel("Allow this provider to receive data for this turn")).not.toBeChecked();
    await composer.getByLabel("ask the research agent").fill("Try the invalid identifier.");
    await composer.getByLabel("Allow this provider to receive data for this turn").check();
    await composer.getByRole("button",{name:"send"}).click();
    await expect(page.getByText("Synthetic fixture: the invalid identifier was rejected.")).toBeVisible({timeout:20_000});
    await expect(page.locator('[data-kind="tool_result"][data-ok="false"]')).toContainText("INVALID_INPUT");
    expect(observed[2].body.messages.some((message:{content?:string})=>message.content === "Summarize the current task evidence.")).toBe(true);
    expect(observed[3].body.messages.at(-1).tool_call_id).toBe("call_bad");
    expect(fixtureError).toBeNull();
    expect(observed).toHaveLength(4);
  } finally {
    try {
      const data = await gql(token,`query { inferenceProviders { id name revision } }`);
      const provider = data.data.inferenceProviders.find((entry:{id:string;name:string}) => entry.id === providerId || entry.name === title);
      if (provider) {
        const removed = await gql(token,`mutation($id:ID!,$revision:Int!){providers{delete(input:{id:$id,expectedRevision:$revision}){deleted credentialCleanupPending errors{code}}}}`,{id:provider.id,revision:provider.revision});
        expect(removed.data.providers.delete.errors).toEqual([]);
        expect(removed.data.providers.delete.deleted).toBe(true);
        expect(removed.data.providers.delete.credentialCleanupPending).toBe(false);
      }
    } finally {
      await new Promise<void>((resolve,reject)=>server.close(error=>error?reject(error):resolve()));
    }
  }
});
