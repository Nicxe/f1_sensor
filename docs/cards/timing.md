---
id: timing
title: Read and configure timing
description: Choose timing columns, push laps, qualifying comparisons and driver details in the F1 Sensor card.
toc_max_heading_level: 3
---

Configure a **Timing** module to follow practice, qualifying or race timing. Add the module in the [F1 Sensor card editor](/cards/modular), then choose the fields and **Module options** described below.

Live timing must be enabled; live and replay data still depend on the selected session. The module does not need a matching Home Assistant timing sensor on a backend with [automatic card data](/features/card-data-and-sensors).

## Choose columns

Timing can follow a session profile or use your selected columns. Choosing your own timing columns keeps them as a custom selection. A module pinned to a driver keeps that driver when you change the card's general focus.

## Follow push laps

In a **Timing** module, open **Module options** and choose **Push laps** to
follow drivers making a likely fast attempt during practice, qualifying or
sprint qualifying.

| Setting | What you see |
| --- | --- |
| Off | Your usual timing table and sorting. This is the default. |
| Push laps first | Likely push laps appear in a group above the other drivers. The remaining rows keep your selected sorting. |
| Push laps only | Only likely push laps and their briefly retained results appear. Duplicate a Timing module to create a separate compact panel. |

Push laps are ordered by progress around the current lap, with the driver
nearest the next finish-line crossing first. The position column still shows
the driver's classification. Timing and minisector passages provide an
approximate track order; it is not an exact position measurement. Driver and
team selections still apply, and push laps are selected before the row limit.

The card distinguishes a possible push lap from a stronger pace assessment.
Highlighted attempts show only received sectors from the current attempt;
earlier lap times do not fill the remaining sectors.
After a highlighted lap finishes, its result stays visible briefly. A driver
who slows down or enters the pits leaves the active group. If there are no
current attempts, the card explains this separately from missing timing data.

The assessment uses fresh timing progress and comparable recent sector pace.
It cannot establish a driver's intention, fuel load or practice programme.
Early attempts, changing weather and incomplete data can make the assessment
less certain. A push lap does not need a green or purple sector.

Live Delay, No Spoiler and replay apply to the assessment and the displayed
timing together. After seeking or reconnecting, the assessment may need fresh
lap evidence before it can highlight a driver. The push setting does not change
race or sprint-race sorting.

## Compare a push lap with the best qualifying lap

Choose **Push laps first** or **Push laps only**, then enable **Show difference
to best lap** beneath **Push laps**. This optional setting is off by default
and applies only to qualifying and sprint qualifying.

The S1, S2 and S3 columns show a signed difference below each received sector
time. S1 compares the first sector, S2 compares the combined first two sectors,
and S3 compares the whole lap. For example, **−0.008** after S1 means the driver
is 0.008 seconds ahead of the reference at that point. **+0.357** after S2 means
the driver is 0.357 seconds behind after two sectors. The difference stays
unchanged between sector passages.

Differences use neutral text with explicit minus or plus signs. Sector-time
colors keep their existing meanings: personal best, recorded time and overall
fastest.

The reference is the fastest valid completed lap in the current qualifying
part, such as Q2 or SQ2, across all drivers. Its driver and time appear below
the push label. Each attempt keeps the same reference through the finish unless
that reference is invalidated. The next attempt can use a newly improved best.
This uses the sectors of one actual lap; it does not combine separate sector
records into a theoretical lap. Driver and team filters do not change the
reference.

The final difference stays with the briefly displayed completed attempt.
Missing reference sectors, corrected or deleted times, and incomplete data
after joining or seeking show **—** instead of an estimated difference.
The option also works with **S1 with minisectors**, **S2 with minisectors** and
**S3 with minisectors**; differences update at sector boundaries only.

## Compare practice lap times

In a **Timing** module, add **Gap to fastest lap** (`best_lap_gap`) to your
selected columns. During practice it shows each driver's best lap relative to
the fastest valid best lap of the session, for example `+0.412`. The fastest
time shows `0.000`; drivers without a valid best time show `—`.

The card prefers the gap supplied by live timing. When it is unavailable, it
calculates the difference from the timing source's current valid best times.
Selecting one driver or team still compares against the whole session. Deleted
or corrected best times update the comparison; old observed laps are not used
to restore a removed time.

This optional column is available for practice in live timing and replay. It
does not replace race gaps or the current-part qualifying gap. Existing timing
profiles and saved columns stay unchanged.

## Compare driver details

Open **Driver details** in a Timing module to choose information that appears when you select a driver. These choices are independent of **Content and columns**. The initial detail fields are Best lap, Tyre age and Status. You can choose other Timing fields, including S1, S2 and S3 minisectors, without adding them to the table. Minisector data is requested only while a selected driver needs it.

Select a driver to expand a detail row directly beneath that driver in the Timing table. You can open several drivers at once, and each driver's details stay attached to their row as the order changes. Select a driver again to close that row, or use **Close all driver details** above the table. Your selection is temporary and belongs to this Timing module. It does not change the card's driver focus. Changing session or replay context clears the selection.

Fields already shown as table columns are omitted from the detail panels. **Recent laps in driver details** can include older completed laps without repeating the laps already shown as table columns. If the chosen detail fields and laps add nothing to the table, the driver names are not opening controls. Clear **Show driver details** to disable them explicitly. Missing values remain missing; the card does not estimate minisector times.

Use **Show text below times** to hide the lap number, qualifying part and other supporting text below timing values. Use **Show time status icon** to hide the arrow, dot or square in a timing value. These choices apply independently to Last lap, Best lap, sector times, combined sector and minisector fields, qualifying times and lap comparisons in that Timing module.


## Recent lap columns

Set **Recent lap columns** under the Timing module's **Module options** to compare the latest 1–30 completed laps directly in the timing table. The default value is 0, which keeps these columns hidden. Each column is labelled with its lap number; a dash means that no usable time is available for that driver and lap.

## Read timing colors and symbols

Open **Accessibility and timing colors** to adjust timing colors and the accompanying signals. Color is only one part of the meaning.

| Signal | Meaning |
| --- | --- |
| Purple and diamond | Overall fastest. |
| Green and circle | Personal best. |
| Yellow and square | A recorded time. Yellow does not mean slower than the previous lap. |
| Neutral previous-lap value | The value belongs to the labelled earlier lap. |
| Down triangle with a negative lap delta | A faster lap than the stated reference lap. |
| Up triangle with a positive lap delta | A slower lap than the stated reference lap. |
| Position arrow | A position change against its stated comparison, not a change in lap time. |

The default sector view keeps values from the same lap together. The **Latest sectors, with lap labels** option can mix the most recently supplied sectors; the individual lap labels matter in that view. A theoretical lap is the sum of personal-best sectors and may combine different laps.

The same purple diamond, green circle and yellow square are used for minisector
status. Yellow means that the provider marked the segment as recorded without a
personal or overall best status. It does not prove that the segment was slower
than the driver's preceding lap. Reset, special, missing and unrecognized source
statuses stay neutral instead of receiving an assumed meaning. Turn on the
Minisectors module's status legend when you want the explanation beside the data.

Minisector status is short-lived dashboard data and can update several times per
second across all drivers. It is delivered only while a visible modular card needs
it and is not exposed as Home Assistant sensor state. This avoids filling Recorder
or sending a complete timing grid for every small change. It also means minisector
status is intended for the F1 Sensor card rather than entity-based automations.

Custom colors can help you distinguish the timing states. Keep symbols or text available and check both light and dark themes. High contrast, reduced motion and readable text alternatives are part of the card's controls; automated checks alone do not establish compatibility with every screen reader or device.

Track Map moves driver markers smoothly between consecutive live or replay positions. It moves directly to the new position when reduced motion is enabled, the session changes, the position is stale or the new sample is too far from the previous one to be a continuous movement.

See [card accessibility](/cards/modular-accessibility) for focused keyboard, contrast and motion guidance.

## Continue

- [Add minisector status](/cards/minisectors)
- [Arrange a wider timing view](/cards/layout)
- [Look up driver timing attributes](/entities/driver-positions)
- [Match live timing to your TV](/features/live-delay)
