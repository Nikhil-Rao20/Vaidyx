"""Known issues, written the way the fixed behaviour should look. Each is a strict xfail: when the fix lands the test
passes, strict mode turns that into a failure, and the fix removes the marker (and moves the test next to the feature).

Every issue found during the V1 run so far (items 1.1, 1.3, 3.1, 3.2, 3.3, 3.4, 3.5, 4.3; see docs_Eswar/changes_v1.md,
"Found during the run") is fixed and its test lives in the feature's own test module; new findings go here first."""
