# Night-v3: the unattended run of 27 Oct 2026

| File | What it is |
|---|---|
| [PLAN.md](PLAN.md) | The owner's nine points, the owner decisions, the phases and items with their status |
| [ORCHESTRATION.md](ORCHESTRATION.md) | Roles, models, lanes, the gate, commits, log tags |
| [PROMPT.md](PROMPT.md) | What every fresh session is told |
| [LOG.md](LOG.md) | Progress, with the Morning summary at the top |
| [research/](research/) | Research notes; `00_current_state.md` is what existed before the run |
| `supervisor.sh`, `run_night.sh` | The supervisor (one session per phase) and its starter |

Start: `docs/night-v3/run_night.sh` (on branch `night-v3`).
Watch: `tail -f docs/night-v3/LOG.md` and `tail -f /data/vaidyx/night-v3/supervisor.log`.
Stop: `kill -- -$(cat /data/vaidyx/night-v3/supervisor.pid)`.
Round transcripts: `/data/vaidyx/night-v3/runs/` (outside the repo).
