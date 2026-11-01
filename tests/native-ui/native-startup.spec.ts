import { expect, test, type Page } from "@playwright/test";

// Frontend contract tests use a controlled native bridge. Real process/database
// startup is verified separately against the built macOS application.
async function installBridge(page: Page, phase = "checking") {
  await page.addInitScript(({ initial }) => {
    const host=window as unknown as Record<string,unknown>;
    host.__CHEMISTRY_DESKTOP__=true;
    host.__nativeCalls=[];
    host.__nativeStatus={phase:initial,message:initial === "error" ? "Docker Desktop needs to finish starting." : "Checking your local workspace…",error:initial === "error" ? "The local database could not start." : null,origin:null,ownedBackend:false,logPath:null};
    host.__TAURI__={core:{invoke:async(command:string)=>{
      (host.__nativeCalls as string[]).push(command);
      if(command === "runtime_status")return host.__nativeStatus;
      if(command === "runtime_retry"){host.__nativeStatus={...(host.__nativeStatus as object),phase:"starting",message:"Opening the research service…",error:null};return host.__nativeStatus;}
      if(command === "runtime_open")return;
      throw new Error("Unexpected native command");
    }}};
  },{initial:phase});
  await page.goto("/?desktop=boot");
}

test("startup displays actual bridge phases and opens only when ready",async({page})=>{
  await page.setViewportSize({width:1280,height:860});
  await installBridge(page);
  await expect(page.getByRole("heading",{name:"Making room for discovery"})).toBeVisible();
  await expect(page.locator('.cs-launch-stages [data-state="complete"]')).toHaveCount(0);
  await page.evaluate(()=>{const host=window as unknown as Record<string,unknown>;host.__nativeStatus={...(host.__nativeStatus as object),phase:"starting",message:"Opening the research service…"};});
  await expect(page.locator('.cs-launch-stages [data-state="complete"]')).toHaveCount(3);
  await expect(page.getByRole("status")).toHaveText("Opening the research service…");
  expect(await page.evaluate(()=>(window as unknown as {__nativeCalls:string[]}).__nativeCalls.includes("runtime_open"))).toBe(false);
  await expect(page.locator(".cs-native-launcher__footer")).toBeInViewport();
  const widths=await page.evaluate(()=>({viewport:innerWidth,scroll:document.documentElement.scrollWidth}));expect(widths.scroll).toBe(widths.viewport);
  await test.info().attach("native-startup-1280",{body:await page.screenshot(),contentType:"image/png"});
  await page.evaluate(()=>{const host=window as unknown as Record<string,unknown>;host.__nativeStatus={...(host.__nativeStatus as object),phase:"ready",message:"Your workspace is ready.",origin:"http://127.0.0.1:8788"};});
  await expect.poll(()=>page.evaluate(()=>(window as unknown as {__nativeCalls:string[]}).__nativeCalls.filter(x=>x === "runtime_open").length)).toBe(1);
});

test("unavailable services show an honest recovery action",async({page})=>{
  await installBridge(page,"error");
  await expect(page.getByRole("alert")).toHaveText("Docker Desktop needs to finish starting.");
  await expect(page.locator('.cs-launch-stages [data-state="complete"]')).toHaveCount(0);
  await page.getByRole("button",{name:"Try again"}).click();
  await expect(page.getByRole("status")).toHaveText("Opening the research service…");
  expect(await page.evaluate(()=>(window as unknown as {__nativeCalls:string[]}).__nativeCalls.includes("runtime_retry"))).toBe(true);
  await expect(page.getByRole("button",{name:"Try again"})).not.toBeVisible();
});

test("reduced motion leaves static visible artwork and usable status",async({page})=>{
  await page.emulateMedia({reducedMotion:"reduce"});
  await page.setViewportSize({width:800,height:600});
  await installBridge(page,"starting");
  await expect(page.getByRole("status")).toBeVisible();
  await expect(page.locator(".cs-native-launcher__brand svg")).toBeVisible();
  await expect(page.locator(".cs-native-launcher__footer")).toBeInViewport();
  const animations=await page.locator(".cs-native-launcher svg, .cs-native-launcher svg path, .cs-native-launcher svg circle").evaluateAll(nodes=>nodes.map(node=>getComputedStyle(node).animationName));
  expect(animations.every(name=>name === "none")).toBe(true);
  expect(await page.evaluate(()=>document.documentElement.scrollWidth)).toBe(800);
  await test.info().attach("native-reduced-motion-800",{body:await page.screenshot({fullPage:true}),contentType:"image/png"});
});

test("paused first-frame animations never hide launch recovery, pages or sheets", async ({ page }) => {
  await installBridge(page, "error");
  await expect(page.getByRole("button", { name: "Try again" })).toBeAttached();
  const opacity = await page.evaluate(() => {
    // Model WKWebView suspending animation timelines while a macOS privacy
    // prompt waits. Essential surfaces must be visible before animation ticks.
    const fixture = document.createElement("div");
    fixture.className = "cs-content";
    fixture.innerHTML = '<section class="cs-projects-page">Workspace content</section><dialog class="cs-create-sheet" open><button>Sheet action</button></dialog>';
    document.body.append(fixture);
    document.getAnimations().forEach((animation) => { animation.pause(); animation.currentTime = 0; });
    return [".cs-native-launcher__story", ".cs-native-launcher__status", ".cs-projects-page", ".cs-create-sheet"].map((selector) => ({ selector, opacity: getComputedStyle(document.querySelector(selector)!).opacity }));
  });
  expect(opacity).toEqual([
    { selector: ".cs-native-launcher__story", opacity: "1" },
    { selector: ".cs-native-launcher__status", opacity: "1" },
    { selector: ".cs-projects-page", opacity: "1" },
    { selector: ".cs-create-sheet", opacity: "1" },
  ]);
});
