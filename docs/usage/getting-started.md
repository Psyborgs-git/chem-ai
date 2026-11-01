# Getting started with Chemistry Studio

Chemistry Studio keeps research questions, scientific records, private notes, source files, calculations and model work in one local workspace. You can use projects, notebooks, records and review workflows without connecting an AI provider or downloading a model.

If chemistry is new to you, start with [Chemistry basics](chemistry-basics.md), then follow [A guided first research exercise](guided-first-research.md). The [Chemistry and Studio glossary](chemistry-glossary.md) explains unfamiliar words while you work.

## Open your installation

For the native Mac app, open Chemistry Studio from Applications. The startup screen checks the installed runtime, database and migrations before opening your workspace. **Try again** retries a reported startup failure. **Startup details** contains the actual failure and local log location. This native package uses the Python environment and Docker database belonging to its checkout; it is not a self-contained scientific-runtime installer.

For a development installation, run the setup in [Local development](../development/local-development.md), then open `http://127.0.0.1:5173`. Continue using the same hostname and port for your session. `localhost` and `127.0.0.1` are different browser origins.

See [Installation](../operations/installation.md) and [Native macOS app](../operations/desktop-macos.md) for runtime setup and startup recovery.

## Set up or sign in

A fresh installation displays **Set up Chemistry Studio**. Enter a login, display name and password, repeat the password, and select **Create owner account**. The password must contain at least 10 characters. This creates the installation's owner account once; there is no public account registration flow.

An installation with an existing owner displays the sign-in form. Use that installation's account. Successful sign-in reloads the current destination. **Sign out** ends the server session and clears identity-scoped client state. An expired session requires sign-in again; the default session lifetime is 12 hours.

Do not create another installation or reset the database to work around a forgotten account. Ask the installation administrator to use the access and recovery procedures in [Administration](../operations/admin.md).

## Find your way around

The main navigation contains five destinations:

| Destination | Use it for |
| --- | --- |
| **Home** | Recent work, starting research, and the local molecular calculator |
| **Projects** | Shared project records and task workspaces |
| **Notebooks** | Your private notes, recipes, formulae and structures |
| **Research library** | Searching for and retaining papers, web sources and chemical records |
| **Local learning** | Private datasets, model assets, training and evaluation jobs |

Open **More** for Downloads, Research memory, Lab, Materials & Products, Evidence, Imports, Model registry, Compute, Providers and documentation. The secondary groups are **Saved work** and **Tools & settings**.

Use **Find your work** in the header, or `Command-K` on Mac and `Control-K` elsewhere, to navigate to tasks, projects, notes, sources, memory and quick actions. The finder searches your work; Help has its own article search. On a narrow window, **Open navigation** opens the sidebar and Escape closes it.

**Agent** in the header opens your private research conversation from any screen. Choose a model before sending a message. Read [Agent and providers](agent-and-providers.md) before authorizing external access or unattended work.

## Make a first useful record

For a calculation, select **Explore molecule** on Home, then enter `CCO` in **Molecular structure**, and select **Calculate properties**, or use **Try ethanol**. A working local RDKit engine produces a saved result. **Open full result** opens its durable record. If the engine is unavailable, select **Check again** after installing or repairing it. A failed calculation keeps an honest failure record; it does not invent descriptors.

For research, create a project under **Projects**, then choose **New research task**. Select **Explore**, enter the research question as the task title, and choose a molecule, material, formulation or **Not sure yet**. **Create task** opens a draft workspace. A task can also begin from Home without selecting a project; the app organizes it in the Research inbox.

For private writing, open **Notebooks**, choose **New notebook**, then **Add page**. Start with a Note and wait for **Saved** after editing. Notebook drafts and scientific record drafts have different save rules; see [Notebooks and editing](notebooks-and-editing.md).

## Understand what is private and what is reviewed

Projects and scientific task records use workspace permissions. Private notebooks, the app-wide Agent, retained private research sources, private learning assets and simulations belong to their author. A workspace administrator's broad read grants do not turn those private resources into shared project records.

Allowing your agent to use a notebook, allowing local training from it, and allowing a particular external provider to receive private context are separate settings. Linking private work to a project is not a publication action.

The app distinguishes hypotheses, extracted claims, calculated values, simulated results and measured observations. Saving a record, completing a run, or passing a software check does not by itself validate a scientific claim. Human reviews remain visible decisions.

## Use Help

After signing in, open **Help & documentation**. Browse the Using the studio, Development, Operations and Reference sections, or search locally by a screen label, command, endpoint, GraphQL field or environment variable. Help articles are bundled with the installed frontend. Reading an article does not send its text to an AI provider or run the commands it contains.

Installation and account recovery instructions remain available as repository Markdown when the app cannot start or sign in. Start with [Installation](../operations/installation.md), [Recovery](../operations/recovery.md), and [Backup and restore](../operations/backup-restore.md).

## When something does not save

Keep the editor open and read its inline error. **Saving**, **Unsaved**, **Saved**, **read only revision**, and a failed request describe different states. Copy valuable unsaved text before reloading when the editor has no recovery action. A conflict means another revision is current; it is not permission to overwrite it.

For unavailable optional features, open **Compute** or Local learning's **Runtimes** details. A visible engine or model entry is not a guarantee that its dependencies, hardware, weights and rights are ready. See [Calculations and simulations](simulations-and-calculations.md) and [Learning and models](learning-and-models.md).
