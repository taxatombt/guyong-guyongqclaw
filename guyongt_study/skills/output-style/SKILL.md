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