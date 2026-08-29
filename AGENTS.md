# Agent Guidelines & Development Rules

These rules and guidelines must be followed by AI coding agents working on the SZenergy Pro Analyser repository.

---

### 1. Test Verification & Visual Validation
* There are and should be tests to verify your code before concluding work. Run the test suite to ensure there are no regressions.
* Always use `.venv/bin/python` to run tests and python scripts.
* The final verification of visual appearance, layout, and UX flows will always be done by the user (this is a visual GUI application and agents cannot see).

### 2. Keep It Simple (Scope Discipline)
* Keep changes focused and simple.
* When asked for a specific thing, do not develop additional unrequested features or overengineer.

### 3. Consider Existing Systems & Flows
* Always evaluate what already in-place systems, architecture, and workflows a change impacts (e.g. state management, threading, event loops, theme handling, data models, or serialization).

### 4. Component-Based Architecture & Short Files
* Keep files short and modular using a component-style approach with clear single responsibilities.

### 5. Consult When Design Decisions Arise
* Most importantly, ask the user when there are multiple options on how to do something and one isn't objectively the best.

### 6. Bash Usage & File Creation
* Only use bash commands when absolutely necessary.
* Creating new files should always be done using the `touch` command before editing them.

### 7. Continuous Guideline Maintenance
* Keep this `AGENTS.md` file updated over time as new patterns, preferences, and project guidelines are established.
