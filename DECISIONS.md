# Decisions

One entry per real choice made in this project — what was picked, what was rejected, and the evidence behind it.

---

**Three separate review passes, not one prompt.**
A single "find any issues" prompt does four jobs shallowly and can't be told what *not* to say. Splitting into security/correctness/tests, each with an explicit "do not report" list, cut the noise from 65 comments to near-zero on clean commits.

**Every finding must quote the diff verbatim.**
The naive version confidently claimed a valid Python feature "wasn't standard." A model can assert anything in prose but can't fake a quote that has to exist in the source — so unquotable claims are checked and dropped automatically, before a human ever sees them.

**Confidence threshold set at 0.7, not 0.5 or 1.0.**
Measured the tradeoff instead of guessing: catch rate stayed flat at 95% from 0.0 to 0.7, then collapsed to 10% at 0.8. 0.7 gives the same catch rate as no filter at all, with maximum safety margin against future noise.

**Ground truth built from inverted bug-fix commits, not hand-written test cases.**
Hand-written bugs risk being bugs the reviewer was specifically built to catch. Real historical fixes — reversed, so the "before" state is reviewable — are bugs that fooled a real human reviewer, which is a fairer test.

**The eval set was filtered twice, and both numbers are reported.**
First pass: commit messages containing "fix" → 35 matches, 66% catch rate. Found 15 weren't code bugs (typos, doc links, cosmetic regex changes). Filtered to what the diff actually touches, not what the message claims → 20 genuine defects, 95% catch rate. Reporting only 95% would have hidden that the measurement was fixed after finding it wrong.

**`pull_request_target`, not `pull_request`, for the workflow trigger.**
`pull_request` doesn't get write permission for PRs from forks, which is why many review bots silently fail on outside contributions. `pull_request_target` does — but it must never execute the PR's own code, only read its diff via the API, since it runs with the base repo's credentials.

**Fail open, not fail closed.**
If the reviewer errors, the workflow exits 0 rather than blocking the merge. A bot that blocks a PR because its own API call timed out gets disabled within a week — the cost of a missed review is lower than the cost of an untrusted gate.

**Related-files search reads the local checkout, not GitHub's code search API.**
Built the API version first since it seemed like the obvious tool. Tested it live — came back empty, even for words definitely in the repo. Confirmed by querying GitHub's search API directly and getting `total_count: 0` twice, hours apart. GitHub's code search index doesn't reliably cover low-traffic repos. Since `pull_request_target` already checks out the full repo, searching those files directly has no indexing lag, needs no extra API call, and works the same at any repo size — strictly better, not just a workaround.

**Related-files findings are never scored or counted as catches.**
They're a pointer ("you might want to check here"), not a claim that something is wrong. Scoring them would blur the difference between "the reviewer found a bug" and "the reviewer found a name that also appears elsewhere," which are very different claims.

**Rejected: switching search method based on repo traffic.**
Considered branching between local search (low-traffic repos) and the GitHub API (high-traffic ones). Rejected because local search has no downside at any traffic level once the repo is already checked out — the API version's only theoretical advantage (avoiding a full checkout) doesn't apply here, since the checkout happens regardless.

**Multi-language support added by extending prompts, not rewriting the pipeline.**
Diff parsing, chunking, and the evidence/confidence logic are already language-agnostic — the only Python-specific line in the whole system was a file-extension filter. Extending to JS/TS meant adding one filter and one paragraph per prompt naming that language's common risk patterns, not rebuilding anything.

**The 95% catch rate is not assumed to generalise to other languages or repos.**
It's a Python-only number, measured on one repo (`psf/requests`). Extending to a new language means re-running the eval harness against that language's own bug-fix history, not assuming the number carries over.
