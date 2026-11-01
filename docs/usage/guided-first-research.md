# A guided first research exercise

This walkthrough ends with a saved molecular calculation and a private source-linked explanation of what it means. You will create a practice project, use the built-in ethanol example and keep calculations separate from physical observations. No chemical handling, AI provider or model training is needed.

Allow time to read the result, not just run it. If molecule, formulation, SMILES or mass fraction are unfamiliar, open [Chemistry basics](chemistry-basics.md) alongside this exercise.

## 1. Open a practice workspace

Sign in using your installation's account. A fresh installation first asks you to create its owner account; follow [Getting started](getting-started.md).

Open **Projects → New project**. Enter `Learning practice` as **project name**, then **Create project**. Open it and choose **New research task**.

Enter `What does an ethanol structure calculation tell me?` as **task title**. Choose **Explore**, select **A molecule**, then **Create task**. The task starts as a draft. The question is deliberately about a software calculation; it does not claim anything about a real sample.

## 2. Read the task sections

Find **Overview**, **Research**, **Candidates**, **Experiments**, **Sources**, **Review** and **Tools**. You do not need to complete every section for this exercise.

**Overview → Define success criteria** opens the criteria editor. For a real research task, criteria identify the target, method, unit, conditions and required evidence before a conclusion is made. A draft is the place to preserve missing information.

This tutorial's learning checklist is simple: save a calculation, reopen it, cite a source and explain its limits. Keep that checklist in your notebook. Leave the scientific task draft without freezing a made-up experimental contract or inventing measurements to make a closure pass. Use **Back to overview** if you opened the editor only to inspect it.

## 3. Calculate the supplied structure

Open **Experiments → Calculations**. Under **Describe a molecule**, select **Use ethanol example**. The **SMILES structure** field should contain `CCO`. Select **Calculate properties**.

If the app reports an unavailable RDKit engine, read the reason and ask the installation administrator to set it up using the calculation runbook. You can continue reading the remaining steps. An unavailable result is not a successful calculation.

When the calculation finishes, inspect **Latest calculation** and select **Open saved result**. Read the saved input, status, engine/method and output. Reopen or reload that result to see that it is a persisted record.

Alternatively, Home's **Explore molecule → Try ethanol → Calculate properties** runs the same kind of descriptor exercise. Expand **Save to a project** to choose the practice project; otherwise Home organizes it under **Quick calculations**. Keep track of which saved run you are discussing.

## 4. Interpret the output in plain language

The result should describe the supplied ethanol structure, including formula `C2H6O` and a molecular-weight value around `46.07`. The exact displayed rounding and descriptor metadata belong to the saved engine result. NIST independently lists the ethanol formula and a value near `46.07`. [NIST: Ethanol](https://webbook.nist.gov/cgi/cbook.cgi?ID=C64175).

Explain it this way: “The software read the ethanol structure I entered and calculated its listed descriptors.” The input is the structure representation. The observation is a successful or failed software run. No physical sample was tested, and no purity, safety or product-performance result was measured.

SMILES is a notation for molecular connectivity; `CCO` is one ethanol representation. It does not encode the history of a sample. [Daylight: SMILES specification](https://daylight.com/dayhtml/doc/theory/theory.smiles.html).

## 5. Write a private research note

Open **Notebooks → New notebook**, name it `Chemistry learning practice`, and create it. Choose **Note** as the new page kind and select **Add page**. Change **Page title** to `Ethanol structure calculation: what I learned`.

In **Notes**, record your actual experience using this template:

```text
Purpose: App-only learning exercise. No physical experiment performed.
Question: What can I learn from the supplied ethanol structure?
Input: CCO, using the app's ethanol example.
Run: Copy the saved result identifier or address from my own session.
Software outcome: Record the actual status and displayed descriptors.
Method: Copy the actual engine/version/method from the saved record.
Source comparison: Record the source I actually read and any difference.
Still unknown: Identity or purity of any real sample; practical performance.
Next question: Write one question I have not answered yet.
```

Replace the prompts with your own saved facts; preserve a failure if that is what happened. Wait for **Saved**. **Preview** shows the rendered note. If a conflict occurs, keep the draft and use **Save a separate copy** when offered. [Notebooks and editing](notebooks-and-editing.md) explains recovery and history.

Under **Notebook settings**, inspect **Allow my agent to use this notebook** and **Allow local training from this notebook**. Neither is needed for this manual exercise. Choose the access you intend, remembering that external-provider disclosure is a separate setting.

## 6. Attach the source you read

Open **Research library**, expand **Save a URL**, and save `https://webbook.nist.gov/cgi/cbook.cgi?ID=C64175`. Select the retained source and inspect its original and available text/metadata.

If retention fails, record the failure and the website you actually read in your note. Do not claim a retained original or extracted passage exists when it does not. Network/source availability can change.

When a source is retained, return to the notebook. Under **Sources and citations**, select it as **Saved source**, enter a locator such as `Ethanol entry: Formula and Molecular weight`, and choose **Attach citation**. Wait for Saved, then use **Review source** to confirm the citation points to the intended record.

The source describes reference information. Your note describes what your run did. Keep both identities visible. Saving a public source does not automatically declare it licensed for training. See [Research library](research-library.md).

## 7. Practice composition arithmetic on paper

Create another Note called `Fictional composition arithmetic`. Keep this exercise in the notebook; it does not create a reviewed formulation or a real product.

Imagine a fictional water-like blend with two unnamed placeholders. These are invented bookkeeping entries, not actual chemicals or instructions to mix them:

| Synthetic entry | Invented mass units | Fraction of the 100-unit total | Mass percent |
| --- | --- | --- | --- |
| Carrier placeholder | 95 | 0.95 | 95 |
| Additive placeholder | 5 | 0.05 | 5 |
| Total | 100 | 1.00 | 100 |

Write: “Mass percent compares ingredient mass with total mass. These invented values contain no experimental data.” Check that `0.05` fraction equals `5` percent, not `0.05` percent. The mass basis is essential. [IUPAC: mass fraction](https://goldbook.iupac.org/terms/view/M03722/plain).

If a real supplier ingredient contains only some active component, its as-supplied quantity and active quantity need separate context. Leave unknown active content unknown. Do not convert the invented mass units into volumes or physical preparation steps.

## 8. Decide what remains unanswered

Return to your first note and separate these statements:

- **Established in this exercise:** the actual saved run status/output and the source fields you read.
- **Representation checked:** the structure submitted to the calculator.
- **Unanswered:** properties or identity of a real sample, laboratory performance and any question the chosen method did not address.

For a future real project, write the desired property, comparison/baseline, unit, method, conditions and evidence needed. A qualified scientific reviewer can help turn that into a meaningful frozen contract and approved plan. The Studio's manual execution workflow records authorized work; it supplies no automatic laboratory qualification.

## 9. Finish the learning exercise

You are finished when you can reopen the saved result, find your notebook and citation, explain the mass-fraction arithmetic, and say why none of those records is a new laboratory measurement.

Keep the practice task in draft if it contains no genuine research contract. Training or activating a model is not needed to complete this exercise. Tutorial notes, synthetic composition values and copied reference data must retain their actual origins if later considered for a dataset.

Continue with [Projects and research tasks](projects-and-tasks.md), [Materials and candidate editing](materials-and-candidates.md), or the [Chemistry and Studio glossary](chemistry-glossary.md). If you later explore local adaptation, first read the base-model/LoRA distinction in [Chemistry basics](chemistry-basics.md) and the evaluation rules in [Learning and models](learning-and-models.md).
