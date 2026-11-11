name: test-driven-development
description: Write code test-first (red, green, refactor) for a new feature, bug fix or behaviour change

RULE: no production code before a test that you saw fail. Wrote code first? Delete it and start again.
Exceptions (throwaway prototype, generated code, config files) only if the user agrees.
1. Pick ONE small behaviour. Do not write all tests up front; go one test, then its code, then the next.
2. RED: write_file or edit_file one test. Name it after the behaviour (test_retries_three_times).
   One behaviour per test; "and" in the name means split it. Call the real code, avoid mocks.
3. See it fail: run_powershell: python -m pytest tests/test_x.py::test_name -q
   It must fail because the feature is missing, not because of a typo or import error.
   Passes straight away? It tests something that already exists; fix the test.
4. GREEN: write the simplest code that makes this test pass. Hardcoding and duplication are fine here.
   No extra features, no logging, no clean-up of other code.
5. See it pass: run the same test, then the whole suite: python -m pytest -q
   Test fails: fix the code, not the test. Another test broke: fix that now.
6. REFACTOR, only while green: remove duplication, improve names, extract helpers. Add no behaviour.
   Run the suite after each change. If it goes red, undo and take a smaller step.
7. Repeat from step 1 for the next behaviour, including edge cases and error cases.

WHEN STUCK
- Cannot see how to test it: write the call you wish existed and its assert first, or ask the user.
- Test is complicated or needs lots of mocks: the design is too coupled; simplify the interface.
- Fixing a bug: first write a test that reproduces it, then follow the cycle.

CHECK BEFORE DONE
- Every new function has a test, and you watched each test fail for the right reason.
- All tests pass with no errors or warnings in the output.
- Tests check results and behaviour, not internal calls. Edge cases and errors are covered.

Final answer: the behaviours covered, test file and code file paths, the last test command and its
pass/fail counts.
