# Chemistry basics for using the Studio

You can use the Studio to ask questions, organize sources and inspect calculations before knowing much chemistry. Start by separating the thing you are describing, the claim you are making and the evidence you have. Those three choices explain many of the app's fields.

This introduction uses everyday analogies to explain records. The examples are reading, arithmetic and software exercises. They are not instructions to obtain, combine, heat or handle chemicals.

## A molecule is one structure

Atoms are the building units in a chemical structure. A molecule contains atoms bonded together; a water molecule has two hydrogen atoms and one oxygen atom. Picture a small connected construction made from different pieces. The analogy helps with connectivity, but atoms are not rigid toy blocks and chemical bonds are not mechanical clips. [ACS: Molecules Matter](https://www.acs.org/middleschoolchemistry/lessonplans/chapter1/lesson1.html) introduces this particle-level picture.

The strict chemical meaning of molecule is a neutral entity made from more than one atom. Ions carry charge, and some solids have extended structures rather than separate molecules. You do not need to settle an unfamiliar material's chemistry to create a draft: **Not sure yet** preserves an unknown target in the Studio. [IUPAC: molecule](https://goldbook.iupac.org/terms/view/M04002).

## A material is what your question concerns

In the Studio, a material identity can describe a defined molecule, polymer, commercial mixture, substance class or something still unknown. A commercial grade adds supplier-specific context. A real sample is a particular physical portion with its own source, history and conditions.

A useful analogy is a map and a particular place. A molecular structure is a representation; the sample is the real thing you would need to identify and examine. A correct map does not prove that you are standing at that location. Likewise, a valid structure entered into the app does not prove what is in a bottle, its purity, its contamination or whether it is safe to use.

## A formulation is an ingredient record

A formulation describes ingredients and their amounts on a declared basis. Think of a recipe card: it tells you the intended composition. A process revision records the ordered procedure. The same ingredient list with a different process can be a different research proposal.

The analogy stops at permission to make something. A saved formulation is a record, and a candidate is a proposal for research. Scientific review, practical feasibility and authorized laboratory work remain separate steps. In this app, an experiment packet does not start equipment.

Use [Materials and candidate editing](materials-and-candidates.md) when you have actual identities, amounts and source context to record. Keep made-up practice compositions in a clearly labeled notebook exercise.

## SMILES is a structure language

SMILES represents atoms and their connections as text. `CCO` describes the ethanol structure: two carbon atoms connected to an oxygen, with implied hydrogens under the notation's rules. It is not the molecular formula `C2H6O`. Different valid SMILES can describe the same structure, and the notation may carry additional charge or stereochemical information. [Daylight: SMILES specification](https://daylight.com/dayhtml/doc/theory/theory.smiles.html).

Think of SMILES as directions for drawing a chemical connectivity diagram. A calculation reads that diagram. It does not inspect a physical sample, prove a manufacturing route or tell you how a finished product performs.

For the first exercise, use the app's ethanol example instead of guessing structures. A parser accepting a SMILES string establishes that the software can interpret it within its supported rules. It is not a chemical safety decision.

## Formula and mass describe different things

`C2H6O` counts elements in the molecular formula. It does not specify every bond or distinguish every possible structure with that formula. The ethanol record in the NIST Chemistry WebBook lists `C2H6O` and a molecular-weight value near `46.07`; the Studio's RDKit result can use slightly different rounding. [NIST: Ethanol](https://webbook.nist.gov/cgi/cbook.cgi?ID=C64175).

**Molar mass** is mass divided by amount of substance, often shown in `g/mol`. A mole is a counting unit for a very large specified collection of entities; it is not a volume. Names such as **Molecular weight** may appear in software outputs, so preserve the displayed descriptor name, unit and method instead of renaming an unfamiliar result. [NIST: quantities and units](https://www.nist.gov/pml/special-publication-811/nist-guide-si-chapter-8).

## Percent always needs a basis

Mass fraction compares one ingredient's mass with the total mass. Mass percent is that fraction multiplied by 100. On a fictional record totaling 100 mass units, 5 units of an ingredient are a mass fraction of `0.05`, or `5` mass percent. This is arithmetic, not a formulation recommendation. [IUPAC: mass fraction](https://goldbook.iupac.org/terms/view/M03722/plain).

A simple analogy is a budget: 5 out of 100 budget units is 5 percent, but you still need to know which budget those units belong to. In a formulation, **total**, **active** or **as supplied** context changes what an amount means. A supplier's ingredient may itself be a mixture; its delivered mass and active-component mass are not interchangeable.

Mass, volume and amount of substance are different quantities. A mass percentage is not automatically a volume percentage or a mole percentage. Converting mass and volume needs appropriate density information and conditions. Keep the original basis when that information is missing. [NIST: quantities and units](https://www.nist.gov/pml/special-publication-811/nist-guide-si-chapter-8).

When editing a structured formulation, inspect **amount basis**, ingredient units, **declared total**, completeness and validation findings. Saving a draft does not silently scale its ingredients to make the total work.

## Ask a question before choosing an answer

These records have different jobs:

| Term | What it means in a research workflow | Everyday analogy |
| --- | --- | --- |
| Research question | What you want to find out | The question on an assignment |
| Hypothesis | A testable proposed explanation or expectation | A prediction written before checking |
| Candidate | The exact proposed material/formulation revision to investigate | One identified design option |
| Baseline | The starting revision against which you plan an improvement | The original design |
| Reference | The comparison target and the facts actually known about it | A benchmark example |
| Success criteria | What result, method, conditions and evidence would count | The marking rubric agreed in advance |

An **Improve** task needs the actual baseline and allowed variation. A **Match** task needs a reference and matching scope. Similar performance or a similar spectrum does not reveal a hidden recipe. **Explore** is appropriate when the question is still taking shape.

The rubric analogy explains why freezing criteria matters: it records the agreed test instead of quietly changing the target after seeing results. A later change creates a new revision. See [Projects and research tasks](projects-and-tasks.md).

## Label where each claim came from

| Kind of information | What it can establish | What to preserve |
| --- | --- | --- |
| Hypothesis | A proposed idea to investigate | Author, assumptions and unanswered questions |
| Source report | What a particular source says | Original, citation and page/table/passage |
| Structural calculation | Output of a method applied to your submitted structure | Input, engine/method, version and saved result |
| Simulation | Output of a model and protocol under assumptions | Conditions, parameters, raw results and convergence |
| Measurement | An observation from actual measurement work | Sample, method, conditions, units and review |
| Learned prediction | Output from a trained model within its intended scope | Model, data lineage and applicability limits |

These are different kinds of evidence, not interchangeable labels. Copying a published number does not make it your laboratory observation. A calculation can be correct for its input while being irrelevant to the real sample or target property.

## Plan comparisons and uncertainty

An experiment changes or examines something under a defined method. A control is a comparison that helps identify what caused the observed difference. A baseline can serve a comparison role, but the terms are not automatically equivalent. Keeping relevant conditions comparable makes the question easier to interpret.

Repeated readings of one sample and independently prepared batches answer different questions. Record which you have. Do not treat copied rows or repeated software output as independent experimental replication.

A measurement result is an estimate with associated uncertainty. Extra decimal places are not a substitute for understanding the method, calibration, sampling and variation. A known mistake should be corrected; uncertainty is not a label that makes a mistake acceptable. [NIST: basic definitions of uncertainty](https://physics.nist.gov/cuu/Uncertainty/basic.html).

For actual laboratory planning, a qualified operator and reviewer choose the method and appropriate controls. The Studio records those choices and their evidence; this introduction supplies no physical experiment procedure.

## Keep a source trail and permission trail

**Provenance** is the trail from an assertion back to its source and transformations. Think of a receipt attached to a number: where it came from, which page or file version, what method produced it and what changed afterward. A citation is part of that trail; it does not prove that the source supports your conclusion.

Source rights answer a different question: what use is permitted. Being able to read a webpage does not by itself settle permission to train on it or send private content elsewhere. The Studio separates source rights, notebook agent/training access and permission for a particular external provider. Preserve an unknown status while permission is unresolved.

## Understand learning before training

A **base model** is the starting learned model. **LoRA** adapts it by training a comparatively small set of additional parameters while keeping the base weights fixed. The resulting **adapter** is used with a compatible base; it is not a new standalone chemical truth database. [Hu and colleagues: LoRA](https://arxiv.org/abs/2106.09685).

As an analogy, imagine a reusable instrument plus an adjustment fitted to that instrument. The adjustment depends on its compatible starting device. This is only an analogy: a neural adapter is numerical learned parameters, not a literal attachment or a set of human-readable corrections.

Training data teaches patterns; held-out evaluation checks behavior on examples kept aside. Neither a lower loss nor a finished adapter establishes a chemical fact. Training on synthetic practice text does not create measured property labels. Private model selection, evaluation and human-approved activation remain separate actions in the Studio.

Start with [A guided first research exercise](guided-first-research.md). Use the [Chemistry and Studio glossary](chemistry-glossary.md) for unfamiliar terms, and [Learning and models](learning-and-models.md) when you have a justified dataset and evaluation question.
