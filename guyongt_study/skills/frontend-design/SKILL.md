**What it does:**
1. Extracts rules from the planned SKILL.md (even if not written yet)
2. Simulates baseline agent behavior
3. Reports which rules agent is likely to violate and with what rationalizations

**If `skill_baseline_tester.py` is not available:** manually simulate:
1. Set up the exact situation where the skill should apply
2. Let the agent handle it without the skill
3. Record the **specific rationalizations** the agent uses to justify violations

Example rationalizations to look for:
- "This is simple enough to skip X"
- "I'll add tests later"
- "This is just a prototype"
- "The user didn't explicitly ask for X"

These rationalizations are the skill's target. A skill that doesn't address actual rationalizations is wishful thinking.

### Step 2: Write the Skill — Minimal and Targeted

**Use the baseline rationalizations as the target.** Every rule in the SKILL.md should address at least one rationalization from Step 1.

Good: "If you write code before writing a failing test, delete the code and start from the test."
Bad: "Always follow TDD best practices."

### Step 3: Verify — Watch It Pass

Re-run the scenario with the skill present. The agent should:
1. Not use the old rationalizations
2. Follow the prescribed behavior

### Step 4: Refactor — Close Loopholes

Find new rationalizations the agent uses → plug them → re-verify.

The first version of a skill rarely catches all cases. Iteration is required.

## SKILL.md Format

### Frontmatter (Required)

```yaml
---
name: skill-name-with-hyphens
description: Use when [specific triggering conditions and symptoms]
---
```

**Rules:**
- `name`: lowercase letters, numbers, hyphens only (no spaces, no special chars)
- `description`: max 1024 characters total
- `description`: **When to Use only** — describe triggering conditions, NOT the skill's workflow or process
- Start with "Use when..." to signal trigger condition

### Body Structure

```markdown
# Skill Name

## Overview
What is this? Core principle in 1-2 sentences.

## When to Use
- Trigger condition 1 (symptoms, not solutions)
- Trigger condition 2
- When NOT to use

## Core Pattern
Before/after code comparison, or step-by-step for techniques

## Quick Reference
Bullets or table for scanning during execution

## Common Mistakes
What goes wrong + specific fixes
```

### Keep Inline vs. Separate Files

**Keep inline:**
- Principles and concepts
- Code patterns under 50 lines
- Everything else

**Separate files for:**
- Heavy reference (100+ lines) — API docs, comprehensive syntax
- Reusable tools — scripts, utilities, templates

## Skill Types

| Type | Description | Example |
|------|-------------|---------|
| **Technique** | Concrete method with steps | `test-driven-development` |
| **Pattern** |思维方式 | `flatten-with-flags` |
| **Reference** | API docs, syntax guides | Office docs |

## Description CSO (Claude Search Optimization)

**Critical rule:** Description = When to Use, NOT What the Skill Does.

Future-you (or another agent) reads the description to decide: "Should I load this skill right now?"

**Good description:**
> "Use when writing code before confirming the implementation matches the spec, or when unsure whether the code satisfies the requirements."

**Bad descriptions (too specific about the skill's internals):**
> "This skill enforces red-green-refactor TDD cycles with mandatory test verification steps."
> "A skill that helps you write better plans with exact file paths and step-by-step instructions."

**Why it matters:** If description describes the skill's process, agents will only load it when they already know what the skill does. If description describes triggering conditions, agents load it when they need it — even before they know the solution.

## Validation Checklist

Before finishing a skill, verify:

- [ ] Name is lowercase with hyphens only
- [ ] Description starts with "Use when..."
- [ ] Description describes symptoms/situations, not the skill's workflow
- [ ] Description is under 500 characters
- [ ] SKILL.md exists at `skills/<skill-name>/SKILL.md`
- [ ] **Baseline test was run** (`skill_baseline_tester.py` or manual simulation)
- [ ] Skill was written to address specific rationalizations, not abstract principles
- [ ] Re-verify showed agent complies with skill present
- [ ] Every rule in SKILL.md addresses at least one rationalization from Step 1

Output Style 指南
文件路径：skills/output-style/SKILL.md
大小：3707 字符
---
name: output-style
description: Use when the user asks to change AI output style, wants educational explanations, wants to learn interactively, or asks for learning mode vs explanatory mode.
---

# Output Style

Controls how the AI presents information to the user. Two distinct styles are available.

## Overview

Output style determines the balance between **task completion** and **educational value**. Choose based on whether the user wants efficient execution or learning alongside work.

## When to Use

**explanatory style** when:
- User asks "explain what you're doing"
- User wants educational insights alongside code
- User wants to learn from the implementation
- "show your work" type requests

**learning style** when:
- User asks to learn about a topic interactively
- User wants step-by-step exploration of a concept
- User is studying or teaching

## Explanatory Style

When in explanatory mode, always include educational insights in output:

```
★ Insight ─────────────────────────────────────
[2-3 key educational points about the implementation]
─────────────────────────────────────────────────
```

### When to Insert Insights

Insert insights **before and after writing code**, not only at the end.

**Before code**: Explain the approach and design choices.
**After code**: Highlight what was interesting, risky, or non-obvious.

### Insight Principles

- Be specific to the codebase or code just written
- Avoid generic programming concepts
- 2-3 focused points, not exhaustive lists
- Educational but not patronizing
- Concise and high-signal

### Good Insight Examples

```
★ Insight ─────────────────────────────────────
1. Node's module caching means require() is idempotent —
   multiple calls to the same module return the same instance.
2. The double-brace pattern {{}} in template literals isn't
   special syntax; it's just how you interpolate within a
   pre-existing {{ }} block context.
─────────────────────────────────────────────────
```

### Bad Insight Examples

```
★ Insight ─────────────────────────────────────
1. Variables store values in memory.
2. Functions can accept parameters.
3. Always test your code.
─────────────────────────────────────────────────
```

(Too generic, obvious to anyone who knows programming)

## Learning Style

When in learning mode, prioritize:

1. **Step-by-step exploration** — Break complex topics into digestible pieces
2. **Socratic questions** — Ask the user what they think before explaining
3. **Concrete analogies** — Connect new concepts to familiar ones
4. **Interactive discovery** — Let the user reach conclusions with guidance

### Learning Structure

```
Topic: [What we're learning]

Step 1: [Simple concept]
  - [Key point]
  - [Why it matters]

Step 2: [Building on that]
  - [Key point]
  - [Example]

Try it yourself:
[Interactive exercise or question]
```

## Quick Reference

| Style | Primary Goal | Insight Frequency | Structure |
|-------|-------------|-------------------|-----------|
| explanatory | Task + learning | Before/after code | Inline with ★ markers |
| learning | Pure learning | Exploratory | Socratic, step-by-step |
| default | Efficiency | Minimal/none | Just deliver |

## Common Mistakes

**Mistake 1: Insights that are too generic**
- ❌ "Always use descriptive variable names"
- ✅ "parseInt vs Number: parseInt truncates to integer, Number casts. parseInt('42px') = 42, Number('42px') = NaN"

**Mistake 2: Waiting until the end to provide insights**
- ❌ All insights bundled at the end
- ✅ Scattered before/after relevant code sections

**Mistake 3: Over-explaining in learning mode**
- ❌ Walls of text without breaks
- ✅ Short paragraphs, questions to the user, interactive prompts

Frontend Design BOLD 美学
文件路径：skills/frontend-design/SKILL.md
大小：5067 字符
---
name: frontend-design
description: Use when building or designing web components, pages, or applications. Also use when the user wants distinctive, memorable UI that avoids generic "AI slop" aesthetics.
---

# Frontend Design

Create distinctive, production-grade frontend interfaces that avoid generic "AI slop" aesthetics. Build web components, pages, and applications with high design quality.

## When to Use

- Building web components, pages, or full applications
- User asks for UI/UX improvements
- User wants distinctive design vs generic templates
- Frontend task involving HTML/CSS/JS, React, Vue, etc.

## Design Thinking Process

Before writing any code, establish a clear aesthetic direction:

### 1. Purpose
What problem does this solve? Who uses it? What context?

### 2. Tone
Pick one dominant aesthetic and commit to it:

| Direction | Character |
|-----------|-----------|
| **brutally minimal** | Extreme restraint, every pixel justified |
| **maximalist chaos** | Layered, rich, dense information |
| **retro-futuristic** | 70s/80s sci-fi aesthetics, CRT, neon |
| **organic/natural** | Earth tones, flowing shapes, natural materials |
| **luxury/refined** | Premium, editorial, sophisticated |
| **playful/toy-like** | Bright, bouncy, childlike joy |
| **editorial/magazine** | Print-inspired, typography-led |
| **brutalist/raw** | Exposed structure, bold, unpolished |
| **art deco/geometric** | Precision, symmetry, ornamental |
| **soft/pastel** | Gentle, calm, muted palette |
| **industrial/utilitarian** | Functional, warehouse, stark |
| **dark/sophisticated** | Deep colors, elegant, premium feel |

### 3. Differentiation
What's the **one thing** someone will remember? The memorable element that makes this different.

## Implementation Standards

### Typography
- **Choose distinctive fonts** — avoid Inter, Roboto, Arial, system-ui
- **Pair strategically** — display font for headings, refined body font for text
- **Unexpected combinations** — Space Grotesk is overused, find fresher options
- **Font size matters** — 16px base is default, adjust for context

### Color & Theme
- **Commit to a cohesive palette** — use CSS variables for consistency
- **Dominant + accent** — not evenly distributed colors
- **Meaningful contrast** — ensure accessibility but maintain aesthetic
- **Dark/light as choice** — don't default to one

### Motion
- **CSS-first** — use CSS animations before JS libraries
- **High-impact moments** — one orchestrated page load beats scattered micro-interactions
- **Staggered reveals** — animation-delay for entrance choreography
- **Hover/active states** — every interactive element should respond
- **Scroll-triggered** — reveal on scroll creates delight

### Spatial Composition
- **Break the grid** — asymmetry and overlap create interest
- **Generous negative space** OR **controlled density** — pick a lane
- **Unexpected layouts** — diagonal flow, offset elements
- **Hierarchy through scale** — size = importance

### Visual Details
- **Backgrounds create atmosphere** — gradients, noise, textures, not flat colors
- **Shadows add depth** — layered shadows, not uniform drop shadows
- **Decorative borders** — custom borders, geometric ornaments
- **Grain overlays** — film grain, paper texture for analog feel

## What NOT to Use

**Never use:**
- Font families: Inter, Roboto, Arial, system-ui
- Purple gradients on white backgrounds
- Generic card layouts with avatar + title + description
- Rounded corners everywhere (8px radius is not universal)
- Blue/purple "AI" color schemes
- Hero sections with centered content and a CTA button
- Cookie-cutter navigation bars

**Never default to:**
- Tailwind CSS without customization
- Bootstrap components
- Generic placeholder illustrations
- Stock photo aesthetics

## Code Standards

### HTML/CSS
- Semantic HTML elements
- CSS custom properties (variables)
- Mobile-responsive (don't assume desktop)
- Accessible (ARIA labels, keyboard navigation)
- CSS-only animations where possible

### React/Vue
- Component composition
- Props for customization
- CSS-in-JS or scoped CSS modules
- Accessible interactive elements

### Production Requirements
- No placeholder content
- All buttons/links functional
- Responsive at standard breakpoints
- Realistic content (not Lorem ipsum)
- No console errors

## Output Format

For each frontend task, deliver:

1. **Design Direction** — one sentence on the chosen aesthetic
2. **Implementation** — complete, working code
3. **Key Design Decisions** — 2-3 sentences on why this approach

## Common Mistakes

**Mistake 1: Half-committed aesthetic**
- ❌ Mixing two conflicting styles
- ✅ Pick one direction and execute it fully

**Mistake 2: Over-designed for simple tasks**
- ❌ Full animation system for a utility page
- ✅ Match complexity to purpose

**Mistake 3: Forgetting accessibility**
- ❌ Ignoring contrast ratios and keyboard nav
- ✅ Aesthetic and accessible can coexist

**Mistake 4: Generic fonts**
- ❌ "I'll just use system fonts for reliability"
- ✅ Distinctive typography even for simple UIs