# What restaurants need, and where the gap is

Research notes, November 2026. Most sources are vendor blogs or vendor documentation, so treat the numbers as indicative.

## What hosts use today

- **Toast Tables**: "Seated" is set when the host seats a party, and "Paid" comes from the POS. "Dirty" or "available" are set **by hand**. Tiles show a timer from when the **check opened**, not from when guests sat down. ([Toast](https://support.toasttab.com/en/article/Using-Toast-Tables-Waitlist))
- **OpenTable**: "Paid" and "Bussing needed" are optional statuses that staff must set **by hand** on the iPad floor plan. ([OpenTable](https://support.opentable.com/s/article/Understanding-statuses-in-GuestCenter?language=en_US))
- **CAKE** updates status automatically when an order is placed or a check is closed, through its own POS. ([CAKE](https://apps.apple.com/us/app/id562046995))
- The most common failure is staff **not updating table status promptly**, which makes the floor plan unreliable. ([AskBiz](https://askbiz.co/blog/real-time-table-availability-restaurant-floor-plan-tablet)) Hosts end up walking the floor or radioing to find out. ([patent background](https://patents.justia.com/patent/20050030162))

**Gap:** POS systems know about orders and payment. Nobody knows automatically when guests **physically left**, when the table is **physically cleared**, or whether anyone has **visited a table yet**.

## Camera products already exist

- **TableWatch by DifiNative** (Intel edge): occupancy, "service status", and duration tracking from video. **It uses the same name as this project.** ([Embedded Computing](https://embeddedcomputing.com/technology/iot/edge-computing/transforming-restaurant-operations-with-ai-tablewatch-from-difinative-powered-by-intel-edge-processing), [Intel](https://builders.intel.com/solutionslibrary/intelligent-automated-table-management-with-vision-al))
- **Tarsyer**: a box on existing cameras that runs 12 checks, including "table not cleaned", and sends **WhatsApp alerts with a photo**. It's aimed at quick-service chains. ([Tarsyer](https://tarsyer.com/industries/restaurants.html))
- **Presto Vision** (2019) tracked how often servers visited tables. An Outback franchise **dropped it within a day** after backlash over employee surveillance. ([CCW](https://www.customercontactweekdigital.com/tools-technologies/news/outback-steakhouse-nixes-employee-surveillance-program-following-customer-backlash), [Techdirt](https://www.techdirt.com/2019/10/24/steak-with-side-surveillance-outback-restaurants-adding-employee-tracking-analytics-to-cameras/))

**Lesson:** detecting dirty tables isn't new on its own. The differences that matter:
1. **Privacy by design.** No photos leave the box, no per-server tracking, nothing that reads as watching staff.
2. **Built for the host stand, not for a manager's phone.**
3. **Quiet.** Restaurant staff already suffer from "tablet hell" and swipe away alerts that all look the same. ([Toast](https://pos.toasttab.com/au/blog/on-the-line/tablet-hell-in-restaurants), [Xenia](https://www.xenia.team/articles/restaurant-notification-fatigue))

## What guests and operators care about

- **Slow service is the top complaint.** 59% of diners say it's the most frustrating part of eating out. 49% get impatient **waiting to pay**, and the average wait for the check was about 10 minutes (Barclaycard, about 2018, via secondary write-ups). ([HGEM](https://www.hgem.com/opinion/speed-of-service-at-payment-a-priority-for-guests), [Sunday](https://sundayapp.com/why-waiting-for-the-check-frustrates-your-guests-and-how-to-avoid-it/))
- **Service standards:** greet within 1–2 minutes, water within about 90 seconds, drinks within 3–5 minutes. ([Menumigo](https://menumigo.com/guides/restaurant-steps-of-service), [FoodDocs](https://www.fooddocs.com/food-safety-templates/restaurant-steps-of-service))
- **Dead time between parties** is estimated at 8–15 minutes per turn, with payment lag and bussing/resetting the biggest pieces. ([KwickBook](https://kwickbook.com/blog/optimize-table-turnover-rate.html), [Petpooja](https://blog.petpooja.com/operations-workflows/top-restaurants-turn-tables-faster-without-rushing/))

## What this means for the features

| Feature | Need | What the camera can really do (tested on real footage) |
|---|---|---|
| Needs clearing | dead time, bussing | Reliable. 97% dish accuracy; set tables stay green. |
| 2. Nobody's been to the table | the greet and first-service standard | **The dish count rising** after seating is visible (drinks, then food). Water poured into pre-set glasses is **not** visible, so this means "nothing new on the table", not "not greeted". |
| 3. Time to first service | speed of service | Same signal as 2. |
| 1. Meal stage | host reads the pace at a glance | Seated, served and left are reliable. "Plates gone" is noisy. |
| 4. Check please? | the top guest frustration | Weakest signal: guests' arms hide plates. **Quiet hint only.** |
| 5. Dead time | lost revenue between parties | Reliable (state times only). |
| 6. Long stay | full nights | Reliable (people only). |
| 7. Room fullness | glanceable pace | Reliable (people only). |

Design rule for the build: **only two things make a sound**, needs-clearing and nobody's-been-to-the-table, because those are the ones staff can act on. Everything else is quiet text on the tile. No per-server numbers, ever.
