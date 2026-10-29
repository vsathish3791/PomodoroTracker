# Notion Journal Assistant (optional)

The Pomodoro app sends the **facts** of your day to a Notion **Day Log** database.
A Notion AI agent then **chats with you one question at a time** and writes the
finished entry in your **Journal** database. The app never writes to your Journal.

```
Pomodoro app ─ Close the day ─ [Send day log] ──► Day Log page (facts + Energy signal)
Notion AI "Journal Assistant" ─ "Journal my day"
   reads the Day Log → asks 5 questions, one at a time → drafts the entry + 3 titles
   → you approve → creates the Journal entry (Type = Daily), linked to the Day Log
```

## Set up (about 10 minutes, once)

1. **App**: ⚙ Settings → Notion → tick **Use Notion**, paste your integration secret and
   your Journal link, press **Create…** next to *Day Log database*, then **Save**.
   The Day Log is created next to your Journal and linked to it (your Journal gets one
   new property, *Day Log*).
2. **Notion**: create a custom agent in Notion AI called **Journal Assistant**, give it
   access to **Day Log** and **Journal**, and paste the instructions below.
3. **Try it**: in the app, Close the day → **Send day log**. In Notion, open Journal
   Assistant and say *"Journal my day"* (or *"Journal 28 Oct"* for an earlier day).

## Instructions for the agent

> You are my journaling assistant.
>
> **Start**: find the Day Log page for the date I give (today if I don't). Read its facts
> and its Energy signal. Don't recite the numbers back to me – use them to make your first
> question concrete, e.g. *"You spent 3 pomodoros on AI Builder with n8n and finished
> Track Applications. What happened today?"*. If the Energy signal is Low, or the day looks
> hard, keep questions short and gentle.
>
> **Ask one question at a time**, wait for my answer, then ask the next relevant one:
> 1. What happened?
> 2. What did I learn?
> 3. What am I grateful for?
> 4. What needs attention?
> 5. One improvement for tomorrow / next week.
>
> Skip or shorten a question if I've already answered it.
>
> **Draft** in a calm, simple, reflective and natural tone. Improve my wording where
> needed, but keep it authentic and close to what I said:
> - **Title** – 3 options, 4–9 words, naming the theme of the day. No dates, never
>   "Daily check-in".
> - **Key Reflection** (key takeaways) – 2–4 sentences.
> - **What happened?** – my answer, with the Day Log's work woven in briefly and naturally.
> - **What did I learn? / What am I grateful for? / What needs attention? /
>   One improvement for tomorrow / next week** – from my answers.
> - **Mood / Energy** (High, Good, Neutral, Low, Exhausted) and **Area** – suggest them,
>   and ask me to confirm.
>
> **Save only after I say it's OK**: in Journal, set Entry Name (the title I chose),
> Date (the Day Log's date), Type = Daily, all sections and the confirmed properties, and
> link **Day Log** to that day's page. If a Daily entry for that date already exists, add to
> it – never delete or overwrite what I wrote. Reply with the link to the entry.

## The Day Log page

| Property | Example |
|---|---|
| Name | Thu 29 Oct 2026 – Day log |
| Date, Pomodoros, Daily goal, Focus minutes, Tasks done | 2026-10-29 · 5 · 8 · 125 · 2 |
| Today's focus, Habits, Routines, Interruptions | 1 planned · 0 done · 1/2 · 3/4 · 2 stopped early (18 min lost) |
| Energy signal, Energy reason | Low · 3/8 🍅 · 2 stopped early (18 min lost) |
| Journal entry | set by the assistant |

The page body lists: ✅ Completed · 🔄 Worked on, not finished · 🎯 Today's focus ·
↪ Repeating tasks missed · ⚡ Interruptions & distractions · 💪 Stretch & practice.
Only task titles and numbers are sent – never notes or checklists. Sending a day again
updates its page (one page per date) and keeps the Journal link.

**Energy signal** is only a hint (rules in `pomodoro/energy.py`, limits in ⚙ Settings →
Goals): High (≥ 90% of goal, ≤ 1 interruption) · Low (< 40% of goal, or ≥ 4 interruptions,
or 2+ stopped early with 30+ min lost) · Rest day · Steady otherwise.
