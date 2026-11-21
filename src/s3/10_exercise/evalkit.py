# Exercise: move the reusable part of the Session 3 eval (5c_cost_guard.py) into this module.
# run_evals.py in this folder is finished: it builds the Extractor and hands the kit two functions,
# run(case) and grade(case, result). Fill in the six TODOs until `python run_evals.py 3` behaves like code/s3/run_evals.py.
# Rule: no ticket field, prompt name, model name or Extractor may appear in this file.
import json, time
from pathlib import Path


def run_all(run, grade, cases, k, max_cost=0.50, abort_after=3):
    """Run every case k times. Returns (results, stopped): stopped is None for a complete run, otherwise the reason.
    run(case) returns a dict with at least failure (None or "api"), errors (a list of strings), cost_usd (a number,
    or None if unknown) and seconds; attempts is optional and counts as 1. grade(case, result) returns a list of reasons."""
    # TODO 1: move run_all() from 5c_cost_guard.py. Five changes: call run(case) where it called
    # extractor.extract(case["text"]); use abort_after where it used ABORT_AFTER; store r.get("attempts", 1)
    # as the attempts of a run (a system without repairs may not report attempts); when an api failure
    # comes with an empty errors list, use "no error text" as its reason; and, because the kit knows nothing
    # about model.toml, make the unknown-cost reason "cost guard: a run reported no cost, so the spend cannot be capped".
    raise NotImplementedError


def rate(case_result):
    """Pass rate over the runs that were graded, or None if every run failed at the API."""
    # TODO 2: move rate() from 5c_cost_guard.py. Nothing in it changes.
    raise NotImplementedError


def summarise(results):
    """Totals over every run of every case. api runs are counted, but they were never graded, so not in the rates."""
    # TODO 3: move summarise() from 5c_cost_guard.py. Nothing in it changes.
    raise NotImplementedError


def gate(report, min_pass):
    """The release gate. Returns the reasons the change must not ship; an empty list means it may."""
    # TODO 4: move gate() from 5c_cost_guard.py, with min_pass where it used MIN_PASS.
    raise NotImplementedError


def verdict(report, min_pass=0.85, max_api_share=0.10):
    """Prints the verdict and returns the exit code: 0 gate passed, 1 gate failed, 2 no verdict."""
    # TODO 5: move verdict() from 5c_cost_guard.py, with max_api_share where it used MAX_API_SHARE, and
    # gate(report, min_pass) where it called gate(report). Return the number: only main() calls sys.exit.
    raise NotImplementedError


def save_report(report, folder, label):
    """Writes the report to folder/<label>-<date>-<time>.json and returns the path."""
    # TODO 6: move the three file-writing lines of evaluate() in 5c_cost_guard.py (path = ..., mkdir, write_text),
    # with Path(folder) where they used HERE / "reports". Return the path.
    raise NotImplementedError
