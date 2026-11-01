# Chemistry and Studio glossary

These short definitions explain the terms you meet in the app. They are an orientation, not a replacement for a method specification, source record or qualified scientific review. See [Chemistry basics](chemistry-basics.md) for analogies and [A guided first research exercise](guided-first-research.md) for an app-only walkthrough.

## Objects and descriptions

| Term | Plain meaning | In the Studio |
| --- | --- | --- |
| Atom | One chemical building unit, identified by its element | Part of a structure representation |
| Molecule | Bonded atoms forming a neutral entity; some materials are described by ions or extended structures instead | A possible known target/identity |
| Molecular formula | The element counts, such as `C2H6O` | A descriptor; not a complete connectivity diagram |
| SMILES | Text encoding of a molecular structure and supported structural detail | Input to structure tools, such as `CCO` |
| Material identity | What substance, polymer, mixture or class is being described | A record that can remain explicitly unknown |
| Material grade | Supplier/grade-specific context for an identity | Keeps a commercial specification distinct |
| Sample | A particular physical portion involved in actual work | Bind measurements to the intended sample |
| Formulation | Ingredients and amounts with a stated basis | A scientific revision, separate from a private recipe note |
| Process | The ordered steps/conditions associated with a proposal | A process revision has its own identity |
| Revision | One stored version of a record | Historical scientific content remains traceable |

For the formal molecule definition, see [IUPAC](https://goldbook.iupac.org/terms/view/M04002). For structure notation and different equivalent SMILES, see the [Daylight specification](https://daylight.com/dayhtml/doc/theory/theory.smiles.html).

## Quantities and comparisons

| Term | Plain meaning | Question to ask |
| --- | --- | --- |
| Unit | The scale attached to a value, such as `g`, `mL` or `s` | “What does this number count or measure?” |
| Basis | What an amount is relative to | “Total mixture, active content, or material as supplied?” |
| Mass fraction | Ingredient mass divided by total mass | “Which total is the denominator?” |
| Mass percent | Mass fraction multiplied by 100 | “Is this `0.05` fraction or `5` percent?” |
| Molar mass | Mass per amount of substance, commonly `g/mol` | “Am I discussing amount of substance rather than volume?” |
| Condition | A relevant circumstance such as temperature or sample preparation | “Would the comparison still be meaningful if this changed?” |
| Metric | A defined property/result used to judge a target | “Which method, unit and conditions define it?” |
| Baseline | The actual starting point for an improvement | “Which exact accepted revision?” |
| Reference | A comparison target, with only the facts known about it | “Am I matching performance, an analytical profile, or both?” |
| Control | A comparison designed to help interpret an effect | “What alternative explanation does it help check?” |
| Uncertainty | Quantified doubt/dispersion associated with an estimate | “How was it evaluated for this result?” |

Mass fraction and percent follow the [IUPAC definition](https://goldbook.iupac.org/terms/view/M03722/plain). Molar mass, density and amount/volume distinctions follow [NIST's quantities guidance](https://www.nist.gov/pml/special-publication-811/nist-guide-si-chapter-8). Uncertainty is different from a known mistake; see [NIST's basic definitions](https://physics.nist.gov/cuu/Uncertainty/basic.html).

## Research and evidence

| Term | Plain meaning | Important boundary |
| --- | --- | --- |
| Hypothesis | A proposed explanation or expectation to investigate | A proposal is not an observed result |
| Candidate | One exact proposed revision considered in a task | Accepted for research does not mean successful |
| Success criteria / contract | The agreed definition of what evidence would count | Freezing preserves the revision being evaluated |
| Calculation / descriptor | A method's output from declared input | It describes that input; no sample was inspected |
| Simulation | A computational model run under stated assumptions/protocol | Numerical stability and convergence are separate |
| Source report / extracted claim | What a specific source states | Copying it does not make it your measurement |
| Measurement | A result from actual observation with a method and conditions | Record sample, unit, review and applicability |
| Replication | Repeated work intended to check reproducibility | Repeated rows are not independent batches |
| Applicable | Relevant to the particular candidate/criterion | Reviewed does not automatically mean applicable |
| Provenance | The source-and-transformation trail behind a record | Preserve original, locator, version and method |
| Citation | A pointer to a source and often a particular passage | Presence of a citation does not prove support |
| Source rights | Permission for a particular use of source material | Public access does not settle training/export permission |
| Amendment | A documented correction that preserves the original | It is not a silent rewrite |
| Closeout | A human decision bound to evaluated task evidence | The evaluator suggests; a human confirms |

See [Experiments and evidence](experiments-and-evidence.md) for the actual review workflow and [Research library](research-library.md) for retained sources and rights.

## Models and learning

| Term | Plain meaning | In the Studio |
| --- | --- | --- |
| Base model | The starting learned model | Must be compatible with the intended runtime/adaptation |
| LoRA | A method that trains a small parameter update while keeping base weights fixed | A form of adaptation; not a new experimental result |
| Adapter | Learned adaptation parameters used with a compatible base | Preserve which base/model revision it belongs to |
| Dataset | Examples with a declared structure, origin and rights | Validation does not establish label truth |
| Synthetic data | Invented or generated examples | Keep separate from measured observations |
| Label / target | The answer/value attached to a training example | Record its actual source and meaning |
| Training split | Examples used to fit the model | Final held-out examples stay out |
| Development split | Examples used while developing/selecting the model | Different from a fresh final assessment |
| Final / held-out split | Examples reserved for independent checking | Do not use their answers to train or select repeatedly |
| Loss | The training objective's numerical error score | Lower loss alone does not establish useful chemistry |
| Evaluation | Recorded checks of behavior on a defined test set | Exact-match or citation-ID checks have limited scope |
| Applicability / coverage | Whether an input resembles the model's supported/training domain | A coverage flag is not a calibrated uncertainty interval |
| Checkpoint | Saved state that supports a defined continuation | Some resumes are warm starts, not identical continuation |
| Activation | The human-approved private active-model change | Separate from previewing/selecting a model for one run |

The LoRA/base distinction comes from the [original LoRA paper](https://arxiv.org/abs/2106.09685). For practical dataset, evaluation and activation rules, read [Learning and models](learning-and-models.md).
