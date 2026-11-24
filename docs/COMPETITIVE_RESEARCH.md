# Competitive research

**Research date: 24 November 2026.** Product documentation and first-party announcements were checked on this date. Availability may vary by region, plan, and rollout.

## Products investigated

| Product | Verified capability and official evidence |
|---|---|
| Gemini in Chrome / Auto Browse | Google describes multi-step browsing tasks (shopping, travel, reservations), use of prior preferences/details, local Chrome or a cloud browser, takeover, resume, and stop controls. Availability is staged and eligibility-limited. [Auto Browse help](https://support.google.com/gemini/answer/16821166) |
| Claude in Chrome / Cowork | Claude can read, click, navigate, and fill sites. Cowork sessions are available across surfaces; browser work can be performed in a side panel or built-in browser. Anthropic documents consequential-action checks and discusses prompt-injection risks. [Chrome help](https://support.claude.com/en/articles/12012173-get-started-with-claude-in-chrome) · [Cowork browser](https://support.claude.com/en/articles/16607400-use-the-built-in-browser-in-claude-cowork) · [Chrome side panel update](https://claude.com/resources/articles/cowork-chrome-side-panel) |
| OpenAI ChatGPT Agent / Computer Use | Official docs cover hosted computer-use sessions, browser-origin approval, screenshots/activity, session reuse/recovery, user clarification, confirmation for consequential actions in controlled runtimes, and treating page content as untrusted. [Agents API computer use](https://developers.openai.com/api/docs/guides/agents-api/tools/computer-use) · [Integration recipes](https://developers.openai.com/api/docs/guides/tools-computer-use-integration) |
| Browser Use | Open-source browser automation and hosted cloud/profile products. Its official repository and product docs describe browser agents, persistent profiles, and managed browser infrastructure. [Repository](https://github.com/browser-use/browser-use) · [Product documentation](https://docs.browser-use.com/) |
| Browserbase Stagehand | Developer-oriented browser SDK exposes semantic `act`, `extract`, `observe`, and agent workflows, with self-healing claims and browser infrastructure. [Stagehand](https://www.browserbase.com/stagehand/) · [Official docs](https://docs.stagehand.dev/) |
| Skyvern | Browser automation with workflow blocks such as browser tasks, extraction, login, conditions, loops, and human interaction; supports Python/TypeScript automation against cloud browsers. [Automation overview](https://docs.skyvern.com/developers/browser-automations/overview) · [Workflow blocks](https://docs.skyvern.com/reference/blocks) |
| KNOWS benchmark | Research benchmark evaluates open-ended browser tasks across search, productivity use, and visual-spatial understanding, with task outcomes represented as artifacts. It is useful evidence that end-to-end task work exceeds single interaction quality. [Benchmark](https://alexgill321.github.io/KNOWS-benchmark/) |

## Capability matrix

Legend: **W** widely implemented in products/docs reviewed; **S** some competitors; **E** emerging; **P** poorly addressed as a cross-product capability; **U** not verified from public first-party material. These are qualitative documentation findings, not a market census.

| Capability | Status | Evidence / interpretation |
|---|---|---|
| Natural-language task execution | W | Present in Gemini Auto Browse, Claude browser/Cowork, OpenAI Computer Use, Browser Use, Stagehand, and Skyvern. |
| Multi-step planning | W | Product experiences and workflow/agent APIs explicitly support tasks that span steps. |
| Multi-tab or cross-site navigation | W | Gemini can work across web tasks; Claude announces cross-tab work; browser frameworks can navigate multiple pages/tabs. |
| Cross-site information extraction | W | Browser agents collect facts across sites; structured extraction is available in developer frameworks. |
| Intelligent form filling | W | Form interaction is a core advertised use case across the reviewed products. |
| Conversational/persistent memory | S | Claude Cowork sessions and Gemini personalization carry context; browser frameworks offer profiles/session persistence. Public docs do not establish uniform provenance/version semantics for every remembered fact. |
| Workflow resumption | S | Gemini documents resume/takeover; OpenAI documents session reuse/recovery; Claude describes cross-surface continuation. Recovery quality is implementation-specific. |
| Human approvals | W | Origin permissions, consequential-action checks, takeovers, or human-interaction blocks are documented in major offerings. Granularity differs. |
| Screenshot interaction | W | OpenAI Computer Use is visual; hosted runtimes and browser frameworks expose screenshots, often alongside DOM methods. |
| DOM/accessibility/semantic interaction | W | Browser frameworks expose DOM/semantic actions; approaches vary between DOM, accessibility, and visual signals. |
| Error recovery / self-healing | S | Stagehand advertises self-healing; OpenAI and others document reconnect/recovery mechanisms; guarantees differ by runtime. |
| Prompt-injection protection | S | Anthropic and OpenAI explicitly discuss untrusted page content and safeguards. No vendor documentation implies complete elimination of risk. |
| Background task execution | S | Gemini and Claude document background or continued work in some surfaces; not universal across local frameworks. |
| Workflow application management | E | Skyvern workflow blocks and hosted control planes are examples; the category is developing. |
| Fact-level provenance, freshness, and destination permission ledger | P | Not prominent as an interoperable, user-inspectable invariant in reviewed product docs. This is a documentation gap, not proof that no product implements it internally. |
| Reconciliation of saved action ledger against actual page before replay | P | Recovery/reconnect is documented by some systems, but explicit per-action state comparison is not consistently surfaced in reviewed public material. |

## Hypothesis review

| Hypothesis | Evidence and existing responses | What remains unresolved publicly | MVP relevance |
|---|---|---|---|
| Memory may lack source/reliability | Official product descriptions emphasize preferences, sessions, or profile persistence; OpenAI Computer Use describes session history and browser activity. | Public materials reviewed do not establish source/version/verification provenance for every reused fact. Internal systems may do more. | High: each fact and handoff needs an inspectable source trail. |
| Context can become stale after edits | Persistent profiles and sessions are available in several tools. | Public docs do not establish universal invalidation of downstream prepared fields when source facts change. | High: versioning and drift invalidation are central. |
| Similar labels can mean different things | Semantic browser interaction is a standard framework feature. | Robust distinction of current/permanent address and other near-neighbors cannot be assumed from label similarity. | High: deliberately ambiguous Portal B field is blocked. |
| Resume may diverge from actual website state | Gemini offers resume; OpenAI recommends reconnecting to the same session and inspecting approval state; sessions can persist. | Reconnection does not itself demonstrate fact/action reconciliation against the current page. | Critical: recovery must observe portal fields before selecting next action. |
| Agent may repeat uncertain action | OpenAI docs say a lost connection before acknowledgement should be treated as unknown and retrieved before deciding to retry. | Exactly-once behavior cannot be guaranteed by the agent when a destination offers no idempotency primitive. | Critical: ledger records uncertain state and suppresses automatic replay. |
| Users may lack transfer explanation | Products increasingly show activity, requests, approvals, or task progress. | Public evidence of a field-by-field source→destination semantic receipt is limited in reviewed docs. | High: make mapping reason, source, permission, and verification inspectable. |
| Permissions may be too coarse | Origin approvals and consequential-action checks are documented. Anthropic discusses controls for sensitive data and site access. | Per-fact × destination × purpose permission semantics vary and are not established as standard. | High: enforce allowlisted local origin and explicit destination checks. |
| Long workflows can fail despite working actions | KNOWS evaluates multi-domain task artifacts; frameworks add workflows, recovery and self-healing. | Reliability remains dependent on site state and evidence; no product-level guarantee was found for arbitrary long flows. | High: checkpoints, visible state and end-to-end tests. |
| Web content can manipulate agents | Both Anthropic and OpenAI explicitly discuss prompt injection and treating page content as untrusted. | Mitigation cannot eliminate the attack class. | Critical: separate page data from policy; page cannot broaden scope or permissions. |

## Patterns, limitations, and opportunity

Basic task execution, navigation, form filling, screenshots, sessions, and approval controls are no longer defensible novelty claims. CarryFlow's narrower hypothesis is **context integrity across handoffs**: a versioned fact is only reused if its provenance, freshness, semantic fit, purpose, and destination permission remain valid; the transfer creates a receipt; and a resumed workflow compares the live form with its action ledger before any repeat.

This is a product hypothesis, not a claim that competitors lack the underlying capability. The MVP demonstrates the mechanism in controlled local sites. Its contribution is the combination of explicit data lineage and reality-checked recovery, not a new browser-control primitive.

## Unverified assumptions

- Competitors may have private/internal fact provenance or action reconciliation not described publicly.
- Current model-specific accuracy and completion rates are not compared here; no unsupported numeric claims are made.
- Availability, plan eligibility, and regional rollouts may change after the research date.
- The KNOWS result is a research benchmark, not a direct evaluation of this prototype.
