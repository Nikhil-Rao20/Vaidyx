# Agent skills

One folder per specialty support agent, each with a `SKILL.md` (YAML frontmatter + Markdown), in the Agent Skills layout.
The file says **who the agent is and what it looks for**. It never says what the agent may do: the tools, the hard rules
(every sentence needs a verified quote; no diagnosis, staging, treatment or image interpretation; guideline text only about
what reports should contain) and the output checks are in `tumour_board/agents.py` and are applied after the skill text on
every call.

```
---
name: radiology                      # must equal the folder name and a role in agents.ROLES
description: one or two sentences   # <= 1024 characters
label: Radiology support             # shown in the UI
department: Radiology                # a hospital department (org.json name, id or alias) or a protocol department name
doc_types: [ct, mri, ...]            # subset of protocols/facts.json doc_types; read first and used for "no documents" detection
guideline_query: imaging report ...  # the pack search run before the first step (records and reporting, never treatment)
version: 1
---
# Focus          <- required: bullet list, becomes the agent's focus line
# What to look for in the records   <- optional guidance, appended to the system prompt
# Points for review to raise        <- optional guidance
```

A hospital's edit is written by an admin from the UI ("Agent skills") to `data/tumour_board/skills/<role>/SKILL.md` and takes
precedence over the file here; "Reset to default" removes it. A file that fails validation is ignored (audited) and the
default is used. Loader: `tumour_board/skills.py`.
