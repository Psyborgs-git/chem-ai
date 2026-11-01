# Research library and saved sources

Use the Research library to discover sources and retain the bytes, readable text and citation metadata you actually reviewed. Downloads presents retained files. Research memory stores private findings and questions with source links.

## Search for a source

Open **Research library** and enter a paper topic, compound or DOI in **Search resources**. Choose a source and select **Search**:

| Source | What it searches |
| --- | --- |
| **OpenAlex papers** | Scholarly records and available paper locations |
| **Crossref** | Publication metadata and DOI records |
| **PubChem** | Chemical records |
| **Web search** | The configured app-local SearXNG service |

**View source** opens a result's website. **Save** attempts to retain the actual available source. Search metadata is not a downloaded full text. Missing full text, a remote rate limit or a failed request is reported without inventing a paper copy.

The optional web-search service starts with `bash infra/local/research-search.sh start` and normally listens on loopback port 8088. Runtime setup belongs to the administrator; see [Agentic research](../operations/agentic-research.md).

## Save a URL or upload a file

Expand **Save a URL**, enter an HTTPS source URL, and select **Save source**. Source-fetch URLs cannot address loopback/private machines or redirect into them. Use an uploaded file when the document is already on your computer instead of trying to fetch a local URL.

Open **More → Downloads** and use **Add a file** to retain a paper, dataset or reference file. Uploading retains a source; it does not automatically approve its claims or declare that its license permits model training.

## Review a retained source

Filter **Saved sources**, then select a source row. The inspector shows its title, media type, origin and available actions:

- **Open** or **Download original** retrieves the retained original.
- **Cite → Export citation** downloads citation JSON.
- **Cite → Export BibTeX** downloads a BibTeX citation.
- **More → Extracted text** opens the readable extraction, if available.
- **More → Original website** opens the recorded public source URL.
- **More → Check for update** fetches a new source version while retaining earlier versions.
- **More → Research source** opens the private Agent with that source as context.

**Citation and file details** exposes the original filename, checksum, retention time and citation metadata. Use these to identify the exact file you reviewed. Unsupported extraction or unavailable readable content remains visible; do not treat an empty extraction as evidence that the original was empty.

## Understand where files live

The protected source copy lives in the local artifact vault. Readable review copies normally appear under `~/Downloads/Chemistry Studio/<workspace>/<owner>/`; the administrator can change the root with `STUDIO_DOWNLOADS_ROOT`. Downloads shows **Storage location** when available.

Learning and simulation artifact downloads use their own job-specific folders beneath `~/Downloads/Chemistry Studio/Artifacts/` in the native app. Filenames avoid collisions. Retained research source folders and scientific job artifact folders serve different purposes.

Insufficient storage blocks new retention instead of silently evicting old files. Back up the database and vault together; a citation record without its source bytes is not a complete retained-source backup. See [Backup and restore](../operations/backup-restore.md).

## Cite a source in a notebook

Open a notebook page, select the source under **Sources and citations**, add a page/table/passage locator, and choose **Attach citation**. **Review source** lets you inspect the retained text and original. See [Notebooks and editing](notebooks-and-editing.md).

An agent may preserve evidence snippets and copies of authorized original artifacts it actually used. Those copies retain source lineage and current rights restrictions; copying an artifact does not create new permission to send or train on it.

## Save and use research memory

Open **More → Research memory**. Add a memory with a title and a finding, decision or question, then choose **Remember**. Source-linked memory can also be created by the agent from authorized current pages and sources.

Select a memory to inspect it. **Continue** opens the Agent with that memory. **More → Forget** prevents future retrieval of that memory. It does not undo earlier training or remove copies already present in past conversations.

**Source changed** and **Needs review** indicate stale dependencies. Revisit the originating page or source and update the finding from current evidence. Stale memory must not be treated as a fresh observation.

## Distinguish retention from extraction review

**Downloads** accepts local files for private retention. **Imports** is a scientific evidence-extraction review surface: it expects an artifact already committed to the vault, runs quarantined extraction, and exposes proposed records for accept/reject/promote actions.

For the latter, an integration can use the artifact upload API to create a staged upload, send bytes to its returned URL, finish it, then submit the artifact identifier under **Imports → Import a stored source**. Do not paste a Downloads source ID where an artifact ID is required. See [Experiments and evidence](experiments-and-evidence.md) and [Backend and contracts](../development/backend-and-contracts.md).

## Rights and privacy

Publicly reachable content is not automatically licensed for training or export. Preserve the declared source rights, confidentiality and provenance. Private provider disclosure, notebook access, training rights and scientific claim review are separate checks. Source revocation affects derived context and retained copies; revocation is not the same as deleting every historical artifact. See [Privacy](../operations/privacy.md).
