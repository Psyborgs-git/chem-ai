# Notebooks and editing

Notebooks hold owner-private notes, recipes, formulae and structures. Scientific contracts, formulation revisions and measurements use separate editors with explicit revision and review rules. Choose the record type that matches the work you are editing.

For a first source-linked note using the built-in molecular example, follow [A guided first research exercise](guided-first-research.md).

## Create and organize notebooks

Open **Notebooks**. Choose **New folder** or **New notebook**, enter its name, and select **Create folder** or **Create notebook**. Select a notebook, choose **New page kind**, then **Add page**. Available page kinds are **Note**, **Recipe**, **Formula**, and **SMILES structure**.

Search within the notebook using **Search pages**. Under **Notebook settings**, rename the notebook and select **Move notebook to folder**. Folder settings let you rename a folder and choose a parent folder. The service rejects invalid folder relationships rather than creating cycles.

## Edit a page

| Page kind | Editing surface |
| --- | --- |
| Note | Markdown text with preview |
| Recipe | Ingredient name, amount and unit rows, plus one procedure step per line |
| Formula | Structured formula content and mathematical notation |
| SMILES structure | A SMILES string with structure validation and a rendered preview when available |

Edit the page title and contents. **Preview** shows the rendered page; **Edit** returns to authoring. Markdown supports headings, lists, tables, fenced code and mathematical notation such as `$c=n/V$`. Raw HTML is not enabled. External images remain links until a person opens them, preventing automatic image requests from disclosing that a private page was viewed.

Notebook content is not automatically a reviewed formulation, measurement or task decision. A recipe page is useful private writing; a scientific formulation revision has quantity validation and acceptance gates. See [Materials and candidates](materials-and-candidates.md).

## Understand autosave and recovery

The toolbar shows **Unsaved**, **Saving...** or **Saved**. The editor starts autosaving after roughly 900 ms without another edit. A confirmed backend revision is required for Saved. You can also choose **More → Save**.

Pages save using an expected revision. If another writer has changed the page, the request reports a conflict rather than silently replacing the newer content. The open draft is retained, and **Save a separate copy** creates a recovered page with your current content and citations. Review the two versions deliberately.

Unsaved notebook drafts are also kept in account-scoped session storage when browser storage is available. Reloading in that browser session can display **Your unsaved draft was recovered for this account**. The draft keeps its original expected revision so recovery cannot silently overwrite a newer server version. Sign-out clears these browser drafts. Session storage is not a backup and may disappear when the browser session ends.

Changing a notebook/page waits for its pending save. **Ask agent** saves the current page before opening the agent with that page as context. If a save fails, keep the editor open, correct the reported issue, retry, or preserve a separate copy before leaving.

## Review or restore history

Select **More → History** to read prior revisions. **Restore as new revision** copies the old content into the current draft. Saving creates a new revision; it does not change the historical record.

Select **More → Trash page** and confirm **Move page to trash**. The notebook's **Trash** section can **Restore page**. Trashing preserves history and makes derived research memory stale. Do not confuse trashing a page with permanently deleting all prior copies, transcripts, exports or training effects.

## Add source citations

Save a source in the Research library first. In the page's **Sources and citations** section:

1. Choose a **Saved source**.
2. Record **Passage, page or table**, such as `Page 4, Table 2`.
3. Choose **Attach citation** and wait for the page to save.
4. Use **Review source** to inspect the retained source text and checksum, or **Download cited original** to review its original bytes.

**Remove** detaches a citation from the current page revision. It does not rewrite the earlier revision or delete the original source. A citation locator records what you reviewed; it does not establish that the source supports every sentence in the note.

## Control agent and training access

Under **Notebook settings**, the following controls are independent:

- **Allow my agent to use this notebook** controls current agent retrieval.
- **Allow local training from this notebook** controls notebook-derived dataset/training use.
- Private-content disclosure to a specific external provider is controlled separately in **Agent → Settings**.

Agent and training access start enabled by default. Notebook opt-outs and source rights are rechecked during use. Edits, trash, opt-outs or source-right changes can invalidate derived memory or checkpointed context. Turning access off does not undo an earlier model update or erase an already saved transcript.

## Other editors use explicit save rules

| Record | How changes become durable |
| --- | --- |
| Task success criteria | **save draft**, then **freeze contract** when ready; new revisions preserve frozen history |
| Formulation | **save formulation draft**; incomplete drafts remain drafts until acceptance |
| Candidate | Propose draft, submit for review, then a human accepts or rejects |
| Lab actuals | **record actuals** persists the actual materials, process, deviations and observations |
| Measurement correction | An amendment with a reason creates a new immutable record |
| Provider settings | Explicit save; blank API-key edit retains the stored key |

Do not assume the notebook's autosave/recovery implementation applies to every scientific form. Read each editor's status and inline findings before navigating away.
