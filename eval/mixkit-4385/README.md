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
