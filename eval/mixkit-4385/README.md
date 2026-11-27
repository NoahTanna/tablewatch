# Real-footage check: Mixkit clip 4385

A free stock clip ("Customers in a minimalist style restaurant", Mixkit Stock Video Free
License) filmed from a fixed high camera, as a time-lapse of a whole service: tables fill,
guests leave dishes behind, staff clear and re-set tables. The video is not stored here
(the license doesn't allow redistributing it). Download it with:

```bash
curl -L -o eval/mixkit-4385/4385.mp4 https://assets.mixkit.co/videos/4385/4385-720.mp4
```

- `zones.json`: the four tables along the right-hand wall.
- `labels_samples.csv`: hand labels for every half-second (30 samples x 4 tables).
  people = guests seated at the table (waiters don't count);
  dishes = any tableware or food on the table (clean set glasses count).

`tests/test_real_footage.py` scores the detector against these labels and runs
automatically when the video and model are present.

Result when this was added (people from the whole frame, dishes from zoomed table crops):

| | correct | missed | false alarms |
|---|---|---|---|
| people | 92% | 0 of 54 | 9 of 66 (2 waiters walking past, the rest at the T1/T2 zone boundary) |
| dishes | 97% | 4 of 72 | 0 of 48 |

After dropping duplicate partial boxes on the same person (see below): people 93%, 8 false alarms.

## Full system on real frames (new screen)

`retime_service.py` holds real frames of the clip long enough for the timers to play out (about 9 minutes),
using `floor.json` here for the map. Streamed like a camera into the agent, server and dashboard, with every
timer set to 1 minute:

```bash
python eval/mixkit-4385/retime_service.py eval/mixkit-4385/4385.mp4 service.mp4
```

Result (November 2026):
- Correct: the set table with clean glasses stayed green; table 2 went "Guests left", red, then free when cleared;
  table 4 went seated, "nothing served", then eating when food arrived.
- Fixed by this run: one diner was detected twice (whole body plus upper body), the second box landed in the next
  table's zone and created a phantom party, a false "nothing served" and a false red. Person boxes that sit almost
  entirely inside another person box are now dropped.
- Still wrong: table 3's guests left a single cup about 15 pixels wide at the far end of the room. After video
  compression it scored under the dish cutoff, so the table went green instead of red. Single small items far
  from the camera are at the limit of a 720p view: use a 1080p or better camera, mounted so no table is far away.
- Still noisy: a "check?" hint on a table whose guests were still eating (guests' arms hide plates). It's silent,
  but visible.
