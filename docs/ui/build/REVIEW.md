# Review guide (filled in during the run; final version at the end)

## How to open everything (localhost through VS Code port forwarding)
| System | URL | Login |
|---|---|---|
| Vaidyx-TB new interface | http://127.0.0.1:7000/tb-nik | the demo logins in ~/vaidyx/.tb_v2_demo_logins (username column) or the new email logins listed in docs/ui/build/LOGINS.md (passwords only in the files named there, never in git) |
| Old interface (unchanged) | http://127.0.0.1:7000/tb | same |
| Demo HIMS | http://127.0.0.1:7130/his | data/his_mock/logins.tsv (8 roles) |
| Demo PACS viewer (through the HIMS) | http://127.0.0.1:7130/api/tb/pacs/ohif/viewer?StudyInstanceUIDs=<uid> | HIMS login |
| LiveKit (video) | ws://127.0.0.1:7880 | tokens issued by Vaidyx |

## What to check, in order
(to be completed)

## Known gaps
(to be completed)
