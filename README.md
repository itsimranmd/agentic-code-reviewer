# Agentic Code Reviewer

**An AI that reviews pull requests - built to highlight only what matters & cut down bot noise**

```
Naive version:   65 comments on 5 clean commits   (~3% of it useful)
This version:     0 comments on the same 5 commits
                  95% catch rate on 20 real, known bugs
                  0 false alarms
```

---

## The problem

Ask any AI to "review this code and point out issues" and it will always find something - that's just what happens when you ask a language model to justify itself.

Here's what that actually looked like, from a one-line change in a real, popular Python library:

> *1. Type Hinting and Protocol Usage - 2. Error Handling - 3. Testing - 4. Code Clarity - 5. Deprecation of `basestring` - 6. Imports - 7. Documentation - 8. Performance Considerations*

Twelve comments. On one line. Two of them were flat-out wrong - it claimed a valid, modern Python feature "wasn't standard," and it flagged a maintainer's email address as something worth double-checking. A developer sees that once and turns the bot off for good.

**So the real project here wasn't "can AI find bugs." It was: can I make it disciplined enough that people actually keep reading what it says.**

---

## How it works

```
   Pull request opened
          |
          v
   Read only the new lines, with real line numbers
          |
   +------+------+------+
   v             v      v
 SECURITY  CORRECTNESS  TESTS      three separate, narrow checks
   |             |      |          instead of one vague one
   +------+------+------+
          v
   Every claim must quote the actual code - unquotable
   claims get thrown out automatically
          v
   Only findings it's fairly confident about get through
          v
   Comments posted on the exact line in the PR
```

Splitting it into three narrow checks instead of one vague prompt matters because one prompt trying to do four jobs does all of them badly. Each check also gets told, explicitly, what *not* to bother reporting - and that part turned out to matter more than anything else.

---

## Part 1: the naive version, and why it didn't work

First attempt: one prompt, one pass, tested on five real code changes from `requests` - the most-downloaded Python library there is. Real code, written by good engineers, not toy examples.

```
change            lines changed   comments it made
6f66281a               31              19
6f205ff4               15              18
1190afd1                1              12
cd90742e                 2               5
6e83187b                 4              10
```

**The smaller the change, the more it complained.** A one-line type annotation got 12 comments. A pure formatting fix - fixing indentation in a comment - got 5, including unsolicited advice about how to write better commit messages. The model doesn't scale its output to how much there actually is to say; it was asked for issues, so it invents some.

I went through all 64 comments by hand. Roughly 3% were things a developer would genuinely act on. The rest was vague hedging ("maybe add more tests," "consider error handling") or just wrong.

---

## Part 2: four fixes, each aimed at something specific that went wrong

**1. Only look at what actually changed.** The reviewer now only sees added lines, with their real line numbers. Commenting on code nobody touched was one of the fastest ways to get ignored.

**2. Three separate checks instead of one.** Security, correctness, and test coverage each get their own prompt, with a clear list of what not to bother mentioning. Vague advice only goes away once it's specifically ruled out.

**3. Every finding has to quote real code -> this is the one that mattered most.** The rule: if a finding can't include an exact quote from the diff, it doesn't count. The code then checks, automatically, whether that quote is actually there.

```
A model can say anything with confidence.
It can't fake a quote that has to exist in the code.
```

This directly fixes the earlier problem - the wrong claim about a Python feature. If the model tries to invent something, there's simply nothing to quote, so it gets dropped before anyone sees it. And it costs nothing to check.

**4. A confidence cutoff.** A diff only shows what changed, not the rest of the file - so there's plenty the reviewer genuinely can't know, like whether a test already covers this. So it's told exactly that, and anything it's not fairly confident about below a 0.7 threshold gets dropped rather than guessed at.

**Result, on the same five commits: 65 comments down to 0.**

Staying silent on a whitespace fix and a version bump is the right call. But zero comments also looks exactly the same whether the reviewer got genuinely better, or just stopped working. There's no way to tell the difference from this alone - which is the whole reason for what came next.

---

## Part 3: 

**The idea: use history that's already labelled.** Every time someone fixes a bug in a real project, that commit is proof of exactly what was wrong and where. Take the code from just before the fix, and the bug is right there.

```
the actual fix:                    what gets reviewed instead:
  - broken line          ->          + broken line   <- this is the known bug
  + fixed line                       - fixed line
```

Flip the added and removed lines, and now there's a diff that *introduces* a real bug that once fooled a real reviewer - along with an answer key for exactly where it is.

### The test set needed cleaning up - twice

**First attempt:** searched commit messages for words like "fix" and "bug." Found 35 matches. Catch rate: **66%.**

**Problem: 15 of those weren't actual code bugs.** "Fix remaining typos," "Fix a broken link," "Fix cosmetic regex formatting" - the word "fix" doesn't always mean a bug got fixed. So instead of trusting the commit message, the filter now checks what the change actually touches - code, not docs, not config, not a revert.

**After cleaning it up: 20 real bugs, 95% caught, zero false alarms.** The one it missed turned out to still be a documentation fix that slipped through - so the real number is arguably closer to a clean sweep.

**Both numbers are reported here on purpose, not just the better-looking one:**

```
35 commits matching "fix"-type keywords:    66% caught
20 after filtering out non-code changes:    95% caught
False alarms, at every setting tested:       0
```

### Choosing where to set the confidence bar

Confidence is a dial, not a fixed setting. Rather than re-running everything at each level, findings were collected once with no filter at all, then filtered afterward at different levels - same result, far cheaper:

```
confidence level     bugs caught     false alarms
      0.0                95%              0
      0.5                95%              0
      0.7                95%              0   <- this is what's live
      0.8                10%              0
```

It stays flat all the way up to 0.7, then drops off a cliff. So 0.7 is the right setting - same number of bugs caught as no filter at all, but with the most safety margin against future false alarms.

---

## Part 4: live on a real pull request

This now runs as a GitHub Action - it comments on real pull requests automatically.

A few choices worth explaining, since they matter once something runs unattended on real code:

- **If it crashes, it fails quietly and gets out of the way.** It should never be the reason a pull request can't be merged just because an API call timed out.
- **It won't repeat itself.** If the same commit gets reviewed twice, it doesn't post the same comment again.
- **It never runs the code it's reviewing.** For pull requests from outside contributors, it only reads the diff through GitHub's API - it doesn't check out and execute anything, for obvious safety reasons.
- **There's a cap on how many files it reviews per PR**, so one giant change can't quietly rack up a big bill.

### Testing it for real

A pull request was opened with four bugs planted on purpose:

| Bug | Caught? | How confident |
|---|---|---|
| A password left in the code | Yes | 90% |
| A SQL injection hole | Yes | 80% |
| A command injection hole | Yes | 70% |
| Code that could crash on bad input | Yes | 70% |

**All four caught, nothing false flagged.**

---

## Getting it working for other languages

This was built for Python first. Turns out most of it doesn't actually care what language it's looking at - reading a diff works the same whether it's Python, JavaScript, or anything else.

So adding JavaScript and TypeScript support only took two small changes: telling it which file types to look at, and adding a short note to each check about mistakes common in those languages (like forgetting to handle a failed async call).

One thing worth being upfront about: the 95% number is a Python number, based on real Python bugs. If this gets extended to another language, that number needs to be measured again for that language - it doesn't automatically carry over.

---

## What this can't do yet

- **It only sees the lines that changed**, not the rest of the file or project. A bug that only shows up somewhere else - like code that calls a function whose behaviour just changed - won't be caught.
- **It's only been tested on one codebase.** 95% is a real number, but it's a number about one library. Whether it holds up elsewhere hasn't been checked.
- **The test set is 20 bugs.** Enough to trust the rough number, not enough to treat it as exact.
- **It costs a small amount per review** - cents, but on a public repo, anyone opening a pull request can trigger that spend.

## What's next

- Test it against a completely different codebase and see if the number holds
- Let it see more than just the diff, so it can catch bugs that span multiple files
- Add more languages, following the same approach used for JavaScript
- Add a mode that just logs what it would say without posting anything, so a team can build trust in it first

---

## What's actually in this repo

```
diff_parser.py       reads a diff and figures out what changed, and where
reviewer.py           the three checks, the quoting rule, the confidence rule
github_client.py      talks to GitHub
review_pr.py           the script that runs automatically on every pull request
eval_filters.py       the rules for telling real bugs apart from doc/config noise
.github/workflows/    the automation setup
results/              the actual test data and numbers, not just claims about them
```

**Built with:** Python, OpenAI's API, GitHub's API, GitHub Actions

---

## Questions someone might ask

**Why not just use a smarter model?**
Probably wouldn't help much by itself. What actually fixed the noise problem was forcing every claim to quote real code and requiring a confidence score - not raw model intelligence. A smarter model still needs somewhere to put its uncertainty.

**Isn't 95% a bit high to believe?**
Fair reaction - it was the same one here. It only looks that clean after going back and fixing mistakes in how the test set was built, twice. Both the messier 66% number and the cleaned-up 95% number are kept in this README on purpose, so nothing's quietly hidden.

**Could a team actually use this?**
As a second pair of eyes next to a human reviewer, worth trying. As a replacement for one, not yet - it genuinely can't see bugs that span multiple files, and it's only been proven on one codebase so far.

---

## How this was actually built

Claude wrote almost all of the code here. What came from this end was the direction: deciding how to actually test whether any of it worked, catching that the first test set was quietly contaminated by misleading commit messages, pushing to make the test set bigger when an early result looked suspiciously good, and asking to extend it to other languages once it became clear the code was more reusable than expected.

Every number in this README comes from a results file that's actually saved in this repo - not just typed here.
